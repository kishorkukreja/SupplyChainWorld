"""S01 v0.5: opaque scenario id, fixtures, generators, hand-worked ledgers, independent verifier, all 25 episodes.

Pinned regressions and exact cases. The property and fuzz coverage is in test_s01_v5_property.py and
test_s01_v5_fuzz.py; the end-to-end run through the model harness is in test_eval19_v2.py.
"""
import ast
import json
import subprocess
import sys
import unittest
from copy import deepcopy
from pathlib import Path

from supplychainworld import dynamic_demo_v5 as demo
from supplychainworld import dynamic_verifier_v5 as dv5
from supplychainworld.agent_runner_v4 import ObservableRunnerV4, scripted_policy_v4
from supplychainworld.agent_runner_v5 import POLICIES_V5, ObservableRunnerV5, scripted_policy_v5
from supplychainworld.dynamic_v4 import OperationalWorldV4, ScenarioV4
from supplychainworld.dynamic_v5 import LABEL_PATTERN, OperationalWorldV5, ScenarioV5, opaque_label

ROOT = Path(__file__).resolve().parents[1]
V4 = {f['fixture_id']: f for f in json.loads((ROOT / 'fixtures/dynamic/v0.4/scenarios.json').read_text())['fixtures']}
V5 = {f['fixture_id']: f for f in demo.load_fixtures()}
HAND4 = json.loads((ROOT / 'fixtures/dynamic/v0.4/hand-ledgers.json').read_text())['fixtures']
HAND5 = demo.load_hand()


