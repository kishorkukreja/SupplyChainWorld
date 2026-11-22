"""Worked example: end-to-end integration on the S01 v0.1 modules.

Template for the next worker. Uses the same entry points a real agent or script
uses: the tool runner drives the simulator, the independent verifier re-checks
the recorded history, and replay re-runs the transcript on a fresh world. No
mocks (nothing here touches the network).
"""
import unittest
from copy import deepcopy

import support  # noqa: F401
from support.s01 import FIXTURES, POLICIES, new_runner, world_factory

from supplychainworld.agent_runner import replay, scripted_policy
from supplychainworld.dynamic_verifier import verify_episode


class EndToEnd(unittest.TestCase):
    def episode(self, fixture_id, policy):
        runner = new_runner(fixture_id)
        transcript = runner.run(scripted_policy(policy))
        world = runner._world
        return transcript, world

    def test_every_fixture_and_policy_runs_verifies_and_replays(self):
        for f in FIXTURES:
            for policy in POLICIES:
                with self.subTest(fixture=f['fixture_id'], policy=policy):
                    transcript, world = self.episode(f['fixture_id'], policy)
                    self.assertEqual(transcript['status'], 'complete')
                    # The verifier reads only the recorded history and the claimed
                    # scorecard; it does not trust any simulator "passed" flag.
                    report = verify_episode(f['scenario'], world.history(), horizon_days=f['horizon_days'],
                                            scorecard=deepcopy(transcript['scorecard']))
                    self.assertTrue(report.complete)
                    self.assertTrue(report.feasible, report.violations)
                    ok, diffs = replay(transcript, world_factory(f['fixture_id']))
                    self.assertTrue(ok, diffs)

    def test_policies_order_as_the_written_rules_say(self):
        # Hand-checked from the five-day fixture: maintain pays 120 in penalties,
        # expedite 24 spend, alternate 40 spend (all PROVISIONAL numbers).
        cost = {p: self.episode('s01-five-day', p)[0]['scorecard']['comparison_cost'] for p in POLICIES}
        self.assertEqual(cost, {'maintain': 120, 'expedite': 24, 'alternate': 40})

    def test_tampered_record_is_caught_by_the_verifier_and_the_replay(self):
        f = FIXTURES[0]
        transcript, world = self.episode(f['fixture_id'], 'expedite')
        # Tamper 1: claim a better scorecard than the history supports.
        lie = deepcopy(transcript['scorecard'])
        lie['comparison_cost'] = 0
        report = verify_episode(f['scenario'], world.history(), horizon_days=f['horizon_days'], scorecard=lie)
        self.assertTrue(report.violations or not report.feasible)
        # Tamper 2: edit the transcript's final state; replay must notice.
        forged = deepcopy(transcript)
        forged['final_state']['delivered_total'] += 1
        ok, diffs = replay(forged, world_factory(f['fixture_id']))
        self.assertFalse(ok)
        self.assertIn('final_state', diffs)


if __name__ == '__main__':
    unittest.main()
