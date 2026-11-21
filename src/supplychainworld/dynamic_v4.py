"""Deterministic operational kernel for the S01 v0.4 scenario family (issue #36, round 3).

Built beside `dynamic.py`, `dynamic_v2.py` and `dynamic_v3.py`, all untouched; the v0.3 scenario
validator, order, day and offer machinery are reused by subclassing. It applies the owner-practitioner
re-review round 3 decisions (not independent, reviewed: no, every number PROVISIONAL, needs practitioner value):

* PRICE BASIS: the reviewer chose "compare premiums only". The alternate supplier's incremental recovery
  cost is its PREMIUM over the primary unit cost (30% x USD 10 = USD 3 a unit on day 1), directly
  comparable with the expedite premium (40% = USD 4 a unit on day 1). Alternate can be cheaper per unit.
* UNRESOLVED CONVENTION (the reviewer has not answered it; flagged loudly in the docs): the base purchase
  cost of any recovery lot is cost-neutral, identical across policies and excluded from the comparison
  (as the primary PO cost was in v0.1). Components created by the alternate buy earn NO salvage credit:
  components left on hand at the end are presumed to be the alternate-bought surplus first, so a premium-only
  reading cannot create a salvage windfall.
* Penalty cap is 20% of order value (was 10%). The percent penalty stays 1.5% a day on the undelivered part.

Everything else is carried forward from v0.3. Quantities are whole units and money is whole USD.
"""
from .dynamic_v3 import SIGNAL_TEXT, OperationalWorldV3, ScenarioV3, _tier  # noqa: F401

SCHEMA = '4.0'
VALUES_STATUS = 'PROVISIONAL, needs practitioner value; not reviewed by a practitioner'
SCORECARD_SCHEMA = 'dyn-scorecard-4'
ALTERNATE_BASIS = ('premium over the base unit cost only, charged per unit of a new lot; the base purchase cost of a '
                   'recovery lot is cost-neutral and excluded; the primary lot still arrives; units left over from '
                   'an alternate buy earn no salvage')


class ScenarioV4(ScenarioV3):
    """v0.3 scenario fields and validation; only the alternate unit cost basis and the version differ."""

    def __init__(self, **kw):
        if kw.get('schema_version', SCHEMA) != SCHEMA or kw.get('runtime_version', SCHEMA) != SCHEMA:
            raise ValueError('unsupported scenario or runtime version')
        kw = {k: v for k, v in kw.items() if k not in ('schema_version', 'runtime_version')}
        super().__init__(**kw)
        self.schema_version = self.runtime_version = SCHEMA

    def alternate_unit_cost(self, premium_pct):
        """Incremental cost of an alternate unit: the premium only (the base cost is cost-neutral)."""
        return self.base_unit_cost * premium_pct // 100


class OperationalWorldV4(OperationalWorldV3):
    """v0.3 world with premium-only alternate pricing and no salvage on alternate-bought surplus."""

    def __init__(self, horizon_days: int = 5, *, scenario: ScenarioV4):
        if not isinstance(scenario, ScenarioV4):
            raise TypeError('scenario must be a ScenarioV4')
        super().__init__(horizon_days, scenario=scenario)

    def snapshot(self):
        s = super().snapshot()
        s['schema_version'] = s['runtime_version'] = SCHEMA
        return s

    def _alternate_received(self):
        return sum(x['quantity'] for x in self._s['lots'] if x['source'] == 'alternate' and x['received'])

    def _salvage_split(self):
        """(eligible, uncredited): leftover components presumed alternate-bought first earn nothing."""
        left = self._s['component_on_hand']
        uncredited = min(left, self._alternate_received())
        return left - uncredited, uncredited

    def observation(self):
        obs = super().observation()
        rules = obs['rules']
        rules['salvage_rule'] = ('components on hand at the end earn the class salvage credit, except units presumed to '
                                 'be left over from an alternate buy, which earn none')
        offers = rules.get('recovery_offers')
        if offers:
            offers['alternate']['basis'] = ALTERNATE_BASIS
        return obs

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
            eligible, _ = self._salvage_split()
            s['salvage_credit'] = eligible * c.salvage_per_component
            self._record('episode_complete', {
                'salvage_credit': s['salvage_credit'],
                'net_cost': s['incremental_spend'] + s['penalties'] - s['salvage_credit']}, True)
            return self.snapshot()
        s['day'] += 1
        self._open_day()
        return self.snapshot()

    def scorecard(self):
        card = super().scorecard()
        eligible, uncredited = self._salvage_split()
        card['schema'] = SCORECARD_SCHEMA
        card['cost']['salvage_eligible_components'] = eligible
        card['cost']['uncredited_alternate_surplus'] = uncredited
        return card
