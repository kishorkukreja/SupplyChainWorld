"""Browser tests: the generated S01 report pages show what the data says.

Opens the committed evidence pages in real Chromium (served from a local
http.server), compares what a person sees with the JSON they were generated
from, checks for console errors and saves real screenshots under
test-output/browser/ (gitignored).
"""
import json
import unittest
from pathlib import Path

from support.browser import BrowserTestCase

ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / 'evidence' / 'issue-26'
V04 = ROOT / 'evidence' / 'issue-36-v04'


def attempt_line(a):
    """The timeline line the generator prints for one runner attempt."""
    args = ', '.join(f'{k}={v}' for k, v in a['arguments'].items())
    outcome = 'accepted' if a['accepted'] else 'rejected'
    return f"#{a['seq']:02d} day {a['day']} agent calls {a['tool']}({args}) -> {outcome}"


@unittest.skipUnless(V26.joinpath('report.html').exists(), 'issue-26 evidence not present')
class Issue26Report(BrowserTestCase):
    def test_report_title_scorecard_and_timeline_match_the_data(self):
        self.open('issue-26/report.html')
        self.assertEqual(self.page.title(), 'S01 demo packet')
        self.assertEqual(self.page.locator('h1').inner_text(), 'S01 supplier-delay demonstration packet')
        self.assertIn('No LLM, no practitioner review', self.page.locator('body').inner_text())

        # Scorecard table: every row and every number equals scorecard.json.
        rows = json.loads((V26 / 'scorecard.json').read_text())
        headers = [h.strip() for h in self.page.locator('table tr').first.locator('th').all_inner_texts()]
        self.assertEqual(headers, list(rows[0]))
        shown = [[c.strip() for c in tr.locator('td').all_inner_texts()]
                 for tr in self.page.locator('table tr').all()[1:]]
        self.assertEqual(shown, [[str(r[h]) for h in headers] for r in rows])

        # Timeline excerpt (5-day expedite episode) lists each recorded attempt.
        transcripts = json.loads((V26 / 'transcripts.json').read_text())
        timeline = self.page.locator('pre').last.inner_text()
        for a in transcripts['s01-five-day']['expedite']['attempts']:
            self.assertIn(attempt_line(a), timeline)
        self.screenshot('issue-26-report')
        self.assert_no_console_errors()

    def test_timeline_page_lists_every_attempt_of_every_episode(self):
        self.open('issue-26/timeline.html')
        self.assertEqual(self.page.title(), 'S01 timeline')
        lines = self.page.locator('pre').inner_text().splitlines()
        shown = [l for l in lines if l.startswith('#')]
        expected = []
        for fixture, policies in json.loads((V26 / 'transcripts.json').read_text()).items():
            for policy, transcript in policies.items():
                self.assertIn(f'=== {fixture} / {policy} (horizon {transcript["horizon_days"]} days, '
                              f'status {transcript["status"]}) ===', lines)
                expected += [attempt_line(a) for a in transcript['attempts']]
        self.assertEqual(shown, expected)    # same entries, same chronological order
        self.screenshot('issue-26-timeline')
        self.assert_no_console_errors()


@unittest.skipUnless(V04.joinpath('report.html').exists(), 'issue-36-v04 evidence not present')
class V04Report(BrowserTestCase):
    def test_v04_report_shows_provisional_banner_and_comparison_numbers(self):
        self.open('issue-36-v04/report.html')
        self.assertEqual(self.page.title(), 'S01 v0.4 packet')
        self.assertEqual(self.page.locator('h1').inner_text(), 'S01 v0.4 family demonstration packet')
        self.assertIn('ALL NUMBERS PROVISIONAL, needs practitioner value',
                      self.page.locator('p').first.inner_text())
        text = self.page.locator('pre').first.inner_text()
        comparison = json.loads((V04 / 'comparison.json').read_text())
        for scenario, data in comparison.items():
            self.assertIn(f'## {scenario}', text)
            m = data['metrics']['net_cost']
            row = '| net_cost | ' + ' | '.join([m['dimension'], m['better']] + [str(v) for v in m['values'].values()])
            self.assertIn(row, text, f'net_cost row for {scenario} differs from comparison.json')
        self.screenshot('issue-36-v04-report')
        self.assert_no_console_errors()


if __name__ == '__main__':
    unittest.main()
