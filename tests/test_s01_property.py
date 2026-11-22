"""Worked example: Hypothesis property tests on the S01 v0.1 kernel.

Template for the next worker. Pattern: generate a whole action sequence, run it,
then assert invariants after EVERY step (not only at the end), plus replay and
independent-verifier agreement. Hypothesis works on plain unittest methods.
"""
import unittest
from copy import deepcopy

from hypothesis import given, strategies as st

import support  # noqa: F401  (loads the Hypothesis profile)
from support.regression import load_regressions, record_on_failure
from support.s01 import finish, world_factory

from supplychainworld.agent_runner import ObservableRunner, replay
from supplychainworld.dynamic_verifier import verify_episode

# One world command per step. Many will be rejected (wrong day, over capacity,
# repeated commitment); rejections are valid behaviour and must leave state alone.
commands = st.one_of(
    st.tuples(st.just('choose_recovery'), st.sampled_from(['maintain', 'expedite', 'alternate'])),
    st.tuples(st.just('release_production'), st.integers(min_value=-2, max_value=8)),
    st.tuples(st.just('close_day'), st.none()))
sequences = st.lists(commands, max_size=40)
fixture_ids = st.sampled_from(['s01-five-day', 's01-fifteen-day-late-events'])


def apply(world, command):
    name, arg = command
    return getattr(world, name)() if name == 'close_day' else getattr(world, name)(arg)


def check_invariants(test, world, opening=4):
    s = world.snapshot()
    test.assertGreaterEqual(s['component_on_hand'], 0)
    test.assertGreaterEqual(s['finished_on_hand'], 0)
    # Conservation: components in = opening + receipts; out = produced.
    received = (8 if s['primary_received'] else 0) + (8 if s['alternate_received'] else 0)
    test.assertEqual(s['component_on_hand'], opening + received - s['produced_total'])
    # Finished goods: everything produced is either on hand or delivered.
    test.assertEqual(s['produced_total'], s['finished_on_hand'] + s['delivered_total'])
    test.assertLessEqual(s['delivered_total'], world.required)
    test.assertLessEqual(s['incremental_spend'], world.recovery_budget)
    # At most one accepted recovery commitment.
    accepted = [e for e in world.history() if e['kind'] == 'recovery' and e['accepted']]
    test.assertLessEqual(len(accepted), 1)


class S01KernelProperties(unittest.TestCase):
    @given(fixture_ids, sequences)
    def test_invariants_hold_after_every_step_and_rejections_change_nothing(self, fid, seq):
        world = world_factory(fid)()
        with record_on_failure('s01_invariants', {'fixture': fid, 'sequence': seq}):
            for command in seq:
                before = world.snapshot()
                result = apply(world, command)
                if isinstance(result, dict) and result.get('accepted') is False:
                    self.assertEqual(world.snapshot(), before, 'rejected command changed state')
                check_invariants(self, world)

    @given(fixture_ids, sequences)
    def test_recorded_run_replays_exactly_and_verifier_accepts(self, fid, seq):
        factory = world_factory(fid)
        runner = ObservableRunner(factory())
        calls = iter(self._to_tool_calls(seq))
        transcript = runner.run(lambda view: next(calls, {'tool': 'advance_day', 'arguments': {}}))
        with record_on_failure('s01_replay', {'fixture': fid, 'sequence': seq}):
            ok, diffs = replay(transcript, factory)
            self.assertTrue(ok, diffs)
            # Independent verifier: re-derives the ledger from the recorded history.
            world = runner._world
            if world.snapshot()['phase'] == 'complete':
                scenario = world._scenario
                report = verify_episode(scenario, world.history(), horizon_days=world.snapshot()['horizon_days'],
                                        scorecard=deepcopy(transcript['scorecard']))
                self.assertTrue(report.feasible, report.violations)

    @staticmethod
    def _to_tool_calls(seq):
        tool = {'choose_recovery': 'commit_recovery', 'release_production': 'release_production',
                'close_day': 'advance_day'}
        key = {'choose_recovery': 'choice', 'release_production': 'quantity'}
        return [{'tool': tool[n], 'arguments': ({key[n]: a} if n in key else {})} for n, a in seq]

    def test_saved_regressions_still_pass(self):
        # Failing examples saved with support.regression replay here permanently.
        for example in load_regressions('s01_invariants'):
            world = world_factory(example['fixture'])()
            for command in example['sequence']:
                apply(world, tuple(command))
                check_invariants(self, world)


if __name__ == '__main__':
    unittest.main()
