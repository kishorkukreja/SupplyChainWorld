import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from supplychainworld import dynamic_demo_v4 as demo
from supplychainworld.agent_runner_v4 import POLICIES_V4

ROOT = Path(__file__).resolve().parents[1]


class PacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet = demo.build_packet()

    def test_every_gate_with_evidence_passes_and_review_gate_stays_open(self):
        g = self.packet['gates']
        for k in ('G1', 'G2', 'G3', 'G4', 'G5', 'G6', 'G7', 'G8'):
            self.assertTrue(g[k]['pass'], (k, g[k]))
        self.assertIsNone(g['G9']['pass'])

    def test_five_scenarios_five_policies_and_both_horizons(self):
        self.assertEqual(set(self.packet['episodes']), {'s04-sudden-5d', 's04-warned-delayed-10d',
                                                        's04-warned-no-delay-10d', 's04-multitier-cancel-10d',
                                                        's04-alt-cheaper-10d'})
        for eps in self.packet['episodes'].values():
            self.assertEqual(list(eps), list(POLICIES_V4))
        self.assertEqual({f['horizon_days'] for f in self.packet['fixtures']}, {5, 10})
        self.assertEqual({f['disruption_class'] for f in self.packet['fixtures']}, {'sudden', 'warned'})

    def test_every_episode_is_feasible_hand_matched_replayed_and_corruption_rejected(self):
        for fid, eps in self.packet['episodes'].items():
            for p, ep in eps.items():
                self.assertTrue(ep['report'].feasible, (fid, p))
                self.assertEqual(ep['hand'], {'ledger': True, 'metrics': True, 'tiers': True}, (fid, p))
                self.assertTrue(ep['replay']['transcript_reproduced'] and ep['replay']['state_sequence_identical'])
                self.assertTrue(all(t['rejected_as_expected'] for t in ep['tamper']), (fid, p))
                names = {t['case'] for t in ep['tamper']}
                for needed in ('duplicate commitment (same commit_id executed twice)', 'over-budget combined recovery',
                               'premature receipt', 'wrong penalty claimed'):
                    self.assertIn(needed, names)
        leaked = [t for ep in self.packet['episodes']['s04-warned-delayed-10d'].values() for t in ep['tamper']
                  if 'leaks the outcome' in t['case']]
        self.assertEqual(len(leaked), 10)

    def test_no_overall_winner_and_trade_offs_are_flagged(self):
        for fid, c in self.packet['comparison'].items():
            self.assertEqual(c['best_on_every_metric'], [], fid)
            self.assertIn('No overall winner', c['trade_offs'])
            dims = {row['dimension'] for row in c['metrics'].values()}
            self.assertEqual(dims, {'cost', 'service', 'tier impact', 'downstream impact', 'supply risk'})
            self.assertNotIn('winner', json.dumps(c['metrics']).lower())

    def test_policies_differ_per_metric_in_the_expected_places(self):
        c = self.packet['comparison']
        no_delay = c['s04-warned-no-delay-10d']['metrics']['net_cost']
        self.assertEqual(no_delay['best_on_this_metric_alone'], ['maintain'])
        # Under the v0.4 premium-only numbers a full alternate buy (USD 24) is cheaper than the delay penalty (USD 30)
        # in the warned and delayed scenario, but maintain stays cheapest when the delay never comes.
        delayed = c['s04-warned-delayed-10d']['metrics']
        self.assertEqual(delayed['net_cost']['best_on_this_metric_alone'], ['alternate_on_alert'])
        self.assertNotIn('maintain', delayed['otif_orders_met']['best_on_this_metric_alone'])
        tier = c['s04-multitier-cancel-10d']['metrics']['cancelled_order_value']
        self.assertEqual(tier['best_on_this_metric_alone'], ['alternate_on_alert', 'combo_on_alert'])

    def test_cheapest_recovery_by_metric_under_the_v04_numbers(self):
        c = self.packet['comparison']
        net = {fid: m['metrics']['net_cost']['best_on_this_metric_alone'] for fid, m in c.items()}
        self.assertEqual(net, {'s04-sudden-5d': ['maintain'], 's04-warned-delayed-10d': ['alternate_on_alert'],
                               's04-warned-no-delay-10d': ['maintain'], 's04-multitier-cancel-10d': ['combo_on_alert'],
                               's04-alt-cheaper-10d': ['alternate_on_alert']})
        for fid, m in c.items():
            v = m['metrics']['recovery_spend']['values']
            self.assertLess(v['alternate_on_alert'], v['expedite_on_alert'], fid)        # premium 3 versus 4 a unit
            self.assertEqual(m['metrics']['recovery_spend']['best_on_this_metric_alone'], ['maintain'], fid)
        # The scenario built so that alternate beats expedite: lower net cost and fewer late unit-days.
        alt = c['s04-alt-cheaper-10d']['metrics']
        self.assertLess(alt['net_cost']['values']['alternate_on_alert'], alt['net_cost']['values']['expedite_on_alert'])
        self.assertEqual(alt['unit_days_late']['best_on_this_metric_alone'], ['alternate_on_alert'])

    def test_findings_say_which_recovery_is_cheapest_and_how_often_maintain_wins_without_a_winner(self):
        f = self.packet['cost_findings']
        for fid, row in f.items():
            self.assertEqual(row['cheaper_of_expedite_vs_alternate_on_recovery_spend'], ['alternate_on_alert'], fid)
            self.assertEqual(row['cheaper_of_expedite_vs_alternate_on_net_cost'], ['alternate_on_alert'], fid)
        self.assertEqual([fid for fid, r in f.items() if r['maintain_wins_net_cost']],
                         ['s04-sudden-5d', 's04-warned-no-delay-10d'])

    def test_v03_net_costs_are_read_from_the_committed_v03_evidence(self):
        v3 = self.packet['v03_net_cost']
        self.assertEqual(set(v3), set(self.packet['episodes']))
        self.assertEqual(v3['s04-sudden-5d']['alternate_on_alert'], 56)      # v0.3 whole-price basis with salvage
        self.assertEqual(v3['s04-alt-cheaper-10d']['alternate_on_alert'], 62)

    def test_no_policy_earns_salvage_on_alternate_bought_surplus_in_any_episode(self):
        for fid, eps in self.packet['episodes'].items():
            for p, ep in eps.items():
                cost = ep['scorecard']['cost']
                if p in ('maintain', 'expedite_on_alert', 'staged_revisit'):
                    self.assertEqual(cost['uncredited_alternate_surplus'], 0, (fid, p))
                self.assertLessEqual(cost['salvage_credit'], eps['maintain']['scorecard']['cost']['salvage_credit'], (fid, p))

    def test_experience_record_has_no_private_answers_and_one_policy(self):
        rec = self.packet['experience']
        self.assertEqual(self.packet['experience_leaks'], [])
        self.assertEqual(self.packet['all_episode_leaks'], {})
        self.assertIn('not an LLM', rec['agent'])
        self.assertIn('PROVISIONAL', rec['values_status'])
        fixture = next(f for f in self.packet['fixtures'] if f['fixture_id'] == rec['scenario_id'])
        text = json.dumps(rec)
        for hidden in ('delayed_arrival_day', 'delay_outcome', 'hand_ledger', 'comparison_by_policy'):
            self.assertNotIn(hidden, text)
        bad = json.loads(text)
        bad['initial_observation']['rules']['delay_outcome'] = 'delay'
        self.assertTrue(demo.find_private_leaks(bad, fixture['scenario']))
        bad = json.loads(text)
        bad['initial_observation']['state']['signals'][0]['level'] = 'high'
        self.assertTrue(demo.find_private_leaks(bad, fixture['scenario']))

    def test_warned_pair_is_observation_identical_until_the_firm_notice(self):
        self.assertTrue(all(self.packet['paired_signal_identical'].values()))
        a = self.packet['episodes']['s04-warned-delayed-10d']['maintain']['transcript']
        b = self.packet['episodes']['s04-warned-no-delay-10d']['maintain']['transcript']
        self.assertNotEqual(a['final_state'], b['final_state'])

    def test_packet_is_deterministic(self):
        again = demo.build_packet()
        for fid, eps in self.packet['episodes'].items():
            for p, ep in eps.items():
                self.assertEqual(ep['scorecard'], again['episodes'][fid][p]['scorecard'])
                self.assertEqual(ep['history'], again['episodes'][fid][p]['history'])


