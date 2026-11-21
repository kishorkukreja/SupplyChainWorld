#!/usr/bin/env python3
"""Regenerate fixtures/dynamic/v0.4/hand-ledgers.json (issue #36, round 3).

This is the reproducible form of the hand-worked ledgers. It deliberately imports NOTHING from
`supplychainworld` (no simulator, no verifier, no runner, no policy code). The only inputs are:

  1. the scenario numbers in fixtures/dynamic/v0.4/scenarios.json (plain data), and
  2. the PLANS table below: for each scenario and declared policy, the recovery commitments that the
     policy's plain-English rule produces. The plans were worked out by hand from the rule text in
     docs/acceptance/dynamic-v0.4-provisional-values.md section 1, not copied from simulator output.
     Policy rules, all fired on the first day an alert is visible (day 1 in every scenario):
       expedite_on_alert   expedite the whole primary lot (8 units)
       alternate_on_alert  buy the whole alternate availability (8 units)
       combo_on_alert      expedite half the lot (4), then buy half the alternate availability (4)
       staged_revisit      expedite half the lot (4); on the first later day the firm delay is visible and
                           an expedite offer still helps, expedite the rest of the lot at that day's price
     Production each day: release min(capacity, components on hand, open demand - finished on hand).

v0.4 conventions (round 3, the second is an UNRESOLVED assumption for the reviewer): an alternate unit costs
its premium only (base cost of a recovery lot is cost-neutral and excluded), and components left on hand at the
end are presumed alternate-bought first, so alternate-bought surplus earns no salvage.

The ledger arithmetic below is a day-by-day table written independently of the simulator
(`dynamic_v3.py`) and of the verifier (`dynamic_verifier_v3.py`): it keeps inbound units in a dated
schedule, and money in simple running sums. The hand ledgers are then compared with the simulator
and the verifier by the tests; any mismatch is investigated, never auto-accepted.

Usage: python scripts/generate_hand_ledgers_v04.py [--check]
  --check  exit nonzero if the committed hand-ledgers.json differs from this script's output.
All numbers are PROVISIONAL, needs practitioner value. Not reviewed by a practitioner.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'fixtures/dynamic/v0.4/scenarios.json'
OUT = ROOT / 'fixtures/dynamic/v0.4/hand-ledgers.json'

# (commit day, choice, units) per scenario and policy. Worked out by hand, see the module docstring.
PLANS = {
    's04-sudden-5d': {
        'maintain': [],
        'expedite_on_alert': [(1, 'expedite', 8)],
        'alternate_on_alert': [(1, 'alternate', 8)],
        'combo_on_alert': [(1, 'expedite', 4), (1, 'alternate', 4)],
        'staged_revisit': [(1, 'expedite', 4), (2, 'expedite', 4)],
    },
    's04-warned-delayed-10d': {
        'maintain': [],
        'expedite_on_alert': [(1, 'expedite', 8)],
        'alternate_on_alert': [(1, 'alternate', 8)],
        'combo_on_alert': [(1, 'expedite', 4), (1, 'alternate', 4)],
        'staged_revisit': [(1, 'expedite', 4), (2, 'expedite', 4)],
    },
    's04-warned-no-delay-10d': {
        'maintain': [],
        'expedite_on_alert': [(1, 'expedite', 8)],
        'alternate_on_alert': [(1, 'alternate', 8)],
        'combo_on_alert': [(1, 'expedite', 4), (1, 'alternate', 4)],
        'staged_revisit': [(1, 'expedite', 4)],          # no firm delay ever, so no revisit
    },
    's04-multitier-cancel-10d': {
        'maintain': [],
        'expedite_on_alert': [(1, 'expedite', 8)],
        'alternate_on_alert': [(1, 'alternate', 8)],
        'combo_on_alert': [(1, 'expedite', 4), (1, 'alternate', 4)],
        'staged_revisit': [(1, 'expedite', 4), (2, 'expedite', 4)],
    },
    's04-alt-cheaper-10d': {
        'maintain': [],
        'expedite_on_alert': [(1, 'expedite', 8)],
        'alternate_on_alert': [(1, 'alternate', 8)],
        'combo_on_alert': [(1, 'expedite', 4), (1, 'alternate', 4)],
        'staged_revisit': [(1, 'expedite', 4), (2, 'expedite', 4)],
    },
}
POLICIES = ('maintain', 'expedite_on_alert', 'alternate_on_alert', 'combo_on_alert', 'staged_revisit')


def card_row(card, day):
    for d, premium, arrival in card:
        if d == day:
            return premium, arrival
    raise SystemExit(f'no rate card row for day {day}')


def work_episode(fx, plan):
    sc, horizon = fx['scenario'], fx['horizon_days']
    base = sc['base_unit_cost']
    salvage_each = base * sc['salvage_pct_by_class'][sc['part_class']] // 100
    weight = {t['tier']: t['weight'] for t in sc['tiers']}
    cancel_after = {t['tier']: t['cancel_days_after_due'] for t in sc['tiers']}

    # ---- inbound schedule. Primary units: the part not expedited arrives on the delayed day when the
    # firm notice reaches it (the notice comes at the opening of notice_day, before that day's actions);
    # a lot whose every unit was expedited before the notice is not moved.
    inbound = {}                       # day -> units, both suppliers
    primary_left = sc['primary_quantity']
    spend = {'expedite': 0, 'alternate': 0}
    units_by_source = {'primary': 0, 'alternate': 0}
    delayed = sc['delay_outcome'] == 'delay'
    for day, choice, qty in plan:
        premium, arrival = card_row(sc['expedite_card' if choice == 'expedite' else 'alternate_card'], day)
        if choice == 'expedite':
            spend['expedite'] += qty * (base * premium // 100)          # premium only
            inbound[arrival] = inbound.get(arrival, 0) + qty
            units_by_source['primary'] += qty
            primary_left -= qty
        else:
            spend['alternate'] += qty * (base * premium // 100)         # premium only; base cost is cost-neutral
            inbound[arrival] = inbound.get(arrival, 0) + qty
            units_by_source['alternate'] += qty
    if primary_left:
        arrive = sc['delayed_arrival_day'] if delayed else sc['primary_promised_day']
        inbound[arrive] = inbound.get(arrive, 0) + primary_left
        units_by_source['primary'] += primary_left

    # ---- orders
    orders = []
    for o in sc['orders']:
        orders.append({'id': o['order_id'], 'tier': o['tier'], 'qty': o['quantity'], 'due': o['due_day'],
                       'val': o['unit_value'], 'ptype': o['penalty_type'], 'rate': o['penalty_rate'],
                       'cap_pct': o['penalty_cap_pct'], 'got': 0, 'cancelled': 0, 'open': True,
                       'pen': 0, 'late_unit_days': 0, 'on_time': None})
    comps, fin, produced, delivered, cancelled_total, penalty_total = sc['opening_components'], 0, 0, 0, 0, 0
    rows = {k: [] for k in ('received', 'produced', 'shipped', 'components_close', 'finished_close',
                            'delivered_total', 'penalty_total', 'spend_total', 'cancelled_total')}
    for day in range(1, horizon + 1):
        got_today = inbound.get(day, 0)
        comps += got_today
        # action phase: production release
        demand = sum(o['qty'] - o['got'] - o['cancelled'] for o in orders if o['open'])
        make = min(sc['daily_capacity'], comps, max(0, demand - fin))
        # close
        comps -= make
        fin += make
        produced += make
        shipped = 0
        for o in sorted((o for o in orders if o['open'] and day >= o['due']),
                        key=lambda o: (-weight[o['tier']], o['id'])):
            ship = min(fin, o['qty'] - o['got'])
            o['got'] += ship
            fin -= ship
            delivered += ship
            shipped += ship
        for o in orders:
            if not o['open'] or day < o['due']:
                continue
            if day == o['due']:
                o['on_time'] = o['got']
            short = o['qty'] - o['got']
            if short == 0:
                o['open'] = False
                continue
            if o['ptype'] == 'percent_of_value':
                fee = short * o['val'] * o['rate'] // 10000
            elif o['ptype'] == 'fixed_per_unit':
                fee = short * o['rate'] if day == o['due'] else 0
            else:
                fee = short * o['rate']
            if o['cap_pct'] is not None:
                room = o['qty'] * o['val'] * o['cap_pct'] // 100 - o['pen']
                fee = max(0, min(fee, room))
            o['pen'] += fee
            penalty_total += fee
            o['late_unit_days'] += short
            if cancel_after[o['tier']] is not None and day == o['due'] + cancel_after[o['tier']]:
                o['cancelled'] += short
                cancelled_total += short
                o['open'] = False
        spent = sum(
            qty * (base * card_row(sc['expedite_card'], d)[0] // 100 if ch == 'expedite'
                   else base * card_row(sc['alternate_card'], d)[0] // 100)
            for d, ch, qty in plan if d <= day)
        for k, v in (('received', got_today), ('produced', make), ('shipped', shipped), ('components_close', comps),
                     ('finished_close', fin), ('delivered_total', delivered), ('penalty_total', penalty_total),
                     ('spend_total', spent), ('cancelled_total', cancelled_total)):
            rows[k].append(v)
    # ---- end of horizon
    # Alternate-bought surplus earns no salvage: leftovers are presumed to be alternate units first.
    alt_received = sum(qty for d, ch, qty in plan if ch == 'alternate'
                       and card_row(sc['alternate_card'], d)[1] <= horizon)
    uncredited = min(comps, alt_received)
    eligible = comps - uncredited
    salvage = eligible * salvage_each
    total_spend = spend['expedite'] + spend['alternate']
    pending = sum(q for d, q in inbound.items() if d > horizon)
    inbound_total = sum(inbound.values())
    otif = sum(1 for o in orders if o['on_time'] == o['qty'])
    tiers = {}
    for o in orders:
        t = tiers.setdefault(o['tier'], {'otif_orders_met': 0, 'ordered': 0, 'on_time_units': 0, 'delivered': 0,
                                         'cancelled': 0, 'unit_days_late': 0, 'penalties': 0})
        t['otif_orders_met'] += 1 if o['on_time'] == o['qty'] else 0
        t['ordered'] += o['qty']
        t['on_time_units'] += o['on_time']
        t['delivered'] += o['got']
        t['cancelled'] += o['cancelled']
        t['unit_days_late'] += o['late_unit_days']
        t['penalties'] += o['pen']
    metrics = {
        'recovery_spend': total_spend, 'expedite_spend': spend['expedite'], 'alternate_spend': spend['alternate'],
        'service_penalties': penalty_total, 'salvage_credit': salvage,
        'net_cost': total_spend + penalty_total - salvage,
        'salvage_eligible_components': eligible, 'uncredited_alternate_surplus': uncredited,
        'ending_components': comps, 'otif_orders_met': otif,
        'on_time_units': sum(o['on_time'] for o in orders), 'delivered_total': delivered,
        'cancelled_units': cancelled_total, 'unit_days_late': sum(o['late_unit_days'] for o in orders),
        'priority_weighted_unit_days_late': sum(weight[o['tier']] * o['late_unit_days'] for o in orders),
        'cancelled_order_value': sum(o['cancelled'] * o['val'] for o in orders),
        'undelivered_at_end': sum(o['qty'] - o['got'] - o['cancelled'] for o in orders),
        'pending_inbound_units': pending,
        'primary_reliance_pct': (100 * units_by_source['primary'] // inbound_total) if inbound_total else None,
        'ending_cover_days_floor': comps // sc['daily_capacity'],
        'recovery_commitments': len(plan), 'unused_recovery_budget': sc['recovery_budget'] - total_spend,
        'tiers': tiers}
    return {'ledger': rows, 'metrics': metrics}


def build():
    data = json.loads(FIXTURES.read_text())
    out = {}
    for fx in data['fixtures']:
        out[fx['fixture_id']] = {p: work_episode(fx, PLANS[fx['fixture_id']][p]) for p in POLICIES}
    return {'basis': 'Hand-worked per-day ledgers and per-episode metrics for issue #36 (S01 v0.4), derived by '
                     'scripts/generate_hand_ledgers_v04.py from the written rules in '
                     'docs/acceptance/dynamic-v0.4-provisional-values.md, never from simulator or verifier output '
                     '(the script imports no project code). Arrays are indexed by day 1..N. Every number is '
                     'PROVISIONAL, needs practitioner value. Synthetic, not reviewed by a practitioner.',
            'fixtures': out}


def main():
    text = json.dumps(build(), indent=1) + '\n'
    if '--check' in sys.argv:
        if OUT.read_text() != text:
            print('hand-ledgers.json differs from the generator output', file=sys.stderr)
            return 1
        print('hand-ledgers.json matches the generator output')
        return 0
    OUT.write_text(text)
    print(f'wrote {OUT}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
