"""Production schema/checker/solver for static rules 1.2 against the v1.2 fixtures (re-review of issue #35).

All numeric policy values in these fixtures are PROVISIONAL and not practitioner-confirmed; the re-review is
not independent. v1.0 and v1.1 modules and fixtures are untouched; tests show 1.2 differing from 1.1 on purpose.
"""
import copy
import json
import unittest
from decimal import Decimal as D
from pathlib import Path

from pydantic import ValidationError

from supplychainworld import schemas_v11 as s11
from supplychainworld import schemas_v12 as s12
from supplychainworld import solvers_v11 as sol11
from supplychainworld import solvers_v12 as sol
from supplychainworld import verification_v11 as chk11
from supplychainworld import verification_v12 as chk

ROOT = Path(__file__).resolve().parents[1]
V12 = ROOT / 'fixtures' / 'reference_cases_v1_2'
N = 33


def case(n):
    return json.loads((V12 / f'ref-{n:02}.json').read_text())


def world(n):
    return s12.World.model_validate(case(n)['world'])


def variant(n, mutate):
    c = case(n)
    mutate(c['world'])
    return c['world']


def award(allocs, cost, flags=(), reqs=(), refs=()):
    return dict(kind='award', allocations=[dict(supplier_id=s, item_id=i, quantity=q) for s, i, q in allocs],
                claimed_total_cost=cost, evidence=['x'], flags=list(flags), clarification_requests=list(reqs),
                approval_refs=list(refs))


def est(cost='9.00'):
    return award([('A', 'component', 4)], cost, ['estimated:A:component'], ['quotes.A.component.variable_freight'])


class FixturesAgainstProduction(unittest.TestCase):
    def test_all_cases_solver_and_checker(self):
        for n in range(1, N + 1):
            with self.subTest(case=n):
                c = case(n)
                w = s12.World.model_validate(c['world'])
                kind = c['expected']['submission']['kind']
                result = sol.solve_reference(w)
                self.assertEqual(result.status, {'award': 'optimal', 'clarification': 'clarification_required',
                                                 'infeasible': 'infeasible'}[kind])
                exp = c['expected']['optimal_cost']
                self.assertEqual(result.total_cost, D(exp) if exp is not None else None)
                task = s12.Task(task_id=c['task']['task_id'], world_id=w.world_id, request=c['request'], expected_outcome=kind,
                                concentration_measures=c['task']['concentration_measures'])
                s12.check_task_world(task, w)
                measures = c['task']['concentration_measures']
                checked = chk.verify(w, result.submission(), expected_outcome=kind, reference_cost=result.total_cost, task_measures=measures)
                self.assertTrue(checked.accepted, checked.critical_failures)
                expected = chk.verify(w, c['expected']['submission'], expected_outcome=kind, reference_cost=exp, task_measures=measures)
                self.assertTrue(expected.accepted, expected.critical_failures)
                if kind == 'award':
                    self.assertEqual(expected.optimality, 'optimal')
                    self.assertEqual(expected.independent_cost, D(exp))
                    self.assertEqual(expected.objective_gap, 0)
                    self.assertEqual(set(c['expected']['submission']['flags']), set(result.flags))
                    self.assertEqual(set(c['expected']['submission']['approval_refs']), set(result.approval_refs))

    def test_alternatives_and_wrong_answers(self):
        for n in range(1, N + 1):
            c = case(n)
            w = s12.World.model_validate(c['world'])
            ref = c['expected']['optimal_cost']
            for alt in c['expected']['valid_alternatives']:
                with self.subTest(case=n, alt=alt['note']):
                    r = chk.verify(w, alt['submission'], reference_cost=ref)
                    self.assertTrue(r.accepted, r.critical_failures)
                    if alt['submission']['kind'] == 'award':
                        self.assertEqual(r.optimality, alt['status'])
                        self.assertEqual(r.independent_cost, D(alt['cost']))
            for wrong in c['known_wrong']:
                with self.subTest(case=n, wrong=wrong['reason']):
                    r = chk.verify(w, wrong['submission'], reference_cost=ref)
                    self.assertFalse(r.accepted, wrong['reason'])

    def test_solver_band_awards_include_equivalent_ones(self):
        costs = [c for c, _ in sol.solve_reference(world(2)).band_awards]
        self.assertEqual((D('8.00') in costs, D('8.40') in costs, D('10.40') in costs), (True, True, False))
        costs = [c for c, _ in sol.solve_reference(world(26)).band_awards]
        self.assertIn(D('505.00'), costs)          # 1% tier band 5.00
        self.assertNotIn(D('505.04'), costs)

    def test_heuristic_is_feasible_but_not_certified(self):
        for n in (1, 3, 8, 12, 17, 22, 28, 31):
            with self.subTest(case=n):
                h = sol.solve_heuristic(world(n))
                self.assertIn(h.status, {'feasible', 'error'})
                if h.status == 'feasible':
                    self.assertTrue(chk.verify(world(n), h.submission()).accepted)
        for n in (29, 30):    # the heuristic also asks first
            self.assertEqual(sol.solve_heuristic(world(n)).status, 'clarification_required')
        self.assertEqual(sol.solve_reference(world(20)).total_cost, D('8.00'))

    def test_v10_and_v11_untouched(self):
        self.assertEqual(len(list((ROOT / 'fixtures' / 'reference_cases').glob('ref-*.json'))), 10)
        self.assertEqual(len(list((ROOT / 'fixtures' / 'reference_cases_v1_1').glob('ref-*.json'))), 22)
        self.assertEqual((chk11.CHECKER_VERSION, chk.CHECKER_VERSION), ('1.1', '1.2'))
        self.assertEqual((sol11.SOLVER_VERSION, sol.SOLVER_VERSION), ('1.1', '1.2'))
        w11 = json.loads((ROOT / 'fixtures' / 'reference_cases_v1_1' / 'ref-17.json').read_text())['world']
        self.assertEqual(w11['constraints']['approval_limit'], '50.00')
        with self.assertRaises(ValidationError):
            s12.World.model_validate(w11)
        with self.assertRaises(ValidationError):
            s11.World.model_validate(case(17)['world'])


