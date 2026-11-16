"""Independent enumeration for the static v1.1 reference cases (issue #35).

Deliberately imports NO production code: no supplychainworld module, no schema, no checker, no solver.
It restates rules 1.1 from docs/task-families/supplier-allocation-v1.1.md and enumerates every
quantity vector of these tiny instances. All numeric policy values are PROVISIONAL.
"""
import json
import unittest
from datetime import date, timedelta
from decimal import Decimal as D
from math import floor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'fixtures' / 'reference_cases_v1_1'


def day(s):
    return date.fromisoformat(s)


def net_of(w, item):
    iid, due = item['item_id'], day(item['due_date'])
    pol = w['policy']
    usable = sum(r['quantity'] for r in w['stock'] if r['item_id'] == iid and r['status'] == 'usable')
    on_time = sum(r['quantity'] for r in w['inbound'] if r['item_id'] == iid and day(r['arrival_date']) <= due)
    credit = sum(floor(D(r['quantity']) * D(pol['late_inbound_credit'])) for r in w['inbound']
                 if r['item_id'] == iid and due < day(r['arrival_date']) <= due + timedelta(days=pol['late_inbound_tolerance_days']))
    return max(0, item['demand'] + item['safety_stock'] - usable - on_time - credit)


def usable_quote(w, q):
    item = next(i for i in w['items'] if i['item_id'] == q['item_id'])
    return q['qualified'] and q['valid_from'] <= w['as_of'] <= q['valid_to'] and day(q['arrival_date']) <= day(item['due_date'])


def order_ok(q, n):
    return n == 0 or (n <= q['capacity'] and n >= q['moq'] and n % q['multiple'] == 0)


def fixed_charge(s, units, goods):
    if s['fixed_charge_basis'] == 'flat':
        return D(s['fixed_charge'])
    m = D(units) if s['fixed_charge_basis'] == 'order_units' else goods
    return [D(t['charge']) for t in s['fixed_charge_table'] if D(t['from_measure']) <= m][-1]


def reachable_floor(w, item, net):
    totals = {0}
    for q in w['quotes']:
        if q['item_id'] == item['item_id'] and usable_quote(w, q):
            totals = {t + n for t in totals for n in range(0, q['capacity'] + 1) if order_ok(q, n) and t + n <= 200}
    above = [t for t in totals if t >= net]
    return min(above) if above else None