class ScriptTests(unittest.TestCase):
    def test_script_writes_the_evidence_packet(self):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, str(ROOT / 'scripts/run_dynamic_demo_v4.py'), '--out', d],
                               capture_output=True, text=True, env={'PYTHONPATH': str(ROOT / 'src'), 'PATH': ''})
            self.assertEqual(r.returncode, 0, r.stderr)
            names = {p.name for p in Path(d).iterdir()}
            for needed in ('timeline.txt', 'scorecard.md', 'comparison.md', 'checks.json', 'replay.json', 'replay.log',
                           'experience-record.json', 'gate-report.md', 'transcripts.json', 'state-ledger.csv'):
                self.assertIn(needed, names)
            self.assertIn('PROVISIONAL', (Path(d) / 'gate-report.md').read_text())
            text = (Path(d) / 'comparison.md').read_text()
            self.assertIn('No overall winner', text)
            self.assertIn('Changed from v0.3', text)
            self.assertIn('UNRESOLVED ASSUMPTION', text)
            self.assertIn('Maintain has the lowest net cost in 2 of 5 scenarios', text)


class HandLedgerGeneratorTests(unittest.TestCase):
    def test_committed_hand_ledgers_are_what_the_generator_script_produces(self):
        r = subprocess.run([sys.executable, str(ROOT / 'scripts/generate_hand_ledgers_v04.py'), '--check'],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_generator_imports_no_project_code(self):
        tree = ast.parse((ROOT / 'scripts/generate_hand_ledgers_v04.py').read_text())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module)
        self.assertEqual(names, {'json', 'sys', 'pathlib'})

    def test_hand_ledgers_cover_every_scenario_and_policy(self):
        hand = demo.load_hand()
        self.assertEqual(set(hand), {f['fixture_id'] for f in demo.load_fixtures()})
        for pols in hand.values():
            self.assertEqual(list(pols), list(POLICIES_V4))


