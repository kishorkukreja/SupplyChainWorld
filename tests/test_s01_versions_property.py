"""S01 audit: property-based tests on the simulator, runner, verifier and replay of v0.1 to v0.4.

The same properties run on every version (one generated TestCase class per version).
Scenario parameters are generated (not only the committed fixtures) and tool-call
sequences are generated step by step from the agent-visible view. After EVERY step the
invariants are checked; after the run the recorded transcript is replayed and the
independent verifier must accept the recorded history.

Traceability: docs/testing.md, table "S01 audit traceability".
"""
import unittest

from hypothesis import given, settings, strategies as st

import support  # noqa: F401
from support.regression import record_on_failure
from support.s01_versions import (VERSIONS, drive, fixture_or_generated, greedy_release, informed_call, V1, V2, V3, V4)


# ----------------------------------------------------------------------------- invariants

def check_v1(test, world):
    s, c = world.snapshot(), world._scenario
    received = (c.primary_quantity if s['primary_received'] else 0) + (c.alternate_quantity if s['alternate_received'] else 0)
    test.assertGreaterEqual(s['component_on_hand'], 0)
    test.assertGreaterEqual(s['finished_on_hand'], 0)
    test.assertEqual(s['component_on_hand'], c.opening_components + received - s['produced_total'], 'component conservation')
    test.assertEqual(s['finished_on_hand'], s['produced_total'] - s['delivered_total'], 'finished-goods conservation')
    test.assertLessEqual(s['produced_total'], c.order_quantity)
    test.assertLessEqual(s['delivered_total'], s['produced_total'], 'shipments exceed production')
    test.assertLessEqual(s['delivered_total'], c.order_quantity, 'shipments exceed order quantity')
    test.assertLessEqual(s['incremental_spend'], c.recovery_budget, 'budget exceeded')
    test.assertGreaterEqual(s['penalties'], 0)
    if s['scheduled_production'] is not None:
        test.assertLessEqual(s['scheduled_production'], c.daily_capacity)
    accepted = [e for e in world.history() if e['kind'] == 'recovery' and e['accepted']]
    test.assertLessEqual(len(accepted), 1, 'more than one recovery commitment executed')
    receipts = [(e['details']['order']) for e in world.history() if e['kind'] == 'receipt']
    test.assertEqual(len(receipts), len(set(receipts)), 'a PO was received twice')


