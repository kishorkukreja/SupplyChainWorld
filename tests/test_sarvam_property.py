"""Property tests for the Sarvam spend guard (src/supplychainworld/sarvam_adapter.py). Mocked transports only: no network, no key."""
import json
import os
import tempfile
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