class EarlierVersionsUntouchedTests(unittest.TestCase):
    def test_v01_and_v02_files_still_exist(self):
        for rel in ('fixtures/dynamic/supplier-delay-inputs.json', 'fixtures/dynamic/verifier-hand-ledgers.json',
                    'evidence/issue-26/gate-report.md', 'src/supplychainworld/dynamic.py',
                    'fixtures/dynamic/v0.2/scenarios.json', 'fixtures/dynamic/v0.2/hand-ledgers.json',
                    'evidence/issue-36/results.md', 'src/supplychainworld/dynamic_v2.py',
                    'src/supplychainworld/dynamic_verifier_v2.py',
                    'fixtures/dynamic/v0.3/scenarios.json', 'fixtures/dynamic/v0.3/hand-ledgers.json',
                    'evidence/issue-36-v03/results.md', 'src/supplychainworld/dynamic_v3.py',
                    'src/supplychainworld/dynamic_verifier_v3.py', 'scripts/generate_hand_ledgers_v03.py'):
            self.assertTrue((ROOT / rel).exists(), rel)

    def test_v04_modules_reuse_nothing_from_v02_data(self):
        for rel in ('src/supplychainworld/dynamic_v4.py', 'src/supplychainworld/dynamic_verifier_v4.py',
                    'src/supplychainworld/dynamic_demo_v4.py', 'src/supplychainworld/agent_runner_v4.py'):
            self.assertNotIn('_v2 import', (ROOT / rel).read_text(), rel)
            self.assertNotIn('dynamic/v0.2', (ROOT / rel).read_text(), rel)


if __name__ == '__main__':
    unittest.main()
