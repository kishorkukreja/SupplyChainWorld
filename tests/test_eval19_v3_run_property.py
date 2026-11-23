"""Property tests for the eval19-3 run plan, roster and queue (src/supplychainworld/eval19_v3_run.py). No network, no key."""
import json
import unittest

from hypothesis import given, settings, strategies as st

import support  # noqa: F401
from support.eval19_run_fixtures import full_plan

from supplychainworld import eval19_v3_run as er
from supplychainworld import sarvam_adapter as sa

MODELS = er.load_roster()
SCENARIOS = [f['fixture_id'] for f in er.fixtures()]


class Queue(unittest.TestCase):
    @given(st.integers(1, er.MAX_REPEATS))
    def test_every_repeat_scenario_model_triple_appears_exactly_once(self, repeats):
        q = er.build_queue(MODELS, SCENARIOS, repeats)
        keys = [(x['repeat'], x['fixture_id'], x['model']) for x in q]
        self.assertEqual(len(keys), repeats * len(SCENARIOS) * len(MODELS))
        self.assertEqual(len(set(keys)), len(keys))

    @given(st.integers(1, er.MAX_REPEATS), st.integers(0, 200))
    def test_any_stopped_prefix_is_balanced_across_models(self, repeats, cut):
        q = er.build_queue(MODELS, SCENARIOS, repeats)[:cut]
        counts = {m['id']: 0 for m in MODELS}
        for x in q:
            counts[x['model']] += 1
        self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)

    @given(st.one_of(st.integers(max_value=0), st.integers(min_value=er.MAX_REPEATS + 1), st.floats(), st.text(), st.none(), st.booleans()))
    def test_a_repeat_count_outside_range_is_refused(self, repeats):
        with self.assertRaises(ValueError):
            er.build_queue(MODELS, SCENARIOS, repeats)

    @given(st.integers(1, er.MAX_REPEATS))
    def test_worst_case_requests_scale_linearly_with_repeats(self, repeats):
        fx = er.fixtures()
        one = er.worst_case_requests(MODELS, fx, 1)
        many = er.worst_case_requests(MODELS, fx, repeats)
        self.assertEqual(many, {p: v * repeats for p, v in one.items()})


MODEL_ID = st.text(alphabet=st.characters(min_codepoint=33, max_codepoint=126), min_size=1, max_size=40)


class Roster(unittest.TestCase):
    @given(MODEL_ID)
    def test_an_openrouter_id_without_free_is_always_refused(self, mid):
        if mid.endswith(':free'):
            mid = mid[:-5] + 'x'
        with self.assertRaises(er.RosterError):
            er.validate_roster({'models': [{'id': mid, 'provider': 'openrouter', 'role': 'actor'}]})

    @given(MODEL_ID)
    def test_a_sarvam_id_outside_the_price_table_is_always_refused(self, mid):
        if mid in sa.PRICES_INR_PER_M:
            mid += '-x'
        with self.assertRaises(er.RosterError):
            er.validate_roster({'models': [{'id': mid, 'provider': 'sarvam', 'role': 'actor'}]})

    @given(st.sampled_from(sorted(sa.PRICES_INR_PER_M)))
    def test_a_duplicate_is_refused(self, mid):
        m = {'id': mid, 'provider': 'sarvam', 'role': 'actor'}
        with self.assertRaises(er.RosterError):
            er.validate_roster({'models': [m, dict(m)]})

    @given(st.sampled_from(['scorer', 'judge', '', None]))
    def test_only_actors_act(self, role):
        with self.assertRaises(er.RosterError):
            er.validate_roster({'models': [{'id': 'sarvam-105b', 'provider': 'sarvam', 'role': role}]})

    def test_the_committed_roster_is_six_models_three_per_route(self):
        self.assertEqual(len(MODELS), 6)
        self.assertEqual(sum(m['provider'] == 'openrouter' for m in MODELS), 3)
        self.assertEqual(sum(m['provider'] == 'sarvam' for m in MODELS), 3)
        self.assertNotIn('glm5.3', [m['id'] for m in MODELS])


class PlanIntegrity(unittest.TestCase):
    def test_the_full_plan_has_sixty_episodes_and_the_owner_cap(self):
        p = full_plan()
        self.assertEqual(p['episodes_total'], 60)
        self.assertEqual(p['episodes_by_provider'], {'openrouter': 30, 'sarvam': 30})
        self.assertEqual(p['spend']['sarvam']['hard_cap_inr'], 10000.0)
        self.assertEqual(p['spend']['openrouter']['ceiling_usd'], 0.0)
        er.check_plan(p)

    @settings(max_examples=60)
    @given(st.data())
    def test_changing_any_field_of_the_plan_is_caught(self, data):
        p = full_plan()
        key = data.draw(st.sampled_from(sorted(k for k in p if k != 'plan_sha256')))
        p[key] = data.draw(st.one_of(st.integers(), st.text(max_size=10), st.none(), st.lists(st.integers(), max_size=3))
                           .filter(lambda v: v != p[key]))
        with self.assertRaises(er.PreflightError):
            er.check_plan(p)

    @given(st.sampled_from(sorted(full_plan()['harness_sha256'])), st.text(alphabet='0123456789abcdef', min_size=64, max_size=64))
    def test_a_changed_file_hash_in_the_plan_is_caught_even_with_a_matching_plan_hash(self, rel, fake):
        p = full_plan()
        if p['harness_sha256'][rel] == fake:
            return
        p['harness_sha256'][rel] = fake
        p['plan_sha256'] = er.sha_plan(p)
        with self.assertRaises(er.PreflightError):
            er.check_plan(p)

    @given(st.integers(1, er.MAX_REPEATS))
    def test_the_plan_is_deterministic_for_fixed_inputs(self, repeats):
        a = er.build_plan(repeats=repeats, git_head='h', now=__import__('datetime').datetime(2026, 11, 23))
        b = er.build_plan(repeats=repeats, git_head='h', now=__import__('datetime').datetime(2026, 11, 23))
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        self.assertEqual(a['plan_sha256'], er.sha_plan(a))

    @given(st.one_of(st.just(0), st.just(-1), st.just(sa.CAP_INR + 0.01), st.floats(allow_nan=True, allow_infinity=True).filter(lambda x: not 0 < x <= sa.CAP_INR)))
    def test_a_cap_outside_zero_to_ten_thousand_is_refused(self, cap):
        with self.assertRaises(ValueError):
            er.build_plan(cap_inr=cap)


if __name__ == '__main__':
    unittest.main()
