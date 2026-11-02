import copy
import json
from pathlib import Path
import unittest
from decimal import Decimal
from supplychainworld.verification import verify

ROOT = Path(__file__).resolve().parents[1]

def case(number=1):
    return json.loads((ROOT / 'fixtures/reference_cases' / f'ref-{number:02}.json').read_text())

class VerificationTests(unittest.TestCase):
    def test_reference_and_wrong_cases(self):
        for number in range(1, 11):
            c = case(number)
            expected = c['expected']
            with self.subTest(case=number):
                result = verify(c['world'], expected['submission'], expected['submission']['kind'], expected['optimal_cost'])
                self.assertTrue(result.accepted, result.critical_failures)
                for wrong in c['known_wrong']:
                    self.assertFalse(verify(c['world'], wrong['submission'], expected['submission']['kind']).accepted)
                for alternative in expected.get('valid_alternatives', []):
                    self.assertTrue(verify(c['world'], alternative).accepted)

    def test_units_duplicates_fractional_and_fake_infeasibility(self):
        c = case()
        for modification in ('unit', 'duplicate', 'fraction', 'cost'):
            s = copy.deepcopy(c['expected']['submission'])
            if modification == 'unit': s['allocations'][0]['unit'] = 'kg'
            if modification == 'duplicate': s['allocations'] *= 2
            if modification == 'fraction': s['allocations'][0]['quantity'] = 4.0
            if modification == 'cost': s['claimed_total_cost'] = '16.00'
            self.assertFalse(verify(c['world'], s).accepted, modification)
        self.assertFalse(verify(c['world'], {'kind':'infeasible', 'evidence':['solver timeout']}).accepted)
        self.assertFalse(verify(c['world'], {'kind':'clarification', 'field':'quotes.A.component.variable_freight', 'evidence':['unknown']}).accepted)

    def test_supplier_rounding_fixed_fee_and_tie(self):
        c = case()
        w = c['world']
        w['suppliers'][0]['fixed_charge'] = '1.005'
        w['quotes'][0]['unit_price'] = '0.001'
        s = c['expected']['submission']
        s['claimed_total_cost'] = '1.01'
        self.assertEqual(verify(w,s).independent_cost, Decimal('1.01'))
        self.assertTrue(verify(w,s).accepted)
        s['claimed_total_cost'] = '2.01'
        self.assertFalse(verify(w,s).accepted)
        w['suppliers'][0]['fixed_charge'] = '0'
        w['quotes'][0]['unit_price'] = w['quotes'][1]['unit_price']
        s['allocations'][0]['supplier_id'] = 'B'
        s['claimed_total_cost'] = '12.00'
        self.assertTrue(verify(w,s, reference_cost='12.00').accepted)

    def test_malformed_world_and_blank_award_evidence(self):
        for mutation in ('negative', 'duplicate', 'date'):
            c = case()
            if mutation == 'negative': c['world']['items'][0]['demand'] = -1
            if mutation == 'duplicate': c['world']['quotes'].append(c['world']['quotes'][0])
            if mutation == 'date': c['world']['as_of'] = 'bad-date'
            result = verify(c['world'],c['expected']['submission'])
            self.assertFalse(result.accepted)
            self.assertIn('schema_validation',result.critical_failures)
        c = case()
        c['expected']['submission']['evidence'] = ['  ']
        self.assertFalse(verify(c['world'],c['expected']['submission']).accepted)

    def test_id_relabel_and_zero_cost(self):
        c = case()
        original = verify(c['world'], c['expected']['submission'])
        raw = json.dumps(c).replace('component','widget').replace('"A"','"X"').replace('"B"','"Y"')
        renamed = json.loads(raw)
        result = verify(renamed['world'],renamed['expected']['submission'])
        self.assertEqual((result.accepted,result.independent_cost),(original.accepted,original.independent_cost))
        for q in c['world']['quotes']: q['unit_price'] = '0'
        c['world']['constraints']['concentration_limit'] = '0.2'
        c['expected']['submission']['claimed_total_cost'] = '0'
        self.assertTrue(verify(c['world'],c['expected']['submission'],reference_cost='0').accepted)

if __name__ == '__main__': unittest.main()