class SafetyStockC1(unittest.TestCase):
    def ss(self, level, std, lead, override=None):
        def m(w):
            w['stock'] = []
            it = w['items'][0]
            it.update(demand=0, service_level=level, demand_std=std, lead_time_periods=lead, safety_stock_override=override)
        return chk.verify(variant(1, m), award([], '0')).safety_stocks['component']

    def test_ceiling_of_service_level_formula(self):
        self.assertEqual(self.ss('0.95', '1', '2'), 3)        # 2.3263
        self.assertEqual(self.ss('0.90', '1', '1'), 2)        # 1.2816
        self.assertEqual(self.ss('0.99', '1', '4'), 5)        # 4.6526
        self.assertEqual(self.ss('0.975', '2.5', '4'), 10)    # 9.8
        self.assertEqual(self.ss('0.975', '12.5', '4'), 49)   # exactly 49: no extra unit
        self.assertEqual(self.ss('0.975', '12.5001', '4'), 50)
        self.assertEqual(self.ss('0.95', '0', '4'), 0)

    def test_checker_and_solver_agree_on_grid(self):
        for level in ('0.90', '0.95', '0.975', '0.99'):
            for std in ('0.5', '1', '2.5', '7'):
                for lead in ('0.25', '1', '2', '3', '9'):
                    it = s12.Item(item_id='x', demand=1, due_date='2026-11-10', service_level=level, demand_std=std, lead_time_periods=lead)
                    exact = chk.safety_stock_units(it.model_dump(mode='json'))
                    self.assertEqual(sol.safety_stock(it), exact, (level, std, lead))

    def test_override_beats_inputs_and_none_means_zero(self):
        self.assertEqual(self.ss('0.95', '1', '2', override=7), 7)
        self.assertEqual(self.ss('0.95', '1', '2', override=0), 0)
        w = case(1)['world']
        w['items'][0].update(service_level=None, demand_std=None, lead_time_periods=None)
        self.assertEqual(chk.verify(w, award([], '0')).safety_stocks['component'], 0)

    def test_item_validation(self):
        base = dict(item_id='x', demand=1, due_date='2026-11-10')
        for bad in (dict(service_level='0.95'), dict(service_level='0.95', demand_std='1'),
                    dict(service_level='0.80', demand_std='1', lead_time_periods='1')):
            with self.assertRaises(ValidationError):
                s12.Item(**base, **bad)
        s12.Item(**base, service_level='0.95', demand_std='1', lead_time_periods='1')

    def test_safety_stock_changes_net_and_award(self):
        r = chk.verify(world(23), award([('A', 'component', 11)], '22.00'))
        self.assertEqual((r.net_requirements, r.safety_stocks), ({'component': 11}, {'component': 10}))
        self.assertTrue(r.accepted)
        self.assertFalse(chk.verify(world(23), award([('A', 'component', 10)], '20.00')).accepted)