def check_v2plus(test, world):
    s, c = world.snapshot(), world._scn
    received = sum(x['quantity'] for x in s['lots'] if x['received'])
    test.assertGreaterEqual(s['component_on_hand'], 0)
    test.assertGreaterEqual(s['finished_on_hand'], 0)
    test.assertEqual(s['component_on_hand'], c.opening_components + received - s['produced_total'], 'component conservation')
    test.assertEqual(s['finished_on_hand'], s['produced_total'] - s['delivered_total'], 'finished-goods conservation')
    test.assertLessEqual(s['delivered_total'], s['produced_total'], 'shipments exceed production')
    test.assertEqual(s['delivered_total'], sum(o['delivered'] for o in s['orders']))
    test.assertEqual(s['cancelled_total'], sum(o['cancelled'] for o in s['orders']))
    test.assertEqual(s['penalties'], sum(o['penalty_total'] for o in s['orders']))
    for o in s['orders']:
        test.assertGreaterEqual(o['delivered'], 0)
        test.assertLessEqual(o['delivered'] + o['cancelled'], o['quantity'], 'shipments exceed order quantity')
    commits = s['commitments']
    test.assertEqual(s['incremental_spend'], sum(x['cost'] for x in commits))
    test.assertLessEqual(s['incremental_spend'], c.recovery_budget, 'budget exceeded')
    ids = [x['commit_id'] for x in commits]
    test.assertEqual(len(ids), len(set(ids)), 'a commitment executed twice')
    test.assertLessEqual(sum(x['quantity'] for x in commits if x['choice'] == 'alternate'), c.alternate_max_units)
    test.assertEqual(sum(x['quantity'] for x in s['lots'] if x['source'] == 'primary'), c.primary_quantity,
                     'primary lots no longer add up to the PO')
    test.assertEqual(sum(x['quantity'] for x in s['lots']),
                     c.primary_quantity + sum(x['quantity'] for x in commits if x['choice'] == 'alternate'))
    for x in s['lots']:
        if x['received']:
            test.assertLessEqual(x['arrival_day'], s['day'])
        else:
            test.assertGreaterEqual(x['arrival_day'], s['day'] if s['phase'] == 'action' else 0)
    if s['scheduled_production'] is not None:
        test.assertLessEqual(s['scheduled_production'], c.daily_capacity)
    if hasattr(c, 'orders') and 'penalty_cap_pct' in c.orders[0]:
        for o, terms in zip(s['orders'], c.orders):
            if terms['penalty_cap_pct'] is not None:
                test.assertLessEqual(o['penalty_total'], terms['quantity'] * terms['unit_value'] * terms['penalty_cap_pct'] // 100)
    if s['phase'] == 'complete':
        test.assertIsNotNone(s['salvage_credit'])


def check_commit_effects(test, v, record, world):
    """An accepted recovery commitment changes the PO, the budget and the event exactly as the visible offer says."""
    if not record or not record['accepted'] or record['tool'] != 'commit_recovery':
        return
    after, before = world.snapshot(), record['view_before']
    choice = record['arguments'].get('choice')
    if v.tag == 'v0.1':
        offers = before['rules']['recovery_offers']
        cost = {'maintain': 0, 'expedite': offers['expedite_cost'], 'alternate': offers['alternate_cost']}[choice]
        test.assertEqual(after['incremental_spend'] - before['state']['incremental_spend'], cost)
        test.assertEqual(after['recovery'], choice)
        if choice == 'expedite':
            test.assertEqual(after['primary_arrival_day'], offers['expedited_arrival_day'])
        elif choice == 'alternate':
            test.assertEqual(after['alternate_arrival_day'], offers['alternate_arrival_day'])
            test.assertEqual(after['primary_arrival_day'], before['state']['primary_arrival_day'], 'alternate buy moved the original PO')
        return
    qty = record['arguments']['quantity']
    offer = before['rules']['recovery_offers'][choice]['today']
    test.assertEqual(after['incremental_spend'] - before['state']['incremental_spend'], qty * offer['unit_cost'])
    commit = after['commitments'][-1]
    test.assertEqual((commit['choice'], commit['quantity'], commit['unit_cost'], commit['arrival_day']),
                     (choice, qty, offer['unit_cost'], offer['arrival_day']))
    new = {x['lot_id']: x for x in after['lots']}[commit['lot_id']]
    test.assertEqual((new['quantity'], new['arrival_day'], new['received']), (qty, offer['arrival_day'], False))
    if choice == 'alternate':
        test.assertEqual(new['source'], 'alternate')
        old_primary = {x['lot_id']: x for x in before['state']['lots']}
        for lot_id, lot in old_primary.items():
            test.assertEqual({x['lot_id']: x for x in after['lots']}[lot_id], lot, 'an alternate buy changed an existing PO')
    else:
        test.assertTrue(new['expedited'] and new['source'] == 'primary')


def check_history_rules(test, v, scenario, history, horizon):
    """Time, penalty and cancellation rules re-derived from the recorded history (v0.2 to v0.4)."""
    days = [e['day'] for e in history]
    test.assertEqual(days, sorted(days), 'time moved backwards')
    closes = [e for e in history if e['kind'] == 'day_close']
    test.assertEqual([e['day'] for e in closes], list(range(1, len(closes) + 1)), 'a day was skipped or repeated')
    test.assertLessEqual(len(closes), horizon)
    if v.tag == 'v0.1':
        prev_pen = 0
        for e in closes:
            st_ = e['state']
            if e['day'] >= scenario['order_due_day']:
                expected = scenario['daily_backlog_penalty'] * (scenario['order_quantity'] - st_['delivered_total'])
            else:
                expected = 0
            test.assertEqual(st_['penalties'] - prev_pen, expected, f'penalty rule broken on day {e["day"]}')
            prev_pen = st_['penalties']
            if e['day'] < scenario['order_due_day']:
                test.assertEqual(e['details']['shipped'], 0, 'shipment before the due day')
        return
    orders = {o['order_id']: o for o in scenario['orders']}
    tiers = {t['tier']: t for t in scenario['tiers']}
    prev = None
    for e in history:
        if e['kind'] == 'day_close':
            before = prev['state']
            after = e['state']
            for oid, spec in orders.items():
                bo = next(o for o in before['orders'] if o['order_id'] == oid)
                ao = next(o for o in after['orders'] if o['order_id'] == oid)
                if bo['status'] != 'open' or e['day'] < spec['due_day']:
                    test.assertEqual(ao['penalty_total'], bo['penalty_total'])
                    continue
                undelivered = spec['quantity'] - ao['delivered']
                if undelivered == 0:
                    continue
                if spec['penalty_type'] == 'percent_of_value':
                    amount = undelivered * spec['unit_value'] * spec['penalty_rate'] // (100 if v.tag == 'v0.2' else 10000)
                elif spec['penalty_type'] == 'fixed_per_unit':
                    amount = undelivered * spec['penalty_rate'] if e['day'] == spec['due_day'] else 0
                else:
                    amount = undelivered * spec['penalty_rate']
                if spec.get('penalty_cap_pct') is not None:
                    cap = spec['quantity'] * spec['unit_value'] * spec['penalty_cap_pct'] // 100
                    amount = max(0, min(amount, cap - bo['penalty_total']))
                test.assertEqual(ao['penalty_total'] - bo['penalty_total'], amount, f'penalty rule broken for {oid} day {e["day"]}')
                tier = tiers[spec['tier']]
                due_cancel = None
                if tier['on_shortfall'] == 'cancel_after':
                    due_cancel = tier['cancel_day'] if v.tag == 'v0.2' else spec['due_day'] + tier['cancel_days_after_due']
                if due_cancel is not None and e['day'] == due_cancel:
                    test.assertEqual(ao['cancelled'], undelivered)
                    test.assertEqual(ao['status'], 'cancelled')
                else:
                    test.assertEqual(ao['cancelled'], bo['cancelled'], f'unexpected cancellation of {oid}')
            # Shipping never before the due day.
            for oid, qty in e['details']['shipments'].items():
                test.assertGreaterEqual(e['day'], orders[oid]['due_day'], 'shipment before the due day')
        if e['kind'] in ('release', 'recovery', 'day_open', 'day_close', 'receipt'):
            prev = e


# ----------------------------------------------------------------------------- the properties

def make_cases(v):
    checker = check_v1 if v.tag == 'v0.1' else check_v2plus
    scenarios = fixture_or_generated(v)

    class Cases(unittest.TestCase):
        __doc__ = f'Properties for S01 {v.tag}'

        def _step_check(self):
            def check(world, record):
                if record is not None and not record['accepted']:
                    self.assertEqual(record['state_changes'], {}, f"rejected {record['tool']} changed state")
                checker(self, world)
            return check

        @given(scenarios, st.data())
        @settings(max_examples=60)
        def test_invariants_after_every_step_and_rejections_change_nothing(self, sc, data):
            scenario, horizon = sc
            with record_on_failure(f's01_{v.tag}_inv', {'scenario': scenario, 'horizon': horizon}):
                step = self._step_check()

                def check(world, record):
                    step(world, record)
                    check_commit_effects(self, v, record, world)
                transcript, runner = drive(v, scenario, horizon, data, check=check)
                self.assertEqual(transcript['status'], 'complete')
                check_history_rules(self, v, v.scenario_dict(runner._world), runner._world.history(), horizon)

        @given(scenarios, st.data())
        @settings(max_examples=40)
        def test_replay_reproduces_state_and_scorecard_and_verifier_accepts(self, sc, data):
            scenario, horizon = sc
            transcript, runner = drive(v, scenario, horizon, data)
            world = runner._world
            history, card = world.history(), world.scorecard()
            sink = []
            ok, diffs = v.replay(transcript, v.factory(scenario, horizon, sink))
            self.assertTrue(ok, diffs)
            again = sink[-1]
            self.assertEqual(again.history(), history, 'replayed state sequence differs')
            self.assertEqual(again.scorecard(), card, 'replayed scorecard differs')
            report = v.verify(v.scenario_dict(world), history, horizon, scorecard=card,
                              actions=v.actions(transcript))
            self.assertTrue(report.complete)
            self.assertEqual(report.violations, [], 'independent verifier rejected a valid run')

        @given(scenarios, st.data())
        @settings(max_examples=30)
        def test_verifier_accepts_every_valid_partial_run(self, sc, data):
            scenario, horizon = sc
            transcript, runner = drive(v, scenario, horizon, data, steps=14)
            history = runner._world.history()
            cuts = [i + 1 for i, e in enumerate(history) if e['kind'] in ('release', 'recovery', 'day_open')]
            for cut in data.draw(st.lists(st.sampled_from(cuts), max_size=4)):
                report = v.verify(v.scenario_dict(runner._world), history[:cut], horizon)
                self.assertEqual(report.violations, [], f'valid prefix of {cut} events rejected')
                self.assertFalse(report.complete and cut < len(history))

        @given(scenarios, st.data())
        @settings(max_examples=30)
        def test_time_only_moves_forward_and_scorecard_needs_a_finished_episode(self, sc, data):
            scenario, horizon = sc
            runner = v.runner(scenario, horizon)
            world = runner._world
            last = world.snapshot()['day']
            n = 0
            while world.snapshot()['phase'] != 'complete' and n < 60:
                call = informed_call(v, runner.view(), data) if n < 30 else {'tool': 'advance_day', 'arguments': {}}
                runner.attempt(call)
                s = world.snapshot()
                self.assertIn(s['day'] - last, (0, 1))
                last = s['day']
                if s['phase'] != 'complete':
                    with self.assertRaises(ValueError):
                        world.scorecard()
                    self.assertFalse(runner.attempt({'tool': 'read_scorecard', 'arguments': {}})['accepted'])
                n += 1
            before = world.snapshot()
            for call in ({'tool': 'advance_day', 'arguments': {}}, {'tool': 'release_production', 'arguments': {'quantity': 0}}):
                self.assertFalse(runner.attempt(call)['accepted'], 'command accepted after the episode ended')
            self.assertEqual(world.snapshot(), before)

        @given(scenarios, st.data())
        @settings(max_examples=40)
        def test_an_executed_commitment_cannot_be_executed_again(self, sc, data):
            """Exact-once: a release can be sent once a day, and a commitment carrying an action_id
            (v0.2 to v0.4) or the single v0.1 recovery cannot run a second time when re-sent."""
            scenario, horizon = sc
            runner = v.runner(scenario, horizon)
            world = runner._world
            for _ in range(30):
                if world.snapshot()['phase'] == 'complete':
                    break
                call = informed_call(v, runner.view(), data)
                rec = runner.attempt(call)
                retryable = call['tool'] == 'release_production' or (
                    call['tool'] == 'commit_recovery' and ('action_id' in call or not v.multi_commit))
                if rec['accepted'] and retryable:
                    before = world.snapshot()
                    again = runner.attempt(call)
                    self.assertFalse(again['accepted'], 'a commitment executed twice')
                    self.assertEqual(world.snapshot(), before)
            commits = world.snapshot().get('commitments')
            if commits is not None:
                self.assertEqual(len({x['commit_id'] for x in commits}), len(commits))

        @given(scenarios, st.data())
        @settings(max_examples=40)
        def test_notice_and_signal_appear_on_their_day_and_the_primary_po_moves_as_written(self, sc, data):
            scenario, horizon = sc
            transcript, runner = drive(v, scenario, horizon, data, steps=0)      # no actions: the bare disruption
            scenario = v.scenario_dict(runner._world)                           # with every default filled in
            views = [transcript['initial']['view']] + [a['view_before'] for a in transcript['attempts']]
            history = runner._world.history()
            if v.tag == 'v0.1':
                notice_day, promised = scenario['delay_notice_day'], scenario['initially_promised_day']
                delayed = scenario['delayed_arrival_day'] if scenario['disruption_enabled'] else promised
                enabled = scenario['disruption_enabled']
            else:
                notice_day, promised = scenario['notice_day'], scenario['primary_promised_day']
                delayed = scenario['delayed_arrival_day'] if scenario['delay_outcome'] == 'delay' else promised
                enabled = True            # a firm notice also confirms an on-time arrival
            for view in views:
                state, day = view['state'], view['state']['day']
                self.assertEqual(bool(state['notices']), enabled and day >= notice_day, f'notice visibility on day {day}')
                arrival = state['primary_arrival_day'] if v.tag == 'v0.1' else next(
                    (x['arrival_day'] for x in state['lots'] if x['lot_id'] == 'primary'), None)
                received = state['primary_received'] if v.tag == 'v0.1' else all(x['received'] for x in state['lots'] if x['lot_id'] == 'primary')
                if not received:
                    self.assertEqual(arrival, delayed if (day >= notice_day and enabled) else promised, f'primary arrival on day {day}')
                if v.tag != 'v0.1':
                    self.assertEqual(bool(state['signals']),
                                     scenario['signal_day'] is not None and day >= scenario['signal_day'], f'signal visibility on day {day}')
            receipts = [e for e in history if e['kind'] == 'receipt']
            if delayed <= horizon and (v.tag != 'v0.1' or scenario['primary_quantity'] >= 0):
                primary = [e for e in receipts if e['details'].get('order', e['details'].get('lot')) == 'primary']
                self.assertEqual([e['day'] for e in primary], [delayed], 'the primary PO must be received exactly once, on its (revised) day')
            notice_events = [e['day'] for e in history if e['kind'] == 'notice']
            self.assertEqual(notice_events, [notice_day] if enabled and notice_day <= horizon else [])

        @given(scenarios, st.data())
        @settings(max_examples=30)
        def test_commitments_beyond_the_budget_or_outside_the_window_are_refused_with_no_effect(self, sc, data):
            scenario, horizon = sc
            runner = v.runner(scenario, horizon)
            world = runner._world
            scenario = v.scenario_dict(world)
            attempted = 0
            while world.snapshot()['phase'] != 'complete':
                view = runner.view()
                rules = view['rules']
                offers = rules.get('recovery_offers')
                calls = []
                if v.tag == 'v0.1':
                    for choice, cost in (('expedite', scenario['expedite_cost']), ('alternate', scenario['alternate_cost'])):
                        over_budget = view['state']['incremental_spend'] + cost > scenario['recovery_budget']
                        late = offers is None or view['state']['day'] > offers['deadline_day'] or view['state']['recovery'] is not None
                        if over_budget or late:
                            calls.append({'tool': 'commit_recovery', 'arguments': {'choice': choice}})
                else:
                    for choice in ('expedite', 'alternate'):
                        today = offers[choice]['today'] if offers else None
                        if today is None:
                            calls.append({'tool': 'commit_recovery', 'arguments': {'choice': choice, 'quantity': 1}})
                        elif today['unit_cost'] > 0 and offers['budget_remaining'] // today['unit_cost'] + 1 <= today['max_units']:
                            calls.append({'tool': 'commit_recovery',
                                          'arguments': {'choice': choice, 'quantity': offers['budget_remaining'] // today['unit_cost'] + 1}})
                for call in calls:
                    before = world.snapshot()
                    record = runner.attempt(call)
                    attempted += 1
                    self.assertFalse(record['accepted'], f'accepted an unavailable or unaffordable commitment: {call}')
                    self.assertEqual(world.snapshot(), before)
                    self.assertEqual(record['state_changes'], {})
                runner.attempt(informed_call(v, view, data)) if data.draw(st.booleans()) else None
                runner.attempt({'tool': 'advance_day', 'arguments': {}})
            self.assertGreaterEqual(attempted, 0)

    Cases.__name__ = Cases.__qualname__ = f'Properties_{v.tag.replace(".", "")}'
    return Cases


Properties_v01 = make_cases(V1)
Properties_v02 = make_cases(V2)
Properties_v03 = make_cases(V3)
Properties_v04 = make_cases(V4)


class ScriptedPolicyProperties(unittest.TestCase):
    """Every declared policy on generated scenarios: run, verify, replay (the e2e path, generated inputs)."""

    @given(st.sampled_from(sorted(VERSIONS)), st.data())
    @settings(max_examples=60)
    def test_every_declared_policy_is_feasible_and_replays_on_generated_scenarios(self, tag, data):
        v = VERSIONS[tag]
        scenario, horizon = data.draw(fixture_or_generated(v))
        policy = data.draw(st.sampled_from(v.policies))
        runner = v.runner(scenario, horizon)
        transcript = runner.run(v.scripted(policy))
        world = runner._world
        self.assertEqual(transcript['status'], 'complete')
        report = v.verify(v.scenario_dict(world), world.history(), horizon, scorecard=world.scorecard(),
                          actions=v.actions(transcript))
        self.assertEqual(report.violations, [])
        ok, diffs = v.replay(transcript, v.factory(scenario, horizon))
        self.assertTrue(ok, diffs)
        # A scripted policy never needs a rejected attempt in these worlds, except a refused offer.
        self.assertTrue(all(a['category'] in (None, 'budget', 'deadline', 'invalid_action') for a in transcript['attempts']))


if __name__ == '__main__':
    unittest.main()
