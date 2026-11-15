import importlib.util
import json
import tempfile
from copy import deepcopy
from pathlib import Path
import unittest

from supplychainworld.dynamic_demo import (EXPERIENCE_FIXTURE, FORBIDDEN_KEYS, POLICIES, build_packet,
                                           find_private_leaks)

ROOT = Path(__file__).resolve().parents[1]
PACKET = build_packet()


def load_script():
    spec = importlib.util.spec_from_file_location('run_dynamic_demo', ROOT / 'scripts/run_dynamic_demo.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PacketTests(unittest.TestCase):
    def test_both_horizons_and_all_policies_run(self):
        self.assertEqual(set(PACKET['episodes']), {'s01-five-day', 's01-fifteen-day-late-events'})
        for runs in PACKET['episodes'].values():
            self.assertEqual(tuple(runs), POLICIES)
            for ep in runs.values():
                self.assertEqual(ep['transcript']['status'], 'complete')

    def test_costs_match_hand_worked_tables(self):
        costs = {fid: {p: ep['scorecard']['comparison_cost'] for p, ep in runs.items()}
                 for fid, runs in PACKET['episodes'].items()}
        self.assertEqual(costs['s01-five-day'], {'maintain': 120, 'expedite': 24, 'alternate': 40})
        self.assertEqual(costs['s01-fifteen-day-late-events'], {'maintain': 200, 'expedite': 24, 'alternate': 40})

    def test_gates_g1_to_g8_pass_and_g9_is_not_claimed(self):
        for k in ('G1', 'G2', 'G3', 'G4', 'G5', 'G6', 'G7', 'G8'):
            self.assertTrue(PACKET['gates'][k]['pass'], k)
        self.assertIsNone(PACKET['gates']['G9']['pass'])

    def test_replay_and_independent_check_for_every_episode(self):
        for runs in PACKET['episodes'].values():
            for ep in runs.values():
                self.assertTrue(ep['report'].feasible)
                self.assertTrue(ep['replay']['transcript_reproduced'])
                self.assertTrue(ep['replay']['state_sequence_identical'])
                self.assertTrue(all(t['rejected_as_expected'] for t in ep['tamper']))

    def test_packet_is_deterministic(self):
        again = build_packet()
        for fid, runs in PACKET['episodes'].items():
            for p, ep in runs.items():
                self.assertEqual(ep['transcript'], again['episodes'][fid][p]['transcript'])
        self.assertEqual(PACKET['experience'], again['experience'])

    def test_rejections_leave_state_unchanged(self):
        for p in PACKET['probes']:
            self.assertGreaterEqual(p['rejected_count'], 2)
            self.assertTrue(p['rejections_left_state_unchanged'])


class NoLeakTests(unittest.TestCase):
    fixture = next(f for f in PACKET['fixtures'] if f['fixture_id'] == EXPERIENCE_FIXTURE)

    def test_experience_record_has_no_private_answers(self):
        self.assertEqual(find_private_leaks(PACKET['experience'], self.fixture['scenario']), [])
        text = json.dumps(PACKET['experience']).lower()
        for key in FORBIDDEN_KEYS:
            self.assertNotIn(f'"{key}"', text)
        for hidden in ('backlog_on_assessment', 'event_days', 'verifier', 'maintain_primary_receipt'):
            self.assertNotIn(hidden, text)

    def test_policies_other_than_the_recorded_one_are_absent(self):
        recoveries = {s['action']['arguments']['choice'] for s in PACKET['experience']['steps']
                      if s['action']['tool'] == 'commit_recovery'}
        self.assertEqual(recoveries, {'expedite'})
        self.assertNotIn('200', {str(v) for v in PACKET['experience']['final_scorecard'].values()})

    def test_nothing_about_the_delay_is_visible_before_the_notice(self):
        rec = PACKET['experience']
        pre = [s for s in rec['steps'] if not s['observation']['state']['notices']]
        self.assertTrue(pre)
        for s in pre:
            self.assertNotIn('recovery_offers', s['observation']['rules'])
            self.assertEqual(s['observation']['state']['primary_arrival_day'], self.fixture['scenario']['initially_promised_day'])

    def test_scanner_detects_planted_leaks(self):
        bad = deepcopy(PACKET['experience'])
        bad['expected_cost'] = 24
        self.assertTrue(find_private_leaks(bad, self.fixture['scenario']))
        bad = deepcopy(PACKET['experience'])
        bad['steps'][0]['observation']['rules']['recovery_offers'] = {'deadline_day': 6}
        self.assertTrue(find_private_leaks(bad, self.fixture['scenario']))
        bad = deepcopy(PACKET['experience'])
        bad['steps'][0]['observation']['state']['primary_arrival_day'] = 12
        self.assertTrue(find_private_leaks(bad, self.fixture['scenario']))


class ScriptTests(unittest.TestCase):
    def test_script_writes_the_evidence_files(self):
        mod = load_script()
        with tempfile.TemporaryDirectory() as d:
            import sys
            old = sys.argv
            sys.argv = ['run_dynamic_demo.py', '--out', d]
            try:
                mod.main()
            finally:
                sys.argv = old
            names = {p.name for p in Path(d).iterdir()}
            for n in ('timeline.txt', 'timeline.html', 'state-ledger.csv', 'scorecard.json', 'checks.json',
                      'replay.json', 'replay.log', 'experience-record.json', 'gate-report.md', 'transcripts.json'):
                self.assertIn(n, names)
            report = (Path(d) / 'gate-report.md').read_text()
            self.assertIn('Practitioner-reviewed: nothing', report)
            self.assertIn('No model ability', report)


if __name__ == '__main__':
    unittest.main()
