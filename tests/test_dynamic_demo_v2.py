import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from supplychainworld import dynamic_demo_v2 as demo
from supplychainworld.agent_runner_v2 import POLICIES_V2

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

    def test_four_scenarios_five_policies_and_both_horizons(self):
        self.assertEqual(set(self.packet['episodes']), {'s02-sudden-5d', 's02-warned-delayed-10d',
                                                        's02-warned-no-delay-10d', 's02-multitier-cancel-10d'})
        for eps in self.packet['episodes'].values():
            self.assertEqual(list(eps), list(POLICIES_V2))
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
        leaked = [t for ep in self.packet['episodes']['s02-warned-delayed-10d'].values() for t in ep['tamper']
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
        no_delay = c['s02-warned-no-delay-10d']['metrics']['net_cost']
        self.assertEqual(no_delay['best_on_this_metric_alone'], ['maintain'])
        delayed = c['s02-warned-delayed-10d']['metrics']['net_cost']
        self.assertNotIn('maintain', delayed['best_on_this_metric_alone'])
        tier = c['s02-multitier-cancel-10d']['metrics']['cancelled_order_value']
        self.assertEqual(tier['best_on_this_metric_alone'], ['alternate_on_alert', 'combo_on_alert'])

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

    def test_warned_pair_is_observation_identical_until_the_firm_notice(self):
        self.assertTrue(all(self.packet['paired_signal_identical'].values()))
        a = self.packet['episodes']['s02-warned-delayed-10d']['maintain']['transcript']
        b = self.packet['episodes']['s02-warned-no-delay-10d']['maintain']['transcript']
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
            r = subprocess.run([sys.executable, str(ROOT / 'scripts/run_dynamic_demo_v2.py'), '--out', d],
                               capture_output=True, text=True, env={'PYTHONPATH': str(ROOT / 'src'), 'PATH': ''})
            self.assertEqual(r.returncode, 0, r.stderr)
            names = {p.name for p in Path(d).iterdir()}
            for needed in ('timeline.txt', 'scorecard.md', 'comparison.md', 'checks.json', 'replay.json', 'replay.log',
                           'experience-record.json', 'gate-report.md', 'transcripts.json', 'state-ledger.csv'):
                self.assertIn(needed, names)
            self.assertIn('PROVISIONAL', (Path(d) / 'gate-report.md').read_text())
            self.assertIn('No overall winner', (Path(d) / 'comparison.md').read_text())


class V01UntouchedTests(unittest.TestCase):
    def test_v01_fixture_and_evidence_files_still_exist(self):
        for rel in ('fixtures/dynamic/supplier-delay-inputs.json', 'fixtures/dynamic/verifier-hand-ledgers.json',
                    'evidence/issue-26/gate-report.md', 'src/supplychainworld/dynamic.py'):
            self.assertTrue((ROOT / rel).exists(), rel)


if __name__ == '__main__':
    unittest.main()
