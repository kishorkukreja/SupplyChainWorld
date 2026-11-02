import json
from pathlib import Path
import unittest
from decimal import Decimal
from supplychainworld.schemas import World
from supplychainworld.solvers import solve_reference, solve_heuristic
from supplychainworld.verification import verify

ROOT = Path(__file__).resolve().parents[1]

def case(number):
    return json.loads((ROOT / 'fixtures/reference_cases' / f'ref-{number:02}.json').read_text())

class SolverTests(unittest.TestCase):
    def test_ten_hand_worked_cases(self):
        for number in range(1, 11):
            with self.subTest(number=number):
                data = case(number)
                result = solve_reference(World.model_validate(data['world']))
                kind = data['expected']['submission']['kind']
                self.assertEqual(result.status, {'award':'optimal', 'clarification':'clarification_required', 'infeasible':'infeasible'}[kind])
                expected = data['expected']['optimal_cost']
                self.assertEqual(result.total_cost, Decimal(expected) if expected is not None else None)
                self.assertEqual(result.submission().kind, kind)
                checked = verify(World.model_validate(data['world']), result.submission(), expected_outcome=kind, reference_cost=result.total_cost)
                self.assertTrue(checked.accepted, checked.critical_failures)
                if kind == 'award':
                    self.assertEqual(checked.independent_cost, result.total_cost)

    def test_invalid_limits_report_error(self):
        world = World.model_validate(case(1)['world'])
        for limits in ({'max_states': -1}, {'max_states': 1.5}, {'time_limit_seconds': float('nan')}):
            self.assertEqual(solve_reference(world, **limits).status, 'error')

    def test_timeout_is_unresolved(self):
        world = World.model_validate(case(1)['world'])
        for limits in ({'max_states': 0}, {'time_limit_seconds': 0}, {'max_states': 1}):
            result = solve_reference(world, **limits)
            self.assertEqual(result.status, 'timeout')
            self.assertEqual(result.lower_bound, Decimal('0'))
            with self.assertRaises(ValueError):
                result.submission()

    def test_timeout_keeps_incumbent_without_optimal_claim(self):
        world = World.model_validate(case(1)['world'])
        result = solve_reference(world, max_states=8)
        self.assertEqual(result.status, 'timeout')
        self.assertIsNotNone(result.total_cost)
        self.assertEqual(result.submission().kind, 'award')

    def test_ties_and_zero_spend(self):
        data = case(1)['world']
        data['quotes'][1]['unit_price'] = '2.00'
        result = solve_reference(World.model_validate(data))
        self.assertEqual(result.status, 'optimal')
        self.assertEqual(result.total_cost, Decimal('8.00'))
        self.assertTrue(verify(World.model_validate(data), result.submission()).accepted)
        alternative = dict(kind='award', allocations=[dict(supplier_id='A', item_id='component', quantity=4)], claimed_total_cost='8.00', evidence=['Equal cost alternate'])
        self.assertTrue(verify(World.model_validate(data), alternative).accepted)
        for q in data['quotes']:
            q['unit_price'] = '0'
        data['constraints']['concentration_limit'] = '0'
        self.assertEqual(solve_reference(World.model_validate(data)).total_cost, Decimal('0.00'))

    def test_heuristic_is_feasible_not_optimal_and_can_fail(self):
        result = solve_heuristic(World.model_validate(case(1)['world']))
        self.assertEqual(result.status, 'feasible')
        self.assertEqual(result.total_cost, Decimal('8.00'))
        self.assertEqual(solve_heuristic(World.model_validate(case(10)['world'])).status, 'error')

    def test_fixed_fee_and_supplier_rounding(self):
        data = case(1)['world']
        data['quotes'] = data['quotes'][:1]
        data['quotes'][0]['unit_price'] = '0.00125'
        data['suppliers'][0]['fixed_charge'] = '0.01'
        self.assertEqual(solve_reference(World.model_validate(data)).total_cost, Decimal('0.02'))

if __name__ == '__main__':
    unittest.main()
