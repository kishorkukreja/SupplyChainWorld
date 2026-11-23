"""Fuzz tests for the Sarvam transport: malformed requests, hostile responses, planted keys. It must refuse or pass through
cleanly, never crash, never lower the spend total, and never leak a key."""
import json
import os
import tempfile
import unittest

from hypothesis import given, settings, strategies as st

import support  # noqa: F401
from support.fuzz import json_blobs

from supplychainworld import sarvam_adapter as sa

MODELS = sorted(sa.PRICES_INR_PER_M)
junk_numbers = st.one_of(st.integers(-5, 10 ** 12), st.floats(allow_nan=True, allow_infinity=True), st.booleans(), st.none(),
                         st.text(max_size=5))


class HostileRequests(unittest.TestCase):
    @settings(max_examples=150)
    @given(st.one_of(st.binary(max_size=60), st.text(max_size=60).map(str.encode),
                     json_blobs.map(lambda b: json.dumps(b).encode()),
                     st.fixed_dictionaries({'model': st.one_of(st.sampled_from(MODELS), st.text(max_size=8), st.none()),
                                            'max_tokens': junk_numbers}).map(lambda d: json.dumps(d, allow_nan=True).encode())))
    def test_a_bad_request_is_refused_with_a_clean_status_and_never_reaches_the_provider(self, body):
        spend, sent = sa.SarvamSpend(100.0), []
        tr = sa.SarvamTransport(lambda r: (sent.append(r), (200, {}, b'{}'))[1], spend)
        status, _, raw = tr({'url': sa.ENDPOINT, 'headers': {}, 'body': body})
        self.assertGreaterEqual(spend.spent_inr, 0)
        if status != 200:
            self.assertIn(status, (400, 402, 403))
            self.assertEqual(sent, [])
            self.assertIn('error', json.loads(raw))
        else:  # only a well-formed request for an allowed model with a sane max_tokens may be sent
            req = json.loads(sent[0]['body'])
            self.assertIn(req['model'], MODELS)
            self.assertNotIn('parallel_tool_calls', req)


class HostileResponses(unittest.TestCase):
    @settings(max_examples=150)
    @given(st.one_of(st.binary(max_size=80),
                     json_blobs.map(lambda b: json.dumps(b).encode()),
                     st.fixed_dictionaries({'choices': st.just([{'message': {}}]),
                                            'usage': st.one_of(st.none(), st.just('x'), st.fixed_dictionaries(
                                                {'prompt_tokens': junk_numbers, 'completion_tokens': junk_numbers}))}
                                           ).map(lambda d: json.dumps(d, allow_nan=True).encode())),
           st.sampled_from([200, 200, 400, 429, 500, 502, 402]))
    def test_a_hostile_answer_never_crashes_never_lowers_the_total_and_never_passes_the_cap_silently(self, raw, status):
        spend = sa.SarvamSpend(50.0)
        tr = sa.SarvamTransport(lambda r: (status, {}, raw), spend)
        before = spend.spent_inr
        out = tr({'url': sa.ENDPOINT, 'headers': {}, 'body': json.dumps({'model': 'sarvam-105b', 'max_tokens': 100,
                                                                         'messages': []}).encode()})
        self.assertEqual(len(out), 3)
        self.assertGreaterEqual(spend.spent_inr, before)
        if out[0] == 200:
            try:
                usage = json.loads(out[2]).get('usage')
            except (ValueError, AttributeError):
                usage = None   # an unreadable answer is passed through as it came, and was charged at the worst case
                self.assertGreater(spend.spent_inr, before)
            if isinstance(usage, dict) and 'cost_inr' in usage:
                self.assertGreaterEqual(usage['cost_inr'], 0)
        if spend.spent_inr >= spend.cap_inr:
            self.assertIsNotNone(spend.exhausted)

    def test_missing_or_junk_usage_is_charged_at_the_worst_case_never_at_zero(self):
        for usage in (None, 'x', {}, {'prompt_tokens': True, 'completion_tokens': 5}, {'prompt_tokens': -1, 'completion_tokens': 5}):
            spend = sa.SarvamSpend(50.0)
            body = {'choices': [{'message': {}}]}
            if usage is not None:
                body['usage'] = usage
            tr = sa.SarvamTransport(lambda r: (200, {}, json.dumps(body).encode()), spend)
            tr({'url': sa.ENDPOINT, 'headers': {}, 'body': json.dumps({'model': 'glm5.3-flash', 'max_tokens': 100,
                                                                      'messages': []}).encode()})
            self.assertEqual(spend.log[0]['basis'], 'worst_case_no_usage')
            self.assertGreater(spend.spent_inr, 0)


class KeysStayOut(unittest.TestCase):
    @given(st.text(alphabet='abcdefghijklmnopqrstuvwxyz0123456789', min_size=12, max_size=30))
    def test_the_key_never_reaches_the_ledger_the_log_or_a_response(self, key):
        key = 'KEY' + key
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'l.jsonl')
            spend = sa.SarvamSpend(50.0, path)
            tr = sa.SarvamTransport(lambda r: (200, {}, json.dumps({'choices': [{'message': {}}], 'usage': {
                'prompt_tokens': 5, 'completion_tokens': 5}}).encode()), spend)
            _, _, raw = tr({'url': sa.ENDPOINT, 'headers': {'Authorization': 'Bearer ' + key},
                            'body': json.dumps({'model': 'sarvam-105b', 'max_tokens': 10, 'messages': []}).encode()})
            with open(path) as fh:
                ledger = fh.read()
            self.assertNotIn(key, ledger + json.dumps(spend.log) + raw.decode())
            self.assertNotIn(key, json.dumps(sa.agent_manifest_fields(sa.SarvamConfig('sarvam-105b'))))


if __name__ == '__main__':
    unittest.main()