def evaluate(w, sub, auto_flags=False):
    """Return the exact total cost of a feasible award submission, else None. Exact Decimal, no rounding."""
    if sub['kind'] != 'award':
        return None
    quotes = {(q['supplier_id'], q['item_id']): q for q in w['quotes']}
    sups = {s['supplier_id']: s for s in w['suppliers']}
    rows = [(r['supplier_id'], r['item_id'], r['quantity']) for r in sub['allocations']]
    if len({(s, i) for s, i, _ in rows}) != len(rows):
        return None
    flags, reqs = set(sub.get('flags', [])), set(sub.get('clarification_requests', []))
    goods, units, bought, line_units = {}, {}, {}, {}
    need_flags, need_reqs = set(), set()
    for sid, iid, n in rows:
        if (sid, iid) not in quotes or type(n) is not int or n < 0:
            return None
        if not n:
            continue
        q = quotes[(sid, iid)]
        item = next(i for i in w['items'] if i['item_id'] == iid)
        if not usable_quote(w, q) or not order_ok(q, n):
            return None
        parts, est = [], False
        for f in ('unit_price', 'variable_freight'):
            v = q[f]
            if v is None:
                est = True
                v = q['last_known_' + f]
                if v is None:
                    return None
                need_reqs.add(f'quotes.{sid}.{iid}.{f}')
            parts.append(D(v))
        value = n * (parts[0] + parts[1])
        if est:
            limit = w['constraints']['approval_limit']
            if item['critical'] or limit is None or not value < D(limit):
                return None
            need_flags.add(f'estimated:{sid}:{iid}')
        goods[sid] = goods.get(sid, D(0)) + value
        units[sid] = units.get(sid, 0) + n
        bought[iid] = bought.get(iid, 0) + n
        line_units[(sid, iid)] = n
    for item in w['items']:
        iid, need = item['item_id'], net_of(w, item)
        have = bought.get(iid, 0)
        if have < need:
            return None
        if item['max_excess'] is not None and have - need > item['max_excess']:
            return None
        if have > need + item['excess_allowance']:
            if not item['moq_excess_allowed'] or have != reachable_floor(w, item, need):
                return None
            need_flags.add(f'moq_excess:{iid}')
    if auto_flags:
        flags, reqs = need_flags, need_reqs
    if not need_flags <= flags or not need_reqs <= reqs:
        return None
    spend = {sid: goods[sid] + fixed_charge(sups[sid], units[sid], goods[sid]) for sid in goods}
    total = sum(spend.values(), D(0))
    if total > D(w['constraints']['budget']):
        return None
    for rule in w['constraints']['concentration']:
        lim = D(rule['limit'])
        if rule['measure'] == 'spend_share':
            if total and any(v > lim * total for v in spend.values()):
                return None
        elif rule['measure'] == 'quantity_share':
            scope = set(rule['item_ids'])
            den = sum(n for (s, i), n in line_units.items() if i in scope)
            for sid in sups:
                if sum(n for (s, i), n in line_units.items() if s == sid and i in scope) > lim * den:
                    return None
        else:
            for item in w['items']:
                if rule['item_ids'] is not None and item['item_id'] not in rule['item_ids']:
                    continue
                den = sum(n for (s, i), n in line_units.items() if i == item['item_id'])
                if any(n > lim * den for (s, i), n in line_units.items() if i == item['item_id']):
                    return None
    if 'claimed_total_cost' in sub and D(sub['claimed_total_cost']) != total:
        return None
    return total


def enumerate_awards(w):
    """Yield (total, allocations) for every feasible award; ceilings only prune impossible totals."""
    quotes = [q for q in w['quotes'] if usable_quote(w, q)]
    limit = {}
    for item in w['items']:
        need = net_of(w, item)
        sizes = [q['capacity'] for q in quotes if q['item_id'] == item['item_id']]
        limit[item['item_id']] = need + (max(sizes, default=0) if item['moq_excess_allowed'] else item['excess_allowance'])
    out, vec = [], []

    def rec(k, running):
        if k == len(quotes):
            allocs = [dict(supplier_id=q['supplier_id'], item_id=q['item_id'], quantity=n) for q, n in zip(quotes, vec) if n]
            v = evaluate(w, dict(kind='award', allocations=allocs), auto_flags=True)
            if v is not None:
                out.append((v, allocs))
            return
        q = quotes[k]
        for n in range(0, q['capacity'] + 1):
            if running.get(q['item_id'], 0) + n > limit[q['item_id']]:
                break
            if not order_ok(q, n):
                continue
            vec.append(n)
            running[q['item_id']] = running.get(q['item_id'], 0) + n
            rec(k + 1, running)
            running[q['item_id']] -= n
            vec.pop()
    rec(0, {})
    return out


def missing_fields(w):
    return {f"quotes.{q['supplier_id']}.{q['item_id']}.{f}" for q in w['quotes'] if usable_quote(w, q)
            for f in ('unit_price', 'variable_freight') if q[f] is None}


def exception_valid(w, sub, feasible):
    if sub['kind'] == 'clarification':
        return sub.get('field') in missing_fields(w) and sub.get('disposition') == 'record_and_escalate' and not feasible
    if sub['kind'] == 'infeasible':
        return not feasible
    return False


def band_status(w, cost, optimum):
    gap = cost - optimum
    if gap == 0:
        return 'optimal'
    pol = w['policy']
    if gap <= D(pol['cost_tolerance_abs']) or gap <= D(pol['cost_tolerance_pct']) * optimum:
        return 'equivalent_to_optimal'
    return 'suboptimal'


