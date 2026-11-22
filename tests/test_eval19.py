"""Offline tests for the issue #19 free-model diagnostic harness. No network, no credentials, mocked transports."""
import inspect
import json
import re
import unittest
from pathlib import Path

from supplychainworld import eval19 as ev
from supplychainworld import llm_adapter as la

ROOT = Path(__file__).resolve().parents[1]
CASES = ev.load_static_cases()
SELECTED = ev.select_static_cases(CASES)
FIXTURES = {f['fixture_id']: f for f in json.loads((ROOT / 'fixtures/dynamic/v0.4/scenarios.json').read_text())['fixtures']}
MODEL = 'test/mock-model:free'


def fake_response(tool=None, args=None, *, raw_args=None, finish='tool_calls'):
    msg = {'role': 'assistant', 'content': None}
    if tool is not None:
        msg['tool_calls'] = [{'id': 'c1', 'type': 'function', 'function': {
            'name': tool, 'arguments': raw_args if raw_args is not None else json.dumps(args or {})}}]
    body = {'choices': [{'message': msg, 'finish_reason': finish}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 10, 'total_tokens': 110}}
    return 200, {}, json.dumps(body).encode()


class Seq:
    """Base transport that returns scripted responses in order and records request bodies."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.bodies = []

    def __call__(self, request):
        self.bodies.append(request['body'].decode())
        r = self.responses.pop(0) if self.responses else (500, {}, b'{}')
        return r


def guarded(base, **kw):
    kw.setdefault('sleep', lambda s: None)
    kw.setdefault('min_interval', 0.0)
    return ev.Guard(base, **kw)


class SelectionTests(unittest.TestCase):
    def test_rule_is_twenty_cases_with_all_exceptions(self):
        self.assertEqual(len(SELECTED), 20)
        exc = [i for i, c in CASES.items() if c['expected']['expected_outcome'] != 'award']
        self.assertEqual(len(exc), 7)
        self.assertTrue(set(exc) <= set(SELECTED))
        kinds = {CASES[i]['expected']['expected_outcome'] for i in SELECTED}
        self.assertEqual(kinds, {'award', 'clarification', 'infeasible'})

    def test_deterministic(self):
        self.assertEqual(ev.select_static_cases(CASES), SELECTED)

    def test_roster_is_free_only(self):
        for m in ev.ROSTER_CORE + ev.ROSTER_CONDITIONAL:
            self.assertTrue(m.endswith(':free'))
            la.AdapterConfig(m)
        with self.assertRaises(la.ModelNotAllowedError):
            la.AdapterConfig('openai/gpt-4o')
        with self.assertRaises(la.ModelNotAllowedError):
            la.AdapterConfig('respan/span-01-lite:free', role_kind='scorer')


class StaticNoLeakTests(unittest.TestCase):
    def test_messages_contain_only_world_and_fixed_text(self):
        for cid, case in CASES.items():
            msgs = ev.static_messages(case)
            text = json.dumps(msgs)
            for secret in ev.static_private_strings(case):
                self.assertNotIn(secret, text, cid)
            for marker in ev.PRIVATE_MARKERS:
                self.assertNotIn(marker, text, cid)
            user = msgs[1]['content']
            payload = json.loads(user.split('Visible world (JSON):\n', 1)[1])
            self.assertEqual(payload, case['world'])
            for key in ('expected', 'known_wrong', 'review', 'purpose', 'rules_exercised', 'changed_from_v1_1', 'task'):
                self.assertNotIn(f'"{key}"', user, cid)
            self.assertNotIn(case['expected']['expected_outcome'] + '_expected', text)

    def test_visible_functions_never_read_private_fields(self):
        for fn in (ev.static_visible_world, ev.static_messages):
            src = inspect.getsource(fn)
            self.assertEqual(set(re.findall(r"case\[['\"](\w+)['\"]\]", src)) - {'world'}, set())

    def test_guard_refuses_private_markers_and_strings(self):
        base = Seq([fake_response('submit_decision', {'kind': 'infeasible', 'evidence': ['x']})])
        g = guarded(base, private_strings=['SECRET-TEXT-123'])
        g.model, g.phase = MODEL, 'static'
        status, _, _ = g({'url': 'u', 'headers': {}, 'body': json.dumps({'m': 'has delay_outcome inside'}).encode()})
        self.assertEqual(status, 418)
        status, _, _ = g({'url': 'u', 'headers': {}, 'body': b'SECRET-TEXT-123'})
        self.assertEqual(status, 418)
        self.assertEqual(g.used_total, 0)
        self.assertEqual(len(g.leak_flags), 2)
        self.assertEqual(base.bodies, [])


class StaticRunTests(unittest.TestCase):
    def run_case(self, cid, responses):
        base = Seq(responses)
        g = guarded(base)
        g.model, g.phase = MODEL, 'static'
        raw = ev.run_static_case(CASES[cid], MODEL, g, sleep=lambda s: None)
        return raw, g, base

    def test_expected_answers_are_accepted_through_the_harness(self):
        for cid in SELECTED:
            sub = CASES[cid]['expected']['submission']
            raw, g, base = self.run_case(cid, [fake_response('submit_decision', sub)])
            self.assertEqual(raw['status'], 'submitted', cid)
            self.assertEqual(len(raw['calls']), 1)
            grade = ev.grade_static(CASES[cid], raw['submission'])
            self.assertTrue(grade['accepted'], (cid, grade))
            self.assertTrue(grade['outcome_matches'])
            body = base.bodies[0]
            for secret in ev.static_private_strings(CASES[cid]):
                self.assertNotIn(secret, body)

    def test_known_wrong_answers_are_rejected(self):
        n = 0
        for cid in SELECTED:
            for kw in CASES[cid].get('known_wrong', []):
                grade = ev.grade_static(CASES[cid], kw['submission'])
                self.assertFalse(grade['accepted'], (cid, kw.get('reason')))
                n += 1
        self.assertGreater(n, 10)

    def test_nudge_once_then_give_up(self):
        raw, g, _ = self.run_case(SELECTED[0], [fake_response(None, finish='length'), fake_response(None)])
        self.assertEqual(raw['status'], 'no_usable_submission')
        self.assertEqual(len(raw['calls']), 2)
        self.assertEqual(g.used_total, 2)
        self.assertIsNone(raw['submission'])
        self.assertEqual(ev.grade_static(CASES[SELECTED[0]], None)['graded'], False)

    def test_nudge_recovers(self):
        cid = SELECTED[0]
        raw, _, _ = self.run_case(cid, [fake_response('submit_decision', raw_args='{not json'),
                                        fake_response('submit_decision', CASES[cid]['expected']['submission'])])
        self.assertEqual(raw['status'], 'submitted')
        self.assertTrue(raw['calls'][0]['malformed_arguments'])

    def test_invalid_schema_is_graded_invalid_not_repaired(self):
        cid = SELECTED[0]
        sub = dict(CASES[cid]['expected']['submission'], bogus_key=1)
        raw, _, _ = self.run_case(cid, [fake_response('submit_decision', sub)])
        grade = ev.grade_static(CASES[cid], raw['submission'])
        self.assertFalse(grade['schema_valid'])
        self.assertFalse(grade['accepted'])

    def test_sanitized_record_has_no_private_text(self):
        cid = SELECTED[1]
        raw, _, _ = self.run_case(cid, [fake_response('submit_decision', CASES[cid]['expected']['submission'])])
        rec = ev.sanitize_static(raw, ev.grade_static(CASES[cid], raw['submission']))
        text = json.dumps(rec)
        self.assertNotIn('calculation', text)
        self.assertEqual(rec['cost_usd'], 0.0)
        self.assertEqual(rec['logical_calls'], 1)

    def test_baselines_use_same_visible_world_and_pass_the_checker(self):
        for cid in SELECTED:
            ref = ev.static_baseline(CASES[cid], 'reference')
            self.assertTrue(ref.get('accepted'), (cid, ref))
            heur = ev.static_baseline(CASES[cid], 'heuristic')
            self.assertIn('graded', heur)


class GuardTests(unittest.TestCase):
    def req(self):
        return {'url': 'u', 'headers': {}, 'body': json.dumps({'model': MODEL, 'messages': []}).encode()}

    def test_phase_and_total_caps(self):
        base = Seq([(200, {}, b'{}')] * 10)
        g = guarded(base, total_cap=5, phase_caps={'a': 2, 'b': 10})
        g.model, g.phase = MODEL, 'a'
        self.assertEqual([g(self.req())[0] for _ in range(3)], [200, 200, 418])
        g.phase = 'b'
        self.assertEqual([g(self.req())[0] for _ in range(4)], [200, 200, 200, 418])
        self.assertEqual(g.used_total, 5)
        self.assertEqual(g.remaining('b'), 0)

    def test_breaker_on_repeated_429_and_403(self):
        g = guarded(Seq([(429, {}, b'{}')] * 10))
        g.model, g.phase = MODEL, 'static'
        for _ in range(ev.BREAKER_429):
            g(self.req())
        self.assertIn(MODEL, g.stopped)
        used = g.used_total
        self.assertEqual(g(self.req())[0], 418)
        self.assertEqual(g.used_total, used)
        g2 = guarded(Seq([(403, {}, b'{}')] * 5))
        g2.model, g2.phase = 'other/m:free', 'static'
        g2(self.req())
        g2(self.req())
        self.assertIn('other/m:free', g2.stopped)

    def test_a_200_resets_the_breaker(self):
        g = guarded(Seq([(429, {}, b'{}')] * 5 + [(200, {}, b'{}')] + [(429, {}, b'{}')] * 5))
        g.model, g.phase = MODEL, 'static'
        for _ in range(11):
            g(self.req())
        self.assertNotIn(MODEL, g.stopped)

    def test_throttle_spaces_requests(self):
        sleeps, now = [], [0.0]
        g = ev.Guard(Seq([(200, {}, b'{}')] * 3), sleep=lambda s: (sleeps.append(s), now.__setitem__(0, now[0] + s)),
                     clock=lambda: now[0], min_interval=3.5)
        g.model, g.phase = MODEL, 'static'
        for _ in range(3):
            g(self.req())
        self.assertEqual(len(sleeps), 2)
        self.assertTrue(all(abs(s - 3.5) < 1e-9 for s in sleeps))

    def test_ledger_has_no_bodies_or_keys(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'ledger.jsonl'
            g = guarded(Seq([(200, {}, b'{}')]), ledger_path=str(p))
            g.model, g.phase = MODEL, 'static'
            g({'url': 'u', 'headers': {'Authorization': 'Bearer sk-or-v1-abcdefabcdefabcdef'},
               'body': json.dumps({'model': MODEL, 'messages': [{'content': 'hello'}]}).encode()})
            text = p.read_text()
            self.assertNotIn('sk-or', text)
            self.assertNotIn('hello', text)
            self.assertEqual(json.loads(text)['effective_status'], 200)

    def test_cap_refusal_is_not_retried_by_the_adapter(self):
        g = guarded(Seq([]), total_cap=0)
        g.model, g.phase = MODEL, 'static'
        with self.assertRaises(la.ProviderError):
            la.chat_request(ev.static_config(MODEL), [{'role': 'user', 'content': 'x'}], [], transport=g, api_key='k',
                            sleep=lambda s: None)
        self.assertEqual(g.refused, 'request cap reached for phase static')


class S01Tests(unittest.TestCase):
    def scripted_calls(self, fixture, policy='maintain'):
        from supplychainworld.agent_runner_v4 import ObservableRunnerV4, scripted_policy_v4
        from supplychainworld.dynamic_demo_v4 import factory
        t = ObservableRunnerV4(factory(fixture)()).run(scripted_policy_v4(policy))
        return [(a['tool'], a['arguments']) for a in t['attempts']], t['scorecard']

    def test_tool_profile_describes_v04_correctly(self):
        from supplychainworld.agent_runner_v4 import ObservableRunnerV4
        from supplychainworld.dynamic_demo_v4 import factory
        defs = ObservableRunnerV4(factory(FIXTURES['s04-sudden-5d'])()).tool_definitions()
        tools = {t['function']['name']: t['function'] for t in ev.s01_tools(defs)}
        q = tools['commit_recovery']['parameters']['properties']
        self.assertEqual(q['choice']['enum'], ['expedite', 'alternate'])
        self.assertIn('recovery lot', q['quantity']['description'])
        self.assertNotIn('finished goods', q['quantity']['description'])
        self.assertNotIn('once only', tools['commit_recovery']['description'])

    def test_mocked_episode_verified_replayed_blinded_no_leak(self):
        for fid in ('s04-warned-delayed-10d', 's04-sudden-5d'):
            fx = FIXTURES[fid]
            calls, card = self.scripted_calls(fx)
            base = Seq([fake_response(t, a) for t, a in calls])
            g = guarded(base, private_strings=list(FIXTURES))
            g.model, g.phase = MODEL, 's01'
            raw = ev.run_s01_episode(fx, MODEL, g, sleep=lambda s: None)
            self.assertEqual(g.leak_flags, [])
            for body in base.bodies:
                for fixture_id in FIXTURES:
                    self.assertNotIn(fixture_id, body)
                self.assertNotIn('warned-delayed', body)
                for marker in ev.PRIVATE_MARKERS:
                    self.assertNotIn(marker, body)
            grade = ev.grade_s01(fx, raw)
            self.assertTrue(grade['completed'])
            self.assertTrue(grade['verifier_feasible'], grade['hard_violation_codes'])
            self.assertTrue(grade['replay_reproduced'], grade['replay_differences'])
            self.assertEqual(grade['observation_leaks'], [])
            self.assertEqual(grade['invalid_actions'], 0)
            self.assertEqual(grade['scorecard']['cost']['net_cost'], card['cost']['net_cost'])
            self.assertEqual(raw['telemetry']['cost_usd'], 0.0)

    def test_expedite_episode_is_verified(self):
        fx = FIXTURES['s04-warned-delayed-10d']
        calls, card = self.scripted_calls(fx, 'combo_on_alert')
        g = guarded(Seq([fake_response(t, a) for t, a in calls]))
        g.model, g.phase = MODEL, 's01'
        raw = ev.run_s01_episode(fx, MODEL, g, sleep=lambda s: None)
        grade = ev.grade_s01(fx, raw)
        self.assertTrue(grade['verifier_feasible'], grade['hard_violation_codes'])
        self.assertTrue(grade['replay_reproduced'])
        self.assertGreaterEqual(len(grade['recovery_commitments']), 1)
        self.assertEqual(grade['scorecard']['cost']['net_cost'], card['cost']['net_cost'])

    def test_invalid_model_actions_are_recorded_not_repaired(self):
        fx = FIXTURES['s04-sudden-5d']
        calls, _ = self.scripted_calls(fx)
        bad = [fake_response('release_production', {'quantity': 9999}), fake_response('delete_everything', {}),
               fake_response('release_production', raw_args='{oops')]
        g = guarded(Seq(bad + [fake_response(t, a) for t, a in calls]))
        g.model, g.phase = MODEL, 's01'
        raw = ev.run_s01_episode(fx, MODEL, g, sleep=lambda s: None)
        grade = ev.grade_s01(fx, raw)
        self.assertEqual(grade['invalid_actions'], 3)
        self.assertTrue(grade['completed'])
        self.assertTrue(grade['replay_reproduced'])
        self.assertTrue(grade['verifier_feasible'])

    def test_provider_failure_ends_episode_honestly(self):
        fx = FIXTURES['s04-sudden-5d']
        g = guarded(Seq([(403, {}, json.dumps({'error': {'message': 'nope'}}).encode())] * 5))
        g.model, g.phase = MODEL, 's01'
        raw = ev.run_s01_episode(fx, MODEL, g, sleep=lambda s: None)
        grade = ev.grade_s01(fx, raw)
        self.assertFalse(grade['completed'])
        self.assertEqual(raw['telemetry']['failure']['error_class'], 'provider_error')
        self.assertEqual(g.used_total, 1)
        self.assertEqual(grade['agent_errors'], 1)
        self.assertTrue(grade['replay_reproduced'])

    def test_baselines_report_metrics_separately(self):
        base = ev.s01_baselines([FIXTURES['s04-sudden-5d']])
        self.assertEqual(len(base['s04-sudden-5d']), 5)
        row = base['s04-sudden-5d']['maintain']
        self.assertIn('net_cost', row)
        self.assertIn('otif_orders_met', row)
        self.assertNotIn('score', row)


if __name__ == '__main__':
    unittest.main()
