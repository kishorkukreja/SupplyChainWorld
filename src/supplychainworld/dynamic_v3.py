"""Deterministic operational kernel for the S01 v0.3 scenario family (issue #36, round 2).

Built beside, not on top of, `dynamic.py` (v0.1) and `dynamic_v2.py` (v0.2); both are untouched. It
applies the owner-practitioner re-review in docs/reviews/2026-11-17-practitioner-re-review-17.md:

* Expedite is a percent premium on a stated base primary unit cost, charged on units moved earlier.
  An alternate-supplier spot buy is a percent premium over the primary unit cost, charged on the whole
  new lot (the primary lot still arrives). Rate cards rise by day.
* Late penalty is a percent of order value per day late (rate in basis points) with a total cap, a
  percent of the order value. Fixed per unit and per unit per day remain contract terms.
* Salvage depends on the part class (standard or custom); a scenario declares its class.
* A cancel-after tier cancels N days after each order's due date; a backlog tier keeps its backlog.
* A warned signal carries a qualitative level (low, medium or high), never a percent, never the outcome.
* Metric proxies are unchanged from v0.2 (accepted by the reviewer as written).

EVERY number in a scenario is PROVISIONAL and needs a practitioner value. This is a narrow
engineering model, not a validated supply-chain simulator. Quantities are whole units and money is
whole USD, so every rate card cell must give a whole-dollar unit cost.
"""
from copy import deepcopy

SCHEMA = '3.0'
VALUES_STATUS = 'PROVISIONAL, needs practitioner value; not reviewed by a practitioner'
PENALTY_TYPES = ('percent_of_value', 'fixed_per_unit', 'per_unit_per_day')
SHORTFALL_RULES = ('backlog', 'cancel_after')
SIGNAL_LEVELS = ('low', 'medium', 'high')
PART_CLASSES = ('standard', 'custom')
SIGNAL_TEXT = 'Possible delay on the primary PO (qualitative level, not a commitment)'
SCORECARD_SCHEMA = 'dyn-scorecard-3'


def _int(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f'{name} must be an integer >= {minimum}')


