"""End-to-end: the eval19-3 run through the real script entry points, adapters, guards, runner, independent checker and replay,
with mocked provider transports at the network edge. No network, no key. Also tests the refusals of the live script."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import support  # noqa: F401
from support.eval19_run_fixtures import KEY, full_plan, mock_routes, small_plan
from support.tracing_fixtures import FakeClient

import test_eval19_v2 as t2
from supplychainworld import eval19_v3_run as er
from supplychainworld import sarvam_adapter as sa

ROOT = Path(__file__).resolve().parents[1]


def run_plan(plan, state, routes, **kw):
    kw.setdefault('keys', {'sarvam': KEY})
    return er.run(plan, state, routes, sleep=lambda s: None, min_interval=0.0, out=lambda *_: None, **kw)


def records(state):
    return {p.name: json.loads(p.read_text()) for p in sorted((Path(state) / 's01').glob('*.json'))}


class FullRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.routes = mock_routes()
        cls.plan = full_plan()
        cls.summary = run_plan(cls.plan, cls.tmp.name, cls.routes)
        cls.recs = records(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_all_sixty_episodes_run_complete_feasible_replayed_and_leak_free(self):
        self.assertEqual(len(self.recs), 60)
        for name, r in self.recs.items():
            self.assertNotIn('not_run', r, name)
            g = r['grade']
            self.assertEqual(g['status'], 'complete', name)
            self.assertTrue(g['verifier_feasible'] and g['replay_reproduced'], name)
            self.assertEqual(g['observation_leaks'], [], name)

    def test_each_model_gets_every_scenario_twice(self):
        counts = {}
        for r in self.recs.values():
            counts[(r['model'], r['fixture_id'])] = counts.get((r['model'], r['fixture_id']), 0) + 1
        self.assertEqual(len(counts), 6 * 5)
        self.assertTrue(all(v == 2 for v in counts.values()))

    def test_sarvam_spend_is_positive_below_the_cap_and_openrouter_is_free(self):
        self.assertGreater(self.summary['sarvam_inr_spent_total'], 0)
        self.assertLessEqual(self.summary['sarvam_inr_spent_total'], sa.CAP_INR)
        for r in self.recs.values():
            if r['provider'] == 'openrouter':
                self.assertEqual(r['manifest_sha256'] and r['telemetry']['cost_usd'], 0, r['model'])
                self.assertIsNone(r['sarvam_inr_this_episode'])
            else:
                self.assertGreater(r['sarvam_inr_this_episode'], 0)

    def test_every_route_only_saw_its_own_models(self):
        seen = {p: {json.loads(b)['model'] for b in routes.bodies} for p, routes in self.routes.items()}
        self.assertEqual(seen['openrouter'], {m['id'] for m in self.plan['models'] if m['provider'] == 'openrouter'})
        self.assertEqual(seen['sarvam'], {m['id'] for m in self.plan['models'] if m['provider'] == 'sarvam'})

    def test_no_secret_is_written_anywhere_in_the_state_directory(self):
        for p in Path(self.tmp.name).rglob('*'):
            if p.is_file():
                self.assertNotIn(KEY, p.read_text(), p.name)

    def test_a_second_run_does_nothing_and_sends_nothing(self):
        sent = {p: len(t.bodies) for p, t in self.routes.items()}
        again = run_plan(self.plan, self.tmp.name, self.routes)
        self.assertEqual(again['episodes_run_now'], 0)
        self.assertEqual(sent, {p: len(t.bodies) for p, t in self.routes.items()})

    def test_the_summary_table_counts_every_episode(self):
        rows = er.summarize(self.tmp.name)
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(v['episodes'] == 10 and v['completed'] == 10 and v['not_run'] == 0 for v in rows.values()))


class ResumeAfterAStop(unittest.TestCase):
    def test_a_stopped_run_continues_to_the_same_records_as_an_uninterrupted_one(self):
        plan = small_plan(fixtures={'s06-sudden-5d'})
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            run_plan(plan, a, mock_routes())
            routes = mock_routes()
            first = run_plan(plan, b, routes, limit=5)
            self.assertEqual(first['episodes_run_now'], 5)
            run_plan(plan, b, mock_routes())
            ra, rb = records(a), records(b)
            self.assertEqual(sorted(ra), sorted(rb))
            for k in ra:
                self.assertEqual(ra[k]['grade'], rb[k]['grade'], k)
                self.assertEqual(ra[k]['requests_used'], rb[k]['requests_used'], k)

    def test_a_restart_cannot_exceed_the_sarvam_cap_or_request_cap(self):
        plan = small_plan(models={'sarvam-105b'}, fixtures={'s06-sudden-5d'})
        with tempfile.TemporaryDirectory() as d:
            first = run_plan(plan, d, mock_routes(), cap_inr=0.002)
            second = run_plan(plan, d, mock_routes(), cap_inr=0.002)
            self.assertLessEqual(second['sarvam_inr_spent_total'], 0.002 + 1e-9)
            self.assertEqual(first['requests'], second['requests'])


class Tracing(unittest.TestCase):
    def test_each_finished_episode_is_exported_once_and_no_key_is_sent(self):
        plan = small_plan(models={'sarvam-105b', 'google/gemma-4-31b-it:free'}, fixtures={'s06-sudden-5d'}, repeats=1)
        client = FakeClient()
        with tempfile.TemporaryDirectory() as d:
            run_plan(plan, d, mock_routes(), trace_client=client, keys={'sarvam': KEY})
            recs = records(d)
        self.assertEqual(len(recs), 2)
        self.assertTrue(all(r['trace'].get('exported') for r in recs.values()), [r['trace'] for r in recs.values()])
        self.assertNotIn(KEY, json.dumps(client.events, default=str) + json.dumps(client.scores, default=str))
        self.assertGreater(client.flushes, 0)


class SarvamCheck(unittest.TestCase):
    def test_the_live_check_makes_one_call_per_model_and_records_spend(self):
        base = t2.PolicyModel('combo_on_alert')

        def ping(request):
            base.bodies.append(request['body'].decode())
            return t2._reply('ping', {})
        with tempfile.TemporaryDirectory() as d:
            res = er.check_sarvam(d, ping, key=KEY, sleep=lambda s: None)
            self.assertEqual(sorted(res), sorted(sa.PRICES_INR_PER_M))
            self.assertTrue(all(r['http'] == 200 and r['tool_call'] for r in res.values()), res)
            self.assertEqual(len(base.bodies), 3)
            saved = json.loads((Path(d) / 'check_sarvam.json').read_text())
            self.assertGreater(saved['inr_spent'], 0)
            self.assertNotIn(KEY, (Path(d) / 'check_sarvam.json').read_text())


class ScriptRefusals(unittest.TestCase):
    def run_script(self, *args):
        env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
        env.pop('SARVAM_API_KEY', None)
        return subprocess.run([sys.executable, str(ROOT / 'scripts' / 'run_eval19_v3.py'), *args], capture_output=True, text=True,
                              env=env, timeout=120)

    def test_run_refuses_without_the_live_flag(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.run_script('run', '--state', d)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('--live', r.stderr + r.stdout)

    def test_run_refuses_when_the_plan_is_missing_or_uncommitted_even_with_live(self):
        with tempfile.TemporaryDirectory() as d:
            missing = self.run_script('run', '--state', d, '--live', '--plan', str(Path(d) / 'nope.json'))
            self.assertNotEqual(missing.returncode, 0)
            plan = Path(d) / 'plan.json'
            plan.write_text(json.dumps(full_plan()))
            untracked = self.run_script('run', '--state', d, '--live', '--plan', str(plan))
            self.assertNotEqual(untracked.returncode, 0)
            self.assertFalse((Path(d) / 's01').exists())

    def test_the_plan_command_writes_a_plan_that_passes_the_checks_and_calls_no_model(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'plan.json'
            r = self.run_script('plan', '--out', str(out))
            self.assertEqual(r.returncode, 0, r.stderr)
            plan = json.loads(out.read_text())
            er.check_plan(plan)
            self.assertEqual(plan['episodes_total'], 60)
            self.assertFalse(er.git_committed_clean(out))


if __name__ == '__main__':
    unittest.main()
