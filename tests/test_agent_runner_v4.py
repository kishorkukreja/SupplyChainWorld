import json
import unittest
from copy import deepcopy
from pathlib import Path

from supplychainworld.agent_runner import ObservableRunner
from supplychainworld.agent_runner_v4 import (POLICIES_V4, ObservableRunnerV4, replay_v4, scripted_policy_v4)
from supplychainworld.dynamic import OperationalWorld
from supplychainworld.dynamic_v4 import OperationalWorldV4, ScenarioV4

ROOT = Path(__file__).resolve().parents[1]
FIX = {f['fixture_id']: f for f in json.loads((ROOT / 'fixtures/dynamic/v0.4/scenarios.json').read_text())['fixtures']}


def factory(fid):
    f = FIX[fid]
    return lambda: OperationalWorldV4(f['horizon_days'], scenario=ScenarioV4(**f['scenario']))


def script(calls):
    it = iter(calls)
    return lambda view: next(it, None)


class ToolInterfaceTests(unittest.TestCase):
    def test_v01_runner_and_world_are_untouched(self):
        self.assertEqual(ObservableRunner(OperationalWorld(5)).run(lambda v: None)['status'], 'agent_stopped')
        with self.assertRaises(TypeError):
            ObservableRunner(factory('s04-sudden-5d')())
        with self.assertRaises(TypeError):
            ObservableRunnerV4(OperationalWorld(5))

    def test_tool_names_are_the_v01_names_with_an_extended_commit(self):
        defs = {d['name']: d for d in ObservableRunnerV4(factory('s04-sudden-5d')()).tool_definitions()}
        self.assertEqual(set(defs), {'read_state', 'read_recovery_offers', 'read_scorecard', 'commit_recovery',
                                     'release_production', 'advance_day'})
        self.assertEqual(defs['commit_recovery']['arguments'], ['choice', 'quantity'])
        self.assertTrue(defs['commit_recovery']['repeatable'])

    def test_view_hides_the_hidden_plan(self):
        r = ObservableRunnerV4(factory('s04-warned-delayed-10d')())
        text = json.dumps(r.view())
        for hidden in ('delay_outcome', 'delayed_arrival_day', 'signal_day', 'notice_day', 'oracle', 'expected'):
            self.assertNotIn(hidden, text)

    def test_combined_commitments_through_the_tools_and_no_duplicate_charge(self):
        calls = [
            {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite', 'quantity': 4}, 'action_id': 'e1'},
            {'tool': 'commit_recovery', 'arguments': {'choice': 'alternate', 'quantity': 4}, 'action_id': 'a1'},
            {'tool': 'commit_recovery', 'arguments': {'choice': 'alternate', 'quantity': 4}, 'action_id': 'a1'},   # retry
            {'tool': 'release_production', 'arguments': {'quantity': 4}}, {'tool': 'advance_day'}]
        w = factory('s04-sudden-5d')()
        t = ObservableRunnerV4(w).run(script(calls))
        self.assertEqual([a['accepted'] for a in t['attempts']], [True, True, False, True, True])
        self.assertEqual(t['attempts'][2]['category'], 'repeated_commitment')
        self.assertEqual(w.snapshot()['incremental_spend'], 16 + 12)
        self.assertEqual([c['commit_id'] for c in w.snapshot()['commitments']], ['e1', 'a1'])

    def test_rejections_are_audited_and_leave_state_unchanged(self):
        calls = [{'tool': 'read_scenario'}, {'tool': 'read_state', 'arguments': {'section': 'future'}},
                 {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite', 'quantity': 8, 'oracle': 1}},
                 {'tool': 'commit_recovery', 'arguments': {'choice': 'buy', 'quantity': 1}},
                 {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite', 'quantity': 99}},
                 {'tool': 'release_production', 'arguments': {'quantity': 9}},
                 {'tool': 'read_scorecard'}, {'tool': 'advance_day', 'arguments': {'x': 1}}, 'garbage']
        w = factory('s04-sudden-5d')()
        t = ObservableRunnerV4(w).run(script(calls))
        self.assertTrue(all(not a['accepted'] for a in t['attempts']))
        self.assertEqual([a['category'] for a in t['attempts']][:3], ['hidden_state', 'hidden_state', 'hidden_state'])
        self.assertTrue(all(a['state_changes'] == {} for a in t['attempts']))
        self.assertEqual(w.snapshot()['incremental_spend'], 0)

    def test_authority_classes_are_enforced(self):
        r = ObservableRunnerV4(factory('s04-sudden-5d')(), granted=('read',))
        rec = r.attempt({'tool': 'commit_recovery', 'arguments': {'choice': 'expedite', 'quantity': 1}})
        self.assertEqual(rec['category'], 'authority')


class PolicyAndReplayTests(unittest.TestCase):
    def test_every_policy_completes_on_every_scenario_and_replays_exactly(self):
        for fid in FIX:
            for p in POLICIES_V4:
                t = ObservableRunnerV4(factory(fid)()).run(scripted_policy_v4(p))
                self.assertEqual(t['status'], 'complete', (fid, p))
                self.assertTrue(all(a['accepted'] for a in t['attempts']), (fid, p))
                ok, diffs = replay_v4(t, factory(fid))
                self.assertTrue(ok, (fid, p, diffs))

    def test_replay_detects_a_changed_transcript(self):
        t = ObservableRunnerV4(factory('s04-sudden-5d')()).run(scripted_policy_v4('combo_on_alert'))
        bad = deepcopy(t)
        next(a for a in bad['attempts'] if a['tool'] == 'commit_recovery')['arguments']['quantity'] = 3
        self.assertFalse(replay_v4(bad, factory('s04-sudden-5d'))[0])
        bad = deepcopy(t)
        bad['scorecard']['cost']['net_cost'] = 1
        self.assertIn('scorecard', replay_v4(bad, factory('s04-sudden-5d'))[1])
        with self.assertRaises(ValueError):
            replay_v4(dict(t, schema='other'), factory('s04-sudden-5d'))

    def test_policies_read_only_the_visible_view(self):
        w = factory('s04-warned-no-delay-10d')()
        seen = []

        def spy(view):
            seen.append(json.dumps(view))
            return scripted_policy_v4('expedite_on_alert')(view)

        ObservableRunnerV4(w).run(lambda v: spy(v))
        self.assertTrue(seen)
        for s in seen:
            self.assertNotIn('delay_outcome', s)
            self.assertNotIn('hint_pct', s)

    def test_policy_behaviour_on_a_warned_no_delay_scenario(self):
        # Reacting to the signal costs money when the delay never materializes; waiting does not.
        costs = {}
        for p in POLICIES_V4:
            t = ObservableRunnerV4(factory('s04-warned-no-delay-10d')()).run(scripted_policy_v4(p))
            costs[p] = t['scorecard']['cost']['net_cost']
        self.assertEqual(costs['maintain'], 0)
        self.assertEqual(costs['staged_revisit'], 16)       # only the hedge half (4 x 4), no revisit without a delay notice
        self.assertGreater(costs['expedite_on_alert'], costs['maintain'])
        self.assertEqual(costs, {'maintain': 0, 'expedite_on_alert': 32, 'alternate_on_alert': 24,
                                 'combo_on_alert': 28, 'staged_revisit': 16})    # premiums only; custom part, no salvage

    def test_policies_by_net_cost_on_the_slow_expedite_scenario(self):
        costs = {}
        for p in POLICIES_V4:
            t = ObservableRunnerV4(factory('s04-alt-cheaper-10d')()).run(scripted_policy_v4(p))
            costs[p] = t['scorecard']['cost']['net_cost']
        self.assertEqual(costs, {'maintain': 78, 'expedite_on_alert': 98, 'alternate_on_alert': 30,
                                 'combo_on_alert': 58, 'staged_revisit': 102})
        self.assertEqual(min(costs, key=costs.get), 'alternate_on_alert')

    def test_the_agent_view_shows_a_level_and_the_rate_card_basis_but_no_percent_hint(self):
        r = ObservableRunnerV4(factory('s04-warned-delayed-10d')())
        v = r.view()
        self.assertEqual(v['state']['signals'][0]['level'], 'medium')
        self.assertEqual(v['rules']['part_class'], 'custom')
        offers = v['rules']['recovery_offers']
        self.assertEqual(offers['expedite']['today']['unit_cost'], 4)
        self.assertIn('premium', offers['expedite']['basis'])

    def test_unknown_policy_is_rejected(self):
        with self.assertRaises(ValueError):
            scripted_policy_v4('clairvoyant')


if __name__ == '__main__':
    unittest.main()
