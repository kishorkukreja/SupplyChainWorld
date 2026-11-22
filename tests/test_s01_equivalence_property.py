"""S01 audit: later versions reduce to the earlier version's behavior where the written rules say they should.

Each property builds a scenario pair that the rules say are equivalent, drives BOTH worlds with the
same generated tool calls and compares the whole state after every call.

* v0.4 == v0.3 when no alternate supply is bought (v0.4 only changes alternate pricing and salvage).
* v0.4 differs from v0.3 by exactly (base unit cost x alternate units) in spend when both accept the same calls.
* v0.3 == v0.2 when the v0.3-only features are switched off (no penalty cap, whole-percent rates,
  one due date per cancel tier, rate cards re-expressed as whole-dollar unit costs).
* v0.2 == v0.1 for a single-order backlog contract with one whole-lot recovery (the v0.1 world).
"""
import unittest
from copy import deepcopy

from hypothesis import assume, given, settings, strategies as st

import support  # noqa: F401
from support.s01_versions import V1, V2, V3, V4, informed_call, v1_scenarios, v3_scenarios

VERSION_KEYS = ('schema_version', 'runtime_version')


def drive_pair(a, b, sa, sb, data, steps=30, avoid_alternate=False):
    """Send the same calls to two runners; yield (call, record_a, record_b) after each."""
    ra, rb = a.runner(*sa), b.runner(*sb)
    out = []
    for _ in range(steps):
        if ra._world.snapshot()['phase'] == 'complete':
            break
        call = informed_call(a, ra.view(), data)
        if avoid_alternate and call['tool'] == 'commit_recovery' and call['arguments'].get('choice') == 'alternate':
            call = {'tool': 'read_state', 'arguments': {}}
        out.append((call, ra.attempt(deepcopy(call)), rb.attempt(deepcopy(call))))
        yield ra._world, rb._world, out[-1]
    while ra._world.snapshot()['phase'] != 'complete':
        call = {'tool': 'advance_day', 'arguments': {}}
        out.append((call, ra.attempt(call), rb.attempt(call)))
        yield ra._world, rb._world, out[-1]


def strip_versions(state, extra=()):
    return {k: v for k, v in state.items() if k not in VERSION_KEYS + tuple(extra)}


class V4EqualsV3WithoutAlternateSupply(unittest.TestCase):
    @given(v3_scenarios(), st.data())
    @settings(max_examples=40)
    def test_identical_state_and_scorecard_when_alternate_is_never_bought(self, sc, data):
        scenario, horizon = sc
        for w3, w4, (call, r3, r4) in drive_pair(V3, V4, (scenario, horizon), (scenario, horizon), data, avoid_alternate=True):
            self.assertEqual(r3['accepted'], r4['accepted'], call)
            self.assertEqual(strip_versions(w3.snapshot()), strip_versions(w4.snapshot()))
        c3, c4 = w3.scorecard(), w4.scorecard()
        self.assertEqual(c4['cost']['uncredited_alternate_surplus'], 0)
        for k in ('salvage_eligible_components', 'uncredited_alternate_surplus'):
            c4['cost'].pop(k)
        c3.pop('schema'), c4.pop('schema')
        self.assertEqual(c3, c4)

    @given(v3_scenarios(), st.data())
    @settings(max_examples=40)
    def test_spend_differs_by_exactly_the_base_cost_of_alternate_units(self, sc, data):
        scenario, horizon = sc
        scenario = {**scenario, 'recovery_budget': 10**6}      # budget never binds, so both accept the same calls
        last = None
        for w3, w4, (call, r3, r4) in drive_pair(V3, V4, (scenario, horizon), (scenario, horizon), data):
            self.assertEqual(r3['accepted'], r4['accepted'], call)
            s3, s4 = w3.snapshot(), w4.snapshot()
            alt_units = sum(c['quantity'] for c in s3['commitments'] if c['choice'] == 'alternate')
            self.assertEqual(s3['incremental_spend'] - s4['incremental_spend'], scenario['base_unit_cost'] * alt_units)
            for key in ('component_on_hand', 'finished_on_hand', 'produced_total', 'delivered_total', 'penalties',
                        'orders', 'lots', 'day', 'phase'):
                self.assertEqual(s3[key], s4[key], key)
            last = (w3, w4)
        s3, s4 = last[0].snapshot(), last[1].snapshot()
        self.assertGreaterEqual(s3['salvage_credit'], s4['salvage_credit'])    # v0.4 never credits alternate surplus more