class RuleRegressions(unittest.TestCase):
    # C2
    def test_late_inbound_window_is_three_days(self):
        def net(arrival):
            def m(w):
                w['inbound'] = [dict(item_id='component', quantity=4, arrival_date=arrival, status='committed')]
            return chk.verify(variant(11, m), award([('A', 'component', 6)], '12.00')).net_requirements['component']
        self.assertEqual(net('2026-11-13'), 4)   # 3 days late: credit 2
        self.assertEqual(net('2026-11-14'), 6)   # 4 days late: nothing
        self.assertEqual(s12.Policy().late_inbound_tolerance_days, 3)
        self.assertEqual(chk.verify(world(1), award([('A', 'component', 8)], '16.00')).net_requirements, {'component': 8})

    # C3
    def test_tolerance_tiers_by_optimum_cost(self):
        for n, opt, pct in ((25, '49.00', '0.03'), (16, '50.00', '0.02'), (27, '499.00', '0.02'), (26, '500.00', '0.01')):
            r = chk.verify(world(n), case(n)['expected']['submission'], reference_cost=opt)
            self.assertEqual(r.tolerance_pct_applied, D(pct), n)
        w = world(26)
        r = chk.verify(w, award([('B', 'component', 4)], '505.00'), reference_cost='500.00')
        self.assertEqual((r.optimality, r.objective_gap, r.objective_gap_pct), ('equivalent_to_optimal', D('5.00'), D('0.01')))
        r = chk.verify(w, award([('C', 'component', 4)], '505.04'), reference_cost='500.00')
        self.assertEqual((r.optimality, r.objective_gap), ('suboptimal', D('5.04')))
        self.assertTrue(r.accepted, 'a suboptimal feasible award is not a hard-policy violation')

    def test_tolerance_scales_with_reference_value(self):
        def m(w):
            w['policy']['cost_tolerance_reference_value'] = '10.00'
        r = chk.verify(variant(4, m), award([('C', 'component', 4)], '8.24'), reference_cost='8.00')
        self.assertEqual((r.tolerance_pct_applied, r.optimality), (D('0.02'), 'suboptimal'))    # optimum 8.00 is 0.8 x reference

    def test_tier_schema_validation_monotone(self):
        w = case(1)['world']
        w['policy']['cost_tolerance_tiers'] = [dict(from_ratio='0', pct='0.01'), dict(from_ratio='1', pct='0.02')]
        with self.assertRaises(ValidationError):
            s12.World.model_validate(w)     # looser for larger orders
        w['policy']['cost_tolerance_tiers'] = [dict(from_ratio='1', pct='0.02')]
        with self.assertRaises(ValidationError):
            s12.World.model_validate(w)     # must start at 0
        w['policy']['cost_tolerance_tiers'] = [dict(from_ratio='0', pct='0.02'), dict(from_ratio='0', pct='0.01')]
        with self.assertRaises(ValidationError):
            s12.World.model_validate(w)
        w['policy']['cost_tolerance_reference_value'] = '0'
        w['policy']['cost_tolerance_tiers'] = [dict(from_ratio='0', pct='0.02')]
        with self.assertRaises(ValidationError):
            s12.World.model_validate(w)

    def test_zero_tiers_mean_exact_ties_only(self):
        r = chk.verify(world(21), award([('B', 'component', 4)], '4.0180'), reference_cost='4.0164')
        self.assertEqual((r.optimality, r.objective_gap), ('suboptimal', D('0.0016')))

    # C4
    def test_approval_limit_boundary_is_at_or_below(self):
        def at(limit):
            def m(w):
                w['constraints']['approval_limit'] = limit
            return chk.verify(variant(17, m), est()).accepted
        self.assertTrue(at('9.01'))
        self.assertTrue(at('9.00'))        # v1.1: strictly under, False here
        self.assertFalse(at('8.99'))
        self.assertFalse(at(None))

    def test_at_limit_estimate_and_above_limit(self):
        good = award([('A', 'component', 40)], '5000.00', ['estimated:A:component'], ['quotes.A.component.variable_freight'])
        r = chk.verify(world(28), good)
        self.assertTrue(r.accepted, r.critical_failures)
        self.assertEqual(r.estimated_lines, ['A:component'])
        self.assertEqual(sol.solve_reference(world(28)).total_cost, D('5000.00'))
        self.assertEqual(sol.solve_reference(world(29)).status, 'clarification_required')
        over = chk.verify(world(29), award([('A', 'component', 40)], '5000.40', ['estimated:A:component'], ['quotes.A.component.variable_freight']))
        self.assertFalse(over.accepted)

    def test_estimate_requires_flag_request_and_non_critical(self):
        self.assertTrue(chk.verify(world(17), est()).accepted)
        for bad in (award([('A', 'component', 4)], '9.00', [], ['quotes.A.component.variable_freight']),
                    award([('A', 'component', 4)], '9.00', ['estimated:A:component'], [])):
            self.assertFalse(chk.verify(world(17), bad).accepted)
        r = chk.verify(case(18)['world'], est())
        self.assertIn('allocation.0.estimate_not_critical', r.critical_failures)

    def test_missing_terms_never_become_zero(self):
        r = chk.verify(world(9), award([('A', 'component', 4)], '4.00'))
        self.assertIn('allocation.0.commercial_terms', r.critical_failures)

    # C6
    def test_ask_first_even_when_other_quotes_cover(self):
        for n in (29, 30):
            w = world(n)
            around = award([('B', 'component', 40 if n == 29 else 20)], '5020.00' if n == 29 else '240.00')
            r = chk.verify(w, around)
            self.assertIn('missing_term_clarification_first', r.critical_failures, n)
            self.assertEqual(sol.solve_reference(w).status, 'clarification_required')
        # the same world under rules 1.1 awards B: the behaviour really changed
        w30 = case(30)['world']
        w30['schema_version'] = '1.1'
        for it in w30['items']:
            it.pop('service_level'), it.pop('demand_std'), it.pop('lead_time_periods'), it.pop('safety_stock_override')
            it['safety_stock'] = 0
        w30['policy'] = dict(late_inbound_tolerance_days=0, late_inbound_credit='0', cost_tolerance_abs='0', cost_tolerance_pct='0')
        w30.pop('approvals')
        self.assertEqual(sol11.solve_reference(s11.World.model_validate(w30)).status, 'optimal')

    def test_estimate_path_still_allows_award_around(self):
        r = chk.verify(world(17), award([('B', 'component', 4)], '9.20'), reference_cost='9.00')
        self.assertTrue(r.accepted)
        self.assertEqual(r.optimality, 'equivalent_to_optimal')

    def test_missing_term_on_item_with_no_need_is_ignored(self):
        def m(w):
            w['items'][0]['demand'] = 0
        self.assertTrue(chk.verify(variant(30, m), award([], '0')).accepted)

    def test_clarification_must_be_escalated_and_name_a_blocking_field(self):
        w = case(9)['world']
        good = dict(kind='clarification', field='quotes.A.component.variable_freight', disposition='record_and_escalate', evidence=['e'])
        self.assertTrue(chk.verify(w, good).accepted)
        self.assertIn('clarification_escalated', chk.verify(w, {**good, 'disposition': None}).critical_failures)
        self.assertIn('missing_field', chk.verify(w, {**good, 'field': 'quotes.A.component.unit_price'}).critical_failures)
        # no blocking gap in ref-17: asking instead of awarding is not a supported answer
        self.assertIn('clarification_required', chk.verify(world(17), good).critical_failures)

    # C5
    def test_moq_excess_approval_above_threshold(self):
        good = award([('A', 'component', 20)], '6000.00', ['moq_excess:component'], [], ['APR-7'])
        self.assertTrue(chk.verify(world(31), good).accepted)
        no_ref = award([('A', 'component', 20)], '6000.00', ['moq_excess:component'])
        self.assertIn('item.component.moq_excess_approval', chk.verify(world(31), no_ref).critical_failures)
        fake = award([('A', 'component', 20)], '6000.00', ['moq_excess:component'], [], ['APR-X'])
        self.assertIn('item.component.moq_excess_approval', chk.verify(world(31), fake).critical_failures)

    def test_moq_excess_threshold_boundary_flag_only(self):
        r = chk.verify(world(33), award([('A', 'component', 20)], '5000.00', ['moq_excess:component']))
        self.assertTrue(r.accepted, r.critical_failures)            # excess value exactly 500.00: flag suffices
        def m(w):
            w['quotes'][0]['unit_price'] = '250.01'
        r = chk.verify(variant(33, m), award([('A', 'component', 20)], '5000.20', ['moq_excess:component']))
        self.assertIn('item.component.moq_excess_approval', r.critical_failures)   # 500.02 is above the threshold

    def test_moq_threshold_is_configurable(self):
        def m(w):
            w['policy']['moq_excess_approval_threshold'] = '700.00'
        r = chk.verify(variant(31, m), award([('A', 'component', 20)], '6000.00', ['moq_excess:component']))
        self.assertTrue(r.accepted, r.critical_failures)

    def test_no_approval_means_request_it(self):
        w = world(32)
        self.assertEqual(sol.solve_reference(w).clarification_field, 'approvals.moq_excess.component')
        self.assertEqual(sol.solve_heuristic(w).status, 'clarification_required')
        bad = dict(kind='clarification', field='approvals.moq_excess.other', disposition='record_and_escalate', evidence=['e'])
        self.assertIn('missing_field', chk.verify(w, bad).critical_failures)

    def test_shelf_cap_and_unjustified_excess(self):
        w = case(8)['world']
        self.assertTrue(chk.verify(w, award([('A', 'component', 4)], '4.00', ['moq_excess:component'])).accepted)
        self.assertIn('item.component.moq_excess_flag', chk.verify(w, award([('A', 'component', 4)], '4.00')).critical_failures)
        w['items'][0]['max_excess'] = 0
        self.assertIn('item.component.shelf_life_cap', chk.verify(w, award([('A', 'component', 4)], '4.00', ['moq_excess:component'])).critical_failures)
        w = case(8)['world']
        w['quotes'][1]['capacity'] = 3          # exact quantity reachable: MOQ no longer justifies excess
        self.assertIn('item.component.excess', chk.verify(w, award([('A', 'component', 4)], '4.00', ['moq_excess:component'])).critical_failures)
        r = chk.verify(world(22), award([('C', 'component', 6)], '6.00'))
        self.assertIn('item.component.shelf_life_cap', r.critical_failures)

    # C7
    def test_spend_share_is_default_and_others_need_task_declaration(self):
        self.assertEqual(s12.ConcentrationRule(limit='0.5').measure, 'spend_share')
        w = world(13)
        task = s12.Task(task_id='t', world_id='ref-13', request='r', expected_outcome='award')
        with self.assertRaises(ValueError):
            s12.check_task_world(task, w)
        s12.check_task_world(s12.Task(task_id='t', world_id='ref-13', request='r', expected_outcome='award',
                                      concentration_measures=['quantity_share']), w)
        a = award([('A', 'Q', 4), ('B', 'P', 4)], '8.80')
        self.assertTrue(chk.verify(w, a, task_measures=['quantity_share']).accepted)
        self.assertIn('concentration_measure_declared', chk.verify(w, a, task_measures=[]).critical_failures)
        with self.assertRaises(ValidationError):
            s12.Task(task_id='t', world_id='w', request='r', expected_outcome='award', concentration_measures=['spend_share'])

    def test_three_measures_are_distinct_and_exact(self):
        w13 = case(13)['world']
        spend_only = copy.deepcopy(w13)
        spend_only['constraints']['concentration'] = [dict(measure='spend_share', limit='0.50', item_ids=None)]
        a = award([('A', 'Q', 4), ('B', 'P', 4)], '8.80')
        self.assertTrue(chk.verify(w13, a).accepted)
        self.assertFalse(chk.verify(spend_only, a).accepted)
        r = chk.verify(case(14)['world'], award([('A', 'P', 2), ('B', 'P', 2), ('A', 'Q', 2)], '8.00'))
        self.assertIn('concentration.0.per_item_share', r.critical_failures)

    # C8, structure
    def test_no_rounding_and_gap_exact(self):
        w = world(21)
        self.assertTrue(chk.verify(w, award([('A', 'component', 4)], '4.0164'), reference_cost='4.0164').accepted)
        self.assertFalse(chk.verify(w, award([('A', 'component', 4)], '4.02')).accepted)
        r = chk.verify(world(16), award([('B', 'component', 10)], '50.40'), reference_cost='50.00')
        self.assertEqual((r.optimality, r.objective_gap, r.objective_gap_pct), ('equivalent_to_optimal', D('0.40'), D('0.008')))
        self.assertEqual(r.non_cost_metrics['quantity_weighted_reliability'], '0.9500')

    def test_fixed_charge_tiers_and_validation(self):
        w = case(20)['world']
        self.assertEqual(chk.verify(w, award([('A', 'component', 6)], '8.00')).independent_cost, D('8.00'))
        w['suppliers'][0]['fixed_charge_table'][0]['from_measure'] = '1'
        with self.assertRaises(ValidationError):
            s12.World.model_validate(w)

    def test_infeasible_claim_needs_capacity_certificate(self):
        w = case(10)['world']
        fake = dict(kind='infeasible', evidence=['Insufficient capacity somewhere'])
        self.assertTrue(chk.verify(w, fake).accepted)
        w['items'][0]['service_level'] = None
        w['items'][0].update(demand_std=None, lead_time_periods=None)
        self.assertIn('capacity_certificate', chk.verify(w, fake).critical_failures)

    def test_schema_version_strict_and_search_limits(self):
        w = case(1)['world']
        w['schema_version'] = '1.1'
        with self.assertRaises(ValidationError):
            s12.World.model_validate(w)
        self.assertFalse(chk.verify(w, award([], '0')).accepted)
        self.assertEqual(sol.solve_reference(world(1), max_states=1).status, 'timeout')
        self.assertEqual(sol.solve_reference(world(1), time_limit_seconds=float('inf')).status, 'error')
        t = s12.Task(task_id='t1', world_id='ref-13', request='r', expected_outcome='award', concentration_measures=['quantity_share'])
        self.assertEqual((t.family_version, t.policy_version, t.schema_version), ('1.2', '1.2', '1.2'))


