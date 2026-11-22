"""Worked example: fuzz tests on the S01 v0.1 tool runner, replay and verifier.

Template for the next worker. Pattern: feed generated malformed or adversarial
input, assert (1) it never crashes, (2) it is rejected, (3) world state is
unchanged, (4) hidden scenario fields never appear in what the agent receives.
"""
import json
import unittest

from hypothesis import given, strategies as st

import support  # noqa: F401
from support import fuzz
from support.s01 import new_runner, world_factory, POLICIES

from supplychainworld.agent_runner import ObservableRunner, replay, scripted_policy
from supplychainworld.dynamic_verifier import ScenarioError, verify_episode

# Scenario mechanics that an agent must never see (names, not values).
HIDDEN_KEYS = ('delay_notice_day', 'delayed_arrival_day', 'initially_promised_day',
               'recovery_deadline_day', 'disruption_enabled', 'opening_components')


class RunnerFuzz(unittest.TestCase):
    @given(fuzz.malformed_tool_calls())
    def test_malformed_calls_are_rejected_with_state_unchanged(self, call):
        runner = new_runner()
        before = runner._world.snapshot()
        record = runner.attempt(call)            # must not raise
        self.assertFalse(record['accepted'], record['reason'])
        self.assertIsNotNone(record['category'])
        self.assertEqual(runner._world.snapshot(), before)
        # What the agent is told contains no hidden scenario field names.
        text = json.dumps(record)
        for key in HIDDEN_KEYS:
            self.assertNotIn(key, text)

    @given(st.lists(st.one_of(fuzz.malformed_tool_calls(), fuzz.json_blobs), max_size=30))
    def test_stream_of_garbage_never_crashes_and_never_moves_the_world(self, calls):
        runner = new_runner()
        before = runner._world.snapshot()
        for call in calls:
            runner.attempt(call)
        # Attempts are recorded, but nothing malformed may change operational state
        # (blobs could by chance be valid reads; reads do not change state either).
        self.assertEqual(runner._world.snapshot(), before)
        json.dumps(runner.transcript())          # the transcript stays serializable

    def test_values_that_are_not_json_are_refused_not_fatal(self):
        runner = new_runner()
        for bad in (float('nan'), float('inf'), {1, 2}, b'x', object, ...):
            record = runner.attempt({'tool': 'release_production', 'arguments': {'quantity': bad}})
            self.assertFalse(record['accepted'])


class ReplayAndVerifierFuzz(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        runner = new_runner()
        cls.transcript = runner.run(scripted_policy('expedite'))
        cls.world = runner._world

    @given(st.data())
    def test_damaged_transcripts_never_crash_replay_with_a_surprising_error(self, data):
        damaged = data.draw(fuzz.mutated_transcripts(self.transcript))
        try:
            ok, diffs = replay(damaged, world_factory())
        except (ValueError, KeyError, TypeError, StopIteration):
            return  # clean refusal of a structurally broken transcript
        self.assertEqual(ok, not diffs)   # verdict and difference list agree

    @given(st.lists(fuzz.json_blobs, max_size=6), st.one_of(st.none(), fuzz.json_blobs))
    def test_verifier_survives_garbage_history(self, history, scorecard):
        scenario, horizon = self.world._scenario, self.world.snapshot()['horizon_days']
        try:
            report = verify_episode(scenario, history, horizon_days=horizon, scorecard=scorecard)
        except ScenarioError:
            return
        self.assertIsInstance(report.violations, list)
        if not history:   # an empty record can never be a complete feasible episode
            self.assertFalse(report.complete and report.feasible)


if __name__ == '__main__':
    unittest.main()
