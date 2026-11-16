"""Production schema/checker/solver for static rules 1.1 against the v1.1 fixtures (issue #35).

All numeric policy values in these fixtures are PROVISIONAL and not practitioner-confirmed.
The v1.0 modules and fixtures are untouched; one test shows 1.0 and 1.1 disagreeing on purpose.
"""
import copy
import json
import unittest
from decimal import Decimal as D
from pathlib import Path

from pydantic import ValidationError

from supplychainworld import schemas, solvers, verification
from supplychainworld import schemas_v11 as s11
from supplychainworld import solvers_v11 as sol
from supplychainworld import verification_v11 as chk

ROOT = Path(__file__).resolve().parents[1]
V11 = ROOT / 'fixtures' / 'reference_cases_v1_1'


def case(n):
    return json.loads((V11 / f'ref-{n:02}.json').read_text())


def world(n):
    return s11.World.model_validate(case(n)['world'])


def variant(n, mutate):
    c = case(n)
    mutate(c['world'])
    return c['world']


def award(allocs, cost, flags=(), reqs=()):
    return dict(kind='award', allocations=[dict(supplier_id=s, item_id=i, quantity=q) for s, i, q in allocs],
                claimed_total_cost=cost, evidence=['x'], flags=list(flags), clarification_requests=list(reqs))


class FixturesAgainstProduction(unittest.TestCase):
    def test_all_cases_solver_and_checker(self):
        for n in range(1, 23):
            with self.subTest(case=n):
                c = case(n)
                w = s11.World.model_validate(c['world'])
                kind = c['expected']['submission']['kind']
                result = sol.solve_reference(w)
                self.assertEqual(result.status, {'award': 'optimal', 'clarification': 'clarification_required',
                                                 'infeasible': 'infeasible'}[kind])
                exp = c['expected']['optimal_cost']
                self.assertEqual(result.total_cost, D(exp) if exp is not None else None)
                checked = chk.verify(w, result.submission(), expected_outcome=kind, reference_cost=result.total_cost)
                self.assertTrue(checked.accepted, checked.critical_failures)
                expected = chk.verify(w, c['expected']['submission'], expected_outcome=kind, reference_cost=exp)
                self.assertTrue(expected.accepted, expected.critical_failures)
                if kind == 'award':
                    self.assertEqual(expected.optimality, 'optimal')
                    self.assertEqual(expected.independent_cost, D(exp))
                    self.assertEqual(expected.objective_gap, 0)
                    self.assertEqual(set(c['expected']['submission']['flags']), set(result.flags))

    def test_alternatives_and_wrong_answers(self):
        for n in range(1, 23):
            c = case(n)
            w = s11.World.model_validate(c['world'])
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
        r = sol.solve_reference(world(2))
        costs = [c for c, _ in r.band_awards]
        self.assertIn(D('8.00'), costs)
        self.assertIn(D('8.40'), costs)
        self.assertNotIn(D('10.40'), costs)

    def test_heuristic_is_feasible_but_not_certified(self):
        for n in (1, 3, 8, 12, 17, 22):
            with self.subTest(case=n):
                h = sol.solve_heuristic(world(n))
                self.assertIn(h.status, {'feasible', 'error'})
                if h.status == 'feasible':
                    self.assertTrue(chk.verify(world(n), h.submission()).accepted)
        # fixed-tier case: greedy by variable cost alone is allowed to be wrong; reference stays optimal
        self.assertEqual(sol.solve_reference(world(20)).total_cost, D('8.00'))

    def test_v10_fixtures_untouched_and_still_v10(self):
        self.assertEqual(len(list((ROOT / 'fixtures' / 'reference_cases').glob('ref-*.json'))), 10)
        w10 = json.loads((ROOT / 'fixtures' / 'reference_cases' / 'ref-02.json').read_text())['world']
        self.assertEqual(w10['schema_version'], '1.0')
        self.assertEqual(verification.CHECKER_VERSION, '1.0')
        self.assertEqual(chk.CHECKER_VERSION, '1.1')
        self.assertTrue(solvers.solve_reference(schemas.World.model_validate(w10)).total_cost == D('8.00'))


