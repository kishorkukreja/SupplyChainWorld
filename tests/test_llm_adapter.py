"""Offline tests for the real-LLM adapter (issue #18). No network, no credentials."""
import inspect
import json
import os
import unittest
from pathlib import Path

from supplychainworld import llm_adapter as la
from supplychainworld.agent_runner import ObservableRunner, replay
from supplychainworld.dynamic import OperationalWorld, SupplierDelayScenario
from supplychainworld.dynamic_demo import FORBIDDEN_KEYS
from supplychainworld.dynamic_verifier import verify_episode

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = {f['fixture_id']: f for f in
            json.loads((ROOT / 'fixtures/dynamic/supplier-delay-inputs.json').read_text())['fixtures']}
FIX = FIXTURES['s01-five-day']
MODEL = 'test/mock-model:free'
FAKE_KEY = 'sk-or-v1-' + 'a1b2c3d4e5f6' * 4


def factory(sink=None):
    def make():
        w = OperationalWorld(FIX['horizon_days'], scenario=SupplierDelayScenario(**FIX['scenario']))
        if sink is not None:
            sink.append(w)
        return w
    return make


def ok(tool=None, args=None, *, usage=True, raw_args=None, content=None, finish='tool_calls', extra=None, model_field=None, cost=None):
    msg = {'role': 'assistant', 'content': content}
    if tool is not None:
        msg['tool_calls'] = [{'id': 'c1', 'type': 'function', 'function': {
            'name': tool, 'arguments': raw_args if raw_args is not None else json.dumps(args or {})}}]
        msg['tool_calls'] += extra or []
    body = {'choices': [{'message': msg, 'finish_reason': finish}]}
    if model_field:
        body['model'] = model_field
    if usage:
        body['usage'] = {'prompt_tokens': 100, 'completion_tokens': 10, 'total_tokens': 110}
        if cost is not None:
            body['usage']['cost'] = cost
    return 200, {}, json.dumps(body).encode()


def http(status, text='err', headers=None):
    return status, headers or {}, json.dumps({'error': {'message': text}}).encode()


