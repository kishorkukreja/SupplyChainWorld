"""An exposure assessor that reads ONLY what an agent is shown (S01.3).

Input: one `view` as returned by `runner.view()` or recorded in a transcript (`clock`, `state`, `rules`, `tools`).
Nothing from the scenario object, the simulator internals or the verifier is used. The assessor projects the
rest of the horizon forward under one recovery option and reports the quantities an assessor needs:

* units_at_risk: units not delivered by the close of their order's due day, per order and in total;
* earliest_feasible_delivery: first day on which every unit still wanted is delivered (None: not within the horizon);
* penalties: contract penalties implied by the visible terms.

What the view does NOT state, so the assessor must assume it (each assumption is a switch in `Conventions` and is
reported in evidence/s01-audit/s01-3-assessment.md): receipts are usable the day they arrive, production completes
at close, shipping is automatic from the due day in tier-weight then order-id order, percent penalties are whole
percent per late day (v0.2) or basis points (v0.3, v0.4), fixed penalties are charged once at the due-day close.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Conventions:
    receipt_usable_same_day: bool = True
    ship_from_due_day: bool = True          # False: ship as soon as finished goods exist
    percent_divisor: int = 10000            # v0.2 used whole percent (100); v0.3 and v0.4 use basis points
    greedy_release: bool = True


V2_CONVENTIONS = Conventions(percent_divisor=100)
V34_CONVENTIONS = Conventions()


def _offer(view, option):
    """(choice, quantity, unit_cost, arrival_day) for a recovery option from today's visible offer, or None."""
    if option == 'maintain':
        return ('maintain', 0, 0, None)
    offers = view['rules'].get('recovery_offers')
    if not offers or 'budget_remaining' not in offers:
        return None
    choice = 'expedite' if option.startswith('expedite') else 'alternate'
    today = offers[choice]['today']
    if not today:
        return None
    unit = today['unit_cost']
    qty = today['max_units'] if unit == 0 else min(today['max_units'], offers['budget_remaining'] // unit)
    if qty < 1:
        return None
    return (choice, qty, unit, today['arrival_day'])


def option_call(view, option):
    """The tool call an agent would make for `option` from this view (None: option not available)."""
    o = _offer(view, option)
    if o is None:
        return None
    if o[0] == 'maintain':
        return None
    return {'tool': 'commit_recovery', 'arguments': {'choice': o[0], 'quantity': o[1]}, 'action_id': 'assess-1'}


def assess(view, option='maintain', *, conv=V34_CONVENTIONS, worst_case=False):
    """Project the episode from this view under `option` ('maintain', 'expedite_max', 'alternate_max').

    worst_case=True drops primary supply that has not yet arrived (an upper bound while a delay is only warned).
    Returns None when the option is not offered today.
    """
    o = _offer(view, option)
    if o is None:
        return None
    s, r, clock = view['state'], view['rules'], view['clock']
    comp, fin = s['component_on_hand'], s['finished_on_hand']
    lots = [dict(x) for x in s['lots']]
    spend = 0
    if o[0] == 'expedite':
        primary = next(x for x in lots if x['lot_id'] == 'primary')
        spend = o[1] * o[2]
        if o[1] == primary['quantity']:
            primary['arrival_day'] = o[3]
        else:
            primary['quantity'] -= o[1]
            lots.append({'lot_id': 'exp', 'source': 'primary', 'quantity': o[1], 'arrival_day': o[3], 'received': False})
    elif o[0] == 'alternate':
        spend = o[1] * o[2]
        lots.append({'lot_id': 'alt', 'source': 'alternate', 'quantity': o[1], 'arrival_day': o[3], 'received': False})
    if worst_case:
        lots = [x for x in lots if x['received'] or x['source'] != 'primary' or x['lot_id'] == 'exp']
    tiers = {t['tier']: t for t in r['tiers']}
    terms = {t['order_id']: t for t in r['orders']}
    orders = {x['order_id']: dict(x) for x in s['orders']}
    horizon = clock['horizon_days']
    shortfall, full_day = {}, None
    for x in orders.values():                       # due days already closed: the view states what was delivered on time
        if x['on_time_units'] is not None:
            shortfall[x['order_id']] = x['quantity'] - x['on_time_units']
    penalties = s['penalties']
    for day in range(clock['current_day'], horizon + 1):
        if day > clock['current_day']:
            for lot in lots:
                if not lot['received'] and lot['arrival_day'] == day:
                    lot['received'] = True
                    comp += lot['quantity']
        if conv.receipt_usable_same_day is False:      # alternative reading: stock is usable only from the next day
            usable = comp - sum(l['quantity'] for l in lots if l['arrival_day'] == day and l['received'] and day > clock['current_day'])
        else:
            usable = comp
        demand = sum(x['quantity'] - x['delivered'] - x['cancelled'] for x in orders.values() if x['status'] == 'open')
        q = s['scheduled_production'] if day == clock['current_day'] and s['scheduled_production'] is not None else \
            max(0, min(r['capacity'], usable, demand - fin))
        comp -= q
        fin += q
        due = [x for x in orders.values() if x['status'] == 'open' and (day >= x['due_day'] or not conv.ship_from_due_day)]
        for x in sorted(due, key=lambda x: (-tiers[x['tier']]['weight'], x['order_id'])):
            ship = min(fin, x['quantity'] - x['delivered'])
            x['delivered'] += ship
            fin -= ship
        for x in orders.values():
            if x['status'] != 'open' or day < x['due_day']:
                continue
            if day == x['due_day']:
                shortfall[x['order_id']] = x['quantity'] - x['delivered']
            undelivered = x['quantity'] - x['delivered']
            if undelivered == 0:
                x['status'] = 'complete'
                continue
            t = terms[x['order_id']]
            if t['penalty_type'] == 'percent_of_value':
                amount = undelivered * t['unit_value'] * t['penalty_rate'] // conv.percent_divisor
            elif t['penalty_type'] == 'fixed_per_unit':
                amount = undelivered * t['penalty_rate'] if day == x['due_day'] else 0
            else:
                amount = undelivered * t['penalty_rate']
            cap = t.get('penalty_cap_pct')
            if cap is not None:
                amount = max(0, min(amount, t['quantity'] * t['unit_value'] * cap // 100 - x['penalty_total']))
            x['penalty_total'] += amount
            penalties += amount
            tier = tiers[x['tier']]
            if tier['on_shortfall'] == 'cancel_after':
                cancel_day = tier['cancel_day'] if 'cancel_day' in tier else x['due_day'] + tier['cancel_days_after_due']
                if day == cancel_day:
                    x['cancelled'] += undelivered
                    x['status'] = 'cancelled'
        if full_day is None and all(x['delivered'] + x['cancelled'] == x['quantity'] for x in orders.values()):
            full_day = day
    return {'option': option, 'units_at_risk': sum(shortfall.values()), 'shortfall_by_order': shortfall,
            'earliest_feasible_delivery': full_day, 'penalties': penalties, 'recovery_spend': s['incremental_spend'] + spend}
