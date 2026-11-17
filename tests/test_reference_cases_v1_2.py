"""Independent enumeration for the static v1.2 reference cases (re-review of issue #35).

Deliberately imports NO production code: no supplychainworld module, no schema, no checker, no solver.
It restates rules 1.2 from docs/task-families/supplier-allocation-v1.2.md and enumerates every
quantity vector of these small instances. Safety stock is computed here by a different method from production
(a 60-digit Decimal square root), from the documented z-table. All numeric policy values are PROVISIONAL.
"""
import json
import unittest
from datetime import date, timedelta
from decimal import Decimal as D, ROUND_CEILING, localcontext
from math import floor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'fixtures' / 'reference_cases_v1_2'
Z = {D('0.90'): D('1.2816'), D('0.95'): D('1.6449'), D('0.975'): D('1.9600'), D('0.99'): D('2.3263')}


def day(s):
    return date.fromisoformat(s)


def safety_of(item):
    if item['safety_stock_override'] is not None:
        return item['safety_stock_override']
    if item['service_level'] is None:
        return 0
    with localcontext() as ctx:
        ctx.prec = 60
        value = Z[D(item['service_level'])] * D(item['demand_std']) * D(item['lead_time_periods']).sqrt()
        return int(value.to_integral_value(rounding=ROUND_CEILING))


def net_of(w, item):
    iid, due = item['item_id'], day(item['due_date'])
    pol = w['policy']
    usable = sum(r['quantity'] for r in w['stock'] if r['item_id'] == iid and r['status'] == 'usable')
    on_time = sum(r['quantity'] for r in w['inbound'] if r['item_id'] == iid and day(r['arrival_date']) <= due)
    credit = sum(floor(D(r['quantity']) * D(pol['late_inbound_credit'])) for r in w['inbound']
                 if r['item_id'] == iid and due < day(r['arrival_date']) <= due + timedelta(days=pol['late_inbound_tolerance_days']))
    return max(0, item['demand'] + safety_of(item) - usable - on_time - credit)


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
            totals = {t + n for t in totals for n in range(0, q['capacity'] + 1) if order_ok(q, n) and t + n <= 300}
    above = [t for t in totals if t >= net]
    return min(above) if above else None


def estimate_cost(q):
    parts = []
    for f in ('unit_price', 'variable_freight'):
        v = q[f] if q[f] is not None else q['last_known_' + f]
        if v is None:
            return None
        parts.append(D(v))
    return parts[0] + parts[1]


def blocking_fields(w):
    """Ask first: eligible quotes of needed items with a missing term that the estimate path does not cover."""
    limit = w['constraints']['approval_limit']
    out = set()
    for q in w['quotes']:
        item = next(i for i in w['items'] if i['item_id'] == q['item_id'])
        need = net_of(w, item)
        if not usable_quote(w, q) or need == 0:
            continue
        miss = [f for f in ('unit_price', 'variable_freight') if q[f] is None]
        if not miss:
            continue
        cost = estimate_cost(q)
        qty = min(q['capacity'], max(need, q['moq']))
        covered = cost is not None and not item['critical'] and limit is not None and qty * cost <= D(limit)
        if not covered:
            out |= {f"quotes.{q['supplier_id']}.{q['item_id']}.{f}" for f in miss}
    return out


def approval_fields(w):
    out = set()
    for item in w['items']:
        need = net_of(w, item)
        if need == 0 or not item['moq_excess_allowed']:
            continue
        floor_ = reachable_floor(w, item, need)
        if floor_ is not None and floor_ > need + item['excess_allowance'] and not any(a['item_id'] == item['item_id'] for a in w['approvals']):
            out.add(f"approvals.moq_excess.{item['item_id']}")
    return out