def v3_as_v2(scenario):
    """Rewrite a v0.3 scenario so the written v0.3 and v0.2 rules coincide, and return both."""
    s3 = deepcopy(scenario)
    due = {}
    for o in s3['orders']:
        o['penalty_cap_pct'] = None
        if o['penalty_type'] == 'percent_of_value':
            o['penalty_rate'] = (o['penalty_rate'] // 100) * 100 if o['penalty_rate'] >= 100 else 0
        tier = next(t for t in s3['tiers'] if t['tier'] == o['tier'])
        if tier['on_shortfall'] == 'cancel_after':
            o['due_day'] = due.setdefault(o['tier'], o['due_day'])
    obj = V3.scenario_cls(**s3)
    s2 = dict(
        scenario_id=s3['scenario_id'], opening_components=s3['opening_components'], daily_capacity=s3['daily_capacity'],
        primary_quantity=s3['primary_quantity'], primary_promised_day=s3['primary_promised_day'],
        signal_day=s3['signal_day'], signal_hint_pct=50 if s3['signal_day'] else None, notice_day=s3['notice_day'],
        delay_outcome=s3['delay_outcome'], delayed_arrival_day=s3['delayed_arrival_day'],
        expedite_curve=[[r['day'], r['unit_cost'], r['arrival_day']] for r in obj.rate_card('expedite')],
        alternate_curve=[[r['day'], r['unit_cost'], r['arrival_day']] for r in obj.rate_card('alternate')],
        alternate_max_units=s3['alternate_max_units'], recovery_budget=s3['recovery_budget'],
        salvage_per_component=obj.salvage_per_component,
        tiers=[{'tier': t['tier'], 'weight': t['weight'], 'on_shortfall': t['on_shortfall'], 'cancel_day': None}
               for t in s3['tiers']],
        orders=[{k: o[k] for k in ('order_id', 'tier', 'quantity', 'due_day', 'unit_value', 'penalty_type')}
                | {'penalty_rate': o['penalty_rate'] // 100 if o['penalty_type'] == 'percent_of_value' else o['penalty_rate']}
                for o in s3['orders']])
    for t2, t3 in zip(s2['tiers'], s3['tiers']):
        if t3['on_shortfall'] == 'cancel_after':
            t2['cancel_day'] = due.get(t3['tier'], 1) + t3['cancel_days_after_due']
    return s2, s3


class V3EqualsV2WhenV03FeaturesAreOff(unittest.TestCase):
    @given(v3_scenarios(), st.data())
    @settings(max_examples=40)
    def test_same_state_after_every_call(self, sc, data):
        scenario, horizon = sc
        s2, s3 = v3_as_v2(scenario)
        # The v0.2 simulator needs a tier with no orders to carry a usable cancel day; keep to valid pairs.
        try:
            V2.scenario_cls(**s2)
        except ValueError:
            assume(False)
        horizon = max(horizon, max(o['due_day'] for o in s3['orders']))
        for w2, w3, (call, r2, r3) in drive_pair(V2, V3, (s2, horizon), (s3, horizon), data):
            self.assertEqual(r2['accepted'], r3['accepted'], call)
            a, b = w2.snapshot(), w3.snapshot()
            self.assertEqual(strip_versions(a, ('signals',)), strip_versions(b, ('signals',)), call)
        self.assertEqual(len(a['signals']), len(b['signals']))
        c2, c3 = w2.scorecard(), w3.scorecard()
        for k in ('expedite_spend', 'alternate_spend'):
            c3['cost'].pop(k)
        c2.pop('schema'), c3.pop('schema')
        self.assertEqual(c2, c3)


class V2EqualsV1ForOneOrderAndWholeLotRecovery(unittest.TestCase):
    @given(v1_scenarios(), st.sampled_from(['maintain', 'expedite', 'alternate']))
    @settings(max_examples=100)
    def test_same_flows_costs_and_scorecard(self, sc, policy):
        scenario, horizon = sc
        assume(scenario['disruption_enabled'] and scenario['primary_quantity'] >= 1 and scenario['alternate_quantity'] >= 1)
        scenario = {**scenario, 'primary_quantity': scenario['primary_quantity'],
                    'expedite_cost': scenario['expedite_cost'] // scenario['primary_quantity'] * scenario['primary_quantity'],
                    'alternate_cost': scenario['alternate_cost'] // scenario['alternate_quantity'] * scenario['alternate_quantity']}
        # Budget covers the dearest option: in v0.1 an unaffordable choice would be retried forever by the script.
        scenario['recovery_budget'] = max(scenario['recovery_budget'], scenario['expedite_cost'], scenario['alternate_cost'])
        n = scenario['notice'] if 'notice' in scenario else scenario['delay_notice_day']
        s2 = dict(
            scenario_id='eq', opening_components=scenario['opening_components'], daily_capacity=scenario['daily_capacity'],
            primary_quantity=scenario['primary_quantity'], primary_promised_day=scenario['initially_promised_day'],
            signal_day=None, signal_hint_pct=None, notice_day=n, delay_outcome='delay',
            delayed_arrival_day=scenario['delayed_arrival_day'],
            expedite_curve=[[n, scenario['expedite_cost'] // scenario['primary_quantity'], scenario['expedited_arrival_day']]],
            alternate_curve=[[n, scenario['alternate_cost'] // scenario['alternate_quantity'], scenario['alternate_arrival_day']]],
            alternate_max_units=scenario['alternate_quantity'], recovery_budget=scenario['recovery_budget'],
            salvage_per_component=0, tiers=[{'tier': 't', 'weight': 1, 'on_shortfall': 'backlog', 'cancel_day': None}],
            orders=[{'order_id': 'O0', 'tier': 't', 'quantity': scenario['order_quantity'], 'due_day': scenario['order_due_day'],
                     'unit_value': 0, 'penalty_type': 'per_unit_per_day', 'penalty_rate': scenario['daily_backlog_penalty']}])
        # v0.1 can only recover on days up to its deadline; v0.2 offers a row on the notice day only. Both scripts
        # commit on the first alert day, which is the notice day, so the two policies take the same action.
        r1, r2 = V1.runner(scenario, horizon), V2.runner(s2, horizon)
        t1 = r1.run(V1.scripted(policy))
        t2 = r2.run(V2.scripted({'maintain': 'maintain', 'expedite': 'expedite_on_alert', 'alternate': 'alternate_on_alert'}[policy]))
        self.assertEqual(t1['status'], 'complete')
        self.assertEqual(t2['status'], 'complete')
        h1 = [e for e in r1._world.history() if e['kind'] == 'day_close']
        h2 = [e for e in r2._world.history() if e['kind'] == 'day_close']
        for e1, e2 in zip(h1, h2):
            for key in ('day', 'component_on_hand', 'finished_on_hand', 'produced_total', 'delivered_total',
                        'penalties', 'incremental_spend'):
                self.assertEqual(e1['state'][key], e2['state'][key], f'day {e1["day"]} {key}')
        c1, c2 = r1._world.scorecard(), r2._world.scorecard()
        self.assertEqual(c1['comparison_cost'], c2['cost']['net_cost'])
        self.assertEqual(c1['incremental_spend'], c2['cost']['recovery_spend'])
        self.assertEqual(c1['service_penalties'], c2['cost']['service_penalties'])
        self.assertEqual(c1['delivered_total'], c2['service']['delivered_total'])
        self.assertEqual(c1['delivered_on_time'], c2['service']['on_time_units'])
        self.assertEqual(c1['ending_components'], c2['supply_risk']['ending_components'])


if __name__ == '__main__':
    unittest.main()
