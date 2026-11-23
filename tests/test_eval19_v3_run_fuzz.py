"""Fuzz tests for the eval19-3 run: malformed roster and plan inputs, and hostile or broken providers. No network, no key."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from hypothesis import HealthCheck, given, settings, strategies as st

import support  # noqa: F401
from support.eval19_run_fixtures import KEY, constant, full_plan, mock_routes, small_plan

from supplychainworld import eval19_v3_run as er
from supplychainworld import sarvam_adapter as sa

ROOT = Path(__file__).resolve().parents[1]
JSON = st.recursive(st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text(max_size=12),
                    lambda c: st.lists(c, max_size=4) | st.dictionaries(st.text(max_size=8), c, max_size=4), max_leaves=12)


class MalformedInputs(unittest.TestCase):
    @settings(max_examples=150)
    @given(JSON)
    def test_a_garbage_roster_only_ever_raises_roster_error(self, obj):
        try:
            er.validate_roster(obj)
        except er.RosterError:
            pass

    @settings(max_examples=150)
    @given(JSON)
    def test_a_garbage_plan_only_ever_raises_preflight_error(self, obj):
        try:
            er.check_plan(obj)
        except er.PreflightError:
            pass

    @settings(max_examples=60, suppress_health_check=[HealthCheck.too_slow])
    @given(st.dictionaries(st.sampled_from(['schema', 'plan_sha256', 'models', 'queue', 'harness_sha256', 'fixture_sha256']), JSON))
    def test_a_plan_with_the_right_keys_and_wrong_values_is_refused_cleanly(self, d):
        p = full_plan()
        p.update(d)
        try:
            er.check_plan(p)
        except er.PreflightError:
            pass

    def test_a_file_edited_after_the_plan_was_made_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            for rel in list(er.HARNESS_FILES) + list(er.FIXTURE_FILES):
                dst = Path(root) / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / rel, dst)
            plan = er.build_plan(root=root, git_head='t')
            er.check_plan(plan, root)
            victim = Path(root) / er.HARNESS_FILES[0]
            victim.write_text(victim.read_text() + '\n# edited\n')
            with self.assertRaises(er.PreflightError):
                er.check_plan(plan, root)
            victim.unlink()
            with self.assertRaises(er.PreflightError):
                er.check_plan(plan, root)


def throwing(request):
    raise OSError('boom ' + KEY)


def junk_ok(request):
    return 200, {}, b'{"choices": "not a list", "usage": 7}'


def not_json(request):
    return 200, {}, b'<html>gateway</html>'


def error_in_200(request):
    return 200, {}, json.dumps({'error': {'message': 'rate limited ' + KEY, 'code': 429}}).encode()


HOSTILE = {'timeout': constant(0), 'server_error': constant(500), 'rate_limited': constant(429), 'forbidden': constant(403),
           'payment': constant(402), 'raises': throwing, 'junk_200': junk_ok, 'not_json': not_json, 'error_in_200': error_in_200}


class HostileProviders(unittest.TestCase):
    def test_every_kind_of_broken_provider_leaves_clean_records_no_crash_and_no_secret(self):
        plan = small_plan(models={'google/gemma-4-31b-it:free', 'glm5.3-flash'}, fixtures={'s06-sudden-5d'}, repeats=1)
        for name, transport in HOSTILE.items():
            with self.subTest(provider=name), tempfile.TemporaryDirectory() as d:
                summary = er.run(plan, d, {'openrouter': transport, 'sarvam': transport}, keys={'sarvam': KEY},
                                 sleep=lambda s: None, min_interval=0.0, out=lambda *_: None)
                recs = {p.name: json.loads(p.read_text()) for p in (Path(d) / 's01').glob('*.json')}
                self.assertEqual(len(recs), 2)
                for r in recs.values():
                    self.assertTrue('not_run' in r or r['grade']['status'] != 'complete', r.get('grade', {}).get('status'))
                    self.assertEqual(r.get('grade', {}).get('observation_leaks', []), [])
                self.assertLessEqual(summary['sarvam_inr_spent_total'], sa.CAP_INR)
                for p in Path(d).rglob('*'):
                    if p.is_file():
                        self.assertNotIn(KEY, p.read_text(), (name, p.name))

    def test_unbillable_failures_are_charged_at_the_worst_case_not_zero(self):
        plan = small_plan(models={'glm5.3-flash'}, fixtures={'s06-sudden-5d'}, repeats=1)
        with tempfile.TemporaryDirectory() as d:
            summary = er.run(plan, d, {'openrouter': constant(500), 'sarvam': constant(500)}, keys={'sarvam': KEY},
                             sleep=lambda s: None, min_interval=0.0, out=lambda *_: None)
        self.assertGreater(summary['sarvam_inr_spent_total'], 0)

    def test_a_model_that_keeps_getting_429_is_stopped_and_its_other_episodes_are_not_run(self):
        plan = small_plan(models={'google/gemma-4-31b-it:free'}, fixtures={'s06-sudden-5d', 's06-warned-delayed-10d'}, repeats=2)
        with tempfile.TemporaryDirectory() as d:
            summary = er.run(plan, d, {'openrouter': constant(429), 'sarvam': constant(500)}, sleep=lambda s: None,
                             min_interval=0.0, out=lambda *_: None)
            recs = [json.loads(p.read_text()) for p in (Path(d) / 's01').glob('*.json')]
        self.assertIn('google/gemma-4-31b-it:free', summary['stopped'])
        self.assertTrue(any('stopped' in r.get('not_run', '') for r in recs))

    @settings(max_examples=12, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(st.lists(st.sampled_from(sorted(HOSTILE)), min_size=1, max_size=3), st.floats(0.0005, 0.05))
    def test_a_mix_of_failures_never_pushes_spend_past_a_tiny_cap(self, kinds, cap):
        plan = small_plan(models={'sarvam-105b', 'deepseekv4.1-flash-1017'}, fixtures={'s06-sudden-5d'}, repeats=1)
        seq = iter(kinds * 1000)
        good = mock_routes()['sarvam']

        def mixed(request):
            k = next(seq)
            return good(request) if k == 'ok' else HOSTILE[k](request)
        with tempfile.TemporaryDirectory() as d:
            summary = er.run(plan, d, {'openrouter': constant(500), 'sarvam': mixed}, keys={'sarvam': KEY}, cap_inr=cap,
                             sleep=lambda s: None, min_interval=0.0, out=lambda *_: None)
        self.assertLessEqual(summary['sarvam_inr_spent_total'], cap + 1e-9)


class PrivateStrings(unittest.TestCase):
    def test_a_request_carrying_a_scenario_name_is_refused_before_it_reaches_the_provider(self):
        from supplychainworld.eval19 import Guard
        sent = []
        g = Guard(lambda req: sent.append(req) or (200, {}, b'{}'), sleep=lambda s: None, min_interval=0.0,
                  private_strings=[f['fixture_id'] for f in er.fixtures()])
        g.model, g.phase = 'm', 'probe'
        for name in (f['fixture_id'] for f in er.fixtures()):
            status, _, _ = g({'url': 'x', 'headers': {}, 'body': json.dumps({'note': name}).encode()})
            self.assertEqual(status, 418, name)
        self.assertEqual(sent, [])
        self.assertEqual(len(g.leak_flags), 5)


if __name__ == '__main__':
    unittest.main()
