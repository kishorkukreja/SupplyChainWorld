"""Offline tests for the Decisions API client. No network, no credentials."""
import inspect
import json
import unittest
from pathlib import Path

from supplychainworld import decisions_client as dc
from supplychainworld import llm_adapter as la

ROOT = Path(__file__).resolve().parents[1]
FAKE_KEY = 'sk-or-v1-' + 'a1b2c3d4e5f6' * 4
STATE = 'Plant P1 day 3: supplier S-A late by 2 days; stock of component C is 40 units.'


def body(answers, usage=True, cost=0, **extra):
    b = {'model': 'respan/span-01-lite', 'answers': {k: {'type': 'noul', 'noul': v} for k, v in answers.items()}}
    if usage:
        b['usage'] = {'input_tokens': 50, 'output_tokens': 0, 'cost': cost}
    b.update(extra)
    return b


class Script:
    """Transport that replays (status, headers, body) tuples and records requests."""

    def __init__(self, *responses):
        self.responses, self.requests = list(responses), []

    def __call__(self, request):
        self.requests.append(request)
        status, headers, payload = self.responses.pop(0)
        if not isinstance(payload, (bytes, bytearray)):
            payload = json.dumps(payload).encode()
        return status, headers, payload


def client(*responses, **kw):
    t = Script(*responses)
    kw.setdefault('sleep', lambda s: None)
    return dc.DecisionsClient(transport=t, api_key=FAKE_KEY, **kw), t


class RosterGuardTests(unittest.TestCase):
    def test_roster_slot_is_verified_scorer(self):
        roster = json.loads((ROOT / 'config/llm_roster.json').read_text())
        spec = roster['roles']['decision_system1']
        self.assertEqual(spec['kind'], 'scorer')
        self.assertTrue(spec['status'].startswith('verified: noul-only'))
        self.assertIn('limitation', spec)
        model, _ = dc.load_scorer_spec()
        self.assertEqual(model, 'respan/span-01-lite')

    def test_rejects_actor_role(self):
        roster = json.loads((ROOT / 'config/llm_roster.json').read_text())
        with self.assertRaises(la.ModelNotAllowedError):
            dc.load_scorer_spec('general_reasoning', roster)

    def test_rejects_unverified_pricing(self):
        spec = {'kind': 'scorer', 'model_id': 'x/y', 'verified_pricing': {'prompt': '0.001', 'completion': '0'}}
        with self.assertRaises(la.ModelNotAllowedError):
            dc.DecisionsClient(spec=spec, api_key='k')
        spec['verified_pricing'] = None
        with self.assertRaises(la.ModelNotAllowedError):
            dc.DecisionsClient(spec=spec, api_key='k')

    def test_rejects_unknown_role_and_model_mismatch(self):
        with self.assertRaises(la.ModelNotAllowedError):
            dc.load_scorer_spec('nope')
        spec = {'kind': 'scorer', 'model_id': 'x/y', 'verified_pricing': {'prompt': '0', 'completion': '0'}}
        with self.assertRaises(la.ModelNotAllowedError):
            dc.DecisionsClient(model='other/model', spec=spec, api_key='k')

    def test_endpoint_is_decisions_not_chat(self):
        c, t = client((200, {}, body({'q': 0.9})))
        c.yes_no(STATE, 'Is C short?', 'C is short.', 'C is not short.')
        self.assertEqual(t.requests[0]['url'], 'https://openrouter.ai/api/alpha/decisions')
        self.assertNotIn('chat/completions', t.requests[0]['url'])


class YesNoTests(unittest.TestCase):
    def test_request_shape_and_result(self):
        c, t = client((200, {}, body({'q': 0.985})))
        r = c.yes_no(STATE, 'Is C short?', 'C is short.', 'C is not short.')
        sent = json.loads(t.requests[0]['body'])
        self.assertEqual(sent, {'model': 'respan/span-01-lite', 'state': STATE, 'questions': {'q': {
            'type': 'noul', 'instructions': 'Is C short?', 'criteria': {'true': 'C is short.', 'false': 'C is not short.'}}}})
        self.assertEqual(r['probability'], 0.985)
        self.assertIs(r['answer'], True)
        self.assertEqual(r['cost_usd'], 0.0)
        self.assertEqual(r['usage']['input_tokens'], 50)

    def test_threshold(self):
        c, _ = client((200, {}, body({'q': 0.4})), (200, {}, body({'q': 0.4})))
        self.assertIs(c.yes_no(STATE, 'a?', 't', 'f')['answer'], False)
        self.assertIs(c.yes_no(STATE, 'a?', 't', 'f', threshold=0.3)['answer'], True)
        with self.assertRaises(ValueError):
            c.yes_no(STATE, 'a?', 't', 'f', threshold=1.5)

    def test_invalid_inputs_make_no_request(self):
        c, t = client()
        for args in (('', 'a?', 't', 'f'), (STATE, '', 't', 'f'), (STATE, 'a?', '', 'f'), (STATE, 'a?', 't', None)):
            with self.assertRaises(dc.UnsupportedQuestionError):
                c.yes_no(*args)
        self.assertEqual(t.requests, [])