class Script:
    """Transport that replays a list of responses and records request bodies."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(json.loads(request['body']))
        self.last_headers = request['headers']
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def run(responses, **cfg):
    cfg.setdefault('model', MODEL)
    sleeps = []
    t = Script(responses)
    runner = ObservableRunner(factory()())
    out = la.run_llm_episode(runner, la.AdapterConfig(**cfg), transport=t, api_key=FAKE_KEY, sleep=sleeps.append)
    out['_t'], out['_sleeps'] = t, sleeps
    return out


class FakeModel:
    """Deterministic stand-in 'model' that reads only the message text it is sent."""

    def __init__(self):
        self.requests = []

    def __call__(self, request):
        body = json.loads(request['body'])
        self.requests.append(body)
        obs = None
        for m in reversed(body['messages']):
            if m['role'] == 'tool':
                obs = json.loads(m['content'])
                break
            if m['role'] == 'user' and m['content'].startswith('Initial observation: '):
                obs = json.loads(m['content'][len('Initial observation: '):])['observation']
                break
        state, rules = obs['state'], obs['rules']
        offers = rules.get('recovery_offers')
        if state['notices'] and state['recovery'] is None and offers and state['day'] <= offers['deadline_day']:
            return ok('commit_recovery', {'choice': 'expedite'})
        if state['scheduled_production'] is None:
            q = min(rules['capacity'], state['component_on_hand'], rules['required'] - state['produced_total'])
            return ok('release_production', {'quantity': q})
        return ok('advance_day', {})


class ConfigTests(unittest.TestCase):
    def test_non_free_model_refused(self):
        for bad in ('openai/gpt-4o', 'x/y:free-not', 'anthropic/claude', '', None, 'x/y:FREE'):
            with self.assertRaises(la.ModelNotAllowedError):
                la.AdapterConfig(bad)

    def test_free_model_accepted_and_limits_validated(self):
        c = la.AdapterConfig(MODEL)
        self.assertEqual(c.cost_ceiling_usd, 0.0)
        for kw in ({'max_model_calls': 0}, {'max_total_tokens': -1}, {'cost_ceiling_usd': -1}, {'max_retries': -1}):
            with self.assertRaises(ValueError):
                la.AdapterConfig(MODEL, **kw)

    def test_roster_config_records_decisions(self):
        cfg = json.loads((ROOT / 'config/llm_roster.json').read_text())
        self.assertEqual(cfg['spend_policy']['approved_monetary_ceiling_usd'], 0.0)
        d = cfg['roles']['decision_system1']
        self.assertEqual((d['kind'], d['status'], d['model_id']), ('scorer', 'verified: noul-only via /api/alpha/decisions', 'respan/span-01-lite'))
        self.assertIn('verified live', d['connectivity'])
        for name, role in cfg['roles'].items():
            self.assertEqual(role['kind'], 'scorer' if name == 'decision_system1' else 'actor')
        for m in cfg['connectivity_check_roster']:
            self.assertTrue(m.endswith(':free'))
        self.assertNotIn('respan/span-01-lite', cfg['connectivity_check_roster'])

    def test_zero_priced_model_without_free_suffix_accepted_only_with_verified_pricing(self):
        with self.assertRaises(la.ModelNotAllowedError):
            la.AdapterConfig('respan/span-01-lite')
        with self.assertRaises(la.ModelNotAllowedError):
            la.AdapterConfig('x/paid', pricing={'prompt': '0.000001', 'completion': '0'})
        with self.assertRaises(la.ModelNotAllowedError):
            la.AdapterConfig('x/partial', pricing={'prompt': '0'})
        c = la.AdapterConfig('respan/span-01-lite', pricing={'prompt': '0', 'completion': '0'})
        self.assertEqual(c.free_basis, 'verified_zero_pricing')
        self.assertEqual(la.call_cost(c.model, {'total_tokens': 3}, la.is_confirmed_free(c)), 0.0)
        self.assertEqual(la.AdapterConfig(MODEL).free_basis, 'id_suffix')

    def test_scorer_role_cannot_act(self):
        with self.assertRaises(la.ModelNotAllowedError):
            la.AdapterConfig(MODEL, role_kind='scorer')
        with self.assertRaises(la.ModelNotAllowedError):
            la.AdapterConfig('respan/span-01-lite', pricing={'prompt': '0', 'completion': '0'}, role_kind='scorer')


class SchemaAndManifestTests(unittest.TestCase):
    def setUp(self):
        r = ObservableRunner(factory()())
        r._world.reset()
        self.defs = r.tool_definitions()

    def test_tools_translated_to_openai_schemas(self):
        tools = la.openai_tools(self.defs)
        names = {t['function']['name'] for t in tools}
        self.assertEqual(names, {'read_state', 'read_recovery_offers', 'read_scorecard',
                                 'commit_recovery', 'release_production', 'advance_day'})
        by = {t['function']['name']: t['function']['parameters'] for t in tools}
        self.assertEqual(by['commit_recovery']['properties']['choice']['enum'], ['maintain', 'expedite', 'alternate'])
        self.assertEqual(by['release_production']['properties']['quantity']['type'], 'integer')
        self.assertEqual(by['advance_day']['properties'], {})
        self.assertTrue(all(t['type'] == 'function' for t in tools))

    def test_ungranted_tools_omitted(self):
        r = ObservableRunner(factory()(), granted=('read',))
        r._world.reset()
        names = {t['function']['name'] for t in la.openai_tools(r.tool_definitions())}
        self.assertEqual(names, {'read_state', 'read_recovery_offers', 'read_scorecard'})

    def test_manifest_pins_everything_and_is_stable(self):
        c = la.AdapterConfig(MODEL)
        m1, m2 = la.build_manifest(c, self.defs), la.build_manifest(c, self.defs)
        self.assertEqual(m1, m2)
        for key in ('model', 'system_prompt', 'tool_schemas', 'memory_policy', 'retry_policy', 'timeout_seconds',
                    'limits', 'spend', 'request_parameters', 'manifest_sha256'):
            self.assertIn(key, m1)
        self.assertEqual(m1['model'], MODEL)
        self.assertEqual(m1['spend']['cost_ceiling_usd'], 0.0)
        m3 = la.build_manifest(la.AdapterConfig(MODEL, max_model_calls=3), self.defs)
        self.assertNotEqual(m1['manifest_sha256'], m3['manifest_sha256'])
        self.assertNotIn(FAKE_KEY, json.dumps(m1))


class HandlingTests(unittest.TestCase):
    def test_malformed_json_arguments_rejected_by_runner_not_repaired(self):
        out = run([ok('release_production', raw_args='{quantity: 4', ), ok(None, content='x')], max_nudges=0)
        a = out['transcript']['attempts'][0]
        self.assertFalse(a['accepted'])
        self.assertEqual(a['category'], 'invalid_arguments')
        self.assertTrue(out['telemetry']['calls'][0]['malformed_arguments'])
        self.assertEqual(out['transcript']['final_state']['produced_total'], 0)

    def test_unknown_tool_and_bad_argument_values_rejected(self):
        out = run([ok('delete_everything', {}), ok('release_production', {'quantity': 'lots'}), ok('release_production', {'quantity': 99})],
                  max_model_calls=3)
        cats = [a['category'] for a in out['transcript']['attempts']]
        self.assertEqual(cats[0], 'unknown_tool')
        self.assertTrue(all(not a['accepted'] for a in out['transcript']['attempts']))
        self.assertFalse(out['episode_complete'])

    def test_hidden_probe_rejected(self):
        out = run([ok('read_scenario', {})], max_model_calls=1)
        self.assertEqual(out['transcript']['attempts'][0]['category'], 'hidden_state')

    def test_multiple_tool_calls_only_first_executed(self):
        extra = [{'id': 'c2', 'type': 'function', 'function': {'name': 'advance_day', 'arguments': '{}'}}]
        out = run([ok('release_production', {'quantity': 0}, extra=extra)], max_model_calls=1)
        self.assertEqual(len(out['transcript']['attempts']), 1)
        self.assertEqual(out['telemetry']['calls'][0]['tool_calls_returned'], 2)

    def test_no_tool_call_nudged_then_stops_without_fabricating(self):
        out = run([ok(None, content='I think we should wait'), ok(None, content='hmm'), ok(None, content='still no')], max_nudges=2)
        self.assertEqual(out['transcript']['attempts'], [])
        self.assertEqual(out['runner_status'], 'agent_stopped')
        self.assertEqual(out['telemetry']['stop_reason'], 'no_tool_call')
        self.assertFalse(out['episode_complete'])
        self.assertIsNone(out['transcript']['scorecard'])
        nudge = out['_t'].requests[1]['messages'][-1]
        self.assertEqual(nudge['role'], 'user')

    def test_nudge_budget_resets_after_a_tool_call(self):
        seq = [ok(None, content='x'), ok('advance_day', {}), ok(None, content='y'), ok('advance_day', {}),
               ok(None, content='z'), ok('advance_day', {})]
        out = run(seq, max_nudges=1, max_model_calls=6)
        self.assertEqual(out['telemetry']['model_calls'], 6)
        self.assertEqual(len(out['transcript']['attempts']), 3)

    def test_rate_limit_retries_with_bounded_backoff_then_succeeds(self):
        out = run([http(429, headers={'Retry-After': '2'}), http(503), ok('advance_day', {})], max_model_calls=1)
        self.assertEqual(out['_sleeps'], [2.0, 2.0])
        c = out['telemetry']['calls'][0]
        self.assertEqual(c['http_requests'], 3)
        self.assertEqual(len(c['retries']), 2)
        self.assertEqual(out['transcript']['attempts'][0]['tool'], 'advance_day')

    def test_backoff_capped_and_retry_limit_reports_failure(self):
        out = run([http(429, headers={'Retry-After': '9999'})] * 4, max_retries=3, backoff_cap_seconds=5)
        self.assertEqual(out['_sleeps'], [5.0, 5.0, 5.0])
        self.assertEqual(out['runner_status'], 'agent_error')
        self.assertEqual(out['telemetry']['failure']['error_class'], 'rate_limited')
        self.assertEqual(len(out['_t'].requests), 4)
        self.assertEqual(out['telemetry']['model_calls'], 1)
        self.assertEqual(out['telemetry']['calls_with_usage'], 0)
        self.assertEqual(out['telemetry']['total_tokens'], 0)
        self.assertEqual(out['telemetry']['cost_usd'], 'unknown')
        self.assertFalse(out['episode_complete'])

    def test_5xx_exhausts_and_network_error_retried(self):
        out = run([http(500), http(502), http(504)], max_retries=2)
        self.assertEqual(out['telemetry']['failure']['error_class'], 'provider_error')
        out = run([(0, {}, b'{"error": {"message": "URLError"}}'), ok('advance_day', {})], max_model_calls=1)
        self.assertEqual(out['transcript']['attempts'][0]['tool'], 'advance_day')

    def test_4xx_not_retried(self):
        out = run([http(401, 'bad key'), ok('advance_day', {})])
        self.assertEqual(len(out['_t'].requests), 1)
        self.assertEqual(out['telemetry']['failure']['error_class'], 'provider_error')
        self.assertEqual(out['_sleeps'], [])

    def test_200_with_error_body_treated_as_provider_error_code(self):
        body = (200, {}, json.dumps({'error': {'message': 'rate limited upstream', 'code': 429}}).encode())
        out = run([body, ok('advance_day', {})], max_model_calls=1)
        self.assertEqual(len(out['_t'].requests), 2)
        self.assertEqual(len(out['_sleeps']), 1)

    def test_refusal_stops_run(self):
        msg = {'choices': [{'message': {'role': 'assistant', 'content': None, 'refusal': 'cannot help'}, 'finish_reason': 'stop'}],
               'usage': {'prompt_tokens': 5, 'completion_tokens': 2, 'total_tokens': 7}}
        out = run([(200, {}, json.dumps(msg).encode())])
        self.assertEqual(out['telemetry']['failure']['error_class'], 'refusal')
        self.assertEqual(out['runner_status'], 'agent_error')
        self.assertEqual(out['transcript']['attempts'][-1]['category'], 'agent_error')
        self.assertIsNone(out['transcript']['scorecard'])

    def test_content_filter_finish_reason_is_refusal(self):
        out = run([ok(None, content='', finish='content_filter')])
        self.assertEqual(out['telemetry']['failure']['error_class'], 'refusal')

    def test_context_limit_http_400(self):
        out = run([http(400, "This model's maximum context length is 8192 tokens")])
        self.assertEqual(out['telemetry']['failure']['error_class'], 'context_limit')
        self.assertEqual(len(out['_t'].requests), 1)

    def test_configured_context_limit_stops(self):
        out = run([ok('advance_day', {})] * 3, max_context_tokens=50)
        self.assertEqual(out['telemetry']['stop_reason'], 'context_limit_configured')

    def test_malformed_response_shapes(self):
        for bad in (b'[]', b'not json', json.dumps({'choices': []}).encode(), json.dumps({'choices': [{'message': 'x'}]}).encode()):
            out = run([(200, {}, bad)])
            self.assertEqual(out['telemetry']['failure']['error_class'], 'malformed_response', bad)
            self.assertFalse(out['episode_complete'])

    def test_incomplete_episode_via_call_limit(self):
        out = run([ok('advance_day', {})] * 5, max_model_calls=2)
        self.assertEqual(out['telemetry']['stop_reason'], 'model_call_limit')
        self.assertEqual(out['telemetry']['model_calls'], 2)
        self.assertEqual(len(out['_t'].requests), 2)
        self.assertFalse(out['episode_complete'])
        self.assertIsNone(out['transcript']['scorecard'])

    def test_token_limit_stops_and_missing_usage_not_invented(self):
        out = run([ok('advance_day', {})] * 5, max_total_tokens=200)
        self.assertEqual(out['telemetry']['stop_reason'], 'token_limit')
        self.assertEqual(out['telemetry']['total_tokens'], 220)
        out = run([ok('advance_day', {}, usage=False)] * 3, max_model_calls=3)
        t = out['telemetry']
        self.assertFalse(t['usage_complete'])
        self.assertEqual(t['total_tokens'], 0)
        self.assertEqual(t['calls_with_usage'], 0)
        self.assertEqual(t['cost_usd'], 'unknown')
        self.assertIsNone(t['calls'][0]['usage'])


class CostTests(unittest.TestCase):
    def test_free_with_usage_is_zero(self):
        out = run([ok('advance_day', {})], max_model_calls=1)
        self.assertEqual(out['telemetry']['cost_usd'], 0.0)
        self.assertTrue(out['telemetry']['usage_complete'])

    def test_missing_usage_is_unknown_not_zero(self):
        out = run([ok('advance_day', {}, usage=False)], max_model_calls=1)
        self.assertEqual(out['telemetry']['cost_usd'], 'unknown')
        self.assertEqual(la.call_cost(MODEL, None), 'unknown')
        self.assertEqual(la.call_cost('paid/model', {'total_tokens': 5}), 'unknown')

    def test_reported_cost_over_ceiling_halts(self):
        out = run([ok('advance_day', {}, cost=0.25)] * 3, cost_ceiling_usd=0.0)
        self.assertEqual(out['telemetry']['stop_reason'], 'cost_ceiling')
        self.assertEqual(out['telemetry']['model_calls'], 1)
        self.assertEqual(out['telemetry']['cost_usd'], 0.25)

    def test_reported_cost_within_ceiling_continues(self):
        out = run([ok('advance_day', {}, cost=0.25)] * 2, cost_ceiling_usd=1.0, max_model_calls=2)
        self.assertEqual(out['telemetry']['model_calls'], 2)
        self.assertAlmostEqual(out['telemetry']['cost_usd'], 0.5)

    def test_latency_recorded(self):
        ticks = iter(range(0, 1000, 1))
        t = Script([ok('advance_day', {})])
        runner = ObservableRunner(factory()())
        out = la.run_llm_episode(runner, la.AdapterConfig(MODEL, max_model_calls=1), transport=t, api_key=FAKE_KEY,
                                 clock=lambda: next(ticks) * 0.5)
        self.assertEqual(out['telemetry']['calls'][0]['latency_ms'], 500.0)


class SecretTests(unittest.TestCase):
    def test_redact_text_patterns(self):
        for s in (f'key {FAKE_KEY} end', 'Authorization: Bearer abcdefghijklmnop', 'sk-abcdefghijklmnopqrstuv',
                  '{"Authorization": "Bearer zzzzzzzzzzzz"}'):
            out = la.redact_text(s)
            self.assertIn('[REDACTED]', out)
            self.assertNotIn('abcdefghijklmnop', out)
            self.assertNotIn('a1b2c3d4e5f6', out)
        self.assertEqual(la.redact_text('plain day 3 text'), 'plain day 3 text')

    def test_redact_deep_and_exact_secret(self):
        data = {'headers': {'Authorization': 'Bearer qqqqqqqqqqqq'}, 'x': ['my-odd-secret-value', {'k': 'my-odd-secret-value!'}]}
        out = la.redact(data, ('my-odd-secret-value',))
        text = json.dumps(out)
        self.assertNotIn('my-odd-secret-value', text)
        self.assertNotIn('qqqqqqqqqqqq', text)

    def test_key_never_in_outputs_even_if_provider_echoes_it(self):
        echo = ok('advance_day', {}, model_field=FAKE_KEY)
        err = http(400, f'bad request key={FAKE_KEY}')
        for responses in ([echo], [err]):
            out = run(responses, max_model_calls=1)
            blob = json.dumps({k: out[k] for k in ('manifest', 'transcript', 'telemetry')})
            self.assertNotIn(FAKE_KEY, blob)
            self.assertNotIn('a1b2c3d4e5f6', blob)

    def test_authorization_header_sent_but_not_stored(self):
        out = run([ok('advance_day', {})], max_model_calls=1)
        self.assertEqual(out['_t'].last_headers['Authorization'], f'Bearer {FAKE_KEY}')
        self.assertNotIn(FAKE_KEY, json.dumps(out['telemetry']))
        self.assertNotIn(FAKE_KEY, json.dumps(out['_t'].requests))

    def test_credential_read_from_environment_only(self):
        old = os.environ.get(la.CREDENTIAL_ENV)
        os.environ[la.CREDENTIAL_ENV] = 'proxy-injected'
        try:
            t = Script([ok('advance_day', {})])
            la.run_llm_episode(ObservableRunner(factory()()), la.AdapterConfig(MODEL, max_model_calls=1), transport=t)
            self.assertEqual(t.last_headers['Authorization'], 'Bearer proxy-injected')
        finally:
            if old is None:
                os.environ.pop(la.CREDENTIAL_ENV, None)
            else:
                os.environ[la.CREDENTIAL_ENV] = old


class NoLeakTests(unittest.TestCase):
    def test_module_does_not_import_world_verifier_or_baselines(self):
        src = inspect.getsource(la)
        for banned in ('dynamic_verifier', 'baselines', 'OperationalWorld', 'SupplierDelayScenario', 'import dynamic',
                       'from .dynamic', 'scorecard()', '.history()', 'snapshot('):
            self.assertNotIn(banned, src, banned)

    def test_requests_contain_only_observable_information(self):
        model = FakeModel()
        la.run_llm_episode(ObservableRunner(factory()()), la.AdapterConfig(MODEL, max_model_calls=12), transport=model, api_key=FAKE_KEY)
        text = json.dumps(model.requests).lower()
        for key in FORBIDDEN_KEYS:
            self.assertNotIn(key, text, key)
        sc = FIX['scenario']
        for hidden in ('opening_components', 'comparison_cost', 'expected', 'verifier', 'hand_ledger', 'disruption_enabled'):
            self.assertNotIn(hidden, text)
        # system prompt is generic: no scenario numbers
        self.assertNotIn(str(sc['expedite_cost']), la.SYSTEM_PROMPT)


class FullEpisodeTests(unittest.TestCase):
    def test_mocked_full_s01_episode_replays_and_verifies(self):
        sink = []
        runner = ObservableRunner(factory(sink)())
        model = FakeModel()
        out = la.run_llm_episode(runner, la.AdapterConfig(MODEL, max_model_calls=12), transport=model, api_key=FAKE_KEY)
        self.assertEqual(out['runner_status'], 'complete')
        self.assertTrue(out['episode_complete'])
        self.assertLessEqual(out['telemetry']['model_calls'], 12)
        self.assertTrue(out['telemetry']['usage_complete'])
        self.assertEqual(out['telemetry']['cost_usd'], 0.0)
        world = sink[0]
        actions = [{'day': a['day'], 'kind': {'commit_recovery': 'recovery', 'release_production': 'release'}[a['tool']],
                    'arguments': a['arguments'], 'result': a['result']}
                   for a in out['transcript']['attempts'] if a['tool'] in ('commit_recovery', 'release_production')]
        report = verify_episode(FIX['scenario'], world.history(), horizon_days=5, scorecard=world.scorecard(), actions=actions)
        self.assertTrue(report.feasible, report.codes())
        ok_replay, diffs = replay(out['transcript'], factory())
        self.assertTrue(ok_replay, diffs)
        self.assertEqual(out['transcript']['scorecard']['comparison_cost'], 24)
        self.assertEqual(len(model.requests), out['telemetry']['model_calls'])

    def test_memory_window_bounds_request_size(self):
        model = FakeModel()
        la.run_llm_episode(ObservableRunner(factory()()), la.AdapterConfig(MODEL, memory_window=2), transport=model, api_key=FAKE_KEY)
        for body in model.requests:
            self.assertLessEqual(len(body['messages']), 2 + 2 * 2)

    def test_request_shape(self):
        model = FakeModel()
        la.run_llm_episode(ObservableRunner(factory()()), la.AdapterConfig(MODEL, max_model_calls=1), transport=model, api_key=FAKE_KEY)
        body = model.requests[0]
        self.assertEqual(body['model'], MODEL)
        self.assertEqual(body['temperature'], 0.0)
        self.assertEqual(body['tool_choice'], 'auto')
        self.assertEqual(body['messages'][0]['role'], 'system')
        self.assertEqual(len(body['tools']), 6)


if __name__ == '__main__':
    unittest.main()