class ScenarioV3:
    """Scenario mechanics, including hidden future events. Keep inside the environment."""
    FIELDS = ('scenario_id', 'opening_components', 'daily_capacity', 'primary_quantity', 'primary_promised_day',
              'signal_day', 'signal_level', 'notice_day', 'delay_outcome', 'delayed_arrival_day',
              'base_unit_cost', 'expedite_card', 'alternate_card', 'alternate_max_units', 'recovery_budget',
              'part_class', 'salvage_pct_by_class', 'tiers', 'orders')

    def __init__(self, **kw):
        extra = set(kw) - set(self.FIELDS) - {'schema_version', 'runtime_version'}
        if extra:
            raise ValueError('unknown scenario fields: ' + ', '.join(sorted(extra)))
        missing = [f for f in self.FIELDS if f not in kw]
        if missing:
            raise ValueError('missing scenario fields: ' + ', '.join(missing))
        if kw.get('schema_version', SCHEMA) != SCHEMA or kw.get('runtime_version', SCHEMA) != SCHEMA:
            raise ValueError('unsupported scenario or runtime version')
        for f in self.FIELDS:
            setattr(self, f, deepcopy(kw[f]))
        self.schema_version = self.runtime_version = SCHEMA
        self._validate()

    @property
    def salvage_per_component(self):
        """Salvage credit per leftover component: class fraction of the base primary unit cost, rounded down."""
        return self.base_unit_cost * self.salvage_pct_by_class[self.part_class] // 100

    def expedite_unit_cost(self, premium_pct):
        """Premium only, charged on each unit moved earlier (the base price is paid on the PO anyway)."""
        return self.base_unit_cost * premium_pct // 100

    def alternate_unit_cost(self, premium_pct):
        """Whole price of a unit from the alternate supplier: base plus premium."""
        return self.base_unit_cost + self.base_unit_cost * premium_pct // 100

    def rate_card(self, choice):
        """Visible rate card rows with the derived whole-dollar unit cost."""
        rows, unit = ((self.expedite_card, self.expedite_unit_cost) if choice == 'expedite'
                      else (self.alternate_card, self.alternate_unit_cost))
        return [{'day': d, 'premium_pct': p, 'unit_cost': unit(p), 'arrival_day': a} for d, p, a in rows]

    def to_dict(self):
        return {f: deepcopy(getattr(self, f)) for f in self.FIELDS}

    def _validate(self):
        if not isinstance(self.scenario_id, str) or not self.scenario_id.strip():
            raise ValueError('scenario_id must be a nonempty string')
        for f in ('opening_components', 'daily_capacity', 'primary_quantity', 'alternate_max_units',
                  'recovery_budget'):
            _int(getattr(self, f), f)
        _int(self.base_unit_cost, 'base_unit_cost', 1)
        if self.part_class not in PART_CLASSES:
            raise ValueError('part_class must be standard or custom')
        if not isinstance(self.salvage_pct_by_class, dict) or set(self.salvage_pct_by_class) != set(PART_CLASSES):
            raise ValueError('salvage_pct_by_class needs exactly standard and custom')
        for k, v in self.salvage_pct_by_class.items():
            _int(v, 'salvage pct ' + k)
            if v > 100:
                raise ValueError('salvage pct must be at most 100')
        for f in ('primary_promised_day', 'notice_day'):
            _int(getattr(self, f), f, 1)
        if self.signal_day is not None:
            _int(self.signal_day, 'signal_day', 1)
            if self.signal_level not in SIGNAL_LEVELS:
                raise ValueError('signal_level must be low, medium or high')
            if not self.signal_day < self.notice_day:
                raise ValueError('signal must precede the firm notice')
        elif self.signal_level is not None:
            raise ValueError('signal_level requires signal_day')
        if not self.notice_day < self.primary_promised_day:
            raise ValueError('firm notice must precede the promised arrival')
        if self.delay_outcome not in ('delay', 'none'):
            raise ValueError('delay_outcome must be delay or none')
        if self.delay_outcome == 'delay':
            _int(self.delayed_arrival_day, 'delayed_arrival_day', 1)
            if self.delayed_arrival_day <= self.primary_promised_day:
                raise ValueError('delayed arrival must follow the promised arrival')
        elif self.delayed_arrival_day is not None:
            raise ValueError('delayed_arrival_day must be None when there is no delay')
        for name in ('expedite_card', 'alternate_card'):
            rows = getattr(self, name)
            if not isinstance(rows, list) or not rows:
                raise ValueError(f'{name} must be a nonempty list of [day, premium_pct, arrival_day]')
            days = set()
            for row in rows:
                if not isinstance(row, list) or len(row) != 3:
                    raise ValueError(f'{name} rows must be [day, premium_pct, arrival_day]')
                _int(row[0], name + ' day', 1)
                _int(row[1], name + ' premium_pct', 1)
                _int(row[2], name + ' arrival_day', 1)
                if row[2] <= row[0] or row[0] in days:
                    raise ValueError(f'{name}: arrival must follow the commit day and days must be unique')
                if self.base_unit_cost * row[1] % 100:
                    raise ValueError(f'{name}: base_unit_cost x premium_pct must be a whole dollar')
                days.add(row[0])
        if not isinstance(self.tiers, list) or not self.tiers:
            raise ValueError('tiers must be a nonempty list')
        names = set()
        for t in self.tiers:
            if not isinstance(t, dict) or set(t) != {'tier', 'weight', 'on_shortfall', 'cancel_days_after_due'}:
                raise ValueError('tier needs exactly tier, weight, on_shortfall, cancel_days_after_due')
            if not isinstance(t['tier'], str) or t['tier'] in names:
                raise ValueError('tier names must be unique strings')
            names.add(t['tier'])
            _int(t['weight'], 'tier weight', 1)
            if t['on_shortfall'] not in SHORTFALL_RULES:
                raise ValueError('unknown on_shortfall rule')
            if t['on_shortfall'] == 'cancel_after':
                _int(t['cancel_days_after_due'], 'cancel_days_after_due', 0)
            elif t['cancel_days_after_due'] is not None:
                raise ValueError('cancel_days_after_due only applies to cancel_after tiers')
        if not isinstance(self.orders, list) or not self.orders:
            raise ValueError('orders must be a nonempty list')
        ids = set()
        for o in self.orders:
            if not isinstance(o, dict) or set(o) != {'order_id', 'tier', 'quantity', 'due_day', 'unit_value',
                                                     'penalty_type', 'penalty_rate', 'penalty_cap_pct'}:
                raise ValueError('order has the wrong fields')
            if not isinstance(o['order_id'], str) or o['order_id'] in ids or o['tier'] not in names:
                raise ValueError('order ids must be unique and tiers known')
            ids.add(o['order_id'])
            _int(o['quantity'], 'order quantity', 1)
            _int(o['due_day'], 'due_day', 1)
            _int(o['unit_value'], 'unit_value')
            _int(o['penalty_rate'], 'penalty_rate')
            if o['penalty_type'] not in PENALTY_TYPES:
                raise ValueError('unknown penalty_type')
            if o['penalty_type'] == 'percent_of_value' and o['penalty_rate'] > 10000:
                raise ValueError('percent_of_value penalty_rate is in basis points and must be at most 10000')
            if o['penalty_cap_pct'] is not None:
                _int(o['penalty_cap_pct'], 'penalty_cap_pct')
                if o['penalty_cap_pct'] > 100:
                    raise ValueError('penalty_cap_pct must be at most 100')