class AskManyTests(unittest.TestCase):
    def test_many_in_one_request(self):
        c, t = client((200, {}, body({'a': 0.2, 'b': 0.8})))
        qs = {'a': dc.make_question('A?', 'yes a', 'no a'), 'b': dc.make_question('B?', 'yes b', 'no b')}
        r = c.ask_many(STATE, qs)
        self.assertEqual(len(t.requests), 1)
        self.assertEqual(r['answers'], {'a': 0.2, 'b': 0.8})

    def test_rejects_non_noul_types(self):
        c, t = client()
        bad = {'type': 'choice', 'instructions': 'Which?', 'choices': ['x', 'y']}
        with self.assertRaisesRegex(dc.UnsupportedQuestionError, 'noul'):
            c.ask_many(STATE, {'k': bad})
        self.assertEqual(t.requests, [])

    def test_rejects_bad_criteria(self):
        c, _ = client()
        for crit in ('string criteria', {'yes': 'a', 'no': 'b'}, {'true': 'a'}, {'true': 'a', 'false': 1}):
            q = {'type': 'noul', 'instructions': 'A?', 'criteria': crit}
            with self.assertRaises(dc.UnsupportedQuestionError):
                c.ask_many(STATE, {'k': q})

    def test_rejects_empty(self):
        c, _ = client()
        with self.assertRaises(dc.UnsupportedQuestionError):
            c.ask_many(STATE, {})
        with self.assertRaises(dc.UnsupportedQuestionError):
            c.ask_many(STATE, [])


class RouteTests(unittest.TestCase):
    OPTS = {'expedite': 'Pay to expedite the order.', 'wait': 'Wait for the supplier.', 'switch': 'Switch supplier.'}

    def test_clear_winner(self):
        c, t = client((200, {}, body({'expedite': 0.9, 'wait': 0.2, 'switch': 0.3})))
        r = c.route(STATE, self.OPTS)
        self.assertEqual(len(t.requests), 1)
        self.assertEqual(set(json.loads(t.requests[0]['body'])['questions']), set(self.OPTS))
        self.assertEqual(r['argmax'], 'expedite')
        self.assertEqual(r['choice'], 'expedite')
        self.assertFalse(r['ambiguous'])
        self.assertAlmostEqual(sum(r['probabilities'].values()), 1.4)  # independent, not normalized
        self.assertIs(r['probabilities_sum_to_one'], False)

    def test_ambiguous_close_top_two(self):
        c, _ = client((200, {}, body({'expedite': 0.8, 'wait': 0.75, 'switch': 0.1})))
        r = c.route(STATE, self.OPTS)
        self.assertTrue(r['ambiguous'])
        self.assertEqual(r['argmax'], 'expedite')

    def test_ambiguous_none_above_threshold(self):
        c, _ = client((200, {}, body({'expedite': 0.4, 'wait': 0.1, 'switch': 0.1})))
        r = c.route(STATE, self.OPTS)
        self.assertTrue(r['ambiguous'])
        self.assertIsNone(r['choice'])
        self.assertEqual(r['argmax'], 'expedite')

    def test_tie_is_deterministic(self):
        c, _ = client((200, {}, body({'expedite': 0.7, 'wait': 0.7, 'switch': 0.0})))
        r = c.route(STATE, self.OPTS)
        self.assertEqual(r['argmax'], 'expedite')
        self.assertTrue(r['ambiguous'])

    def test_needs_two_options(self):
        c, _ = client()
        with self.assertRaises(dc.UnsupportedQuestionError):
            c.route(STATE, {'only': 'one'})


