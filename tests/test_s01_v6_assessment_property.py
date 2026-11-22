"""S01.3 for v0.6: an assessor that sees ONLY the agent view, conventions block included, matches the independent checker.

`evidence/s01-audit/s01-3-assessment.md` found that v0.2 to v0.5 show every number but not the rules that turn numbers
into outcomes (finding F6). v0.6 states them in `rules['conventions']`. The assessor here (`support/s01_assess_v6.py`)
reads every convention from that block, refuses to guess when one is missing, and is compared with the ground truth: the
same episode executed through the runner and re-derived by the independent v0.6 checker from the commands (never the
simulator's own numbers).

* exact: once the firm notice is visible (or the disruption turns out not to happen) units at risk, shortfall per order,
  earliest feasible delivery, penalties and recovery spend equal the checker's, for generated scenarios (Hypothesis) and for
  every committed fixture x every decision day x every recovery option;
* bounded: while a delay is only warned the assessment is a lower bound and the worst case an upper bound (the early-warning
  information boundary is kept on purpose; the warned twins stay indistinguishable);
* load-bearing: each stated convention, read differently, changes the answer on a committed fixture, so a model that ignores
  or misreads the block gets a different (wrong) result; the stated reading gives the checker's numbers exactly;
* no silent defaults: with the block removed or a value missing or unknown, the assessor raises instead of guessing.

Remaining ambiguity is listed in the test `RemainingGaps` and in docs/testing.md.
"""
import unittest
from copy import deepcopy

from hypothesis import given, settings, strategies as st

import support  # noqa: F401
import test_s01_assessment_property as base
from supplychainworld.dynamic_v5 import opaque_label
from support import s01_assess_v6 as a6
from support.s01_v6 import V6, SCENARIOS_V6
from support.s01_versions import fixture_scenario

OPTIONS = base.OPTIONS
STATS = {}


def compare(test, scenario, horizon, day, option):
    """Assess from the view alone and compare with the checker's ground truth. True when a comparison was made."""
    view, report = base.counterfactual(V6, scenario, horizon, day, option)
    seen = base.agent_only(view)
    est = a6.assess(seen, option)
    if est is None:
        return False
    real = base.truth(report)
    if real['earliest_feasible_delivery'] is not None:
        real['earliest_feasible_delivery'] = max(real['earliest_feasible_delivery'], day)
    firm = bool(seen['state']['notices']) or scenario['delay_outcome'] == 'none'
    kind = 'exact' if firm else 'bounded'
    STATS[(kind, option)] = STATS.get((kind, option), 0) + 1
    label = f'day {day} {option}'
    if firm:
        for key in ('shortfall_by_order', 'units_at_risk', 'earliest_feasible_delivery', 'penalties', 'recovery_spend'):
            test.assertEqual(est[key], real[key], f'{label}: {key}')
    else:
        worst = a6.assess(seen, option, worst_case=True)
        test.assertLessEqual(est['units_at_risk'], real['units_at_risk'], f'{label}: optimistic bound')
        test.assertGreaterEqual(worst['units_at_risk'], real['units_at_risk'], f'{label}: worst-case bound')
        test.assertEqual(est['recovery_spend'], real['recovery_spend'], f'{label}: spend')
    return True