def evaluate(w, sub, auto=False):
    """Return the exact total cost of a feasible award submission, else None. Exact Decimal, no rounding."""
    if sub['kind'] != 'award':
        return None
    if blocking_fields(w):
        return None            # ask first: never award around a gap the estimate path cannot cover
    quotes = {(q['supplier_id'], q['item_id']): q for q in w['quotes']}
    sups = {s['supplier_id']: s for s in w['suppliers']}
    rows = [(r['supplier_id'], r['item_id'], r['quantity']) for r in sub['allocations']]
    if len({(s, i) for s, i, _ in rows}) != len(rows):
        return None
    flags, reqs, refs = set(sub.get('flags', [])), set(sub.get('clarification_requests', [])), set(sub.get('approval_refs', []))
    goods, units, bought, line_units, item_goods = {}, {}, {}, {}, {}
    need_flags, need_reqs = set(), set()
    limit = w['constraints']['approval_limit']
    for sid, iid, n in rows:
        if (sid, iid) not in quotes or type(n) is not int or n < 0:
            return None
        if not n:
            continue
        q = quotes[(sid, iid)]
        item = next(i for i in w['items'] if i['item_id'] == iid)
        if not usable_quote(w, q) or not order_ok(q, n):
            return None
        est = any(q[f] is None for f in ('unit_price', 'variable_freight'))
        cost = estimate_cost(q)
        if cost is None:
            return None
        value = n * cost
        if est:
            for f in ('unit_price', 'variable_freight'):
                if q[f] is None:
                    need_reqs.add(f'quotes.{sid}.{iid}.{f}')
            if item['critical'] or limit is None or not value <= D(limit):   # at or below the limit
                return None
            need_flags.add(f'estimated:{sid}:{iid}')
        goods[sid] = goods.get(sid, D(0)) + value
        units[sid] = units.get(sid, 0) + n
        bought[iid] = bought.get(iid, 0) + n
        item_goods[iid] = item_goods.get(iid, D(0)) + value
        line_units[(sid, iid)] = n
    thr = D(w['policy']['moq_excess_approval_threshold'])
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
            excess = have - need - item['excess_allowance']
            if excess * item_goods[iid] > thr * have:                 # value above the threshold needs approval
                on_file = sorted(a['approval_id'] for a in w['approvals'] if a['item_id'] == iid)
                if auto:
                    if not on_file:
                        return None
                    refs.add(on_file[0])
                elif not (set(on_file) & refs):
                    return None
    if auto:
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
            v = evaluate(w, dict(kind='award', allocations=allocs), auto=True)
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


def exception_valid(w, sub, feasible):
    if sub['kind'] == 'clarification':
        askable = blocking_fields(w) | approval_fields(w)
        return sub.get('field') in askable and sub.get('disposition') == 'record_and_escalate' and not feasible
    if sub['kind'] == 'infeasible':
        # supported only by an eligible order-capacity shortfall on some item
        for item in w['items']:
            top = sum(max([n for n in range(q['capacity'] + 1) if order_ok(q, n)]) for q in w['quotes']
                      if q['item_id'] == item['item_id'] and usable_quote(w, q))
            if top < net_of(w, item):
                return not feasible
        return False
    return False


def tolerance_pct(w, optimum):
    pol = w['policy']
    scale = D(pol['cost_tolerance_reference_value'])
    pct = D(0)
    for tier in pol['cost_tolerance_tiers']:
        if optimum >= D(tier['from_ratio']) * scale:
            pct = D(tier['pct'])
    return pct


def band_status(w, cost, optimum):
    gap = cost - optimum
    if gap == 0:
        return 'optimal'
    if gap <= D(w['policy']['cost_tolerance_abs']) or gap <= tolerance_pct(w, optimum) * optimum:
        return 'equivalent_to_optimal'
    return 'suboptimal'


