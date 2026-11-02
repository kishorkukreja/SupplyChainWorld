"""Independent tiny-case enumeration: deliberately does not import application code."""
import itertools
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'fixtures' / 'reference_cases'
D = Decimal

def evaluate(w, submission):
    if submission['kind'] != 'award':
        return None
    amounts = {}
    rows = submission['allocations']
    keys = [(r['supplier_id'], r['item_id']) for r in rows]
    if len(set(keys)) != len(keys): return None
    quantities = dict(zip(keys, (r['quantity'] for r in rows)))
    quotes = {(q['supplier_id'], q['item_id']): q for q in w['quotes']}
    if set(quantities) - set(quotes): return None
    for key, qty in quantities.items():
        if type(qty) is not int or qty < 0: return None
        if not qty: continue
        q = quotes[key]
        item = next(i for i in w['items'] if i['item_id'] == key[1])
        if not q['qualified'] or not q['valid_from'] <= w['as_of'] <= q['valid_to'] or q['arrival_date'] > item['due_date']: return None
        if qty > q['capacity'] or qty < q['moq'] or qty % q['multiple']: return None
        if q['unit_price'] is None or q['variable_freight'] is None: return None
        amounts[key[0]] = amounts.get(key[0], D(0)) + qty * (D(q['unit_price']) + D(q['variable_freight']))
    for item in w['items']:
        ident = item['item_id']
        stock = sum(r['quantity'] for r in w['stock'] if r['item_id']==ident and r['status']=='usable')
        inbound = sum(r['quantity'] for r in w['inbound'] if r['item_id']==ident and r['status']=='committed' and r['arrival_date'] <= item['due_date'])
        net = max(0, item['demand']-stock-inbound)
        bought = sum(qty for (s,i),qty in quantities.items() if i==ident)
        if not net <= bought <= net + item['excess_allowance']: return None
    for s in w['suppliers']:
        if s['supplier_id'] in amounts:
            amounts[s['supplier_id']] = (amounts[s['supplier_id']] + D(s['fixed_charge'])).quantize(D('.01'), rounding=ROUND_HALF_UP)
    total = sum(amounts.values(), D(0))
    if total > D(w['constraints']['budget']): return None
    cap = w['constraints']['concentration_limit']
    if cap is not None and total and any(a > D(cap)*total for a in amounts.values()): return None
    if 'claimed_total_cost' in submission and D(submission['claimed_total_cost']) != total: return None
    return total

class ReferenceCases(unittest.TestCase):
    def test_all_ten_hand_results_and_wrong_submissions(self):
        paths = sorted(ROOT.glob('ref-*.json'))
        self.assertEqual(len(paths),10)
        for path in paths:
            with self.subTest(case=path.stem):
                c=json.loads(path.read_text()); w=c['world']; expected=c['expected']
                self.assertFalse(c['review']['practitioner_signoff'])
                self.assertTrue(expected['calculation'])
                if expected['submission']['kind']=='clarification':
                    self.assertTrue(any(q['variable_freight'] is None for q in w['quotes']))
                else:
                    costs=[]
                    for vector in itertools.product(*(range(q['capacity']+1) for q in w['quotes'])):
                        sub={'kind':'award','allocations':[dict(supplier_id=q['supplier_id'],item_id=q['item_id'],quantity=n) for q,n in zip(w['quotes'],vector) if n]}
                        value=evaluate(w,sub)
                        if value is not None: costs.append(value)
                    if expected['optimal_cost'] is None: self.assertEqual(costs,[])
                    else:
                        self.assertEqual(min(costs),D(expected['optimal_cost']))
                        self.assertEqual(evaluate(w,expected['submission']),min(costs))
                        for alternative in expected.get('valid_alternatives',[]): self.assertEqual(evaluate(w,alternative),min(costs))
                for wrong in c['known_wrong']: self.assertIsNone(evaluate(w,wrong['submission']))

if __name__=='__main__': unittest.main(verbosity=2)