def _tier(scn, name):
    return next(t for t in scn.tiers if t['tier'] == name)


class OperationalWorldV3:
    """One factory, one component, several customer orders in tiers (v0.3 family).

    Instances own their state; `snapshot` and `history` return detached copies. Rejected commands
    are recorded without changing operational state. The public methods mirror
    `OperationalWorld` so the observable runner can drive either world.
    """

    def __init__(self, horizon_days: int = 5, *, scenario: ScenarioV3):
        if type(horizon_days) is not int or horizon_days < 1:
            raise ValueError('horizon_days must be a positive integer')
        if not isinstance(scenario, ScenarioV3):
            raise TypeError('scenario must be a ScenarioV3')
        for o in scenario.orders:
            if o['due_day'] > horizon_days:
                raise ValueError('every order must fall due within the horizon')
        self._scn = scenario
        self._horizon = horizon_days
        self.reset()

    # ------------------------------------------------------------------ state
    def reset(self):
        c = self._scn
        self._s = {
            'schema_version': SCHEMA, 'runtime_version': SCHEMA, 'scenario_id': c.scenario_id, 'day': 1,
            'horizon_days': self._horizon, 'phase': 'action', 'component_on_hand': c.opening_components,
            'finished_on_hand': 0, 'produced_total': 0, 'delivered_total': 0, 'cancelled_total': 0,
            'lots': [{'lot_id': 'primary', 'source': 'primary', 'quantity': c.primary_quantity,
                      'arrival_day': c.primary_promised_day, 'received': False, 'expedited': False}],
            'orders': [{'order_id': o['order_id'], 'tier': o['tier'], 'quantity': o['quantity'], 'due_day': o['due_day'],
                        'delivered': 0, 'cancelled': 0, 'status': 'open', 'penalty_total': 0,
                        'unit_days_late': 0, 'days_short': 0, 'on_time_units': None} for o in c.orders],
            'incremental_spend': 0, 'penalties': 0, 'salvage_credit': None, 'scheduled_production': None,
            'commitments': [], 'signals': [], 'notices': [], 'open_demand': 0}
        self._refresh()
        self._history = []
        self._open_day()
        return self.snapshot()

    def _refresh(self):
        s = self._s
        s['open_demand'] = sum(o['quantity'] - o['delivered'] - o['cancelled']
                               for o in s['orders'] if o['status'] == 'open')

    def snapshot(self):
        return deepcopy(self._s)

    def history(self):
        return deepcopy(self._history)

    def _record(self, kind, details, accepted, reason=None):
        self._refresh()
        self._history.append({'day': self._s['day'], 'kind': kind, 'details': deepcopy(details),
                              'accepted': accepted, 'reason': reason, 'state': self.snapshot()})

    def _reject(self, kind, details, reason):
        self._record(kind, details, False, reason)
        return {'accepted': False, 'reason': reason}

    # ------------------------------------------------------------- observation
    def _alert_visible(self):
        return bool(self._s['signals'] or self._s['notices'])

    def _row(self, card, day):
        return next((r for r in card if r[0] == day), None)

    def _expedite_today(self):
        row = self._row(self._scn.expedite_card, self._s['day'])
        lot = next((x for x in self._s['lots'] if x['lot_id'] == 'primary'), None)
        if row is None or lot is None or lot['received'] or lot['expedited'] or lot['arrival_day'] <= row[2]:
            return None
        return {'unit_cost': self._scn.expedite_unit_cost(row[1]), 'premium_pct': row[1], 'arrival_day': row[2],
                'max_units': lot['quantity']}

    def _alternate_today(self):
        row = self._row(self._scn.alternate_card, self._s['day'])
        bought = sum(c['quantity'] for c in self._s['commitments'] if c['choice'] == 'alternate')
        left = self._scn.alternate_max_units - bought
        if row is None or left <= 0:
            return None
        return {'unit_cost': self._scn.alternate_unit_cost(row[1]), 'premium_pct': row[1], 'arrival_day': row[2],
                'max_units': left}

    def observation(self):
        """Visible state and decision rules, excluding the hidden future event plan."""
        c, s = self._scn, self._s
        rules = {'capacity': c.daily_capacity, 'recovery_budget': c.recovery_budget,
                 'base_unit_cost': c.base_unit_cost, 'part_class': c.part_class,
                 'salvage_pct_by_class': deepcopy(c.salvage_pct_by_class),
                 'salvage_per_component': c.salvage_per_component,
                 'tiers': deepcopy(c.tiers), 'orders': deepcopy(c.orders), 'values_status': VALUES_STATUS}
        if self._alert_visible():
            rules['recovery_offers'] = {
                'budget_remaining': c.recovery_budget - s['incremental_spend'],
                'expedite': {'basis': 'premium on the base unit cost, charged per unit moved earlier',
                             'rate_card': c.rate_card('expedite'), 'today': self._expedite_today()},
                'alternate': {'basis': 'base unit cost plus premium, charged per unit of a new lot; the primary lot still arrives',
                              'rate_card': c.rate_card('alternate'), 'today': self._alternate_today()}}
        return {'state': self.snapshot(), 'rules': rules}

    # ---------------------------------------------------------------- commands
    def choose_recovery(self, choice, quantity=None, commit_id=None):
        """Commit one recovery action: expedite or alternate, `quantity` units, today's price."""
        d = {'choice': choice, 'quantity': quantity, 'commit_id': commit_id}
        c, s = self._scn, self._s
        if s['phase'] != 'action':
            return self._reject('recovery', d, 'episode is closed')
        if not self._alert_visible():
            return self._reject('recovery', d, 'recovery unavailable: no disruption alert yet')
        if choice not in ('expedite', 'alternate'):
            return self._reject('recovery', d, 'unknown recovery option')
        if type(quantity) is not int or quantity < 1:
            return self._reject('recovery', d, 'quantity must be a positive integer')
        ids = {x['commit_id'] for x in s['commitments']}
        if commit_id is not None and (not isinstance(commit_id, str) or not commit_id or commit_id in ids):
            return self._reject('recovery', d, 'duplicate commitment: commit_id already executed or invalid')
        offer = self._expedite_today() if choice == 'expedite' else self._alternate_today()
        if offer is None:
            return self._reject('recovery', d, 'recovery offer window not open, closed or exhausted today')
        if quantity > offer['max_units']:
            return self._reject('recovery', d, 'quantity exceeds units available for this recovery')
        cost = quantity * offer['unit_cost']
        if s['incremental_spend'] + cost > c.recovery_budget:
            return self._reject('recovery', d, 'recovery budget exceeded')
        if commit_id is None:
            n = len(s['commitments']) + 1
            while f'c{n}' in ids:
                n += 1
            commit_id = f'c{n}'
        s['incremental_spend'] += cost
        if choice == 'expedite':
            lot = next(x for x in s['lots'] if x['lot_id'] == 'primary')
            if quantity == lot['quantity']:
                lot['arrival_day'], lot['expedited'] = offer['arrival_day'], True
                lot_id = 'primary'
            else:
                lot['quantity'] -= quantity
                lot_id = f"exp{sum(1 for x in s['commitments'] if x['choice'] == 'expedite') + 1}"
                s['lots'].append({'lot_id': lot_id, 'source': 'primary', 'quantity': quantity,
                                  'arrival_day': offer['arrival_day'], 'received': False, 'expedited': True})
        else:
            lot_id = f"alt{sum(1 for x in s['commitments'] if x['choice'] == 'alternate') + 1}"
            s['lots'].append({'lot_id': lot_id, 'source': 'alternate', 'quantity': quantity,
                              'arrival_day': offer['arrival_day'], 'received': False, 'expedited': False})
        s['commitments'].append({'commit_id': commit_id, 'day': s['day'], 'choice': choice, 'quantity': quantity,
                                 'unit_cost': offer['unit_cost'], 'cost': cost,
                                 'arrival_day': offer['arrival_day'], 'lot_id': lot_id})
        self._record('recovery', {'choice': choice, 'quantity': quantity, 'commit_id': commit_id}, True)
        return {'accepted': True, 'commit_id': commit_id}

    def release_production(self, quantity):
        d = {'quantity': quantity}
        s = self._s
        if s['phase'] != 'action':
            return self._reject('release', d, 'episode is closed')
        if s['scheduled_production'] is not None:
            return self._reject('release', d, 'daily production already released')
        if type(quantity) is not int or quantity < 0:
            return self._reject('release', d, 'quantity must be a nonnegative integer')
        if quantity > self._scn.daily_capacity or quantity > s['component_on_hand']:
            return self._reject('release', d, 'capacity or available material exceeded')
        self._refresh()
        if quantity + s['finished_on_hand'] > s['open_demand']:
            return self._reject('release', d, 'production exceeds open customer demand')
        s['scheduled_production'] = quantity
        self._record('release', d, True)
        return {'accepted': True}

    def close_day(self):
        s, c = self._s, self._scn
        if s['phase'] != 'action':
            return self._reject('close_day', {}, 'episode is closed')
        q = s['scheduled_production'] or 0
        s['component_on_hand'] -= q
        s['finished_on_hand'] += q
        s['produced_total'] += q
        s['scheduled_production'] = None
        shipments, penalties, cancels = {}, {}, {}
        weight = {t['tier']: t['weight'] for t in c.tiers}
        due = [o for o in s['orders'] if o['status'] == 'open' and s['day'] >= o['due_day']]
        for o in sorted(due, key=lambda x: (-weight[x['tier']], x['order_id'])):
            ship = min(s['finished_on_hand'], o['quantity'] - o['delivered'])
            if ship:
                o['delivered'] += ship
                s['finished_on_hand'] -= ship
                s['delivered_total'] += ship
                shipments[o['order_id']] = ship
        spec = {o['order_id']: o for o in c.orders}
        for o in s['orders']:
            if o['status'] != 'open' or s['day'] < o['due_day']:
                continue
            if s['day'] == o['due_day']:
                o['on_time_units'] = o['delivered']
            undelivered = o['quantity'] - o['delivered']
            if undelivered == 0:
                o['status'] = 'complete'
                continue
            terms = spec[o['order_id']]
            if terms['penalty_type'] == 'percent_of_value':
                amount = undelivered * terms['unit_value'] * terms['penalty_rate'] // 10000
            elif terms['penalty_type'] == 'fixed_per_unit':
                amount = undelivered * terms['penalty_rate'] if s['day'] == o['due_day'] else 0
            else:
                amount = undelivered * terms['penalty_rate']
            if terms['penalty_cap_pct'] is not None:
                cap = o['quantity'] * terms['unit_value'] * terms['penalty_cap_pct'] // 100
                amount = max(0, min(amount, cap - o['penalty_total']))
            o['penalty_total'] += amount
            s['penalties'] += amount
            o['unit_days_late'] += undelivered
            o['days_short'] += 1
            if amount:
                penalties[o['order_id']] = amount
            tier = _tier(c, o['tier'])
            if tier['on_shortfall'] == 'cancel_after' and s['day'] == o['due_day'] + tier['cancel_days_after_due']:
                o['cancelled'] += undelivered
                o['status'] = 'cancelled'
                s['cancelled_total'] += undelivered
                cancels[o['order_id']] = undelivered
        shipped = sum(shipments.values())
        self._record('day_close', {'produced': q, 'shipped': shipped, 'shipments': shipments,
                                   'penalties': penalties, 'cancelled': cancels}, True)
        if s['day'] == self._horizon:
            s['phase'] = 'complete'
            s['salvage_credit'] = s['component_on_hand'] * c.salvage_per_component
            self._record('episode_complete', {
                'salvage_credit': s['salvage_credit'],
                'net_cost': s['incremental_spend'] + s['penalties'] - s['salvage_credit']}, True)
            return self.snapshot()
        s['day'] += 1
        self._open_day()
        return self.snapshot()

    def _open_day(self):
        s, c = self._s, self._scn
        for lot in s['lots']:
            if not lot['received'] and lot['arrival_day'] == s['day']:
                lot['received'] = True
                s['component_on_hand'] += lot['quantity']
                self._record('receipt', {'lot': lot['lot_id'], 'source': lot['source'], 'quantity': lot['quantity']}, True)
        self._record('opening_before_notice', {}, True)
        if c.signal_day == s['day']:
            sig = {'day': s['day'], 'level': c.signal_level, 'text': SIGNAL_TEXT}
            s['signals'].append(sig)
            self._record('signal', {'level': c.signal_level}, True)
        if c.notice_day == s['day']:
            if c.delay_outcome == 'delay':
                lot = next((x for x in s['lots'] if x['lot_id'] == 'primary'), None)
                if lot is not None and not lot['received'] and not lot['expedited']:
                    lot['arrival_day'] = c.delayed_arrival_day
                d = {'kind': 'delay_confirmed', 'original_day': c.primary_promised_day,
                     'revised_day': c.delayed_arrival_day}
                text = f"Primary PO delayed from day {d['original_day']} to day {d['revised_day']}"
            else:
                d = {'kind': 'on_time_confirmed', 'promised_day': c.primary_promised_day}
                text = f"Primary PO confirmed on time for day {d['promised_day']}"
            s['notices'].append({'day': s['day'], **d, 'text': text})
            self._record('notice', d, True)
        self._record('day_open', {}, True)

    # --------------------------------------------------------------- scorecard
    def scorecard(self):
        """Separate metric blocks. Nothing here is combined into a single ranking number."""
        s, c = self._s, self._scn
        if s['phase'] != 'complete':
            raise ValueError('scorecard requires completed episode')
        weight = {t['tier']: t['weight'] for t in c.tiers}
        value = {o['order_id']: o['unit_value'] for o in c.orders}
        orders, tiers = [], {}
        for o in s['orders']:
            row = {'order_id': o['order_id'], 'tier': o['tier'], 'ordered': o['quantity'],
                   'otif': o['on_time_units'] == o['quantity'], 'on_time_units': o['on_time_units'],
                   'delivered': o['delivered'], 'cancelled': o['cancelled'],
                   'unit_days_late': o['unit_days_late'], 'days_short': o['days_short'],
                   'penalty': o['penalty_total']}
            orders.append(row)
            t = tiers.setdefault(o['tier'], {'orders': 0, 'otif_orders_met': 0, 'ordered': 0, 'on_time_units': 0,
                                             'delivered': 0, 'cancelled': 0, 'unit_days_late': 0, 'penalties': 0})
            t['orders'] += 1
            t['otif_orders_met'] += int(row['otif'])
            for k, src in (('ordered', 'ordered'), ('on_time_units', 'on_time_units'), ('delivered', 'delivered'),
                           ('cancelled', 'cancelled'), ('unit_days_late', 'unit_days_late'), ('penalties', 'penalty')):
                t[k] += row[src]
        inbound = sum(x['quantity'] for x in s['lots'])
        primary = sum(x['quantity'] for x in s['lots'] if x['source'] == 'primary')
        return {
            'schema': SCORECARD_SCHEMA,
            'cost': {'recovery_spend': s['incremental_spend'],
                     'expedite_spend': sum(x['cost'] for x in s['commitments'] if x['choice'] == 'expedite'),
                     'alternate_spend': sum(x['cost'] for x in s['commitments'] if x['choice'] == 'alternate'),
                     'service_penalties': s['penalties'],
                     'salvage_credit': s['salvage_credit'],
                     'net_cost': s['incremental_spend'] + s['penalties'] - s['salvage_credit']},
            'service': {'otif_orders_met': sum(int(r['otif']) for r in orders), 'orders_total': len(orders),
                        'on_time_units': sum(r['on_time_units'] for r in orders),
                        'ordered_units': sum(r['ordered'] for r in orders), 'delivered_total': s['delivered_total'],
                        'cancelled_units': s['cancelled_total'],
                        'unit_days_late': sum(r['unit_days_late'] for r in orders), 'orders': orders},
            'tier_impact': {'by_tier': tiers,
                            'priority_weighted_unit_days_late': sum(weight[r['tier']] * r['unit_days_late'] for r in orders)},
            'downstream': {'cancelled_units': s['cancelled_total'],
                           'cancelled_order_value': sum(r['cancelled'] * value[r['order_id']] for r in orders),
                           'undelivered_at_end': sum(o['quantity'] - o['delivered'] - o['cancelled'] for o in s['orders'])},
            'supply_risk': {'ending_components': s['component_on_hand'],
                            'pending_inbound_units': sum(x['quantity'] for x in s['lots'] if not x['received']),
                            'ending_cover_days_floor': (s['component_on_hand'] // c.daily_capacity) if c.daily_capacity else None,
                            'primary_reliance_pct': (100 * primary // inbound) if inbound else None,
                            'recovery_commitments': len(s['commitments']),
                            'unused_recovery_budget': c.recovery_budget - s['incremental_spend']},
            'values_status': VALUES_STATUS}
