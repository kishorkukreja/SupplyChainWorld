import ast
import json
import unittest
from copy import deepcopy
from pathlib import Path

from supplychainworld import dynamic_verifier_v3 as dv
from supplychainworld.agent_runner_v3 import POLICIES_V3, ObservableRunnerV3, scripted_policy_v3
from supplychainworld.dynamic_v3 import OperationalWorldV3, ScenarioV3

ROOT = Path(__file__).resolve().parents[1]
FIX = {f['fixture_id']: f for f in json.loads((ROOT / 'fixtures/dynamic/v0.3/scenarios.json').read_text())['fixtures']}
HAND = json.loads((ROOT / 'fixtures/dynamic/v0.3/hand-ledgers.json').read_text())['fixtures']
LEDGER = ('received', 'produced', 'shipped', 'components_close', 'finished_close', 'delivered_total',
          'penalty_total', 'spend_total', 'cancelled_total')


def episode(fid, policy):
    f = FIX[fid]
    w = OperationalWorldV3(f['horizon_days'], scenario=ScenarioV3(**f['scenario']))
    ObservableRunnerV3(w).run(scripted_policy_v3(policy))
    return f, w.history(), w.scorecard()


def verify(f, history, card=None):
    return dv.verify_episode(f['scenario'], history, horizon_days=f['horizon_days'], scorecard=card)


class HandWorkedLedgerTests(unittest.TestCase):
    def test_verifier_ledger_equals_hand_work_for_every_episode(self):
        n = 0
        for fid, pols in HAND.items():
            for policy in POLICIES_V3:
                f, h, card = episode(fid, policy)
                rep = verify(f, h, card)
                self.assertTrue(rep.feasible, (fid, policy, rep.violations))
                for k in LEDGER:
                    self.assertEqual([r[k] for r in rep.ledger], pols[policy]['ledger'][k], (fid, policy, k))
                n += 1
        self.assertEqual(n, 25)

    def test_verifier_scorecard_equals_hand_metrics(self):
        paths = {'recovery_spend': ('cost', 'recovery_spend'), 'expedite_spend': ('cost', 'expedite_spend'),
                 'alternate_spend': ('cost', 'alternate_spend'), 'service_penalties': ('cost', 'service_penalties'),
                 'salvage_credit': ('cost', 'salvage_credit'), 'net_cost': ('cost', 'net_cost'),
                 'ending_components': ('supply_risk', 'ending_components'),
                 'otif_orders_met': ('service', 'otif_orders_met'), 'on_time_units': ('service', 'on_time_units'),
                 'cancelled_units': ('service', 'cancelled_units'), 'unit_days_late': ('service', 'unit_days_late'),
                 'priority_weighted_unit_days_late': ('tier_impact', 'priority_weighted_unit_days_late'),
                 'cancelled_order_value': ('downstream', 'cancelled_order_value'),
                 'primary_reliance_pct': ('supply_risk', 'primary_reliance_pct'),
                 'recovery_commitments': ('supply_risk', 'recovery_commitments')}
        for fid, pols in HAND.items():
            for policy in POLICIES_V3:
                f, h, _ = episode(fid, policy)
                card = verify(f, h).scorecard
                for k, path in paths.items():
                    self.assertEqual(card[path[0]][path[1]], pols[policy]['metrics'][k], (fid, policy, k))

    def test_net_cost_is_reported_beside_its_parts_and_never_as_a_rank(self):
        f, h, _ = episode('s03-multitier-cancel-10d', 'alternate_on_alert')
        card = verify(f, h).scorecard
        self.assertEqual(card['cost'], {'recovery_spend': 104, 'expedite_spend': 0, 'alternate_spend': 104,
                                        'service_penalties': 13, 'salvage_credit': 24, 'net_cost': 93})
        self.assertNotIn('rank', json.dumps(card).lower())


