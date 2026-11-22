"""Fuzz tests for S01 v0.5: malformed and adversarial input to the tool runner, the scenario id and the leak scan.

Assert: no crash, clean rejection, state unchanged, no outcome class and no hidden field in anything the agent is told,
and every refusal reason maps to a stated rule (so a refusal can never be an unexplained rule).
"""
import json
import unittest
from copy import deepcopy

from hypothesis import given, strategies as st

import support  # noqa: F401
from support import fuzz
from support.s01v5 import FIXTURES

from supplychainworld import dynamic_demo_v5 as demo
from supplychainworld import dynamic_verifier_v5 as dv5
from supplychainworld.agent_runner_v5 import ObservableRunnerV5, rule_for_reason
from supplychainworld.dynamic_v5 import ScenarioV5

HIDDEN_KEYS = ('delay_outcome', 'delayed_arrival_day', 'signal_day', 'notice_day', 'opening_components')
FIXTURE = FIXTURES['s05-warned-delayed-10d']


def new_runner():
    return ObservableRunnerV5(demo.factory(FIXTURE)())


def told_text(record):
    return json.dumps({k: record[k] for k in ('reason', 'result', 'category')}).lower()


class RunnerFuzz(unittest.TestCase):
    @given(fuzz.malformed_tool_calls())
    def test_malformed_calls_are_rejected_state_unchanged_and_explained_by_a_rule(self, call):
        runner = new_runner()
        before = runner._world.snapshot()
        record = runner.attempt(call)
        self.assertFalse(record['accepted'], record['reason'])
        self.assertEqual(runner._world.snapshot(), before)
        self.assertIsNotNone(rule_for_reason(record['reason']), record['reason'])
        text = told_text(record)
        for key in HIDDEN_KEYS:
            self.assertNotIn(key, text)
        for word in dv5.OUTCOME_WORDS:
            self.assertNotIn(word, text)

    @given(st.lists(st.one_of(fuzz.malformed_tool_calls(), fuzz.json_blobs), max_size=30))
    def test_stream_of_garbage_never_crashes_and_never_moves_the_world(self, calls):
        runner = new_runner()
        before = runner._world.snapshot()
        for call in calls:
            runner.attempt(call)
        self.assertEqual(runner._world.snapshot(), before)
        json.dumps(runner.transcript())
        # The agent-visible view never shows the outcome class or the hidden plan, whatever was sent.
        for a in runner.transcript()['attempts']:
            self.assertEqual(dv5.check_observations_for_leaks(
                FIXTURE['scenario'], [{'state': a['view_before']['state'], 'rules': a['view_before']['rules'],
                                       'last_outcome': a['view_before']['last_outcome']}]), [])

    @given(st.lists(fuzz.valid_call_sequences(max_len=20), min_size=1, max_size=1))
    def test_well_formed_sequences_leave_every_observation_clean_and_every_refusal_explained(self, seqs):
        runner = new_runner()
        it = iter(seqs[0])
        t = runner.run(lambda view: next(it, None) or (
            {'tool': 'advance_day', 'arguments': {}} if view['state']['phase'] != 'complete' else None))
        self.assertEqual(dv5.check_observations_for_leaks(
            FIXTURE['scenario'], [{'state': a['view_before']['state'], 'rules': a['view_before']['rules'],
                                   'last_outcome': a['view_before']['last_outcome']} for a in t['attempts']]), [])
        for a in t['attempts']:
            if not a['accepted']:
                self.assertIsNotNone(rule_for_reason(a['reason']), a['reason'])


class ScenarioIdFuzz(unittest.TestCase):
    @given(fuzz.json_blobs)
    def test_any_junk_scenario_id_is_refused_cleanly(self, junk):
        with self.assertRaises(ValueError):
            ScenarioV5(**dict(FIXTURE['scenario'], scenario_id=junk))

    @given(st.sampled_from(sorted(FIXTURE['scenario'])), fuzz.json_blobs)
    def test_junk_in_any_field_is_a_clean_refusal_or_a_consistent_scenario(self, key, junk):
        sc = dict(FIXTURE['scenario'])
        sc[key] = junk
        try:
            s = ScenarioV5(**sc)
        except (ValueError, TypeError):
            return                                   # refused cleanly
        # Accepted only when the label still matches its visible parameters.
        self.assertEqual(s.scenario_id, dv5.expected_label(s.to_dict()))


class LeakScanFuzz(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        t = new_runner().run(lambda v: None)
        cls.obs = [{'state': t['initial']['view']['state'], 'rules': t['initial']['view']['rules'],
                    'last_outcome': t['initial']['view']['last_outcome']}]

    @given(st.lists(fuzz.json_blobs, max_size=4))
    def test_garbage_observations_never_crash_and_are_never_reported_clean(self, blobs):
        out = dv5.check_observations_for_leaks(FIXTURE['scenario'], blobs)
        self.assertIsInstance(out, list)
        if blobs:
            self.assertTrue(out)

    @given(st.data())
    def test_damaged_real_observations_never_crash_and_a_changed_id_is_always_found(self, data):
        obs = deepcopy(self.obs)
        kind = data.draw(st.sampled_from(['drop_state_key', 'new_id', 'blob']))
        if kind == 'drop_state_key':
            del obs[0]['state'][data.draw(st.sampled_from(sorted(obs[0]['state'])))]
        elif kind == 'new_id':
            obs[0]['state']['scenario_id'] = data.draw(st.text(max_size=20).filter(lambda x: x != FIXTURE['scenario']['scenario_id']))
        else:
            obs[0]['rules'] = data.draw(fuzz.json_blobs)
        out = dv5.check_observations_for_leaks(FIXTURE['scenario'], obs)
        self.assertIsInstance(out, list)
        if kind == 'new_id':
            self.assertTrue(any('opaque' in x for x in out), out)


if __name__ == '__main__':
    unittest.main()