class RuleRegressions(unittest.TestCase):
    # A1
    def test_net_requirement_with_safety_stock_and_late_credit(self):
        r = chk.verify(world(1), award([('A', 'component', 8)], '16.00'))
        self.assertEqual(r.net_requirements, {'component': 8})
        self.assertEqual(chk.verify(world(11), award([('A', 'component', 3)], '6.00')).net_requirements, {'component': 3})

    def test_late_inbound_window_edges(self):
        def net(tol, credit, arrival):
            def m(w):
                w['inbound'] = [dict(item_id='component', quantity=4, arrival_date=arrival, status='committed')]
                w['policy'].update(late_inbound_tolerance_days=tol, late_inbound_credit=credit)
            return chk.verify(variant(11, m), award([('A', 'component', 6)], '12.00')).net_requirements['component']
        self.assertEqual(net(3, '0.50', '2026-11-13'), 4)   # 3 days late, inside window: credit 2
        self.assertEqual(net(3, '0.50', '2026-11-14'), 6)   # 4 days late: no credit
        self.assertEqual(net(3, '0.25', '2026-11-11'), 5)   # floor(4*0.25)=1
        self.assertEqual(net(0, '1', '2026-11-11'), 6)      # zero tolerance: late never counts
        self.assertEqual(net(3, '1', '2026-11-10'), 2)      # on time counts in full regardless of credit

    def test_held_and_reserved_stock_never_count(self):
        def m(w):
            w['stock'] = [dict(item_id='component', quantity=9, status='held'), dict(item_id='component', quantity=9, status='reserved')]
        self.assertEqual(chk.verify(variant(11, m), award([('A', 'component', 6)], '12.00')).net_requirements['component'], 6 - 2 - 1)

    # A2
    def test_three_concentration_measures_are_distinct(self):
        w13 = case(13)['world']
        spend_only = copy.deepcopy(w13)
        spend_only['constraints']['concentration'] = [dict(measure='spend_share', limit='0.50', item_ids=None)]
        a = award([('A', 'Q', 4), ('B', 'P', 4)], '8.80')
        self.assertTrue(chk.verify(w13, a).accepted)                 # quantity share 0.5 each
        self.assertFalse(chk.verify(spend_only, a).accepted)         # B holds 4.80 / 8.80
        qty_only = copy.deepcopy(w13)
        qty_only['constraints']['concentration'][0]['limit'] = '0.40'
        self.assertIn('concentration.0.quantity_share', chk.verify(qty_only, a).critical_failures)

    def test_per_item_share_and_zero_denominator(self):
        r = chk.verify(case(14)['world'], award([('A', 'P', 2), ('B', 'P', 2), ('A', 'Q', 2)], '8.00'))
        self.assertIn('concentration.0.per_item_share', r.critical_failures)
        w = case(15)['world']
        w['items'][0]['demand'] = 0
        self.assertTrue(chk.verify(w, award([], '0')).accepted)       # zero spend passes concentration

    def test_concentration_rule_validation(self):
        w = case(13)['world']
        w['constraints']['concentration'] = [dict(measure='quantity_share', limit='0.5', item_ids=None)]
        with self.assertRaises(ValidationError):
            s11.World.model_validate(w)
        w['constraints']['concentration'] = [dict(measure='spend_share', limit='1.5', item_ids=None)]
        with self.assertRaises(ValidationError):
            s11.World.model_validate(w)

    # A3
    def test_gap_is_reported_exactly_alongside_equivalence(self):
        r = chk.verify(world(16), award([('B', 'component', 10)], '50.40'), reference_cost='50.00')
        self.assertEqual((r.optimality, r.objective_gap, r.objective_gap_pct), ('equivalent_to_optimal', D('0.40'), D('0.008')))
        self.assertTrue(r.accepted)
        far = chk.verify(world(16), award([('C', 'component', 10)], '52.00'), reference_cost='50.00')
        self.assertEqual((far.optimality, far.objective_gap), ('suboptimal', D('2.00')))
        self.assertTrue(far.accepted, 'a suboptimal feasible award is not a hard-policy violation')

    def test_non_cost_metrics_are_separate_and_never_change_cost(self):
        r = chk.verify(world(16), award([('B', 'component', 10)], '50.40'), reference_cost='50.00')
        self.assertEqual(r.non_cost_metrics['quantity_weighted_reliability'], '0.9500')
        self.assertEqual(r.non_cost_metrics['max_lead_time_risk'], '0.20')
        self.assertEqual(r.independent_cost, D('50.40'))
        self.assertEqual(r.non_cost_metrics['min_arrival_slack_days'], 1)

    def test_zero_tolerance_means_exact_ties_only(self):
        r = chk.verify(world(21), award([('B', 'component', 4)], '4.0180'), reference_cost='4.0164')
        self.assertEqual((r.optimality, r.objective_gap), ('suboptimal', D('0.0016')))

    # A4
    def test_missing_terms_never_become_zero(self):
        r = chk.verify(world(9), award([('A', 'component', 4)], '4.00'))
        self.assertIn('allocation.0.commercial_terms', r.critical_failures)
        self.assertFalse(r.accepted)

    def test_estimated_path_requires_flag_request_and_limit(self):
        good = award([('A', 'component', 4)], '9.00', ['estimated:A:component'], ['quotes.A.component.variable_freight'])
        self.assertTrue(chk.verify(world(17), good).accepted)
        self.assertEqual(chk.verify(world(17), good).estimated_lines, ['A:component'])
        for bad in (award([('A', 'component', 4)], '9.00', [], ['quotes.A.component.variable_freight']),
                    award([('A', 'component', 4)], '9.00', ['estimated:A:component'], [])):
            self.assertFalse(chk.verify(world(17), bad).accepted)

    def test_approval_limit_boundary_is_strictly_under(self):
        def at(limit):
            def m(w):
                w['constraints']['approval_limit'] = limit
            return chk.verify(variant(17, m), award([('A', 'component', 4)], '9.00', ['estimated:A:component'],
                                                  ['quotes.A.component.variable_freight'])).accepted
        self.assertTrue(at('9.01'))
        self.assertFalse(at('9.00'))
        self.assertFalse(at(None))

    def test_critical_part_escalates(self):
        w = case(18)['world']
        est = award([('A', 'component', 4)], '9.00', ['estimated:A:component'], ['quotes.A.component.variable_freight'])
        self.assertIn('allocation.0.estimate_not_critical', chk.verify(w, est).critical_failures)
        self.assertEqual(sol.solve_reference(s11.World.model_validate(w)).status, 'clarification_required')

    def test_clarification_must_be_escalated_and_name_a_missing_field(self):
        w = case(9)['world']
        good = dict(kind='clarification', field='quotes.A.component.variable_freight', disposition='record_and_escalate', evidence=['e'])
        self.assertTrue(chk.verify(w, good).accepted)
        self.assertIn('clarification_escalated', chk.verify(w, {**good, 'disposition': None}).critical_failures)
        self.assertIn('missing_field', chk.verify(w, {**good, 'field': 'quotes.A.component.unit_price'}).critical_failures)

    # A5
    def test_fixed_charge_tiers(self):
        for units, expected in ((1, '1.00'), (4, '4.00'), (5, '5.00'), (6, '6.00')):
            w = case(20)['world']
            w['items'][0]['demand'] = units
            cost = units * D('1.00') + (D('2.00') if units >= 5 else D('6.00'))
            self.assertEqual(chk.verify(w, award([('A', 'component', units)], str(cost))).independent_cost, cost)
        w = case(20)['world']
        # value tier edge: B goods value exactly 10.00 -> second tier
        w['quotes'][1]['unit_price'] = '2.00'
        w['items'][0]['demand'] = 5
        r = chk.verify(w, award([('B', 'component', 5)], '11.00'))
        self.assertEqual(r.independent_cost, D('11.00'))
        w['quotes'][1]['unit_price'] = '1.999'
        self.assertEqual(chk.verify(w, award([('B', 'component', 5)], '12.995')).independent_cost, D('12.995'))

    def test_fixed_charge_schema_validation(self):
        w = case(20)['world']
        w['suppliers'][0]['fixed_charge_table'][0]['from_measure'] = '1'
        with self.assertRaises(ValidationError):
            s11.World.model_validate(w)
        w = case(20)['world']
        w['suppliers'][0]['fixed_charge'] = '1.00'
        with self.assertRaises(ValidationError):
            s11.World.model_validate(w)

    def test_no_rounding_v10_and_v11_disagree(self):
        c = case(21)
        w11 = s11.World.model_validate(c['world'])
        r11 = chk.verify(w11, award([('A', 'component', 4)], '4.0164'), reference_cost='4.0164')
        self.assertTrue(r11.accepted)
        self.assertEqual(r11.independent_cost, D('4.0164'))
        # The same numbers under frozen v1.0 rules round each supplier to cents.
        w10 = json.loads(json.dumps(c['world']))
        w10['schema_version'] = '1.0'
        for key in ('policy',):
            w10.pop(key)
        w10['constraints'] = dict(budget='4.02', concentration_limit=None)
        w10['items'] = [dict(item_id='component', unit='each', demand=4, due_date='2026-11-10', excess_allowance=0, schema_version='1.0')]
        w10['suppliers'] = [dict(supplier_id=s['supplier_id'], fixed_charge='0.00', schema_version='1.0') for s in w10['suppliers']]
        w10['quotes'] = [dict(schema_version='1.0', **{k: q[k] for k in ('supplier_id', 'item_id', 'unit_price', 'variable_freight', 'capacity', 'moq', 'multiple', 'qualified', 'valid_from', 'valid_to', 'arrival_date')}) for q in w10['quotes']]
        w10['stock'], w10['inbound'] = [], []
        w10['visibility'] = dict(classification='public_synthetic', schema_version='1.0')
        w10v = schemas.World.model_validate(w10)
        v10 = verification.verify(w10v, dict(kind='award', allocations=[dict(supplier_id='A', item_id='component', quantity=4)],
                                             claimed_total_cost='4.02', evidence=['x']))
        self.assertTrue(v10.accepted, v10.critical_failures)
        self.assertEqual(v10.independent_cost, D('4.02'))
        self.assertNotEqual(v10.independent_cost, r11.independent_cost)
        self.assertEqual(solvers.solve_reference(w10v).total_cost, D('4.01'))                    # 1.0: rounding artifact, split A3+B1 = 3.01+1.00
        self.assertEqual(sol.solve_reference(w11).total_cost, D('4.0164'))                       # 1.1: A strictly wins
        self.assertFalse(chk.verify(w11, award([('A', 'component', 4)], '4.02')).accepted)       # v1.0 claim rejected

    # A6
    def test_moq_excess_needs_flag_and_stays_under_shelf_cap(self):
        w = case(8)['world']
        self.assertTrue(chk.verify(w, award([('A', 'component', 4)], '4.00', ['moq_excess:component'])).accepted)
        self.assertIn('item.component.moq_excess_flag', chk.verify(w, award([('A', 'component', 4)], '4.00')).critical_failures)
        w['items'][0]['max_excess'] = 0
        self.assertIn('item.component.shelf_life_cap', chk.verify(w, award([('A', 'component', 4)], '4.00', ['moq_excess:component'])).critical_failures)

    def test_moq_excess_not_justified_when_exact_quantity_reachable(self):
        w = case(8)['world']
        w['quotes'][1]['capacity'] = 3          # B can now reach exactly 3: MOQ no longer justifies excess
        r = chk.verify(w, award([('A', 'component', 4)], '4.00', ['moq_excess:component']))
        self.assertIn('item.component.excess', r.critical_failures)
        w['items'][0]['moq_excess_allowed'] = False
        w['quotes'][1]['capacity'] = 2
        self.assertIn('item.component.excess', chk.verify(w, award([('A', 'component', 4)], '4.00', ['moq_excess:component'])).critical_failures)

    def test_shelf_cap_binds_even_inside_explicit_allowance(self):
        r = chk.verify(world(22), award([('C', 'component', 6)], '6.00'))
        self.assertIn('item.component.shelf_life_cap', r.critical_failures)
        self.assertNotIn('item.component.excess', r.critical_failures)

    # infeasibility certificate
    def test_infeasible_claim_needs_capacity_certificate(self):
        w = case(10)['world']
        fake = dict(kind='infeasible', evidence=['Insufficient capacity somewhere'])
        self.assertTrue(chk.verify(w, fake).accepted)
        w['items'][0]['safety_stock'] = 0
        self.assertIn('capacity_certificate', chk.verify(w, fake).critical_failures)

    def test_schema_version_strict(self):
        w = case(1)['world']
        w['schema_version'] = '1.0'
        with self.assertRaises(ValidationError):
            s11.World.model_validate(w)
        self.assertFalse(chk.verify(w, award([], '0')).accepted)

    def test_solver_search_limits(self):
        self.assertEqual(sol.solve_reference(world(1), max_states=1).status, 'timeout')
        self.assertEqual(sol.solve_reference(world(1), time_limit_seconds=float('inf')).status, 'error')

    def test_task_contract(self):
        t = s11.Task(task_id='t1', world_id='ref-13', request='r', expected_outcome='award', concentration_measures=['quantity_share'])
        self.assertEqual((t.family_version, t.policy_version, t.schema_version), ('1.1', '1.1', '1.1'))



class ProvisionalTable(unittest.TestCase):
    def test_table_matches_fixtures_and_marks_every_row(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('gen', ROOT / 'scripts' / 'generate_static_v11_provisional_table.py')
        gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen)
        text = (ROOT / 'docs' / 'acceptance' / 'static-v1.1-provisional-values.md').read_text()
        self.assertEqual(text, gen.render(), 'regenerate with scripts/generate_static_v11_provisional_table.py')
        rows = [line for line in text.splitlines() if line.startswith('| ref-')]
        self.assertGreater(len(rows), 40)
        self.assertTrue(all('PROVISIONAL, needs practitioner value' in r for r in rows))
        self.assertNotIn(chr(0x2014), text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