class ReferenceCasesV11(unittest.TestCase):
    def cases(self):
        paths = sorted(ROOT.glob('ref-*.json'))
        return [(p.stem, json.loads(p.read_text())) for p in paths]

    def test_case_count_and_labels(self):
        cases = self.cases()
        self.assertEqual(len(cases), 22)
        for name, c in cases:
            with self.subTest(case=name):
                self.assertEqual(c['world']['schema_version'], '1.1')
                self.assertFalse(c['review']['practitioner_signoff'])
                self.assertFalse(c['review']['reviewed_by_practitioner'])
                self.assertTrue(c['review']['awaiting_re_review'])
                self.assertIn('PROVISIONAL', c['review']['values_status'])
                self.assertTrue(c['expected']['calculation'])
                self.assertTrue(c['known_wrong'])
                if int(name[4:]) <= 10:
                    self.assertTrue(c['expected']['valid_alternatives'], 'ten tuned cases need an alternative valid answer')

    def test_every_case_by_independent_enumeration(self):
        for name, c in self.cases():
            with self.subTest(case=name):
                w, exp = c['world'], c['expected']
                awards = enumerate_awards(w)
                sub = exp['submission']
                if sub['kind'] == 'award':
                    optimum = min(v for v, _ in awards)
                    self.assertEqual(optimum, D(exp['optimal_cost']))
                    self.assertEqual(evaluate(w, sub), optimum)
                else:
                    self.assertEqual(awards, [], 'exception cases must have no feasible award')
                    self.assertIsNone(exp['optimal_cost'])
                    self.assertTrue(exception_valid(w, sub, awards))
                for alt in exp['valid_alternatives']:
                    s = alt['submission']
                    if s['kind'] == 'award':
                        v = evaluate(w, s)
                        self.assertIsNotNone(v, alt['note'])
                        self.assertEqual(band_status(w, v, optimum), alt['status'], alt['note'])
                        self.assertEqual(v, D(alt['cost']))
                    else:
                        self.assertTrue(exception_valid(w, s, awards), alt['note'])
                for wrong in c['known_wrong']:
                    s = wrong['submission']
                    if s['kind'] == 'award':
                        self.assertIsNone(evaluate(w, s), wrong['reason'])
                    else:
                        self.assertFalse(exception_valid(w, s, awards), wrong['reason'])

    def test_ties_and_alternatives_exist_for_tie_cases(self):
        by = dict(self.cases())
        for name in ('ref-05', 'ref-06', 'ref-07', 'ref-14', 'ref-15'):
            awards = enumerate_awards(by[name]['world'])
            best = min(v for v, _ in awards)
            self.assertGreater(len([1 for v, _ in awards if v == best]), 1, name)

    def test_equivalence_band_edges(self):
        w = dict(self.cases())['ref-04']['world']
        self.assertEqual(band_status(w, D('8.16'), D('8.00')), 'equivalent_to_optimal')   # exactly on the band
        self.assertEqual(band_status(w, D('8.1601'), D('8.00')), 'suboptimal')

    def test_v10_rounding_and_v11_exact_arithmetic_differ(self):
        """A, B cost 4.0164 and 4.0180 exactly; v1.0 rounds both to 4.02, v1.1 never rounds."""
        w = dict(self.cases())['ref-21']['world']
        costs = {q['supplier_id']: 4 * D(q['unit_price']) for q in w['quotes']}
        self.assertEqual(costs, {'A': D('4.0164'), 'B': D('4.0180')})
        self.assertEqual({k: v.quantize(D('0.01'), rounding='ROUND_HALF_UP') for k, v in costs.items()},
                         {'A': D('4.02'), 'B': D('4.02')})
        self.assertEqual(sorted(costs.values())[0], D('4.0164'))
        self.assertLess(costs['A'], costs['B'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
