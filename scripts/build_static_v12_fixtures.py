#!/usr/bin/env python3
"""Build fixtures/reference_cases_v1_2/ from the frozen v1.1 fixtures plus new v1.2 cases.

Every number is PROVISIONAL, needs practitioner value; the re-review answers are not independent.
The v1.1 fixtures are read only. Correctness is NOT taken from this script: tests/test_reference_cases_v1_2.py
re-derives every optimum, alternative and wrong answer by enumeration with no production code, and
tests/test_static_v12.py runs the production checker and solver against the result.
Run: python scripts/build_static_v12_fixtures.py
"""
import copy
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'fixtures' / 'reference_cases_v1_1'
OUT = ROOT / 'fixtures' / 'reference_cases_v1_2'

DEFAULT_TIERS = [dict(from_ratio='0', pct='0.03'), dict(from_ratio='0.5', pct='0.02'), dict(from_ratio='5', pct='0.01')]
NO_TIERS = [dict(from_ratio='0', pct='0')]
TEXT_KEYS = ('purpose', 'request', 'calculation', 'note', 'reason')
VER = re.compile(r'(?<![\d.])(v?)1\.1(?![\d])')


def bump(value):
    if isinstance(value, dict):
        return {k: (VER.sub(r'\g<1>1.2', v) if k in TEXT_KEYS and isinstance(v, str) else bump(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [bump(v) for v in value]
    return value


# ---------- small builders -------------------------------------------------------------------------------------
def aw(allocs, cost, flags=(), reqs=(), refs=()):
    return dict(kind='award', allocations=[dict(supplier_id=s, item_id=i, quantity=q) for s, i, q in allocs],
                claimed_total_cost=cost, evidence=['Visible quotation and policy records'],
                flags=list(flags), clarification_requests=list(reqs), approval_refs=list(refs))


def clar(field, text):
    return dict(kind='clarification', field=field, disposition='record_and_escalate', evidence=[text])


def item(iid, demand, **kw):
    base = dict(item_id=iid, unit='each', demand=demand, due_date='2026-11-10', excess_allowance=0, service_level=None,
                demand_std=None, lead_time_periods=None, safety_stock_override=None, critical=False,
                moq_excess_allowed=False, max_excess=None)
    base.update(kw)
    return base


def supplier(sid, fixed='0.00', rel=None):
    return dict(supplier_id=sid, fixed_charge=fixed, fixed_charge_basis='flat', fixed_charge_table=[], reliability_score=rel)


def quote(sid, iid, price, freight, cap, moq=1, mul=1, qual=True, arr='2026-11-09', lkp=None, lkf=None, risk=None):
    return dict(supplier_id=sid, item_id=iid, unit_price=price, variable_freight=freight, capacity=cap, moq=moq, multiple=mul,
                qualified=qual, valid_from='2026-01-01', valid_to='2026-12-31', arrival_date=arr,
                last_known_unit_price=lkp, last_known_variable_freight=lkf, lead_time_risk=risk)


def policy(abs_='0', tiers=None, tol_days=3, credit='0.50', threshold='500.00', ref_value='100.00'):
    return dict(late_inbound_tolerance_days=tol_days, late_inbound_credit=credit, cost_tolerance_abs=abs_,
                cost_tolerance_reference_value=ref_value, cost_tolerance_tiers=copy.deepcopy(tiers or DEFAULT_TIERS),
                moq_excess_approval_threshold=threshold)


def world(wid, seed, items, suppliers, quotes, budget, **kw):
    return dict(schema_version='1.2', world_id=wid, seed=seed, currency='USD', calendar='gregorian', as_of='2026-11-02',
                items=items, stock=kw.get('stock', []), inbound=kw.get('inbound', []), suppliers=suppliers, quotes=quotes,
                constraints=dict(budget=budget, concentration=kw.get('concentration', []), approval_limit=kw.get('limit')),
                policy=kw.get('policy', policy()), approvals=kw.get('approvals', []),
                visibility=dict(classification='public_synthetic'))


def case(cid, purpose, rules, w, expected, calc, alts, wrongs, changed, measures=()):
    n = int(cid[4:])
    return dict(case_id=cid, rules_version='1.2', purpose=purpose, rules_exercised=rules,
                request=f'Allocate component purchases for {purpose}; minimize landed cost subject to visible policy (rules 1.2), or submit a supported exception.',
                task=dict(task_id=f'task-{cid}', concentration_measures=list(measures)),
                changed_from_v1_1=changed,
                world=w,
                expected=dict(submission=expected, optimal_cost=(expected['claimed_total_cost'] if expected['kind'] == 'award' else None),
                              calculation=calc, expected_outcome=expected['kind'], valid_alternatives=alts),
                known_wrong=wrongs,
                review=dict(status='arithmetic_checked_practitioner_pending', practitioner_signoff=False,
                            reviewed_by_practitioner=False, awaiting_re_review=True,
                            values_status='PROVISIONAL, needs practitioner value',
                            required_review=['every numeric policy value and procurement convention in this case'],
                            source='entirely synthetic; no external business records; owner-practitioner review is not independent'))


def alt(sub, status, cost, note):
    return dict(submission=sub, status=status, cost=cost, note=note)


def wrong(sub, reason):
    return dict(submission=sub, reason=reason)


def exc_alt(sub, note):
    return dict(submission=sub, status='valid_exception', cost=None, note=note)


# ---------- re-tuned v1.1 cases ----------------------------------------------------------------------------------
RULE_MAP = {'A1': 'C1', 'A2': 'C7', 'A3': 'C3', 'A4': 'C4', 'A5': 'C8', 'A6': 'C5'}


def upgrade(n):
    c = json.loads((SRC / f'ref-{n:02}.json').read_text())
    c = bump(c)
    c['rules_version'] = '1.2'
    w = c['world']
    w['schema_version'] = '1.2'
    for it in w['items']:
        ss = it.pop('safety_stock')
        it.update(service_level=None, demand_std=None, lead_time_periods=None, safety_stock_override=None)
        it['_old_ss'] = ss
    pol = w['policy']
    old_pct = pol.pop('cost_tolerance_pct')
    pol.update(late_inbound_tolerance_days=3, late_inbound_credit='0.50', cost_tolerance_reference_value='100.00',
               cost_tolerance_tiers=copy.deepcopy(DEFAULT_TIERS), moq_excess_approval_threshold='500.00')
    w['approvals'] = []
    if w['constraints']['approval_limit'] is not None:
        w['constraints']['approval_limit'] = '5000.00'
    for it in w['items']:
        it.pop('_old_ss')
    for sub in [c['expected']['submission'], *[a['submission'] for a in c['expected']['valid_alternatives']],
                *[a['submission'] for a in c['known_wrong']]]:
        if sub['kind'] == 'award':
            sub['approval_refs'] = []
    c['rules_exercised'] = sorted({RULE_MAP.get(r, r) for r in c['rules_exercised']})
    c['task'] = dict(task_id=f'task-{c["case_id"]}', concentration_measures=[])
    c['changed_from_v1_1'] = []
    return c


def service_level(it, std, lead, level='0.95'):
    it.update(service_level=level, demand_std=std, lead_time_periods=lead)


def retune():
    cases = {}
    for n in range(1, 23):
        cases[n] = upgrade(n)
    chg = lambda n, text: cases[n]['changed_from_v1_1'].append(text)
    for n in cases:
        chg(n, 'Cost tolerance is now tiered by optimum cost relative to the reference value (3% / 2% / 1%); policy.cost_tolerance_pct removed')
        chg(n, 'Late-inbound tolerance default is 3 days (was 2 in ref-01, 0 elsewhere); credit 0.50')

    # ref-01: service-level safety stock, 3-day window edge
    c = cases[1]
    service_level(c['world']['items'][0], '1', '2')
    c['world']['inbound'][1]['arrival_date'] = '2026-11-13'
    c['expected']['calculation'] = ('Safety stock = ceil(z(95%) x std x sqrt(lead)) = ceil(1.6449 x 1 x sqrt(2)) = ceil(2.3263) = 3. '
                                    'Net = 10 demand + 3 safety - 2 usable - 1 on-time inbound - floor(4 x 0.50) = 2 late credit '
                                    '(arrives 2026-11-13, exactly 3 days late: edge of the 3-day window, inclusive) = 8; the 50 held units and the 50 units 4 days late earn nothing. '
                                    'A: 8 x 2.00 = 16.00; B: 24.00; mixed awards only add cost.')
    c['expected']['valid_alternatives'][0]['note'] = 'feasible mix; gap 1.00 exceeds the 3% tier band 0.48 (optimum 16.00 is below the 50.00 tier bound)'
    chg(1, 'Safety stock 3 now comes from service level 0.95, std 1, lead time 2 (was a direct input of 3)')
    chg(1, 'Late inbound of 4 units now arrives exactly 3 days late (edge of the 3-day window; was 2 days late in a 2-day window)')

    c = cases[3]
    service_level(c['world']['items'][0], '1', '1')
    c['expected']['calculation'] = ('Safety stock = ceil(1.6449 x 1 x sqrt(1)) = 2. Net = 4 + 2 safety - 1 usable = 5. A orders are 4,6,8,10 (MOQ 3, multiple 2); B any 1..10. '
                                    'A4+B1 = 4 x 1.00 + 1 x 2.00 = 6.00. A6 would cost 6.00 but exceeds net 5 with no allowance. B5 = 10.00. Optimum 6.00.')
    chg(3, 'Safety stock 2 now from service level 0.95, std 1, lead time 1')

    c = cases[4]
    c['world']['quotes'][2]['unit_price'] = '2.06'
    c['expected']['calculation'] = ('A arrives 2026-11-11, after the 2026-11-10 deadline: ineligible (late-inbound tolerance never applies to new orders). B4 = 8.00. C4 = 8.24. '
                                    'Optimum 8.00 is below the 50.00 tier bound, so tolerance is 3% = 0.24, and C (gap exactly 0.24, inclusive) is equivalent-to-optimal.')
    c['expected']['valid_alternatives'][0].update(cost='8.24', note='gap 0.24 equals the 3% tier band; lead-time risk 0.05 vs 0.30 reported separately')
    c['expected']['valid_alternatives'][0]['submission'] = aw([('C', 'component', 4)], '8.24')
    chg(4, 'Band edge moved from 2% (C at 2.04) to the 3% tier (C at 2.06): gap 0.24')

    c = cases[8]
    c['expected']['calculation'] += (' C5: excess value = 1 unit x 1.00 = 1.00, not above the 500.00 approval threshold, so the flag alone suffices (no approval record needed).')
    chg(8, 'Explicitly below the MOQ-excess approval threshold: flag only (excess value 1.00 <= 500.00)')

    c = cases[9]
    c['expected']['calculation'] += ' Approval limit is 5,000.00 (was 50.00); irrelevant here because no last known value exists.'
    chg(9, 'Approval limit 5,000.00 (was 50.00)')

    c = cases[10]
    service_level(c['world']['items'][0], '0.5', '1')
    c['expected']['calculation'] = ('Safety stock = ceil(1.6449 x 0.5 x sqrt(1)) = ceil(0.82245) = 1. Net = 3 + 1 = 4. Eligible capacity 2+1 = 3 < 4, so no award exists; without the safety stock the case would be feasible.')
    chg(10, 'Safety stock 1 now from service level 0.95, std 0.5, lead time 1')

    c = cases[12]
    service_level(c['world']['items'][0], '1', '2')
    c['expected']['calculation'] = ('X: safety stock = ceil(1.6449 x 1 x sqrt(2)) = 3; net = 5 + 3 - 6 = 2 (v1.0 would buy 0). Y: net 2. X cheapest at A (1.00): 2.00. Y cheapest at B (1.00): 2.00. '
                                    'Both suppliers charge nothing fixed. Total 4.00 is the optimum.')
    chg(12, 'Safety stock of X now from service level 0.95, std 1, lead time 2')

    c = cases[16]
    c['expected']['calculation'] = ('A: 50.00 (optimum, exactly at the 50.00 tier bound, so the 2% tier applies: band 1.00). B: 50.40, gap 0.40 is above the absolute band 0.25 but within 2% of 50.00 = 1.00, so equivalent-to-optimal. '
                                    'C: 52.00, gap 2.00 exceeds both 0.25 and 1.00, suboptimal. Reliability and lead-time risk are reported beside cost, never combined.')
    c['expected']['valid_alternatives'][0]['note'] = 'inside the 2% tier band (1.00)'
    chg(16, 'Fractional band now 2% (optimum exactly at the 50.00 tier bound) instead of a fixed 1%')

    c = cases[17]
    c['expected']['calculation'] = ('Freight on A is missing; the agent requests it first. Last known freight 0.25 gives line value 4 x (2.00 + 0.25) = 9.00, at or below the 5,000.00 approval limit, and the part is not critical, '
                                    'so the estimate path covers A: an award flagged estimated is allowed, and awarding around A is also allowed. B (complete): 4 x 2.30 = 9.20, gap 0.20 <= abs band 0.25, equivalent-to-optimal.')
    chg(17, 'Approval limit 5,000.00 (was 50.00); estimate allowed at or below the limit')

    c = cases[18]
    chg(18, 'Approval limit 5,000.00 (was 50.00); the critical flag still closes the estimate path')

    c = cases[19]
    w = c['world']
    w['items'][0]['demand'] = 40
    w['quotes'][0].update(unit_price='120.00', last_known_variable_freight='10.00')
    w['constraints']['budget'] = '10000.00'
    sub = c['known_wrong'][0]['submission']
    sub['claimed_total_cost'] = '5200.00'
    c['expected']['submission']['evidence'] = ['Freight missing; estimated line value 5,200.00 is above the 5,000.00 approval limit; escalate.']
    c['expected']['calculation'] = ('Last known freight 10.00: line 40 x (120.00 + 10.00) = 5,200.00 is above the provisional 5,000.00 approval limit, so the estimate path is closed: request and escalate.')
    chg(19, 'Scaled to the 5,000.00 limit: demand 40 at 120.00 + last known freight 10.00 = 5,200.00 (was 90.00 against 50.00)')

    c = cases[21]
    c['world']['policy']['cost_tolerance_tiers'] = copy.deepcopy(NO_TIERS)
    chg(21, 'Tolerance tiers set to 0% explicitly so exact ties only are equivalent (the rounding diagnostic needs it)')

    c = cases[2]
    c['expected']['valid_alternatives'][1]['note'] = 'two suppliers pay the fixed charge once for A; gap 2.40 exceeds the 0.50 absolute band and the 3% tier band 0.24'
    for n in (6, 13, 14, 15):
        pass
    cases[13]['task']['concentration_measures'] = ['quantity_share']
    cases[14]['task']['concentration_measures'] = ['per_item_share']
    chg(13, 'Task declares quantity_share (non-default measure); spend_share stays the default for all other cases')
    chg(14, 'Task declares per_item_share (non-default measure)')
    return cases


# ---------- new v1.2 cases ---------------------------------------------------------------------------------------
def new_cases():
    out = {}
    std = [supplier('A'), supplier('B')]

    # 23: service level 97.5%, ceiling of 9.8
    it = item('component', 2)
    service_level(it, '2.5', '4', '0.975')
    w = world('ref-23', 23, [it], std, [quote('A', 'component', '2.00', '0.00', 14), quote('B', 'component', '3.00', '0.00', 14)], '100.00',
              stock=[dict(item_id='component', quantity=1, status='usable')])
    out[23] = case('ref-23', 'service-level safety stock rounded up', ['C1'], w, aw([('A', 'component', 11)], '22.00'),
                   'Safety stock = ceil(z(97.5%) x std x sqrt(lead)) = ceil(1.9600 x 2.5 x sqrt(4)) = ceil(9.8) = 10. Net = 2 demand + 10 safety - 1 usable = 11. A11 = 22.00; B11 = 33.00; A10+B1 = 23.00 (gap 1.00 > 3% tier band 0.66). Optimum 22.00.',
                   [alt(aw([('A', 'component', 10), ('B', 'component', 1)], '23.00'), 'suboptimal', '23.00', 'feasible mix; gap 1.00 exceeds the 3% tier band 0.66')],
                   [wrong(aw([('A', 'component', 10)], '20.00'), 'floor instead of ceiling: safety stock 9 gives net 10, below the true net 11'),
                    wrong(aw([('A', 'component', 1)], '2.00'), 'ignores safety stock: net 1 instead of 11'),
                    wrong(aw([('A', 'component', 12)], '24.00'), 'excess of 1 over net 11 with no allowance')],
                   ['New: service-level safety stock at 97.5% (z 1.9600) with a fractional result rounded up'])

    # 24: exact integer boundary 49
    it = item('component', 1)
    service_level(it, '12.5', '4', '0.975')
    w = world('ref-24', 24, [it], std, [quote('A', 'component', '1.00', '0.00', 60), quote('B', 'component', '1.50', '0.00', 60)], '200.00')
    out[24] = case('ref-24', 'service-level safety stock exactly an integer', ['C1', 'C3'], w, aw([('A', 'component', 50)], '50.00'),
                   'z x std x sqrt(lead) = 1.9600 x 12.5 x 2 = 49 exactly, so the ceiling is 49 (not 50). Net = 1 + 49 = 50. A50 = 50.00 (optimum, exactly at the 50.00 tier bound, so the 2% tier applies: band 1.00). A49+B1 = 50.50, gap 0.50 equivalent. A40+B10 = 55.00, gap 5.00 suboptimal.',
                   [alt(aw([('A', 'component', 49), ('B', 'component', 1)], '50.50'), 'equivalent_to_optimal', '50.50', 'gap 0.50 <= 2% tier band 1.00'),
                    alt(aw([('A', 'component', 40), ('B', 'component', 10)], '55.00'), 'suboptimal', '55.00', 'gap 5.00 exceeds 1.00')],
                   [wrong(aw([('A', 'component', 51)], '51.00'), 'ceiling applied to an exact integer (50 instead of 49): net 51, one unit of excess'),
                    wrong(aw([('A', 'component', 49)], '49.00'), 'forgot the demand unit: 49 < net 50')],
                   ['New: exact-integer boundary of the safety-stock ceiling'])

    # 25 to 27 tolerance tiers
    def tier_case(n, purpose, prices, caps_demand, optimum, band_text, alt_edge, alt_far, tier_note, budget='1000.00'):
        ids = ['A', 'B', 'C']
        qs = [quote(s, 'component', p, '0.00', 10 if caps_demand == 10 else 10) for s, p in zip(ids, prices)]
        w = world(f'ref-{n}', n, [item('component', caps_demand)], [supplier(s) for s in ids], qs, budget)
        return w
    # 25: optimum 49.00, 3% tier
    w = tier_case(25, '', ['4.90', '5.047', '5.048'], 10, None, None, None, None, None, '200.00')
    out[25] = case('ref-25', 'tolerance tier below the reference scale (3%)', ['C3'], w, aw([('A', 'component', 10)], '49.00'),
                   'Optimum A10 = 49.00. Reference value 100.00: ratio 0.49 is below 0.5, so the 3% tier applies, band 1.47. B10 = 50.47, gap 1.47 (edge, inclusive): equivalent. C10 = 50.48, gap 1.48: suboptimal.',
                   [alt(aw([('B', 'component', 10)], '50.47'), 'equivalent_to_optimal', '50.47', 'gap exactly 1.47 = 3% of 49.00'),
                    alt(aw([('C', 'component', 10)], '50.48'), 'suboptimal', '50.48', 'gap 1.48 is just outside the band')],
                   [wrong(aw([('B', 'component', 10)], '49.00'), 'claimed the optimum cost for a quote that costs 50.47')],
                   ['New: tolerance tier 3% (optimum below half the reference value)'])
    # 26: optimum 500.00 exactly, 1% tier
    qs = [quote('A', 'component', '125.00', '0.00', 10), quote('B', 'component', '126.25', '0.00', 10), quote('C', 'component', '126.26', '0.00', 10)]
    w = world('ref-26', 26, [item('component', 4)], [supplier(s) for s in 'ABC'], qs, '2000.00')
    out[26] = case('ref-26', 'tolerance tier at the large-order bound (1%)', ['C3'], w, aw([('A', 'component', 4)], '500.00'),
                   'Optimum A4 = 500.00 = 5 x reference 100.00, so the 1% tier applies (bound inclusive): band 5.00. B4 = 505.00, gap 5.00 (edge): equivalent. C4 = 505.04, gap 5.04: suboptimal (it would pass under the 2% or 3% tier).',
                   [alt(aw([('B', 'component', 4)], '505.00'), 'equivalent_to_optimal', '505.00', 'gap exactly 5.00 = 1% of 500.00'),
                    alt(aw([('C', 'component', 4)], '505.04'), 'suboptimal', '505.04', 'gap 5.04 exceeds the 1% band')],
                   [wrong(aw([('A', 'component', 3)], '375.00'), 'short by one unit')],
                   ['New: tolerance tier 1% at exactly 5 x reference value'])
    # 27: optimum 499.00, 2% tier
    qs = [quote('A', 'component', '249.50', '0.00', 10), quote('B', 'component', '254.49', '0.00', 10), quote('C', 'component', '254.50', '0.00', 10)]
    w = world('ref-27', 27, [item('component', 2)], [supplier(s) for s in 'ABC'], qs, '2000.00')
    out[27] = case('ref-27', 'tolerance tier just below the large-order bound (2%)', ['C3'], w, aw([('A', 'component', 2)], '499.00'),
                   'Optimum A2 = 499.00, ratio 4.99 is below 5, so the 2% tier applies: band 9.98. B2 = 508.98, gap 9.98 (edge): equivalent. C2 = 509.00, gap 10.00: suboptimal. The same 9.98 gap would be suboptimal at an optimum of 500.00 (ref-26).',
                   [alt(aw([('B', 'component', 2)], '508.98'), 'equivalent_to_optimal', '508.98', 'gap exactly 9.98 = 2% of 499.00'),
                    alt(aw([('C', 'component', 2)], '509.00'), 'suboptimal', '509.00', 'gap 10.00 exceeds the 2% band')],
                   [wrong(aw([('B', 'component', 2)], '499.00'), 'claimed the optimum cost for a quote that costs 508.98')],
                   ['New: tolerance tier 2% just below 5 x reference value'])

    # 28: at-limit estimate allowed
    def est_world(n, lkf):
        qs = [quote('A', 'component', '120.00', None, 100, lkf=lkf), quote('B', 'component', '125.50', '0.00', 100),
              quote('C', 'component', '127.50', '0.00', 100)]
        return world(f'ref-{n}', n, [item('component', 40)], [supplier(s) for s in 'ABC'], qs, '10000.00', limit='5000.00')
    w = est_world(28, '5.00')
    est = aw([('A', 'component', 40)], '5000.00', ['estimated:A:component'], ['quotes.A.component.variable_freight'])
    out[28] = case('ref-28', 'estimate exactly at the approval limit', ['C4', 'C6'], w, est,
                   'A freight is missing; last known 5.00 gives line 40 x (120.00 + 5.00) = 5,000.00, exactly the 5,000.00 approval limit. The boundary is at or below, so the estimate is allowed (flagged estimated, field requested). B40 = 5,020.00 (gap 20.00 <= 1% tier band 50.00): equivalent. C40 = 5,100.00: suboptimal.',
                   [alt(aw([('B', 'component', 40)], '5020.00'), 'equivalent_to_optimal', '5020.00', 'award around A is allowed because the estimate path covers A'),
                    alt(aw([('C', 'component', 40)], '5100.00'), 'suboptimal', '5100.00', 'gap 100.00 exceeds the band')],
                   [wrong(aw([('A', 'component', 40)], '4800.00'), 'substituted zero freight, no flag, no request'),
                    wrong(aw([('A', 'component', 40)], '5000.00'), 'estimate used without the estimated flag or the clarification request'),
                    wrong(clar('quotes.A.component.variable_freight', 'Escalated although the line is exactly at the limit'), 'v1.1 boundary (strictly under) applied: at the limit the estimate is allowed, so escalating is wrong')],
                   ['New: boundary changed from strictly under to at or under the approval limit (line exactly 5,000.00)'])

    # 29: one step above the limit, other quotes exist
    w = est_world(29, '5.01')
    clar_sub = clar('quotes.A.component.variable_freight', 'Freight missing on A; last known gives 5,000.40 which is above the 5,000.00 approval limit; ask first and escalate.')
    out[29] = case('ref-29', 'estimate just above the approval limit escalates', ['C4', 'C6'], w, clar_sub,
                   'Last known freight 5.01 gives line 40 x (120.00 + 5.01) = 5,000.40, above the 5,000.00 limit by 0.40, so the estimate path does not cover A. B and C are complete and could cover the need, but the gap is not awarded around: ask clarification first and escalate.',
                   [exc_alt(clar('quotes.A.component.variable_freight', 'Estimate above the limit; asked for the freight and escalated.'), 'alternative wording')],
                   [wrong(aw([('B', 'component', 40)], '5020.00'), 'awarded around the missing term although the estimate path does not apply to A'),
                    wrong(aw([('A', 'component', 40)], '5000.40', ['estimated:A:component'], ['quotes.A.component.variable_freight']), 'estimate above the approval limit'),
                    wrong(aw([('A', 'component', 39), ('B', 'component', 1)], '5000.89', ['estimated:A:component'], ['quotes.A.component.variable_freight']),
                          'each line is under the limit but the missing term on A is not covered by the estimate path; ask first')],
                   ['New: above-limit escalation by 0.40 while other complete quotes exist'])

    # 30: ask first despite alternatives (critical)
    qs = [quote('A', 'component', '10.00', None, 30, lkf='1.00'), quote('B', 'component', '12.00', '0.00', 30)]
    w = world('ref-30', 30, [item('component', 20, critical=True)], [supplier('A'), supplier('B')], qs, '1000.00', limit='5000.00')
    out[30] = case('ref-30', 'ask clarification first despite a complete alternative quote', ['C4', 'C6'], w,
                   clar('quotes.A.component.variable_freight', 'Freight missing on A for a critical part; B could cover the need, but ask first and escalate.'),
                   'A is cheaper but its freight is missing and the part is critical, so no estimate. B is complete (20 x 12.00 = 240.00) and could cover the need. v1.1 would award B; v1.2 reverts to asking first: the missing term is never awarded around.',
                   [exc_alt(clar('quotes.A.component.variable_freight', 'Critical part, missing freight; asked and escalated.'), 'alternative wording')],
                   [wrong(aw([('B', 'component', 20)], '240.00'), 'awarded around a missing term that the estimate path cannot cover'),
                    wrong(aw([('A', 'component', 20)], '220.00', ['estimated:A:component'], ['quotes.A.component.variable_freight']), 'estimate on a critical part')],
                   ['New: v1.0 ask-first behaviour restored even when a complete alternative quote exists'])

    # 31 to 33: MOQ excess approval
    def moq_world(n, price_a, price_b, approvals):
        qs = [quote('A', 'component', price_a, '0.00', 40, moq=20, mul=20), quote('B', 'component', price_b, '0.00', 20, moq=10, mul=10)]
        return world(f'ref-{n}', n, [item('component', 18, moq_excess_allowed=True)], [supplier('A'), supplier('B')], qs, '20000.00',
                     limit='5000.00', approvals=approvals)
    appr = [dict(approval_id='APR-7', kind='moq_excess', item_id='component')]
    w = moq_world(31, '300.00', '310.00', appr)
    out[31] = case('ref-31', 'MOQ excess above the approval threshold with an approval on file', ['C5'], w,
                   aw([('A', 'component', 20)], '6000.00', ['moq_excess:component'], [], ['APR-7']),
                   'Net 18. A sizes 20, 40; B sizes 10, 20. The smallest reachable total at or above 18 is 20, so 2 units of excess are MOQ-forced. Excess value = 2 x 300.00 = 600.00, above the 500.00 approval threshold, so the award needs the flag moq_excess:component and the approval reference APR-7 (granted record on file). A20 = 6,000.00 (optimum). B20 = 6,200.00 (excess value 620.00, also needs APR-7), gap 200.00 > 1% band 60.00: suboptimal.',
                   [alt(aw([('B', 'component', 20)], '6200.00', ['moq_excess:component'], [], ['APR-7']), 'suboptimal', '6200.00', 'MOQ-forced excess on B, approved by APR-7; gap 200.00 exceeds 60.00')],
                   [wrong(aw([('A', 'component', 20)], '6000.00', ['moq_excess:component']), 'flag without the approval reference although the excess value 600.00 exceeds 500.00'),
                    wrong(aw([('A', 'component', 20)], '6000.00', [], [], ['APR-7']), 'approval cited but the excess is not flagged'),
                    wrong(aw([('A', 'component', 20)], '6000.00', ['moq_excess:component'], [], ['APR-X']), 'approval reference does not exist on file'),
                    wrong(aw([('A', 'component', 40)], '12000.00', ['moq_excess:component'], [], ['APR-7']), 'excess of 22 is beyond the smallest reachable total; MOQ does not justify it')],
                   ['New: MOQ excess now requires an approval reference when its value is above 500.00'])
    w = moq_world(32, '300.00', '310.00', [])
    out[32] = case('ref-32', 'MOQ excess above the approval threshold without any approval', ['C5', 'C6'], w,
                   clar('approvals.moq_excess.component', 'MOQ forces 2 units of excess worth 600.00, above the 500.00 threshold, and no approval is on file; request approval and escalate.'),
                   'Same world as ref-31 but no approval record exists. Every award needs the forced excess (smallest reachable total 20, value 600.00 or 620.00 above 500.00), and none may be awarded without an approval. The supported answer is to request the approval and escalate.',
                   [exc_alt(clar('approvals.moq_excess.component', 'Approval for MOQ excess on component is missing; asked and escalated.'), 'alternative wording')],
                   [wrong(aw([('A', 'component', 20)], '6000.00', ['moq_excess:component']), 'awarded the excess with no approval on file'),
                    wrong(aw([('A', 'component', 20)], '6000.00', ['moq_excess:component'], [], ['APR-7']), 'cites an approval that is not in this world'),
                    wrong(dict(kind='infeasible', evidence=['Insufficient capacity somewhere']), 'capacity is sufficient; infeasible is unsupported')],
                   ['New: the without-approval counterpart of ref-31; correct answer is a request for approval'])
    appr9 = [dict(approval_id='APR-9', kind='moq_excess', item_id='component')]
    w = moq_world(33, '250.00', '260.00', appr9)
    out[33] = case('ref-33', 'MOQ excess exactly at the approval threshold needs only a flag', ['C5'], w,
                   aw([('A', 'component', 20)], '5000.00', ['moq_excess:component']),
                   'Net 18, forced excess 2 (smallest reachable total 20). A20: excess value 2 x 250.00 = 500.00, exactly the threshold, not above it, so the flag alone suffices (an approval is on file but not required). B20: excess value 520.00 is above the threshold and needs APR-9. A20 = 5,000.00 optimum; B20 = 5,200.00, gap 200.00 > 1% band 50.00.',
                   [alt(aw([('A', 'component', 20)], '5000.00', ['moq_excess:component'], [], ['APR-9']), 'optimal', '5000.00', 'citing the approval that was not required is allowed'),
                    alt(aw([('B', 'component', 20)], '5200.00', ['moq_excess:component'], [], ['APR-9']), 'suboptimal', '5200.00', 'B excess value 520.00 needs and cites APR-9')],
                   [wrong(aw([('B', 'component', 20)], '5200.00', ['moq_excess:component']), 'B excess value 520.00 is above the threshold and no approval reference is cited'),
                    wrong(aw([('A', 'component', 20)], '5000.00'), 'excess not flagged')],
                   ['New: boundary of the MOQ-excess approval threshold (above 500.00 needs approval, 500.00 does not)'])
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cases = retune()
    cases.update(new_cases())
    for n, c in sorted(cases.items()):
        (OUT / f'ref-{n:02}.json').write_text(json.dumps(c, indent=2) + '\n')
    print(f'wrote {len(cases)} cases to {OUT}')


if __name__ == '__main__':
    main()