class Assessment_v06(unittest.TestCase):
    @given(SCENARIOS_V6, st.data())
    @settings(max_examples=60)
    def test_assessment_from_the_view_alone_matches_the_checker_on_generated_scenarios(self, sc, data):
        scenario, horizon = sc
        compare(self, scenario, horizon, data.draw(st.integers(1, horizon)), data.draw(st.sampled_from(OPTIONS)))

    def test_every_fixture_every_decision_day_every_option(self):
        made = 0
        for f in V6.fixtures():
            scenario, horizon = fixture_scenario(V6, f)
            for day in range(1, horizon + 1):
                for option in OPTIONS:
                    with self.subTest(fixture=f['fixture_id'], day=day, option=option):
                        made += compare(self, scenario, horizon, day, option)
        self.assertGreater(made, 20)

    def test_zz_exact_and_bounded_comparisons_were_made_for_every_option(self):
        for kind in ('exact', 'bounded'):
            for option in OPTIONS:
                self.assertGreater(STATS.get((kind, option), 0), 0, f'no {kind} comparison for {option}')

    @given(SCENARIOS_V6, st.data())
    @settings(max_examples=25)
    def test_the_warned_twins_stay_identical_to_the_agent_before_the_firm_notice(self, sc, data):
        scenario, horizon = sc
        if scenario['delay_outcome'] != 'delay' or scenario['notice_day'] < 2:
            return
        day = data.draw(st.integers(1, scenario['notice_day'] - 1))
        view, _ = base.counterfactual(V6, scenario, horizon, day, 'maintain')
        primary = next(x for x in view['state']['lots'] if x['lot_id'] == 'primary')
        self.assertEqual(primary['arrival_day'], scenario['primary_promised_day'])
        self.assertEqual(view['state']['notices'], [])
        self.assertIn('conventions', view['rules'])      # the block is visible before the notice and says nothing of the outcome


class ConventionsAreLoadBearing(unittest.TestCase):
    """Each convention, read differently, changes the answer on a committed fixture; the stated reading is exact."""

    ALTERNATIVES = {
        'receipts usable only from the next day': ('receipts_usable_on_arrival_day', False),
        'goods shipped as soon as they exist': ('shipping_starts_on', 'as_soon_as_finished'),
        'orders served by order id only': ('shipping_priority', 'order_id_ascending'),
        'percent penalty read as whole percent': ('penalty_rate_divisor_percent_of_value', 100),
    }

    @staticmethod
    def cases():
        """Every fixture, plus the two-tier fixture with its order ids renamed so that id order and priority order
        differ (in the committed one they coincide, so the serving-order convention cannot show there)."""
        out = [fixture_scenario(V6, f) for f in V6.fixtures()]
        scenario, horizon = deepcopy(fixture_scenario(V6, next(f for f in V6.fixtures() if 'multitier' in f['fixture_id'])))
        for o, new in zip(scenario['orders'], ('Z1', 'A1')):
            o['order_id'] = new
        scenario['scenario_id'] = opaque_label(scenario)
        return out + [(scenario, horizon)]

    def test_a_different_reading_of_each_stated_convention_changes_the_answer_somewhere(self):
        for name, (key, other) in self.ALTERNATIVES.items():
            differs = False
            for scenario, horizon in self.cases():
                for day in range(1, horizon + 1):
                    for option in OPTIONS:
                        view, report = base.counterfactual(V6, scenario, horizon, day, option)
                        seen = base.agent_only(view)
                        right = a6.assess(seen, option)
                        if right is None:
                            continue
                        bent = deepcopy(seen)
                        bent['rules']['conventions']['parameters'][key] = other
                        wrong = a6.assess(bent, option)
                        keys = ('units_at_risk', 'earliest_feasible_delivery', 'penalties', 'shortfall_by_order')
                        differs |= any(right[k] != wrong[k] for k in keys)
            self.assertTrue(differs, f'"{name}" never changed an assessment: the stated convention would not be load-bearing')

    def test_the_assessor_refuses_to_guess_when_the_block_is_missing_or_not_understood(self):
        scenario, horizon = fixture_scenario(V6, V6.fixtures()[3])
        view, _ = base.counterfactual(V6, scenario, horizon, 1, 'maintain')
        seen = base.agent_only(view)
        gone = deepcopy(seen)
        del gone['rules']['conventions']
        with self.assertRaises(a6.ConventionError):
            a6.assess(gone, 'maintain')
        for key in a6.REQUIRED:
            lacking = deepcopy(seen)
            del lacking['rules']['conventions']['parameters'][key]
            with self.assertRaises(a6.ConventionError, msg=key):
                a6.assess(lacking, 'maintain')
        for key in a6.SUPPORTED:
            odd = deepcopy(seen)
            odd['rules']['conventions']['parameters'][key] = 'something_else'
            with self.assertRaises(a6.ConventionError, msg=key):
                a6.assess(odd, 'maintain')

    def test_the_older_assessor_needs_defaults_the_v06_assessor_reads(self):
        """The v0.2 to v0.5 assessor takes `Conventions()` defaults the observation never states; v0.6 reads them."""
        import inspect
        from support import s01_assess
        self.assertIs(inspect.signature(s01_assess.assess).parameters['conv'].default, s01_assess.V34_CONVENTIONS)
        self.assertNotIn('conv', inspect.signature(a6.assess).parameters)