class FixtureTests(unittest.TestCase):
    def test_five_scenarios_with_opaque_ids_and_unchanged_numbers(self):
        self.assertEqual(len(V5), 5)
        for fid, f in V5.items():
            old = V4[fid.replace('s05-', 's04-')]
            self.assertRegex(f['scenario']['scenario_id'], LABEL_PATTERN)
            self.assertEqual({k: v for k, v in f['scenario'].items() if k != 'scenario_id'},
                             {k: v for k, v in old['scenario'].items() if k != 'scenario_id'}, fid)
            self.assertEqual((f['horizon_days'], f['disruption_class']), (old['horizon_days'], old['disruption_class']))

    def test_the_paired_warned_scenarios_share_one_label_and_others_differ(self):
        labels = {fid: f['scenario']['scenario_id'] for fid, f in V5.items()}
        self.assertEqual(labels[demo.PAIR[0]], labels[demo.PAIR[1]])
        self.assertEqual(len(set(labels.values())), 4)

    def test_no_outcome_word_in_any_scenario_id(self):
        for f in V5.values():
            for word in ('delay', 'warn', 'sudden', 'cancel', 'alt', 'multitier', 'tier'):
                self.assertNotIn(word, f['scenario']['scenario_id'])

    def test_hand_ledgers_are_the_v04_ledgers_because_no_number_changed(self):
        self.assertEqual({k.replace('s04-', 's05-'): v for k, v in HAND4.items()}, HAND5)

    def test_committed_fixtures_equal_generator_output(self):
        for script in ('generate_fixtures_v05.py', 'generate_hand_ledgers_v05.py'):
            r = subprocess.run([sys.executable, str(ROOT / 'scripts' / script), '--check'], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, (script, r.stdout, r.stderr))

    def test_generators_import_nothing_from_the_project(self):
        for script in ('generate_fixtures_v05.py', 'generate_hand_ledgers_v05.py'):
            names = set()
            for node in ast.walk(ast.parse((ROOT / 'scripts' / script).read_text())):
                if isinstance(node, ast.Import):
                    names |= {a.name.split('.')[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom):
                    names.add((node.module or '').split('.')[0])
            self.assertFalse({n for n in names if 'supplychainworld' in n or n.startswith('.')}, script)

    def test_fixture_label_equals_the_simulator_and_the_independent_verifier_label(self):
        for f in V5.values():
            self.assertEqual(f['scenario']['scenario_id'], opaque_label(f['scenario']))
            self.assertEqual(f['scenario']['scenario_id'], dv5.expected_label(f['scenario']))


class WorldTests(unittest.TestCase):
    def test_world_state_shows_only_the_opaque_label(self):
        for f in V5.values():
            w = demo.factory(f)()
            self.assertEqual(w.snapshot()['scenario_id'], f['scenario']['scenario_id'])
            self.assertEqual(w.snapshot()['schema_version'], '5.0')

    def test_descriptive_names_and_wrong_labels_are_refused(self):
        sc = deepcopy(V5['s05-warned-delayed-10d']['scenario'])
        for bad in ('s04-warned-delayed-10d', 'scn-warned-delayed', 'scn-00000000', 'SCN-BC29021C', 'scn-bc29021', '', ' scn-bc29021c'):
            with self.assertRaises(ValueError, msg=bad):
                ScenarioV5(**dict(sc, scenario_id=bad))
        with self.assertRaises(TypeError):
            OperationalWorldV5(10, scenario=ScenarioV4(**V4['s04-sudden-5d']['scenario']))
        with self.assertRaises(TypeError):
            demo.ObservableRunnerV5(OperationalWorldV4(5, scenario=ScenarioV4(**V4['s04-sudden-5d']['scenario'])))

    def test_the_v04_defect_is_real_and_the_v05_checks_catch_it(self):
        """In v0.4 the twins differ in the world state before any notice; v0.5 verifier scan flags that world."""
        def first_view(fid):
            f = V4[fid]
            w = OperationalWorldV4(f['horizon_days'], scenario=ScenarioV4(**f['scenario']))
            return f, ObservableRunnerV4(w).run(scripted_policy_v4('maintain'))
        fa, ta = first_view('s04-warned-delayed-10d')
        fb, tb = first_view('s04-warned-no-delay-10d')
        self.assertEqual(ta['initial']['view']['state']['scenario_id'], 's04-warned-delayed-10d')
        self.assertNotEqual(ta['initial']['view']['state'], tb['initial']['view']['state'])
        leaks = dv5.check_observations_for_leaks(
            demo.load_fixtures()[1]['scenario'], [{'state': ta['initial']['view']['state'], 'rules': ta['initial']['view']['rules']}])
        self.assertTrue(any('opaque' in x for x in leaks), leaks)
        self.assertTrue(any('outcome wording' in x for x in leaks), leaks)

    def test_the_twin_streams_are_equal_for_every_scripted_policy(self):
        eps = demo.run_all()
        self.assertEqual(demo.paired_identical(eps), {p: True for p in POLICIES_V5})

    def test_notice_text_and_errors_do_not_name_the_class(self):
        f = V5['s05-warned-delayed-10d']
        w = demo.factory(f)()
        t = ObservableRunnerV5(w).run(_seq([
            {'tool': 'release_production', 'arguments': {'quantity': 9}},        # over capacity
            {'tool': 'release_production', 'arguments': {'quantity': 4}},
            {'tool': 'release_production', 'arguments': {'quantity': 1}},        # second release
            {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite', 'quantity': 99}},
            {'tool': 'advance_day'}]))
        self.assertEqual(sum(1 for a in t['attempts'] if not a['accepted']), 3)
        for a in t['attempts']:
            if not a['accepted']:
                for word in dv5.OUTCOME_WORDS:
                    self.assertNotIn(word, (a['reason'] or '').lower())


def _seq(calls):
    it = iter(calls)
    return lambda view: next(it, None)


class AllEpisodesAgree(unittest.TestCase):
    """Five scenarios x five policies = 25 episodes: simulator, independent verifier and hand ledgers agree."""

    @classmethod
    def setUpClass(cls):
        cls.episodes = demo.run_all()
        cls.summary = demo.summarize(cls.episodes)

    def test_twenty_five_episodes(self):
        self.assertEqual(self.summary['episodes'], 25)
        self.assertEqual(sum(len(v) for v in self.episodes.values()), 25)

    def test_every_episode_agrees(self):
        for r in self.summary['rows']:
            self.assertTrue(r['verifier_feasible'], r)
            self.assertTrue(r['matches_hand_ledger'], r)
            self.assertTrue(r['replay_reproduced'], r)
            self.assertTrue(r['leak_scan_clean'], r)

    def test_verifier_ledger_equals_hand_work_directly(self):
        keys = ('received', 'produced', 'shipped', 'components_close', 'finished_close', 'delivered_total',
                'penalty_total', 'spend_total', 'cancelled_total')
        for fid, by in self.episodes.items():
            for p, ep in by.items():
                for k in keys:
                    self.assertEqual([r[k] for r in ep['report'].ledger], HAND5[fid][p]['ledger'][k], (fid, p, k))

    def test_v05_results_equal_v04_results_for_the_same_policy(self):
        """Same numbers and rules: every scorecard equals the v0.4 scorecard for the renamed scenario."""
        for fid, by in self.episodes.items():
            f4 = V4[fid.replace('s05-', 's04-')]
            for p, ep in by.items():
                w = OperationalWorldV4(f4['horizon_days'], scenario=ScenarioV4(**f4['scenario']))
                ObservableRunnerV4(w).run(scripted_policy_v4(p))
                self.assertEqual(ep['scorecard'], w.scorecard(), (fid, p))

    def test_summary_flags(self):
        s = self.summary
        self.assertTrue(s['all_verifier_feasible'] and s['all_match_hand_ledgers'] and s['all_replay_reproduced']
                        and s['all_leak_scans_clean'])
        self.assertEqual(s['paired_scenarios_identical_before_notice'], {p: True for p in POLICIES_V5})


class VerifierV5Tests(unittest.TestCase):
    def setUp(self):
        self.f = V5['s05-warned-delayed-10d']
        w = demo.factory(self.f)()
        self.t = ObservableRunnerV5(w).run(scripted_policy_v5('combo_on_alert'))
        self.h, self.card = w.history(), w.scorecard()

    def verify(self, scenario=None, history=None):
        return dv5.verify_episode(scenario or self.f['scenario'], history or self.h, horizon_days=self.f['horizon_days'],
                                  scorecard=self.card)

    def test_clean_episode_passes(self):
        self.assertTrue(self.verify().feasible)

    def test_descriptive_scenario_id_is_a_violation(self):
        bad = dict(self.f['scenario'], scenario_id='s05-warned-delayed-10d')
        self.assertIn('scenario_id_not_opaque', self.verify(bad).codes())

    def test_a_well_formed_but_wrong_label_is_a_violation(self):
        bad = dict(self.f['scenario'], scenario_id='scn-deadbeef')
        self.assertIn('scenario_id_mismatch', self.verify(bad).codes())

    def test_a_state_carrying_a_different_id_is_a_violation(self):
        h = deepcopy(self.h)
        h[3]['state']['scenario_id'] = 's05-warned-delayed-10d'
        self.assertIn('scenario_id_mismatch', self.verify(history=h).codes())

    def test_outcome_wording_anywhere_before_the_notice_is_a_leak(self):
        obs = demo.observations_of(self.t)
        self.assertEqual(dv5.check_observations_for_leaks(self.f['scenario'], obs), [])
        for place in ('reason', 'rules', 'text'):
            bad = deepcopy(obs)
            if place == 'reason':
                bad[0]['last_outcome'] = {'seq': 1, 'tool': 'x', 'accepted': False, 'category': 'x',
                                          'reason': 'refused because this is the delayed case'}
            elif place == 'rules':
                bad[0]['rules']['note'] = 'warned scenario'
            else:
                bad[0]['state']['signals'] = [{'day': 1, 'level': 'medium', 'text': 'Sudden event'}]
            self.assertTrue(dv5.check_observations_for_leaks(self.f['scenario'], bad), place)

    def test_wording_after_the_notice_is_allowed(self):
        obs = demo.observations_of(self.t)
        after = next(o for o in obs if o['state']['notices'])
        self.assertIn('delayed', after['state']['notices'][0]['text'].lower())
        self.assertEqual(dv5.check_observations_for_leaks(self.f['scenario'], [after]), [])

    def test_verifier_does_not_import_the_simulator(self):
        src = (ROOT / 'src/supplychainworld/dynamic_verifier_v5.py').read_text()
        names = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                names |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                names.add(('.' * node.level) + (node.module or '') + '|' + ','.join(a.name for a in node.names))
        self.assertEqual(names, {'hashlib', 'json', '.|dynamic_verifier_v4'})
        v4src = (ROOT / 'src/supplychainworld/dynamic_verifier_v4.py').read_text()
        v4names = set()
        for node in ast.walk(ast.parse(v4src)):
            if isinstance(node, ast.Import):
                v4names |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                v4names.add(('.' * node.level) + (node.module or ''))
        self.assertEqual(v4names, {'dataclasses'})      # the one verifier v5 builds on is itself independent

    def test_self_reported_pass_flags_are_still_ignored(self):
        h = deepcopy(self.h)
        for e in h:
            e['passed'] = True
        r = dv5.verify_episode(self.f['scenario'], h, horizon_days=self.f['horizon_days'], scorecard={**self.card, 'verified': True})
        self.assertTrue(r.ignored_self_reports)


if __name__ == '__main__':
    unittest.main()
