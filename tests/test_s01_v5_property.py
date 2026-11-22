"""Property tests for S01 v0.5 (issue #19 fixes, finding 1: the scenario id must not give the outcome away).

Hypothesis generates whole scenarios and whole action sequences. The headline property: for generated twin
scenarios (identical except for the hidden outcome, delayed or not), EVERYTHING the agent can see, the opening view,
every state, rules text, clock, tool result and error reason, is identical until the firm notice is visible.
"""
import unittest

from hypothesis import given, strategies as st

import support  # noqa: F401  (loads the Hypothesis profile)
from support.s01v5 import action_lists, blind_agent, make_scenario, visible_scenarios, world_for

from supplychainworld.agent_runner_v5 import ObservableRunnerV5, replay_v5, rule_for_reason
from supplychainworld.dynamic_demo_v5 import actions_of, observations_of, prefix_before_firm_notice
from supplychainworld.dynamic_v5 import LABEL_PATTERN, ScenarioV5, opaque_label
from supplychainworld.dynamic_verifier_v5 import check_observations_for_leaks, expected_label, verify_episode


def run(scenario, horizon, actions):
    world = world_for(scenario, horizon)
    transcript = ObservableRunnerV5(world).run(blind_agent(actions))
    return world, transcript


class TwinScenarioProperties(unittest.TestCase):
    @given(visible_scenarios(warned=True), action_lists)
    def test_warned_delayed_and_warned_no_delay_look_identical_until_the_firm_notice(self, vis, actions):
        visible, horizon, delayed_day = vis
        _, a = run(make_scenario(visible, True, delayed_day), horizon, actions)
        _, b = run(make_scenario(visible, False, delayed_day), horizon, actions)
        self.assertEqual(a['initial']['view'], b['initial']['view'])
        pre_a, pre_b = prefix_before_firm_notice(a), prefix_before_firm_notice(b)
        self.assertTrue(pre_a)
        self.assertEqual(pre_a, pre_b)
        # Also every event the agent could be shown, except the one that opens the notice day itself.
        for x, y in zip(a['attempts'][:len(pre_a)], b['attempts'][:len(pre_b)]):
            if not any(e['kind'] == 'notice' for e in x['events']):
                self.assertEqual(x['events'], y['events'])
                self.assertEqual(x['state_changes'], y['state_changes'])

    @given(visible_scenarios(warned=False), action_lists)
    def test_unwarned_twins_are_identical_until_the_firm_notice_too(self, vis, actions):
        visible, horizon, delayed_day = vis
        _, a = run(make_scenario(visible, True, delayed_day), horizon, actions)
        _, b = run(make_scenario(visible, False, delayed_day), horizon, actions)
        self.assertEqual(prefix_before_firm_notice(a), prefix_before_firm_notice(b))

    @given(visible_scenarios(), st.booleans(), st.booleans())
    def test_label_ignores_the_outcome_and_is_opaque(self, vis, d1, d2):
        visible, horizon, delayed_day = vis
        s1, s2 = make_scenario(visible, d1, delayed_day), make_scenario(visible, d2, delayed_day + 1)
        self.assertEqual(s1['scenario_id'], s2['scenario_id'])
        self.assertRegex(s1['scenario_id'], LABEL_PATTERN)
        self.assertEqual(s1['scenario_id'], expected_label(s1))     # the verifier derives the same label on its own
        sid = world_for(s1, horizon).snapshot()['scenario_id']
        for word in ('delay', 'warn', 'sudden', 'alt', 'cancel', 'tier', 'day'):
            self.assertNotIn(word, sid)

    @given(visible_scenarios(), st.text(max_size=24))
    def test_a_scenario_id_that_is_not_the_exact_label_is_refused(self, vis, text):
        visible, horizon, delayed_day = vis
        s = make_scenario(visible, True, delayed_day)
        good = s['scenario_id']
        if text != good:
            with self.assertRaises(ValueError):
                ScenarioV5(**dict(s, scenario_id=text))
        self.assertEqual(ScenarioV5(**s).scenario_id, good)
        # A visible change changes the label, so the label really is derived from the parameters.
        changed = dict(s, recovery_budget=s['recovery_budget'] + 1)
        self.assertNotEqual(opaque_label(changed), good)


class WholeEpisodeProperties(unittest.TestCase):
    @given(visible_scenarios(), st.booleans(), action_lists)
    def test_any_episode_verifies_replays_and_leaks_nothing(self, vis, delay, actions):
        visible, horizon, delayed_day = vis
        scenario = make_scenario(visible, delay, delayed_day)
        world, t = run(scenario, horizon, actions)
        self.assertEqual(t['status'], 'complete')
        report = verify_episode(scenario, world.history(), horizon_days=horizon, scorecard=world.scorecard(),
                                actions=actions_of(t))
        self.assertTrue(report.feasible, report.violations)
        ok, diffs = replay_v5(t, lambda: world_for(scenario, horizon))
        self.assertTrue(ok, diffs)
        self.assertEqual(check_observations_for_leaks(scenario, observations_of(t)), [])
        for rec in t['attempts']:
            if not rec['accepted']:
                self.assertIsNotNone(rule_for_reason(rec['reason']), rec['reason'])   # every refusal has a stated rule

    @given(visible_scenarios(), st.booleans(), action_lists)
    def test_rejected_calls_change_nothing_and_stock_never_goes_negative(self, vis, delay, actions):
        visible, horizon, delayed_day = vis
        scenario = make_scenario(visible, delay, delayed_day)
        spend_cap = scenario['recovery_budget']
        _, t = run(scenario, horizon, actions)
        for rec in t['attempts']:
            if not rec['accepted']:
                self.assertEqual(rec['state_changes'], {})
            st_ = rec['view_before']['state']
            self.assertGreaterEqual(st_['component_on_hand'], 0)
            self.assertGreaterEqual(st_['finished_on_hand'], 0)
            self.assertLessEqual(st_['incremental_spend'], spend_cap)


if __name__ == '__main__':
    unittest.main()