class StatementsAndParametersAgree(unittest.TestCase):
    PARAM_TO_STATEMENT = {
        'receipts_usable_on_arrival_day': 'receipts_usable_on_arrival_day', 'production_completes_at': 'production_completes_at',
        'shipping_starts_on': 'shipping_starts_on', 'shipping_priority': 'shipping_priority',
        'penalty_rate_divisor_percent_of_value': 'penalty_rate_unit_percent_of_value',
        'penalty_rate_unit_percent_of_value': 'penalty_rate_unit_percent_of_value',
        'penalty_rate_unit_fixed_per_unit': 'penalty_rate_unit_fixed_per_unit',
        'penalty_rate_unit_per_unit_per_day': 'penalty_rate_unit_per_unit_per_day',
        'penalty_rounding': 'penalty_assessed_at', 'penalty_cap_basis': 'penalty_cap', 'cancellation_day': 'cancellation',
        'on_time_means': 'on_time_units', 'auto_key_prefix': 'repeated_purchase'}

    def setUp(self):
        from supplychainworld.dynamic_v6 import conventions_block
        self.block = conventions_block()

    def test_every_parameter_has_a_statement_and_every_statement_is_a_single_plain_sentence_group(self):
        self.assertEqual(sorted(self.block['parameters']), sorted(self.PARAM_TO_STATEMENT))
        for param, statement in self.PARAM_TO_STATEMENT.items():
            self.assertIn(statement, self.block['statements'], param)
        for key, text in self.block['statements'].items():
            self.assertTrue(text.endswith('.'), key)
            self.assertLess(len(text), 420, key)

    def test_the_numbers_and_words_in_the_statements_agree_with_the_parameters(self):
        st_, p = self.block['statements'], self.block['parameters']
        self.assertIn(str(p['penalty_rate_divisor_percent_of_value']), st_['penalty_rate_unit_percent_of_value'])
        self.assertIn('basis points', st_['penalty_rate_unit_percent_of_value'])
        self.assertIn(p['auto_key_prefix'], st_['repeated_purchase'])
        self.assertIn('once', st_['penalty_rate_unit_fixed_per_unit'])
        self.assertIn('rounded down', st_['penalty_assessed_at'])
        self.assertIn('ascending', st_['shipping_priority'])
        self.assertIn('close of today', st_['production_completes_at'])
        self.assertIn('already arrived', st_['receipts_usable_on_arrival_day'])
        self.assertIn('never shipped before the due day', st_['shipping_starts_on'])


class RemainingGaps(unittest.TestCase):
    """What the conventions block still does NOT settle. Reported as gaps, not as passing."""

    GAPS = (
        'before a firm notice of a real delay only a range is knowable (kept on purpose: the information boundary)',
        'the agent future release and recovery decisions are its own; the assessor assumes greedy production and one stated option',
        'earliest_feasible_delivery and units_at_risk are definitions of the assessor, not fields the world reports',
        'the penalty cap and the penalty arithmetic are stated, but an example per penalty type is not shown in the view',
        'what a person or a model concludes from the block is untested: no model was run',
    )

    def test_the_gaps_are_recorded(self):
        self.assertEqual(len(self.GAPS), 5)

    def test_before_the_notice_the_answer_is_bounded_not_exact_for_a_real_delay(self):
        scenario, horizon = fixture_scenario(V6, next(f for f in V6.fixtures() if 'warned-delayed' in f['fixture_id']))
        view, report = base.counterfactual(V6, scenario, horizon, 1, 'maintain')
        seen = base.agent_only(view)
        est, worst = a6.assess(seen, 'maintain'), a6.assess(seen, 'maintain', worst_case=True)
        real = base.truth(report)
        self.assertLess(est['units_at_risk'], real['units_at_risk'])
        self.assertGreaterEqual(worst['units_at_risk'], real['units_at_risk'])


if __name__ == '__main__':
    unittest.main()