class AdversarialTests(unittest.TestCase):
    def setUp(self):
        self.f, self.h, self.card = episode('s03-warned-delayed-10d', 'combo_on_alert')

    def alert_at(self, h):
        return next(i for i, e in enumerate(h) if e['kind'] == 'day_open' and (e['state']['signals'] or e['state']['notices']))

    def insert(self, h, calls):
        i = self.alert_at(h)
        for k, d in enumerate(calls):
            h.insert(i + 1 + k, {'day': h[i]['day'], 'kind': 'recovery', 'details': d, 'accepted': True,
                                 'reason': None, 'state': deepcopy(h[i]['state'])})

    def test_genuine_episodes_pass(self):
        self.assertTrue(verify(self.f, self.h, self.card).feasible)

    def test_duplicate_commitment(self):
        h = deepcopy(self.h)
        self.insert(h, [{'choice': 'alternate', 'quantity': 1, 'commit_id': 'd'}] * 2)
        self.assertIn('duplicate_commitment', verify(self.f, h).codes())

    def test_duplicate_charge_for_a_repeated_commit(self):
        h = deepcopy(self.h)
        first = next(e for e in h if e['kind'] == 'recovery' and e['accepted'])
        h.insert(h.index(first) + 1, deepcopy(first))
        self.assertIn('duplicate_commitment', verify(self.f, h).codes())

    def test_over_budget_combination(self):
        h = deepcopy(self.h)
        self.insert(h, [{'choice': 'expedite', 'quantity': 8, 'commit_id': 'a'},
                        {'choice': 'alternate', 'quantity': 8, 'commit_id': 'b'}])
        self.assertIn('budget_exceeded', verify(self.f, h).codes())

    def test_recovery_after_the_window_and_oversized_quantities(self):
        h = deepcopy(self.h)
        late = deepcopy(next(e for e in h if e['kind'] == 'day_open' and e['day'] == 5))
        h.insert(h.index(next(e for e in h if e['kind'] == 'day_open' and e['day'] == 5)) + 1,
                 {'day': 5, 'kind': 'recovery', 'details': {'choice': 'alternate', 'quantity': 1, 'commit_id': 'z'},
                  'accepted': True, 'reason': None, 'state': late['state']})
        self.assertIn('recovery_window_closed', verify(self.f, h).codes())
        h = deepcopy(self.h)
        self.insert(h, [{'choice': 'expedite', 'quantity': 9, 'commit_id': 'a'}])
        self.assertIn('expedite_exceeds_units', verify(self.f, h).codes())
        h = deepcopy(self.h)
        self.insert(h, [{'choice': 'alternate', 'quantity': 9, 'commit_id': 'a'}])
        self.assertIn('alternate_exceeds_availability', verify(self.f, h).codes())
        h = deepcopy(self.h)
        self.insert(h, [{'choice': 'expedite', 'quantity': 0, 'commit_id': 'a'}, {'choice': 'swap', 'quantity': 1}])
        self.assertTrue({'invalid_quantity', 'unknown_recovery_option'} <= set(verify(self.f, h).codes()))

    def test_premature_recovery_before_any_alert(self):
        sc = deepcopy(FIX['s03-sudden-5d']['scenario'])
        sc.update(notice_day=2, primary_promised_day=4, delayed_arrival_day=6,
                  expedite_card=[[1, 40, 2], [2, 50, 3], [3, 60, 5]], alternate_card=[[1, 30, 2], [2, 40, 3], [3, 50, 5]])
        w = OperationalWorldV3(5, scenario=ScenarioV3(**sc))
        self.assertFalse(w.choose_recovery('alternate', 1)['accepted'])
        h = w.history()
        self.assertTrue(dv.verify_episode(sc, h, horizon_days=5).feasible)   # a correctly rejected command is feasible
        claim = deepcopy(h)
        next(e for e in claim if e['kind'] == 'recovery')['accepted'] = True
        self.assertIn('premature_recovery', dv.verify_episode(sc, claim, horizon_days=5).codes())

    def test_premature_or_wrong_receipt(self):
        h = deepcopy(self.h)
        next(e for e in h if e['kind'] == 'receipt')['day'] -= 1
        self.assertIn('receipt_timing_or_quantity', verify(self.f, h).codes())
        h = deepcopy(self.h)
        next(e for e in h if e['kind'] == 'receipt')['details']['quantity'] += 1
        self.assertIn('receipt_timing_or_quantity', verify(self.f, h).codes())

    def test_wrong_penalty_is_named(self):
        f, h0, card = episode('s03-multitier-cancel-10d', 'maintain')
        h = deepcopy(h0)
        close = next(e for e in h if e['kind'] == 'day_close' and e['day'] == 3)
        close['details']['penalties']['S1'] += 1
        close['state']['penalties'] += 1
        self.assertIn('penalty_mismatch', verify(f, h).codes())
        # A simulator that used the wrong contract term (per unit per day instead of a fixed fee) is caught.
        sc = deepcopy(f['scenario'])
        sc['orders'][0].update(penalty_type='per_unit_per_day')
        w = OperationalWorldV3(f['horizon_days'], scenario=ScenarioV3(**sc))
        ObservableRunnerV3(w).run(scripted_policy_v3('maintain'))
        rep = verify(f, w.history(), w.scorecard())
        self.assertFalse(rep.feasible)
        self.assertTrue({'penalty_mismatch', 'scorecard_mismatch'} & set(rep.codes()))

    def test_tampering_with_state_and_inventory(self):
        h = deepcopy(self.h)
        close = next(e for e in h if e['kind'] == 'day_close')
        close['state']['finished_on_hand'] += 1
        rep = verify(self.f, h)
        self.assertTrue({'ledger_mismatch', 'finished_goods_conservation'} <= set(rep.codes()))
        h = deepcopy(self.h)
        next(e for e in h if e['kind'] == 'day_close')['state']['component_on_hand'] += 4
        self.assertIn('component_conservation', verify(self.f, h).codes())
        h = deepcopy(self.h)
        h = [e for e in h if not (e['kind'] == 'day_close' and e['day'] == 3)]
        self.assertFalse(verify(self.f, h).feasible)
        h = deepcopy(self.h)
        h.append(deepcopy(h[-1]))
        self.assertFalse(verify(self.f, h).feasible)

    def test_cancellation_cannot_be_forged(self):
        f, h0, _ = episode('s03-multitier-cancel-10d', 'maintain')
        h = deepcopy(h0)
        close9 = next(e for e in h if e['kind'] == 'day_close' and e['day'] == 9)
        self.assertEqual(close9['details']['cancelled'], {'S1': 4})
        close9['details']['cancelled'] = {}
        self.assertFalse(verify(f, h).feasible)
        # Cancelling on the old horizon day 5 instead of six days after the due date is not feasible either.
        h = deepcopy(h0)
        next(e for e in h if e['kind'] == 'day_close' and e['day'] == 5)['details']['cancelled'] = {'S1': 4}
        self.assertFalse(verify(f, h).feasible)

    def test_leaked_early_signal(self):
        f, h0, card = episode('s03-warned-delayed-10d', 'maintain')
        h = deepcopy(h0)
        next(e for e in h if e['kind'] == 'signal')['details']['will_delay'] = True
        self.assertIn('signal_leak', verify(f, h).codes())
        h = deepcopy(h0)
        for e in h:
            if e['state']['signals'] and not e['state']['notices']:
                e['state']['signals'][0]['text'] = 'Primary PO will be delayed to day 6'
        self.assertIn('signal_leak', verify(f, h).codes())
        h = deepcopy(h0)
        for e in h:
            if e['state']['signals'] and not e['state']['notices']:
                e['state']['signals'][0]['revised_day'] = 6
        self.assertIn('signal_leak', verify(f, h).codes())
        # A numeric hint creeping back in, or a level that differs from the declared one, is a leak.
        h = deepcopy(h0)
        for e in h:
            if e['state']['signals'] and not e['state']['notices']:
                e['state']['signals'][0]['hint_pct'] = 60
        self.assertIn('signal_leak', verify(f, h).codes())
        h = deepcopy(h0)
        next(e for e in h if e['kind'] == 'signal')['details']['level'] = 'high'
        self.assertIn('signal_leak', verify(f, h).codes())

    def test_forged_scorecard_and_self_reports(self):
        f, h, card = episode('s03-warned-delayed-10d', 'maintain')
        forged = deepcopy(card)
        forged['cost']['net_cost'] = 0
        forged['service']['orders'][0]['otif'] = True
        rep = verify(f, h, forged)
        self.assertIn('scorecard_mismatch', rep.codes())
        h2 = deepcopy(h)
        for e in h2:
            e['passed'] = True
        rep = verify(f, h2, {**card, 'verified': True})
        self.assertTrue(rep.feasible)
        self.assertTrue({'passed', 'verified'} <= set(rep.ignored_self_reports))
        self.assertIn('scorecard_for_incomplete_episode', dv.verify_episode(
            f['scenario'], [e for e in h if e['day'] < 4], horizon_days=f['horizon_days'], scorecard=card).codes())

    def test_scenario_errors(self):
        f, h, _ = episode('s03-sudden-5d', 'maintain')
        sc = f['scenario']
        for bad in (dict(sc, daily_capacity=-1), dict(sc, surprise=1), {k: v for k, v in sc.items() if k != 'orders'},
                    dict(sc, delay_outcome='x'), dict(sc, notice_day=5), dict(sc, signal_level='high'),
                    dict(sc, part_class='bespoke'), dict(sc, base_unit_cost=0), dict(sc, expedite_card=[[1, 45, 2]]),
                    dict(sc, salvage_pct_by_class={'standard': 60}),
                    dict(sc, orders=[dict(sc['orders'][0], penalty_cap_pct=101)]),
                    dict(sc, tiers=[dict(sc['tiers'][0], cancel_days_after_due=3)])):
            with self.assertRaises(dv.ScenarioError):
                dv.verify_episode(bad, h, horizon_days=5)
        with self.assertRaises(dv.ScenarioError):
            dv.verify_episode(sc, h, horizon_days=0)
        with self.assertRaises(dv.ScenarioError):
            dv.verify_episode(sc, h, horizon_days=2)   # an order falls due after the horizon

    def test_action_log_must_match_the_history(self):
        f, h, card = episode('s03-sudden-5d', 'combo_on_alert')
        good = [{'day': e['day'], 'kind': e['kind'], 'arguments': e['details'], 'result': {'accepted': True, 'commit_id': e['details'].get('commit_id')}}
                for e in h if e['kind'] in ('recovery', 'release') and e['accepted']]
        self.assertTrue(dv.verify_episode(f['scenario'], h, horizon_days=5, actions=good).feasible)
        self.assertIn('action_log_mismatch', dv.verify_episode(f['scenario'], h, horizon_days=5, actions=good[:-1]).codes())


