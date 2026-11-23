"""Property tests for the Sarvam spend guard (src/supplychainworld/sarvam_adapter.py). Mocked transports only: no network, no key."""
import json
import os
import tempfile
import threading
import unittest

from hypothesis import given, settings, strategies as st

import support  # noqa: F401

from supplychainworld import llm_adapter as la
from supplychainworld import sarvam_adapter as sa

MODELS = sorted(sa.PRICES_INR_PER_M)


def request(model, chars=200, max_tokens=500):
    body = {'model': model, 'messages': [{'role': 'user', 'content': 'x' * chars}], 'max_tokens': max_tokens,
            'parallel_tool_calls': False, 'tool_choice': 'auto'}
    return {'url': sa.ENDPOINT, 'headers': {'Authorization': 'Bearer test'}, 'body': json.dumps(body).encode()}


def reply(prompt, completion):
    body = {'choices': [{'message': {'role': 'assistant', 'content': 'ok'}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': prompt, 'completion_tokens': completion, 'total_tokens': prompt + completion}}
    return 200, {}, json.dumps(body).encode()


@st.composite
def honest_call(draw):
    """A call whose reported usage stays inside what the request allowed."""
    chars, max_tokens = draw(st.integers(0, 20000)), draw(st.integers(1, 4096))
    return (draw(st.sampled_from(MODELS)), chars, max_tokens, draw(st.integers(0, chars)), draw(st.integers(0, max_tokens)))


calls = st.lists(honest_call(), max_size=40)


class SpendProperties(unittest.TestCase):
    @settings(max_examples=80)
    @given(st.floats(0.01, 5.0), calls)
    def test_the_cap_is_never_passed_each_charge_matches_the_table_and_a_refusal_never_reaches_the_provider(self, cap, seq):
        spend = sa.SarvamSpend(cap)
        sent = []

        def base(req):
            sent.append(req)
            return reply(*usage_now[0])
        usage_now = [(0, 0)]
        tr = sa.SarvamTransport(base, spend)
        for model, chars, max_tokens, pt, ct in seq:
            usage_now[0] = (pt, ct)
            before_sent, before_spent = len(sent), spend.spent_inr
            status, _, raw = tr(request(model, chars, max_tokens))
            self.assertLessEqual(spend.spent_inr, cap + 1e-9)
            if status == 402:
                self.assertEqual(len(sent), before_sent)
                self.assertEqual(spend.spent_inr, before_spent)
            else:
                self.assertEqual(status, 200)
                charge = spend.spent_inr - before_spent
                self.assertAlmostEqual(charge, sa.price_inr(model, pt, ct), places=7)
                usage = json.loads(raw)['usage']
                self.assertAlmostEqual(usage['cost'] * sa.USD_INR, usage['cost_inr'], places=9)

    @given(st.floats(0.01, 50.0), calls)
    def test_the_ledger_rebuilds_the_exact_total_after_a_restart(self, cap, seq):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'spend.jsonl')
            spend = sa.SarvamSpend(cap, path)
            tr = sa.SarvamTransport(lambda req: reply(10, 10), spend)
            for model, chars, max_tokens, _, _ in seq:
                tr(request(model, chars, max_tokens))
            again = sa.SarvamSpend(cap, path)
            self.assertAlmostEqual(again.spent_inr, spend.spent_inr, places=6)
            self.assertEqual(again.calls, spend.calls)
            self.assertEqual(again.exhausted, spend.exhausted)

    @given(st.sampled_from(MODELS))
    def test_a_provider_402_stops_every_later_call_for_good(self, model):
        spend = sa.SarvamSpend(10.0)
        n = []
        tr = sa.SarvamTransport(lambda req: (n.append(1), (402, {}, b'{"error":{"code":402}}'))[1], spend)
        self.assertEqual(tr(request(model))[0], 402)
        self.assertEqual(spend.exhausted, 'credits_exhausted')
        for _ in range(3):
            self.assertEqual(tr(request(model))[0], 402)
        self.assertEqual(len(n), 1)


    @given(st.sampled_from(MODELS), st.integers(1, 100), st.integers(101, 100000))
    def test_a_provider_billing_more_than_the_request_allowed_is_counted_then_everything_stops(self, model, max_tokens, billed):
        spend = sa.SarvamSpend(1000.0)
        n = []
        tr = sa.SarvamTransport(lambda req: (n.append(1), reply(0, billed))[1], spend)
        self.assertEqual(tr(request(model, 10, max_tokens))[0], 200)
        self.assertEqual(spend.exhausted, 'provider_exceeded_limits')
        self.assertAlmostEqual(spend.spent_inr, sa.price_inr(model, 0, billed), places=7)
        self.assertEqual(tr(request(model, 10, max_tokens))[0], 402)
        self.assertEqual(len(n), 1)


def worst_for(model, chars, max_tokens):
    return sa.price_inr(model, len(request(model, chars, max_tokens)['body']) / sa.CHARS_PER_TOKEN_WORST, max_tokens)


class BillingUnknownIsCountedAtTheWorstCase(unittest.TestCase):
    """Review finding: a timeout, a 5xx or an unreadable 200 may still have been billed; only a 4xx refusal proves it was not."""

    @given(st.sampled_from(MODELS), st.integers(0, 5000), st.integers(1, 2048),
           st.sampled_from([0, 500, 502, 503, 504]))
    def test_a_timeout_or_server_error_is_charged_at_the_worst_case(self, model, chars, max_tokens, status):
        spend = sa.SarvamSpend(1000.0)
        tr = sa.SarvamTransport(lambda r: (status, {}, b''), spend)
        self.assertEqual(tr(request(model, chars, max_tokens))[0], status)
        self.assertAlmostEqual(spend.spent_inr, worst_for(model, chars, max_tokens), places=7)
        self.assertEqual(spend.log[0]['basis'], 'unknown_billing_worst_case')

    @given(st.sampled_from(MODELS), st.sampled_from([400, 401, 403, 404, 413, 422, 429]))
    def test_a_4xx_refusal_is_not_charged(self, model, status):
        spend = sa.SarvamSpend(1000.0)
        tr = sa.SarvamTransport(lambda r: (status, {}, b'{}'), spend)
        tr(request(model))
        self.assertEqual(spend.spent_inr, 0.0)
        self.assertEqual(spend.log[0]['basis'], 'rejected_not_billed')

    @given(st.sampled_from(MODELS), st.sampled_from([b'', b'not json', b'[]', b'{"error": {"code": 500}}']))
    def test_an_unreadable_200_is_charged_at_the_worst_case(self, model, raw):
        spend = sa.SarvamSpend(1000.0)
        sa.SarvamTransport(lambda r: (200, {}, raw), spend)(request(model, 100, 50))
        self.assertAlmostEqual(spend.spent_inr, worst_for(model, 100, 50), places=7)

    def test_repeated_timeouts_use_up_the_allowance_and_then_nothing_more_is_sent(self):
        spend, sent = sa.SarvamSpend(0.5), []
        tr = sa.SarvamTransport(lambda r: (sent.append(1), (0, {}, b''))[1], spend)
        for _ in range(200):
            tr(request('sarvam-105b', 2000, 1000))
        self.assertLessEqual(spend.spent_inr, 0.5)
        n = len(sent)
        self.assertGreater(n, 0)
        self.assertEqual(tr(request('sarvam-105b', 2000, 1000))[0], 402)
        self.assertEqual(len(sent), n)


class ReservationsAreAtomicAndDurable(unittest.TestCase):
    """Review findings: admission must be atomic across concurrent calls, and a reservation must be on disk before dispatch."""

    def test_two_concurrent_calls_cannot_both_be_admitted_past_the_cap(self):
        worst = worst_for('sarvam-105b', 1000, 1000)
        spend = sa.SarvamSpend(worst * 1.5)
        in_base, release, results = threading.Event(), threading.Event(), []

        def base(req):
            in_base.set()
            release.wait(5)
            return reply(1000, 1000)
        tr = sa.SarvamTransport(base, spend)
        t1 = threading.Thread(target=lambda: results.append(tr(request('sarvam-105b', 1000, 1000))[0]))
        t1.start()
        self.assertTrue(in_base.wait(5))
        results.append(tr(request('sarvam-105b', 1000, 1000))[0])   # admitted only if the first one's worst case was not reserved
        release.set()
        t1.join(5)
        self.assertEqual(sorted(results), [200, 402])
        self.assertLessEqual(spend.spent_inr, spend.cap_inr)

    @settings(max_examples=40)
    @given(st.sampled_from(MODELS), st.integers(0, 3000), st.integers(1, 1024))
    def test_the_reservation_is_on_disk_before_the_request_leaves_and_survives_a_crash(self, model, chars, max_tokens):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'spend.jsonl')
            spend = sa.SarvamSpend(1000.0, path)
            seen = []

            def base(req):
                with open(path) as fh:
                    seen.extend(json.loads(line) for line in fh)
                raise RuntimeError('process died after the provider accepted the request')
            with self.assertRaises(RuntimeError):
                sa.SarvamTransport(base, spend)(request(model, chars, max_tokens))
            self.assertEqual([r['kind'] for r in seen], ['reserve'])
            worst = worst_for(model, chars, max_tokens)
            self.assertAlmostEqual(spend.spent_inr, worst, places=7)
            again = sa.SarvamSpend(1000.0, path)       # a restart still counts the unresolved reservation
            self.assertAlmostEqual(again.spent_inr, worst, places=7)
            self.assertEqual(again.calls, 0)
            self.assertEqual(len(again.reserved), 1)

    def test_a_settled_call_leaves_no_open_reservation_and_a_restart_matches(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'spend.jsonl')
            spend = sa.SarvamSpend(1000.0, path)
            sa.SarvamTransport(lambda r: reply(50, 20), spend)(request('glm5.3-flash', 100, 200))
            self.assertEqual(spend.reserved, {})
            again = sa.SarvamSpend(1000.0, path)
            self.assertEqual(again.reserved, {})
            self.assertAlmostEqual(again.spent_inr, sa.price_inr('glm5.3-flash', 50, 20), places=8)


class RulesStillHold(unittest.TestCase):
    def test_the_prices_are_positive_and_the_cap_ceiling_is_one_thousand_rupees(self):
        self.assertEqual(sa.CAP_INR, 1000.0)
        for pin, pout in sa.PRICES_INR_PER_M.values():
            self.assertGreater(pin, 0)
            self.assertGreater(pout, 0)

    def test_the_openrouter_free_only_rule_is_unchanged(self):
        for model in ('z-ai/glm-5', 'deepseek/deepseek-v4-flash', 'sarvam-105b', 'glm5.3-flash'):
            with self.assertRaises(la.ModelNotAllowedError):
                la.AdapterConfig(model)
        la.AdapterConfig('baidu/ernie-5.5-flash-preview:free')

    @given(st.one_of(st.text(max_size=20), st.sampled_from(['z-ai/glm-5', 'glm5.3', 'deepseekv4-pro', 'sarvam-prism'])))
    def test_only_models_in_the_price_table_are_accepted(self, model):
        if model in sa.PRICES_INR_PER_M:
            sa.SarvamConfig(model)
        else:
            with self.assertRaises(sa.SarvamModelNotAllowed):
                sa.SarvamConfig(model)

    def test_the_cap_cannot_be_zero_negative_boolean_or_above_one_thousand(self):
        for bad in (0, -1, True, 1000.01, None, 'x', float('nan')):
            with self.assertRaises(ValueError):
                sa.SarvamConfig('sarvam-105b', cap_inr=bad)
            with self.assertRaises(ValueError):
                sa.SarvamSpend(bad)
        sa.SarvamConfig('sarvam-105b', cap_inr=1000)


if __name__ == '__main__':
    unittest.main()
