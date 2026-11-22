"""S01 v0.6: fuzz tests (malformed, duplicated, out-of-order, extreme and adversarial input).

v0.6 runs through the same generic fuzz suites as the earlier versions (malformed tool calls through the runner; twin
scenarios that differ only in the hidden outcome look identical until the firm notice; damaged scenario files; damaged
transcripts; garbage histories, scorecards and action logs fed to the checker). Nothing is skipped for v0.6. The extra
cases are about what v0.6 adds: repeated, reused, reserved-prefix and extreme action ids, and a hostile reader of the
conventions block.
"""
import json
import unittest
from copy import deepcopy

from hypothesis import given, settings, strategies as st

import support  # noqa: F401
import test_s01_versions_fuzz as tf
from support import fuzz
from support.s01_v6 import V6, SCENARIOS_V6
from support.s01_versions import fixture_scenario

RunnerFuzz_v06 = tf.make_runner_cases(V6)
EarlyWarningTwins_v06 = tf.make_twin_cases(V6)
ScenarioFuzz_v06 = tf.make_scenario_fuzz(V6)
RecordFuzz_v06 = tf.make_record_fuzz(V6)

ID = st.one_of(st.none(), st.sampled_from(['a', 'b', 'auto-00000000', 'auto-', 'AUTO-1', '', ' ', 'x' * 500, 'auto-\u0000']),
               fuzz.json_blobs)


@st.composite
def commit_storm(draw):
    n = draw(st.integers(1, 25))
    calls = []
    for _ in range(n):
        kind = draw(st.sampled_from(['commit', 'commit', 'commit', 'advance', 'release']))
        if kind == 'commit':
            call = {'tool': 'commit_recovery', 'arguments': {
                'choice': draw(st.sampled_from(['expedite', 'alternate', 'expedite', 'bogus'])),
                'quantity': draw(st.one_of(st.integers(-2, 5), st.integers(-2 ** 40, 2 ** 40), st.just(True), st.just(1.5)))}}
            action_id = draw(ID)
            if action_id is not None:
                call['action_id'] = action_id
        elif kind == 'advance':
            call = {'tool': 'advance_day', 'arguments': {}}
        else:
            call = {'tool': 'release_production', 'arguments': {'quantity': draw(st.integers(0, 4))}}
        calls.append(call)
    return calls


class ActionIdStorm(unittest.TestCase):
    """Whatever ids arrive (none, repeated, reserved, huge, wrong type), the world stays consistent and the checker agrees."""

    base = fixture_scenario(V6, V6.fixtures()[1])

    @given(commit_storm())
    @settings(max_examples=120)
    def test_rejected_calls_change_nothing_ids_stay_unique_and_the_checker_accepts_the_history(self, calls):
        scenario, horizon = self.base
        runner = V6.runner(scenario, horizon)
        world = runner._world
        for call in calls:
            before = world.snapshot()
            try:
                rec = runner.attempt(deepcopy(call))
            except Exception as exc:  # noqa: BLE001
                self.fail(f'crash on {call!r}: {type(exc).__name__}: {exc}')
            if not rec['accepted']:
                self.assertEqual(world.snapshot(), before, f'a refused call changed state: {call!r}')
            commits = world.snapshot()['commitments']
            self.assertEqual(len({c['commit_id'] for c in commits}), len(commits))
            self.assertFalse([c for c in commits if str(c['commit_id']).startswith('auto-')
                              and c['commit_id'] != support_key(c)], 'a reserved key was used by an explicit id')
        while world.snapshot()['phase'] != 'complete':
            runner.attempt({'tool': 'advance_day', 'arguments': {}})
        report = V6.verify(V6.scenario_dict(world), world.history(), horizon, scorecard=world.scorecard())
        self.assertEqual(report.violations, [])

    @given(SCENARIOS_V6, st.integers(1, 3))
    @settings(max_examples=40)
    def test_repeating_the_whole_call_stream_is_refused_for_every_commitment(self, sc, rounds):
        scenario, horizon = sc
        runner = V6.runner(scenario, horizon)
        runner.attempt({'tool': 'advance_day', 'arguments': {}})
        view = runner.view()
        offers = view['rules'].get('recovery_offers')
        if not offers:
            return
        call = {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite', 'quantity': 1}}
        first = runner.attempt(deepcopy(call))
        executed = int(first['accepted'])
        for _ in range(rounds):
            self.assertFalse(runner.attempt(deepcopy(call))['accepted'])
        self.assertEqual(len(runner._world.snapshot()['commitments']), executed)


def support_key(commit):
    from supplychainworld.dynamic_v6 import derived_commit_key
    return derived_commit_key(commit['day'], commit['choice'], commit['quantity'])


class ConventionsAreInertData(unittest.TestCase):
    """The block is data: reading, copying or editing a copy cannot change the world."""

    @given(SCENARIOS_V6, st.data())
    @settings(max_examples=30)
    def test_editing_the_block_the_agent_received_does_not_change_the_world(self, sc, data):
        scenario, horizon = sc
        runner = V6.runner(scenario, horizon)
        view = runner.view()
        view['rules']['conventions']['parameters']['penalty_rate_divisor_percent_of_value'] = 1
        view['rules']['conventions']['statements'].clear()
        again = runner.view()
        self.assertEqual(again['rules']['conventions']['parameters']['penalty_rate_divisor_percent_of_value'], 10000)
        self.assertTrue(again['rules']['conventions']['statements'])
        json.dumps(again['rules']['conventions'])


if __name__ == '__main__':
    unittest.main()