class LeakScanTests(unittest.TestCase):
    def observations(self, fid, policy):
        f = FIX[fid]
        w = OperationalWorldV3(f['horizon_days'], scenario=ScenarioV3(**f['scenario']))
        t = ObservableRunnerV3(w).run(scripted_policy_v3(policy))
        return f, [{'state': a['view_before']['state'], 'rules': a['view_before']['rules'],
                    'last_outcome': a['view_before']['last_outcome']} for a in t['attempts']]

    def test_clean_observations_pass_and_leaks_are_found(self):
        f, obs = self.observations('s03-warned-delayed-10d', 'staged_revisit')
        self.assertEqual(dv.check_observations_for_leaks(f['scenario'], obs), [])
        bad = deepcopy(obs)
        bad[0]['state']['signals'][0]['text'] = 'Primary PO will be delayed to day 6'
        self.assertTrue(dv.check_observations_for_leaks(f['scenario'], bad))
        bad = deepcopy(obs)
        bad[0]['state']['signals'][0]['level'] = 'high'          # not the declared level
        self.assertTrue(dv.check_observations_for_leaks(f['scenario'], bad))
        bad = deepcopy(obs)
        bad[0]['state']['signals'][0]['hint_pct'] = 60           # a numeric hint is a leak channel
        self.assertTrue(dv.check_observations_for_leaks(f['scenario'], bad))
        bad = deepcopy(obs)
        bad[0]['rules']['delayed_arrival_day'] = 6
        self.assertTrue(dv.check_observations_for_leaks(f['scenario'], bad))
        bad = deepcopy(obs)
        bad[0]['state']['lots'][0]['arrival_day'] = 6
        self.assertTrue(dv.check_observations_for_leaks(f['scenario'], bad))


