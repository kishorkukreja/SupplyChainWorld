"""S01 audit: browser tests (Playwright) for the generated report and timeline pages of v0.1 to v0.4.

The pages are generated FRESH into a temporary directory by the real demo scripts (not read from the committed
evidence), served from a local http.server and opened in Chromium. Assertions compare what a person sees with the
source JSON: visible title, the scorecard numbers, the per-metric blocks, the gate table and every timeline entry.
Any console error, uncaught page error or failed request fails the test. Screenshots are real captures saved under
test-output/browser/ (gitignored); one representative small image per version is committed by hand under
evidence/s01-audit/screenshots/.
"""
import html as htmllib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from support.browser import BrowserTestCase

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = {'v0.1': 'run_dynamic_demo.py', 'v0.2': 'run_dynamic_demo_v2.py', 'v0.3': 'run_dynamic_demo_v3.py',
           'v0.4': 'run_dynamic_demo_v4.py'}
DIRS = {'v0.1': 'v01', 'v0.2': 'v02', 'v0.3': 'v03', 'v0.4': 'v04'}
DEMOS = {'v0.2': 'dynamic_demo_v2', 'v0.3': 'dynamic_demo_v3', 'v0.4': 'dynamic_demo_v4'}


def run(cmd):
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'), PYTHONHASHSEED='0')
    done = subprocess.run([sys.executable, *cmd], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr


def attempt_line(a):
    """The timeline line the demo scripts print for one runner attempt."""
    args = ','.join(f'{k}={v}' for k, v in a['arguments'].items())
    verdict = 'accepted' if a['accepted'] else f"REJECTED ({a['reason']})"
    return f"#{a['seq']:02d} day {a['day']} agent calls {a['tool']}({args}) -> {verdict}"


def md_rows(text, heading):
    """Table rows (lists of cells) of the first markdown table after `heading` in `text`."""
    start = text.index(heading)
    rows = []
    for line in text[start:].splitlines()[1:]:
        if line.startswith('|'):
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if not set(''.join(cells)) <= set('-'):
                rows.append(cells)
        elif rows:
            break
    return rows


class GeneratedPages(BrowserTestCase):
    tmp = None

    @classmethod
    def serve_directory(cls):
        return cls.tmp

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='s01-pages-'))
        for tag, script in SCRIPTS.items():
            run([str(ROOT / 'scripts' / script), '--out', str(cls.tmp / DIRS[tag])])
        for tag in ('v0.2', 'v0.3', 'v0.4'):
            run([str(ROOT / 'scripts' / 'render_s01_timeline_html.py'), '--timeline', str(cls.tmp / DIRS[tag] / 'timeline.txt'),
                 '--out', str(cls.tmp / DIRS[tag] / 'timeline.html'), '--title', f'S01 {tag} timeline'])
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ---------------------------------------------------------------- helpers
    def data(self, tag, name):
        return json.loads((self.tmp / DIRS[tag] / name).read_text())

    def check_timeline(self, tag):
        transcripts = self.data(tag, 'transcripts.json')
        pre = self.page.locator('pre').first.text_content()
        lines = pre.splitlines()
        shown = [line for line in lines if line.startswith('#')]
        expected = []
        for fixture, policies in transcripts.items():
            for policy, t in policies.items():
                header = f"=== {fixture} / {policy} (horizon {t['horizon_days']} days, status {t['status']}) ==="
                self.assertIn(header, lines)
                expected += [attempt_line(a) for a in t['attempts']]
        self.assertEqual(shown, expected, 'timeline entries or their order differ from transcripts.json')
        return len(expected)

    # ---------------------------------------------------------------- v0.1
    def test_v01_report_scorecard_and_timeline_match_the_source_json(self):
        self.open('v01/report.html')
        self.assertEqual(self.page.title(), 'S01 demo packet')
        self.assertEqual(self.page.locator('h1').inner_text(), 'S01 supplier-delay demonstration packet')
        self.assertIn('No LLM, no practitioner review', self.page.locator('body').inner_text())
        rows = self.data('v0.1', 'scorecard.json')
        headers = [h.strip() for h in self.page.locator('table tr').first.locator('th').all_inner_texts()]
        self.assertEqual(headers, list(rows[0]))
        shown = [[c.strip() for c in tr.locator('td').all_inner_texts()] for tr in self.page.locator('table tr').all()[1:]]
        self.assertEqual(shown, [[str(r[h]) for h in headers] for r in rows])
        self.assertEqual(len(rows), 2 * 3)            # two horizons x three policies
        # The hand-worked acceptance numbers are visible: maintain 120, expedite 24, alternate 40 on the 5-day case.
        five = {r['policy']: r['comparison_cost'] for r in rows if r['fixture'] == 's01-five-day'}
        self.assertEqual(five, {'maintain': 120, 'expedite': 24, 'alternate': 40})
        gates = self.page.locator('pre').first.text_content()
        for g in ('G1', 'G2', 'G3', 'G4', 'G5', 'G6', 'G7', 'G8', 'G9'):
            self.assertIn(f'| {g} ', gates)
        self.assertIn('Partial', gates)               # G9 is never shown as passed
        self.assert_no_console_errors()

    def test_v01_timeline_page_lists_every_attempt_of_every_episode(self):
        self.open('v01/timeline.html')
        self.assertEqual(self.page.title(), 'S01 timeline')
        n = self.check_timeline('v0.1')
        self.assertGreater(n, 30)
        self.page.set_viewport_size({'width': 1000, 'height': 560})
        self.screenshot('s01-audit-v01-timeline', full_page=False)
        self.assert_no_console_errors()

    # ---------------------------------------------------------------- v0.2 to v0.4
    def check_report(self, tag):
        mod = importlib.import_module(f'supplychainworld.{DEMOS[tag]}')
        n = tag[-1]
        self.open(f'{DIRS[tag]}/report.html')
        self.assertEqual(self.page.title(), f'S01 v0.{n} packet')
        self.assertEqual(self.page.locator('h1').inner_text(), f'S01 v0.{n} family demonstration packet')
        banner = self.page.locator('p').first.inner_text()
        self.assertIn('PROVISIONAL', banner)
        self.assertIn('no LLM', banner)
        self.assertIn('reviewed: no', banner)
        comparison, gates = (self.page.locator('pre').nth(i).text_content() for i in (0, 1))
        self.assertEqual(comparison, (self.tmp / DIRS[tag] / 'comparison.md').read_text())
        full = self.data(tag, 'scorecard.json')['full_scorecards']
        comp = self.data(tag, 'comparison.json')
        blocks = 0
        for fid, per_metric in comp.items():
            rows = md_rows(comparison, f'## {fid}')
            header, body = rows[0], rows[1:]
            policies = header[3:-1]
            self.assertEqual(policies, list(full[fid]))
            self.assertEqual([r[0] for r in body], list(mod.METRICS), f'metric blocks of {fid}')
            for cells in body:
                metric = cells[0]
                path = mod.METRICS[metric][0]
                for policy, shown in zip(policies, cells[3:-1]):
                    value = full[fid][policy]
                    for key in path:
                        value = value[key]
                    self.assertEqual(shown, str(value), f'{fid} {policy} {metric}: page shows {shown}, scorecard says {value}')
                self.assertEqual(cells[-1], ', '.join(per_metric['metrics'][metric]['best_on_this_metric_alone']))
                blocks += 1
        self.assertEqual(blocks, len(comp) * len(mod.METRICS))
        # Gate table: nine gates, none shown as passed without evidence, G9 open.
        rows = md_rows(gates, '| Gate |')
        by_gate = {r[0].split()[0]: r[1] for r in rows}
        self.assertEqual(sorted(by_gate), [f'G{i}' for i in range(1, 10)])
        self.assertTrue(all(by_gate[f'G{i}'] == 'Evidence produced, unreviewed' for i in range(1, 9)), by_gate)
        self.assertTrue(by_gate['G9'].startswith('Partial'), by_gate['G9'])
        self.assertEqual(gates, (self.tmp / DIRS[tag] / 'gate-report.md').read_text())
        self.page.set_viewport_size({'width': 1000, 'height': 560})
        self.screenshot(f's01-audit-{DIRS[tag]}-report', full_page=False)
        self.assert_no_console_errors()

    def check_timeline_page(self, tag):
        self.open(f'{DIRS[tag]}/timeline.html')
        self.assertEqual(self.page.title(), f'S01 {tag} timeline')
        self.assertEqual(self.page.locator('h1').inner_text(), f'S01 {tag} timeline')
        self.assertGreater(self.check_timeline(tag), 100)
        self.assert_no_console_errors()

    def test_v02_report_per_metric_blocks_and_gates(self):
        self.check_report('v0.2')

    def test_v03_report_per_metric_blocks_and_gates(self):
        self.check_report('v0.3')

    def test_v04_report_per_metric_blocks_and_gates(self):
        self.check_report('v0.4')

    def test_v02_timeline_page(self):
        self.check_timeline_page('v0.2')

    def test_v03_timeline_page(self):
        self.check_timeline_page('v0.3')

    def test_v04_timeline_page(self):
        self.check_timeline_page('v0.4')

    def test_v04_report_shows_the_net_cost_comparison_against_v03(self):
        self.open('v04/report.html')
        text = self.page.locator('pre').first.text_content()
        comp = self.data('v0.4', 'comparison.json')
        for fid, data in comp.items():
            m = data['metrics']['net_cost']
            row = '| net_cost | ' + ' | '.join([m['dimension'], m['better']] + [str(v) for v in m['values'].values()])
            self.assertIn(row, text)
        self.assertIn('No overall winner is declared', text)
        self.assert_no_console_errors()

    def test_the_page_shows_no_overall_winner_and_marks_values_provisional_on_every_version(self):
        for tag in ('v0.2', 'v0.3', 'v0.4'):
            self.open(f'{DIRS[tag]}/report.html')
            body = self.page.locator('body').inner_text()
            self.assertIn('PROVISIONAL', body)
            self.assertIn('No overall winner is declared', body)
            self.assertNotRegex(body.lower(), r'overall winner is [a-z_]+_on_alert')
        self.assert_no_console_errors()


if __name__ == '__main__':
    unittest.main()
