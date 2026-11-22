"""S01 v0.6: browser tests (Playwright) for the generated report page.

The page is generated FRESH into a temporary directory by the real demo script (`scripts/run_dynamic_demo_v6.py`), served from
a local http.server and opened in Chromium. A second test opens the COMMITTED page `evidence/s01-v06/report.html` the same way.
Assertions compare what a person sees (titles, scorecard numbers, per-metric blocks, conventions, experience record, gate table,
every timeline entry) with the source JSON next to the page. Any console error, uncaught page error or failed request fails the
test. Screenshots are real captures: they go to test-output/browser/ (gitignored); with SCW_EVIDENCE_SCREENSHOTS=1 the committed
page's capture is also saved under evidence/s01-v06/screenshots/ (it was viewed to confirm the page renders).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import support  # noqa: F401
from support.browser import BrowserTestCase

ROOT = Path(__file__).resolve().parents[1]
GATES = [f'G{i}' for i in range(1, 10)]


def run_script(out):
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'), PYTHONHASHSEED='0')
    done = subprocess.run([sys.executable, str(ROOT / 'scripts/run_dynamic_demo_v6.py'), '--out', str(out)], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr


def attempt_line(a):
    args = ','.join(f'{k}={v}' for k, v in a['arguments'].items())
    verdict = 'accepted' if a['accepted'] else f"REJECTED ({a['reason']})"
    return f"#{a['seq']:02d} day {a['day']} agent calls {a['tool']}({args}) -> {verdict}"


class ReportPage(BrowserTestCase):
    tmp = None

    @classmethod
    def serve_directory(cls):
        return cls.tmp

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='s01-v06-page-'))
        run_script(cls.tmp / 'fresh')
        shutil.copytree(ROOT / 'evidence/s01-v06', cls.tmp / 'committed')
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def data(self, which, name):
        return json.loads((self.tmp / which / name).read_text())

    def table_rows(self, selector):
        table = self.page.locator(selector)
        headers = [h.strip() for h in table.locator('thead th').all_inner_texts()]
        rows = [[c.strip() for c in tr.locator('td').all_inner_texts()] for tr in table.locator('tbody tr').all()]
        return headers, rows

    # ------------------------------------------------------------------ the checks, run on both pages
    def check_page(self, which):
        self.open(f'{which}/report.html')
        self.assertEqual(self.page.title(), 'S01 v0.6 packet')
        self.assertEqual(self.page.locator('h1').inner_text(), 'S01 v0.6 family demonstration packet')
        banner = self.page.locator('#banner').inner_text()
        for word in ('PROVISIONAL', 'no LLM', 'practitioner review: none'):
            self.assertIn(word, banner)
        self.assertIn('No overall winner is declared', self.page.locator('#no-winner').inner_text())

        # scorecards
        flat = self.data(which, 'scorecard.json')['flat']
        headers, rows = self.table_rows('#scorecard-table')
        self.assertEqual(headers, list(flat[0]))
        self.assertEqual(rows, [[str(r[h]) for h in headers] for r in flat])
        self.assertEqual(len(rows), 25)

        # per-metric blocks
        comp = self.data(which, 'comparison.json')
        full = self.data(which, 'scorecard.json')['full_scorecards']
        blocks = self.page.locator('.metric-block')
        self.assertEqual(blocks.count(), 5)
        shown_metrics = 0
        for i, (fid, c) in enumerate(comp.items()):
            block = blocks.nth(i)
            self.assertEqual(block.get_attribute('data-fixture'), fid)
            self.assertEqual(block.locator('h3').inner_text(), fid)
            policies = list(full[fid])
            heads = [h.strip() for h in block.locator('thead th').all_inner_texts()]
            self.assertEqual(heads, ['metric', 'dimension', 'better', *policies, 'best here'])
            body = [[x.strip() for x in tr.locator('td').all_inner_texts()] for tr in block.locator('tbody tr').all()]
            self.assertEqual([r[0] for r in body], list(c['metrics']))
            for cells in body:
                m = c['metrics'][cells[0]]
                self.assertEqual(cells[3:-1], [str(m['values'][p]) for p in policies], f'{fid} {cells[0]}')
                self.assertEqual(cells[-1], ', '.join(m['best_on_this_metric_alone']))
                shown_metrics += 1
        self.assertEqual(shown_metrics, 5 * 13)

        # conventions the agent is told
        statements = self.data(which, 'transcripts.json')['s06-sudden-5d']['maintain']['initial']['view']['rules']['conventions']['statements']
        items = [li.strip() for li in self.page.locator('ul.conv li').all_inner_texts()]
        self.assertEqual(items, [f'{k}: {v}' for k, v in statements.items()])

        # experience record: the page shows the committed markdown, and says what the readability check is
        record = (self.tmp / which / 'experience-record.md').read_text()
        self.assertEqual(self.page.locator('#experience-plain').text_content(), record)
        note = self.page.locator('#readability').inner_text()
        self.assertIn('no problems found', note)
        self.assertIn('does not show that a person finds the record readable', note)

        # checks per episode
        headers, rows = self.table_rows('#checks-table')
        self.assertEqual(len(rows), 25)
        for row in rows:
            self.assertEqual(row[2:], ['True'] * 5, row)

        # gates
        headers, rows = self.table_rows('#gates-table')
        self.assertEqual([r[0].split()[0] for r in rows], GATES)
        self.assertTrue(all(r[1] == 'Evidence produced, unreviewed' for r in rows[:8]), rows)
        self.assertTrue(rows[8][1].startswith('Partial'), rows[8])

        # timeline: every entry of every episode, in order
        transcripts = self.data(which, 'transcripts.json')
        details = self.page.locator('details[data-fixture]')
        self.assertEqual(details.count(), 25)
        i = total = 0
        for fid, per_policy in transcripts.items():
            for policy, t in per_policy.items():
                d = details.nth(i)
                i += 1
                self.assertEqual(d.get_attribute('data-fixture'), fid)
                self.assertEqual(d.get_attribute('data-policy'), policy)
                self.assertEqual(d.locator('summary').inner_text(),
                                 f"=== {fid} / {policy} (horizon {t['horizon_days']} days, status {t['status']}) ===")
                want = [attempt_line(a) for a in t['attempts']]
                got = [x.strip() for x in d.locator('li.attempt').all_text_contents()]
                self.assertEqual(got, want, f'{fid} {policy}')
                total += len(want)
        self.assertGreater(total, 400)
        self.assertEqual(self.page.locator('li.attempt').count(), total)
        self.assert_no_console_errors()

    def test_the_freshly_generated_page_matches_its_source_json(self):
        self.check_page('fresh')

    def test_the_committed_page_matches_its_source_json_and_is_saved_as_a_screenshot(self):
        self.check_page('committed')
        self.page.set_viewport_size({'width': 1200, 'height': 900})
        self.page.goto(f'{self._server.base_url}/committed/report.html')
        path = self.screenshot('s01-v06-report', full_page=False)
        if os.environ.get('SCW_EVIDENCE_SCREENSHOTS'):
            target = ROOT / 'evidence/s01-v06/screenshots'
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy(path, target / 's01-v06-report.png')
        self.assert_no_console_errors()

    def test_the_page_fits_a_phone_width_without_sideways_scrolling_and_follows_the_colour_scheme(self):
        self.page.set_viewport_size({'width': 390, 'height': 800})
        self.open('fresh/report.html')
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), 390)
        self.assertGreater(self.page.locator('#scorecard-table').evaluate('t => t.scrollWidth'), 390)   # scrolls inside its box
        self.page.emulate_media(color_scheme='dark')
        dark = self.page.evaluate('getComputedStyle(document.body).backgroundColor')
        self.page.emulate_media(color_scheme='light')
        light = self.page.evaluate('getComputedStyle(document.body).backgroundColor')
        self.assertNotEqual(dark, light)
        self.assert_no_console_errors()

    def test_the_page_loads_nothing_from_outside_and_runs_no_script(self):
        text = (self.tmp / 'fresh/report.html').read_text().lower()
        self.assertNotIn('<script', text)
        self.assertNotIn('http://', text)
        self.assertNotIn('https://', text)


if __name__ == '__main__':
    unittest.main()
