#!/usr/bin/env python3
"""Generate docs/acceptance/static-v1.2-provisional-values.md from the v1.2 fixtures.

Every policy number a fixture sets is listed with the marker and a 'changed from v1.1' column, so the reviewer can
re-review all of them. Run: PYTHONPATH=src python scripts/generate_static_v12_provisional_table.py [--check]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'fixtures' / 'reference_cases_v1_2'
OUT = ROOT / 'docs' / 'acceptance' / 'static-v1.2-provisional-values.md'
MARK = 'PROVISIONAL, needs practitioner value'

DEFAULT_POLICY = {
    'late_inbound_tolerance_days': 3, 'late_inbound_credit': '0.50', 'cost_tolerance_abs': '0',
    'cost_tolerance_reference_value': '100.00', 'moq_excess_approval_threshold': '500.00',
}
DEFAULT_TIERS = [('0', '0.03'), ('0.5', '0.02'), ('5', '0.01')]

STRUCTURAL = [
    ('Safety stock', 'ceil(z(service level) x demand std x sqrt(lead time periods)); z fixed at 0.90 = 1.2816, 0.95 = 1.6449, 0.975 = 1.9600, 0.99 = 2.3263; evaluated exactly as the smallest integer s with s x s >= (z x std)^2 x lead time; explicit override kept', 'C1', 'Changed: v1.1 took a direct safety-stock quantity per item'),
    ('Late inbound credit', 'Unchanged mechanism (floor of quantity x credit, window inclusive); window 3 days', 'C2', 'Changed: window value only (v1.1 fixtures used 0, 2 and 3 days)'),
    ('Cost band', 'Equivalent-to-optimal if gap <= absolute band OR gap <= tier pct x optimum; tier chosen by optimum / reference value; larger orders never get a looser tolerance; exact gap always reported', 'C3', 'Changed: v1.1 used one fixed fraction per world'),
    ('Estimate boundary', 'Line value (qty x (price + freight) on last known terms) at or below the approval limit and the item non-critical', 'C4', 'Changed: v1.1 required strictly under the limit'),
    ('Ask clarification first', 'If an eligible quote for a needed item has a missing term and the estimate path does not cover it, no award is acceptable; the answer is a clarification. The estimate path covers a quote when the item is non-critical, last known terms exist, and min(capacity, max(net, MOQ)) x estimated unit cost is at or below the limit', 'C6', 'Changed: v1.1 awarded around a missing term when other quotes could cover the need'),
    ('MOQ excess approval', 'Flag always; when excess units x item goods value / units bought is above the threshold, a granted approval record for the item must also be cited. Threshold value was not given by the reviewer', 'C5', 'Changed: v1.1 needed only the flag'),
    ('Concentration measure', 'spend_share is the default; quantity_share and per_item_share only when the task declares them', 'C7', 'Changed: v1.1 let any world declare any measure'),
    ('Held and reserved stock', 'Still never counts', 'C1', 'Unchanged'),
    ('Non-cost factors', 'Reliability and lead-time risk are report-only metrics', 'C3', 'Unchanged'),
    ('Fixed charge basis', 'Table by order units or goods value; largest lower bound not above the measure', 'C8', 'Unchanged'),
    ('Rounding', 'Removed; exact Decimal', 'C8', 'Unchanged; resolved by reviewer, not provisional'),
    ('Shelf-life cap', 'max_excess caps all excess, including explicit allowance and MOQ excess', 'C5', 'Unchanged'),
]

CHANGED = {
    'service_level': 'New (v1.1 had a direct safety-stock quantity)',
    'demand_std': 'New',
    'lead_time_periods': 'New',
    'safety_stock_override': 'New (explicit override)',
    'late_inbound_tolerance_days': 'Changed: 3 days (was 2 or 0)',
    'late_inbound_credit': 'Same 0.50',
    'cost_tolerance_abs': 'Same',
    'cost_tolerance_reference_value': 'New (scale for the tiers)',
    'cost_tolerance_tiers': 'Changed: tiers replace one fixed fraction',
    'moq_excess_approval_threshold': 'New',
    'approval_limit': 'Changed: 5,000.00 (was 50.00); at or below allowed (was strictly under)',
    'approval': 'New',
    'concentration': 'Same limit; task must declare non-spend measures',
    'excess_allowance': 'Same', 'max_excess': 'Same', 'critical': 'Same', 'moq_excess_allowed': 'Same',
    'reliability_score': 'Same', 'lead_time_risk': 'Same', 'fixed_charge': 'Same', 'last_known': 'Same (values, not rule)',
}
MEANING = {
    'service_level': 'Target service level (z-table key)',
    'demand_std': 'Per-period demand standard deviation (units)',
    'lead_time_periods': 'Replenishment lead time (periods)',
    'safety_stock_override': 'Explicit safety stock override (units)',
    'late_inbound_tolerance_days': 'Late-inbound tolerance window (days after item deadline)',
    'late_inbound_credit': 'Fraction of a late inbound line counted (floor to whole units)',
    'cost_tolerance_abs': 'Equivalent-to-optimal band, absolute USD',
    'cost_tolerance_reference_value': 'Reference value that scales the tolerance tiers (USD)',
    'cost_tolerance_tiers': 'Tolerance fraction by optimum / reference value (from ratio: pct)',
    'moq_excess_approval_threshold': 'MOQ excess value above which an approval reference is needed (USD)',
    'approval_limit': 'Approval limit in USD (estimate allowed at or below)',
    'approval': 'Granted MOQ-excess approval record',
    'concentration': 'Concentration limit (measure per task)',
    'excess_allowance': 'Explicit permitted excess units',
    'max_excess': 'Shelf-life / obsolescence cap on all excess (units)',
    'critical': 'Part is critical (estimate never allowed)',
    'moq_excess_allowed': 'MOQ may justify excess (flag, and approval above the threshold)',
    'reliability_score': 'Supplier reliability score (report-only metric)',
    'lead_time_risk': 'Quote lead-time risk (report-only metric)',
    'fixed_charge': 'Fixed supplier charge (flat or table row, USD)',
    'last_known': 'Last known price or freight used for a flagged estimate',
}


def rows_for(case_id, w):
    out = []

    def add(key, where, value):
        out.append((case_id, f'{where}', MEANING[key], value, CHANGED[key]))

    for item in w['items']:
        iid = item['item_id']
        for key in ('service_level', 'demand_std', 'lead_time_periods', 'safety_stock_override', 'excess_allowance', 'max_excess'):
            if item[key] not in (0, None):
                add(key, f'items.{iid}.{key}', item[key])
        if item['critical']:
            add('critical', f'items.{iid}.critical', 'true')
        if item['moq_excess_allowed']:
            add('moq_excess_allowed', f'items.{iid}.moq_excess_allowed', 'true')
    pol = w['policy']
    for key, default in DEFAULT_POLICY.items():
        if str(pol[key]) != str(default):
            add(key, f'policy.{key}', pol[key])
    tiers = [(t['from_ratio'], t['pct']) for t in pol['cost_tolerance_tiers']]
    if tiers != DEFAULT_TIERS:
        add('cost_tolerance_tiers', 'policy.cost_tolerance_tiers', ', '.join(f'{a}: {b}' for a, b in tiers))
    if w['constraints']['approval_limit'] is not None:
        add('approval_limit', 'constraints.approval_limit', w['constraints']['approval_limit'])
    for n, rule in enumerate(w['constraints']['concentration']):
        add('concentration', f"constraints.concentration[{n}] {rule['measure']}", rule['limit'])
    for a in w['approvals']:
        add('approval', f"approvals.{a['approval_id']} ({a['item_id']})", 'granted')
    for s in w['suppliers']:
        sid = s['supplier_id']
        if s['reliability_score'] is not None:
            add('reliability_score', f'suppliers.{sid}.reliability_score', s['reliability_score'])
        if s['fixed_charge'] is not None and s['fixed_charge'] != '0.00':
            add('fixed_charge', f'suppliers.{sid}.fixed_charge (flat)', s['fixed_charge'])
        for t in s['fixed_charge_table']:
            add('fixed_charge', f"suppliers.{sid}.table[{s['fixed_charge_basis']} >= {t['from_measure']}]", t['charge'])
    for q in w['quotes']:
        key = f"quotes.{q['supplier_id']}.{q['item_id']}"
        if q['lead_time_risk'] is not None:
            add('lead_time_risk', key + '.lead_time_risk', q['lead_time_risk'])
        for f in ('last_known_unit_price', 'last_known_variable_freight'):
            if q[f] is not None:
                add('last_known', f'{key}.{f}', q[f])
    return out


def render():
    lines = [
        '# Static supplier allocation 1.2: provisional values',
        '',
        '**Status: every number below is PROVISIONAL, needs practitioner value.** Reviewed by a practitioner: no (the re-review of 2026-11-17 is by the project owner and is **not independent**). Not independently reviewed. Awaiting re-review of this table.',
        '',
        'Source: owner-practitioner re-review round 2 (docs/reviews/2026-11-17-practitioner-re-review-17.md; not independent) applied to the 1.1 rules. '
        'The reviewer gave directions and ranges, not point values, so every number here was chosen by the implementer inside the stated direction and is unconfirmed. '
        'The numbers exist only so the rules can be exercised and tested. They are not practice, not benchmarks and not recommendations. Generated by '
        '`scripts/generate_static_v12_provisional_table.py` from `fixtures/reference_cases_v1_2/`; a test fails if this file drifts from the fixtures.',
        '',
        '## Default policy values (apply to every case unless a row below overrides them)',
        '',
        '| Field | Value | Reviewer input | Changed from v1.1 | Marker |',
        '| --- | --- | --- | --- | --- |',
        '| `policy.late_inbound_tolerance_days` | 3 | 2 to 3 days | Changed: was 2 (ref-01) or 0 | ' + MARK + ' |',
        '| `policy.late_inbound_credit` | 0.50 | 50% | Same | ' + MARK + ' |',
        '| `policy.cost_tolerance_reference_value` | 100.00 USD | none (scale is scenario-agnostic) | New | ' + MARK + ' |',
        '| `policy.cost_tolerance_tiers` | 0: 3%, 0.5: 2%, 5: 1% of optimum (optimum below 50: 3%, 50 up to below 500: 2%, 500 and above: 1% when the reference is 100.00) | tighter for large orders, looser for small; shape and constants not given | Changed: replaces one fixed fraction | ' + MARK + ' |',
        '| `constraints.approval_limit` | 5,000.00 USD in the estimate cases | range 1,000 to 10,000 | Changed: was 50.00, boundary at or below | ' + MARK + ' |',
        '| `policy.moq_excess_approval_threshold` | 500.00 USD | not given | New | ' + MARK + ' |',
        '| service level | 0.95 (97.5% in ref-23 and ref-24) | service-level based; level not given | New | ' + MARK + ' |',
        '| z-table | 0.90: 1.2816, 0.95: 1.6449, 0.975: 1.9600, 0.99: 2.3263 | none | New | ' + MARK + ' |',
        '',
        '## Structural rule choices needing confirmation',
        '',
        '| Rule | Choice made | Rule id | Changed from v1.1 | Marker |',
        '| --- | --- | --- | --- | --- |',
    ]
    for name, choice, rid, changed in STRUCTURAL:
        marker = 'resolved by reviewer, not provisional' if name == 'Rounding' else MARK
        lines.append(f'| {name} | {choice} | {rid} | {changed} | {marker} |')
    lines += [
        '',
        '## Numeric policy values by case',
        '',
        'Prices, demands, capacities and dates are synthetic scenario inputs shown in each fixture beside its hand calculation; they carry no practice claim. '
        'Default policy values above are not repeated per case.',
        '',
        '| Case | Field | Meaning | Value | Changed from v1.1 | Marker |',
        '| --- | --- | --- | --- | --- | --- |',
    ]
    for path in sorted(FIXTURES.glob('ref-*.json')):
        c = json.loads(path.read_text())
        for case_id, where, meaning, value, changed in rows_for(c['case_id'], c['world']):
            lines.append(f'| {case_id} | `{where}` | {meaning} | {value} | {changed} | {MARK} |')
    lines += ['', 'Open values still requested from the reviewer: target service level and demand variability per real item, '
              'late-inbound window (2 or 3 days), tolerance tier constants and reference value, the exact approval limit inside 1,000 to 10,000, '
              'the MOQ approval threshold, and which concentration measure applies to which real task.', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    text = render()
    if '--check' in sys.argv:
        sys.exit(0 if OUT.read_text() == text else 1)
    OUT.write_text(text)
    print(f'wrote {OUT} ({len(text.splitlines())} lines)')
