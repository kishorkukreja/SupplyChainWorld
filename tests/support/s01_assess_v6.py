"""An exposure assessor for S01 v0.6 that reads ONLY what an agent is shown, conventions block included (S01.3).

Input: one `view` (`clock`, `state`, `rules`, `tools`) as returned by `runner.view()` or recorded in a transcript.
Unlike `s01_assess.py` (v0.2 to v0.5), nothing is assumed: every convention the assessor needs is READ from
`rules['conventions']['parameters']`, a missing or unknown value raises `ConventionError` (the assessor refuses to
guess), and flipping a stated value changes the answer (tests use that to show the block is load-bearing). It uses no
scenario object, no simulator internals and no checker output.

Quantities (definitions of the assessor, not of the world):
* units_at_risk: units not delivered by the close of the order's due day (the world's `on_time_means`);
* earliest_feasible_delivery: first day on which every unit still wanted is delivered or cancelled;
* shortfall_by_order, penalties, recovery_spend under one recovery option taken today with greedy production.
"""

REQUIRED = ('receipts_usable_on_arrival_day', 'production_completes_at', 'shipping_starts_on', 'shipping_priority',
            'penalty_rate_divisor_percent_of_value', 'penalty_rate_unit_fixed_per_unit',
            'penalty_rate_unit_per_unit_per_day', 'penalty_rounding', 'penalty_cap_basis', 'cancellation_day',
            'on_time_means')
SUPPORTED = {
    'production_completes_at': ('day_close',),
    'shipping_starts_on': ('order_due_day', 'as_soon_as_finished'),
    'shipping_priority': ('tier_weight_descending_then_order_id_ascending', 'order_id_ascending'),
    'penalty_rate_unit_fixed_per_unit': ('usd_per_undelivered_unit_charged_once_on_due_day',),
    'penalty_rate_unit_per_unit_per_day': ('usd_per_undelivered_unit_per_day_from_due_day',),
    'penalty_rounding': ('down_to_whole_usd_each_day_per_order',),
    'penalty_cap_basis': ('percent_of_order_value',),
    'cancellation_day': ('due_day_plus_cancel_days_after_due',),
    'on_time_means': ('delivered_by_close_of_due_day',),
}


class ConventionError(ValueError):
    pass


def conventions_of(view):
    block = view['rules'].get('conventions')
    if not isinstance(block, dict) or not isinstance(block.get('parameters'), dict):
        raise ConventionError('the view carries no conventions block')
    params = block['parameters']
    for key in REQUIRED:
        if key not in params:
            raise ConventionError(f'conventions.parameters lacks {key}')
    for key, allowed in SUPPORTED.items():
        if params[key] not in allowed:
            raise ConventionError(f'unsupported value for {key}: {params[key]!r}')
    if type(params['receipts_usable_on_arrival_day']) is not bool:
        raise ConventionError('receipts_usable_on_arrival_day must be true or false')
    if type(params['penalty_rate_divisor_percent_of_value']) is not int or params['penalty_rate_divisor_percent_of_value'] < 1:
        raise ConventionError('penalty_rate_divisor_percent_of_value must be a positive integer')
    return params


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
    o = _offer(view, option)
    if o is None or o[0] == 'maintain':
        return None
    return {'tool': 'commit_recovery', 'arguments': {'choice': o[0], 'quantity': o[1]}, 'action_id': 'assess-1'}


def assess(view, option='maintain', *, worst_case=False):
    """Project the episode from this view under `option`; None when the option is not offered today."""
    conv = conventions_of(view)
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
    for x in orders.values():                   # due days already closed: the view states what was delivered on time
        if x['on_time_units'] is not None:
            shortfall[x['order_id']] = x['quantity'] - x['on_time_units']
    penalties = s['penalties']
    for day in range(clock['current_day'], horizon + 1):
        arrived_today = 0
        if day > clock['current_day']:
            for lot in lots:
                if not lot['received'] and lot['arrival_day'] == day:
                    lot['received'] = True
                    comp += lot['quantity']
                    arrived_today += lot['quantity']
        usable = comp if conv['receipts_usable_on_arrival_day'] else comp - arrived_today
        demand = sum(x['quantity'] - x['delivered'] - x['cancelled'] for x in orders.values() if x['status'] == 'open')
        q = s['scheduled_production'] if day == clock['current_day'] and s['scheduled_production'] is not None else \
            max(0, min(r['capacity'], usable, demand - fin))
        comp -= q
        fin += q
        eligible = [x for x in orders.values() if x['status'] == 'open'
                    and (day >= x['due_day'] or conv['shipping_starts_on'] == 'as_soon_as_finished')]
        if conv['shipping_priority'] == 'order_id_ascending':
            sequence = sorted(eligible, key=lambda x: x['order_id'])
        else:
            sequence = sorted(eligible, key=lambda x: (-tiers[x['tier']]['weight'], x['order_id']))
        for x in sequence:
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
                amount = undelivered * t['unit_value'] * t['penalty_rate'] // conv['penalty_rate_divisor_percent_of_value']
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
            if tier['on_shortfall'] == 'cancel_after' and day == x['due_day'] + tier['cancel_days_after_due']:
                x['cancelled'] += undelivered
                x['status'] = 'cancelled'
        if full_day is None and all(x['delivered'] + x['cancelled'] == x['quantity'] for x in orders.values()):
            full_day = day
    return {'option': option, 'units_at_risk': sum(shortfall.values()), 'shortfall_by_order': shortfall,
            'earliest_feasible_delivery': full_day, 'penalties': penalties, 'recovery_spend': s['incremental_spend'] + spend}