class ProvisionalTable(unittest.TestCase):
    def test_table_matches_fixtures_and_marks_every_row(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('gen12', ROOT / 'scripts' / 'generate_static_v12_provisional_table.py')
        gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen)
        text = (ROOT / 'docs' / 'acceptance' / 'static-v1.2-provisional-values.md').read_text()
        self.assertEqual(text, gen.render(), 'regenerate with scripts/generate_static_v12_provisional_table.py')
        rows = [line for line in text.splitlines() if line.startswith('| ref-')]
        self.assertGreater(len(rows), 40)
        self.assertTrue(all('PROVISIONAL, needs practitioner value' in r for r in rows))
        self.assertIn('Changed from v1.1', text)
        self.assertIn('not independent', text.lower())
        self.assertNotIn(chr(0x2014), text)

    def test_docs_state_review_status_and_have_no_em_dash(self):
        for rel in ('docs/task-families/supplier-allocation-v1.2.md', 'docs/acceptance/static-v1.2-provisional-values.md'):
            text = (ROOT / rel).read_text()
            self.assertIn('not independent', text.lower(), rel)
            self.assertIn('Reviewed by a practitioner: no', text.replace('**', ''), rel)
            self.assertNotIn(chr(0x2014), text, rel)

    def test_fixtures_have_no_em_dash(self):
        for p in V12.glob('ref-*.json'):
            self.assertNotIn(chr(0x2014), p.read_text(), p.name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