class RetryAndErrorTests(unittest.TestCase):
    def test_retries_then_succeeds(self):
        waits = []
        c, t = client((429, {'Retry-After': '2'}, {'error': {'message': 'slow down'}}),
                      (503, {}, {'error': {'message': 'down'}}), (200, {}, body({'q': 0.6})), sleep=waits.append)
        r = c.yes_no(STATE, 'a?', 't', 'f')
        self.assertEqual(r['retries'], 2)
        self.assertEqual(len(t.requests), 3)
        self.assertEqual(waits, [2.0, 2.0])
        self.assertEqual(c.http_requests, 3)

    def test_retries_bounded_429(self):
        c, t = client(*[(429, {}, {'error': {'message': 'x'}})] * 3, max_retries=2)
        with self.assertRaises(la.RateLimitedError):
            c.yes_no(STATE, 'a?', 't', 'f')
        self.assertEqual(len(t.requests), 3)

    def test_retries_bounded_5xx_and_network(self):
        c, t = client((500, {}, b''), (0, {}, b'{}'), max_retries=1)
        with self.assertRaises(la.ProviderError):
            c.yes_no(STATE, 'a?', 't', 'f')
        self.assertEqual(len(t.requests), 2)

    def test_400_not_retried(self):
        c, t = client((400, {}, {'error': {'message': 'Respan only accepts noul questions'}}))
        with self.assertRaisesRegex(la.ProviderError, 'HTTP 400'):
            c.yes_no(STATE, 'a?', 't', 'f')
        self.assertEqual(len(t.requests), 1)

    def test_error_in_200_body(self):
        c, _ = client((200, {}, {'error': {'message': 'bad'}}))
        with self.assertRaises(la.ProviderError):
            c.yes_no(STATE, 'a?', 't', 'f')

    def test_secret_redacted_from_errors_and_summary(self):
        c, _ = client((401, {}, {'error': {'message': f'bad key {FAKE_KEY}'}}))
        with self.assertRaises(la.ProviderError) as cm:
            c.yes_no(STATE, 'a?', 't', 'f')
        self.assertNotIn(FAKE_KEY, str(cm.exception))
        self.assertNotIn(FAKE_KEY, json.dumps(c.summary()))


class MalformedResponseTests(unittest.TestCase):
    def check(self, payload):
        c, _ = client((200, {}, payload))
        with self.assertRaises(dc.DecisionsResponseError):
            c.yes_no(STATE, 'a?', 't', 'f')
        self.assertEqual(c.calls, [])

    def test_non_json(self):
        self.check(b'<html>')

    def test_non_object(self):
        self.check([1, 2])

    def test_missing_answers(self):
        self.check({'usage': {}})

    def test_missing_key(self):
        self.check(body({'other': 0.5}))

    def test_wrong_type(self):
        self.check({'answers': {'q': {'type': 'choice', 'noul': 0.5}}})

    def test_missing_noul(self):
        self.check({'answers': {'q': {'type': 'noul'}}})

    def test_out_of_range_and_bad_values(self):
        for v in (1.5, -0.1, 'high', None, True, float('nan')):
            self.check(body({'q': v}))


class UsageCostTests(unittest.TestCase):
    def test_usage_totals_and_unknown(self):
        c, _ = client((200, {}, body({'q': 0.5})), (200, {}, body({'q': 0.5}, usage=False)),
                      (200, {}, {'answers': {'q': {'type': 'noul', 'noul': 0.5}}, 'usage': {'input_tokens': 7}}))
        c.yes_no(STATE, 'a?', 't', 'f')
        r2 = c.yes_no(STATE, 'a?', 't', 'f')
        r3 = c.yes_no(STATE, 'a?', 't', 'f')
        self.assertEqual(r2['cost_usd'], 'unknown')
        self.assertIsNone(r2['usage'])
        self.assertEqual(r3['cost_usd'], 'unknown')
        self.assertEqual(c.usage_total['input_tokens'], 57)
        self.assertEqual(c.unknown_cost_calls, 2)
        self.assertEqual(c.total_cost_usd, 0.0)

    def test_nonzero_cost_trips_ceiling(self):
        c, t = client((200, {}, body({'q': 0.5}, cost=0.001)), (200, {}, body({'q': 0.5})))
        with self.assertRaises(dc.CostCeilingError):
            c.yes_no(STATE, 'a?', 't', 'f')
        with self.assertRaises(dc.CostCeilingError):
            c.yes_no(STATE, 'a?', 't', 'f')
        self.assertEqual(len(t.requests), 1)


class IsolationTests(unittest.TestCase):
    def test_only_state_string_and_questions_are_sent(self):
        c, t = client((200, {}, body({'q': 0.5})))
        c.yes_no(STATE, 'Is C short?', 'C is short.', 'C is not short.')
        sent = json.loads(t.requests[0]['body'])
        self.assertEqual(set(sent), {'model', 'state', 'questions'})
        self.assertEqual(sent['state'], STATE)
        self.assertNotIn(FAKE_KEY, t.requests[0]['body'].decode())

    def test_non_string_state_rejected(self):
        c, t = client()
        for state in ({'world': 'obj'}, None, ['x'], ''):
            with self.assertRaises(dc.UnsupportedQuestionError):
                c.yes_no(state, 'a?', 't', 'f')
        self.assertEqual(t.requests, [])

    def test_module_has_no_world_imports(self):
        src = inspect.getsource(dc)
        for forbidden in ('dynamic', 'agent_runner', 'verifier', 'scenario', 'ObservableRunner', 'import requests'):
            self.assertNotIn('import ' + forbidden, src)
            self.assertNotIn('from .' + forbidden, src)


if __name__ == '__main__':
    unittest.main()
