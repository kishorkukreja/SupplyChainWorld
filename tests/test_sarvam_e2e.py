"""End-to-end: S01 v0.6 episodes on Sarvam model ids through the real adapter, runner, checker and replay, with a mocked provider
behind SarvamTransport and the same Guard that wraps the OpenRouter transport. No network, no key."""
import json
import unittest

import support  # noqa: F401
import test_eval19_v2 as t2

from supplychainworld import eval19_v3 as ev3
from supplychainworld import sarvam_adapter as sa
from supplychainworld.agent_runner_v6 import POLICIES_V6
from supplychainworld.eval19 import Guard
from supplychainworld.dynamic_demo_v6 import load_fixtures

FIXTURES = load_fixtures()


class Rig:
    def __init__(self, policy, cap_inr=sa.CAP_INR, model='sarvam-105b'):
        self.spend = sa.SarvamSpend(cap_inr)
        self.base = t2.PolicyModel(policy)
        self.guard = Guard(sa.SarvamTransport(self.base, self.spend), sleep=lambda s: None, min_interval=0.0)
        self.guard.model, self.guard.phase = model, 's01'
        self.model, self.cap = model, cap_inr

    def run(self, fixture):
        return sa.run_s01_episode(fixture, self.model, self.guard, cap_inr=self.cap, sleep=lambda s: None)


class SarvamEpisodes(unittest.TestCase):
    def test_every_scenario_and_policy_completes_feasible_replayed_clean_and_priced_on_all_three_models(self):
        for model in sorted(sa.PRICES_INR_PER_M):
            for policy in POLICIES_V6:
                for fx in FIXTURES:
                    rig = Rig(policy, model=model)
                    raw = rig.run(fx)
                    g = ev3.grade_s01(fx, raw)
                    key = (model, policy, fx['fixture_id'])
                    self.assertEqual(g['status'], 'complete', key)
                    self.assertTrue(g['verifier_feasible'] and g['replay_reproduced'], key)
                    self.assertEqual(g['observation_leaks'], [], key)
                    self.assertEqual(rig.spend.calls, len(raw['telemetry']['calls']), key)
                    self.assertGreater(rig.spend.spent_inr, 0, key)
                    self.assertAlmostEqual(raw['telemetry']['cost_usd'] * sa.USD_INR, rig.spend.spent_inr, places=6)

    def test_the_sarvam_path_reaches_the_same_scorecard_as_the_openrouter_path(self):
        for fx in FIXTURES:
            via_sarvam = ev3.grade_s01(fx, Rig('combo_on_alert').run(fx))['metrics']
            base = t2.PolicyModel('combo_on_alert')
            g = t2.guarded(base, private_strings=[])
            g.model, g.phase = t2.MODEL, 's01'
            via_or = ev3.grade_s01(fx, ev3.run_s01_episode(fx, t2.MODEL, g, sleep=lambda s: None))['metrics']
            self.assertEqual(via_sarvam, via_or, fx['fixture_id'])

    def test_the_manifest_says_sarvam_paid_and_capped_not_openrouter_free(self):
        raw = Rig('combo_on_alert').run(FIXTURES[0])
        m = raw['manifest']
        self.assertEqual(m['provider'], 'sarvam')
        self.assertFalse(m['spend']['free_only'])
        self.assertEqual(m['spend']['cap_inr'], 10000.0)
        self.assertEqual(m['credential']['env_var'], 'SARVAM_API_KEY')
        self.assertIn('PROVISIONAL', m['spend']['cost_rule'])

    def test_no_request_to_the_provider_carries_the_fields_sarvam_may_reject(self):
        rig = Rig('combo_on_alert')
        rig.run(FIXTURES[0])
        self.assertTrue(rig.base.bodies)
        # the guard sees the adapter's request; the provider (base) must receive it without the dropped fields
        self.assertTrue(all('parallel_tool_calls' not in b for b in rig.base.bodies))


class CapStopsTheRun(unittest.TestCase):
    def test_a_tiny_cap_ends_the_episode_in_a_clean_error_and_sends_nothing_more(self):
        rig = Rig('combo_on_alert', cap_inr=0.5)
        # shrink the allowance further by pre-spending almost all of it
        rig.spend.record('sarvam-105b', 0.499, 'usage', 1, 1)
        raw = rig.run(FIXTURES[0])
        self.assertNotEqual(raw['transcript']['status'], 'complete')
        self.assertLessEqual(rig.spend.spent_inr, 0.5 + 1e-9)
        n = len(rig.base.bodies)
        raw2 = rig.run(FIXTURES[1])
        self.assertEqual(len(rig.base.bodies), n)
        self.assertNotEqual(raw2['transcript']['status'], 'complete')

    def test_a_provider_that_runs_out_of_credits_stops_the_run_for_good(self):
        spend = sa.SarvamSpend(1000.0)
        calls = []

        def base(req):
            calls.append(1)
            return 402, {}, json.dumps({'error': {'code': 402, 'message': 'insufficient_quota_error'}}).encode()
        guard = Guard(sa.SarvamTransport(base, spend), sleep=lambda s: None, min_interval=0.0)
        guard.model, guard.phase = 'glm5.3-flash', 's01'
        raw = sa.run_s01_episode(FIXTURES[0], 'glm5.3-flash', guard, sleep=lambda s: None)
        self.assertNotEqual(raw['transcript']['status'], 'complete')
        self.assertEqual(spend.exhausted, 'credits_exhausted')
        self.assertEqual(len(calls), 1)

    def test_the_guard_still_blocks_a_private_marker_before_the_transport_sees_it(self):
        spend, sent = sa.SarvamSpend(1000.0), []
        guard = Guard(sa.SarvamTransport(lambda r: sent.append(r), spend), sleep=lambda s: None, min_interval=0.0,
                      private_strings=['sarvam-105b'])
        guard.model, guard.phase = 'sarvam-105b', 's01'
        sa.run_s01_episode(FIXTURES[0], 'sarvam-105b', guard, sleep=lambda s: None)
        self.assertEqual(sent, [])
        self.assertTrue(guard.leak_flags)


if __name__ == '__main__':
    unittest.main()