class ReferenceCasesV12(unittest.TestCase):
    def cases(self):
        paths = sorted(ROOT.glob('ref-*.json'))
        return [(p.stem, json.loads(p.read_text())) for p in paths]

    def test_case_count_and_labels(self):
        cases = self.cases()
        self.assertEqual(len(cases), 33)
        for name, c in cases:
            with self.subTest(case=name):
                self.assertEqual(c['world']['schema_version'], '1.2')
                self.assertFalse(c['review']['practitioner_signoff'])
                self.assertFalse(c['review']['reviewed_by_practitioner'])
                self.assertTrue(c['review']['awaiting_re_review'])
                self.assertIn('PROVISIONAL', c['review']['values_status'])
                self.assertIn('not independent', c['review']['source'])
                self.assertTrue(c['expected']['calculation'])
                self.assertTrue(c['known_wrong'])
                self.assertTrue(c['expected']['valid_alternatives'], 'every case needs an alternative valid answer')
                self.assertTrue(c['changed_from_v1_1'])

    def test_every_case_by_independent_enumeration(self):
        for name, c in self.cases():
            with self.subTest(case=name):
                w, exp = c['world'], c['expected']
                awards = enumerate_awards(w)
                sub = exp['submission']
                optimum = None
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

    def test_service_level_safety_stock_values(self):
        by = dict(self.cases())
        expected = {'ref-01': 3, 'ref-03': 2, 'ref-10': 1, 'ref-23': 10, 'ref-24': 49}
        for name, ss in expected.items():
            item = by[name]['world']['items'][0]
            self.assertEqual(safety_of(item), ss, name)
        x = by['ref-12']['world']['items'][0]
        self.assertEqual(safety_of(x), 3)
        # exact boundary: 1.96 x 12.5 x sqrt(4) = 49 exactly; a hair more std rounds up to 50
        item = dict(by['ref-24']['world']['items'][0])
        self.assertEqual(safety_of(item), 49)
        item['demand_std'] = '12.5001'
        self.assertEqual(safety_of(item), 50)
        item['safety_stock_override'] = 7
        self.assertEqual(safety_of(item), 7)

    def test_tolerance_tier_edges(self):
        by = dict(self.cases())
        w = by['ref-04']['world']
        self.assertEqual(band_status(w, D('8.24'), D('8.00')), 'equivalent_to_optimal')   # exactly on the 3% band
        self.assertEqual(band_status(w, D('8.2401'), D('8.00')), 'suboptimal')
        w = by['ref-26']['world']
        self.assertEqual(tolerance_pct(w, D('499.99')), D('0.02'))
        self.assertEqual(tolerance_pct(w, D('500.00')), D('0.01'))
        self.assertEqual(tolerance_pct(w, D('49.99')), D('0.03'))
        self.assertEqual(tolerance_pct(w, D('50.00')), D('0.02'))
        # monotone: the allowed absolute gap on a 500 order is never looser than 1% while a 499 order gets 2%
        self.assertEqual(band_status(w, D('508.98'), D('499.00')), 'equivalent_to_optimal')
        self.assertEqual(band_status(w, D('508.98'), D('500.00')), 'suboptimal')

    def test_approval_limit_boundary_at_or_below(self):
        w = dict(self.cases())['ref-28']['world']
        est = dict(kind='award', allocations=[dict(supplier_id='A', item_id='component', quantity=40)], claimed_total_cost='5000.00',
                   flags=['estimated:A:component'], clarification_requests=['quotes.A.component.variable_freight'])
        self.assertEqual(evaluate(w, est), D('5000.00'))
        w['quotes'][0]['last_known_variable_freight'] = '5.01'
        self.assertEqual(blocking_fields(w), {'quotes.A.component.variable_freight'})

    def test_v11_rounding_difference_is_still_visible(self):
        """A, B cost 4.0164 and 4.0180 exactly; v1.0 rounds both to 4.02, v1.2 (like v1.1) never rounds."""
        w = dict(self.cases())['ref-21']['world']
        costs = {q['supplier_id']: 4 * D(q['unit_price']) for q in w['quotes']}
        self.assertEqual(costs, {'A': D('4.0164'), 'B': D('4.0180')})
        self.assertLess(costs['A'], costs['B'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