class IndependenceTests(unittest.TestCase):
    def test_verifier_does_not_import_the_simulator(self):
        src = (ROOT / 'src/supplychainworld/dynamic_verifier_v3.py').read_text()
        names = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                names |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                names.add(('.' * node.level) + (node.module or ''))
        self.assertEqual(names, {'dataclasses'})

    def _sabotage(self, fid, policy, **changes):
        # A world with a wrong rule still self-reports a scorecard; the verifier derives its own from the true scenario.
        f = FIX[fid]
        sabotaged = deepcopy(f['scenario'])
        sabotaged.update(changes)
        w = OperationalWorldV3(f['horizon_days'], scenario=ScenarioV3(**sabotaged))
        ObservableRunnerV3(w).run(scripted_policy_v3(policy))
        return dv.verify_episode(f['scenario'], w.history(), horizon_days=f['horizon_days'], scorecard=w.scorecard())

    def test_verifier_catches_a_sabotaged_simulator_rule(self):
        self.assertFalse(self._sabotage('s03-sudden-5d', 'alternate_on_alert',
                                        salvage_pct_by_class={'standard': 90, 'custom': 0}).feasible)

    def test_verifier_catches_each_new_v03_rule_when_the_simulator_breaks_it(self):
        sc = FIX['s03-multitier-cancel-10d']['scenario']
        # wrong part class (salvage), wrong premium on either rate card, wrong cancellation lag, wrong penalty rate
        self.assertIn('scorecard_mismatch', self._sabotage('s03-sudden-5d', 'alternate_on_alert', part_class='custom').codes())
        self.assertFalse(self._sabotage('s03-sudden-5d', 'expedite_on_alert', expedite_card=[[1, 30, 2], [2, 50, 3]]).feasible)
        self.assertFalse(self._sabotage('s03-sudden-5d', 'alternate_on_alert', alternate_card=[[1, 20, 2], [2, 40, 3]]).feasible)
        tiers = [sc['tiers'][0], dict(sc['tiers'][1], cancel_days_after_due=2)]
        self.assertFalse(self._sabotage('s03-multitier-cancel-10d', 'maintain', tiers=tiers).feasible)
        tiers = [dict(sc['tiers'][0], weight=1), sc['tiers'][1]]          # weights 1 to 1 instead of 5 to 1
        self.assertFalse(self._sabotage('s03-multitier-cancel-10d', 'maintain', tiers=tiers).feasible)
        o = dict(sc['orders'][1], penalty_rate=200)
        self.assertFalse(self._sabotage('s03-multitier-cancel-10d', 'maintain', orders=[sc['orders'][0], o]).feasible)

    def test_verifier_catches_a_simulator_that_ignores_the_penalty_cap(self):
        f = FIX['s03-alt-cheaper-10d']
        true_sc = deepcopy(f['scenario'])
        true_sc['orders'][0]['penalty_cap_pct'] = 5               # the cap binds at USD 60
        no_cap = deepcopy(true_sc)
        no_cap['orders'][0]['penalty_cap_pct'] = None
        w = OperationalWorldV3(10, scenario=ScenarioV3(**no_cap))
        ObservableRunnerV3(w).run(scripted_policy_v3('maintain'))
        rep = dv.verify_episode(true_sc, w.history(), horizon_days=10, scorecard=w.scorecard())
        self.assertTrue({'penalty_mismatch', 'scorecard_mismatch'} & set(rep.codes()))
        w = OperationalWorldV3(10, scenario=ScenarioV3(**true_sc))
        ObservableRunnerV3(w).run(scripted_policy_v3('maintain'))
        good = dv.verify_episode(true_sc, w.history(), horizon_days=10, scorecard=w.scorecard())
        self.assertTrue(good.feasible)
        self.assertEqual(good.scorecard['cost']['service_penalties'], 60)


if __name__ == '__main__':
    unittest.main()
