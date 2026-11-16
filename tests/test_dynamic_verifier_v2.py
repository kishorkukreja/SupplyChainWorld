import ast
import json
import unittest
from copy import deepcopy
from pathlib import Path

from supplychainworld import dynamic_verifier_v2 as dv
from supplychainworld.agent_runner_v2 import POLICIES_V2, ObservableRunnerV2, scripted_policy_v2
from supplychainworld.dynamic_v2 import OperationalWorldV2, ScenarioV2

ROOT = Path(__file__).resolve().parents[1]
FIX = {f['fixture_id']: f for f in json.loads((ROOT / 'fixtures/dynamic/v0.2/scenarios.json').read_text())['fixtures']}
HAND = json.loads((ROOT / 'fixtures/dynamic/v0.2/hand-ledgers.json').read_text())['fixtures']
LEDGER = ('received', 'produced', 'shipped', 'components_close', 'finished_close', 'delivered_total',
          'penalty_total', 'spend_total', 'cancelled_total')


def episode(fid, policy):
    f = FIX[fid]
    w = OperationalWorldV2(f['horizon_days'], scenario=ScenarioV2(**f['scenario']))
    ObservableRunnerV2(w).run(scripted_policy_v2(policy))
    return f, w.history(), w.scorecard()


def verify(f, history, card=None):
    return dv.verify_episode(f['scenario'], history, horizon_days=f['horizon_days'], scorecard=card)


class HandWorkedLedgerTests(unittest.TestCase):
    def test_verifier_ledger_equals_hand_work_for_every_episode(self):
        n = 0
        for fid, pols in HAND.items():
            for policy in POLICIES_V2:
                f, h, card = episode(fid, policy)
                rep = verify(f, h, card)
                self.assertTrue(rep.feasible, (fid, policy, rep.violations))
                for k in LEDGER:
                    self.assertEqual([r[k] for r in rep.ledger], pols[policy]['ledger'][k], (fid, policy, k))
                n += 1
        self.assertEqual(n, 20)

    def test_verifier_scorecard_equals_hand_metrics(self):
        paths = {'recovery_spend': ('cost', 'recovery_spend'), 'service_penalties': ('cost', 'service_penalties'),
                 'salvage_credit': ('cost', 'salvage_credit'), 'net_cost': ('cost', 'net_cost'),
                 'ending_components': ('supply_risk', 'ending_components'),
                 'otif_orders_met': ('service', 'otif_orders_met'), 'on_time_units': ('service', 'on_time_units'),
                 'cancelled_units': ('service', 'cancelled_units'), 'unit_days_late': ('service', 'unit_days_late'),
                 'priority_weighted_unit_days_late': ('tier_impact', 'priority_weighted_unit_days_late'),
                 'cancelled_order_value': ('downstream', 'cancelled_order_value'),
                 'primary_reliance_pct': ('supply_risk', 'primary_reliance_pct'),
                 'recovery_commitments': ('supply_risk', 'recovery_commitments')}
        for fid, pols in HAND.items():
            for policy in POLICIES_V2:
                f, h, _ = episode(fid, policy)
                card = verify(f, h).scorecard
                for k, path in paths.items():
                    self.assertEqual(card[path[0]][path[1]], pols[policy]['metrics'][k], (fid, policy, k))

    def test_net_cost_is_reported_beside_its_parts_and_never_as_a_rank(self):
        f, h, _ = episode('s02-multitier-cancel-10d', 'alternate_on_alert')
        card = verify(f, h).scorecard
        self.assertEqual(card['cost'], {'recovery_spend': 40, 'service_penalties': 24, 'salvage_credit': 8, 'net_cost': 56})
        self.assertNotIn('rank', json.dumps(card).lower())


class AdversarialTests(unittest.TestCase):
    def setUp(self):
        self.f, self.h, self.card = episode('s02-warned-delayed-10d', 'combo_on_alert')

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
        sc = deepcopy(FIX['s02-sudden-5d']['scenario'])
        sc.update(notice_day=2, primary_promised_day=4, delayed_arrival_day=6,
                  expedite_curve=[[1, 3, 2], [2, 4, 3], [3, 5, 5]], alternate_curve=[[1, 5, 2], [2, 6, 3], [3, 7, 5]])
        w = OperationalWorldV2(5, scenario=ScenarioV2(**sc))
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
        f, h0, card = episode('s02-multitier-cancel-10d', 'maintain')
        h = deepcopy(h0)
        close = next(e for e in h if e['kind'] == 'day_close' and e['day'] == 3)
        close['details']['penalties']['S1'] += 1
        close['state']['penalties'] += 1
        self.assertIn('penalty_mismatch', verify(f, h).codes())
        # A simulator that used the wrong contract term (per unit per day instead of a fixed fee) is caught.
        sc = deepcopy(f['scenario'])
        sc['orders'][0].update(penalty_type='per_unit_per_day')
        w = OperationalWorldV2(f['horizon_days'], scenario=ScenarioV2(**sc))
        ObservableRunnerV2(w).run(scripted_policy_v2('maintain'))
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
        f, h0, _ = episode('s02-multitier-cancel-10d', 'maintain')
        h = deepcopy(h0)
        close5 = next(e for e in h if e['kind'] == 'day_close' and e['day'] == 5)
        close5['details']['cancelled'] = {}
        self.assertFalse(verify(f, h).feasible)

    def test_leaked_early_signal(self):
        f, h0, card = episode('s02-warned-delayed-10d', 'maintain')
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

    def test_forged_scorecard_and_self_reports(self):
        f, h, card = episode('s02-warned-delayed-10d', 'maintain')
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
        f, h, _ = episode('s02-sudden-5d', 'maintain')
        sc = f['scenario']
        for bad in (dict(sc, daily_capacity=-1), dict(sc, surprise=1), {k: v for k, v in sc.items() if k != 'orders'},
                    dict(sc, delay_outcome='x'), dict(sc, notice_day=5)):
            with self.assertRaises(dv.ScenarioError):
                dv.verify_episode(bad, h, horizon_days=5)
        with self.assertRaises(dv.ScenarioError):
            dv.verify_episode(sc, h, horizon_days=0)
        with self.assertRaises(dv.ScenarioError):
            dv.verify_episode(sc, h, horizon_days=2)   # an order falls due after the horizon

    def test_action_log_must_match_the_history(self):
        f, h, card = episode('s02-sudden-5d', 'combo_on_alert')
        good = [{'day': e['day'], 'kind': e['kind'], 'arguments': e['details'], 'result': {'accepted': True, 'commit_id': e['details'].get('commit_id')}}
                for e in h if e['kind'] in ('recovery', 'release') and e['accepted']]
        self.assertTrue(dv.verify_episode(f['scenario'], h, horizon_days=5, actions=good).feasible)
        self.assertIn('action_log_mismatch', dv.verify_episode(f['scenario'], h, horizon_days=5, actions=good[:-1]).codes())


class LeakScanTests(unittest.TestCase):
    def observations(self, fid, policy):
        f = FIX[fid]
        w = OperationalWorldV2(f['horizon_days'], scenario=ScenarioV2(**f['scenario']))
        t = ObservableRunnerV2(w).run(scripted_policy_v2(policy))
        return f, [{'state': a['view_before']['state'], 'rules': a['view_before']['rules'],
                    'last_outcome': a['view_before']['last_outcome']} for a in t['attempts']]

    def test_clean_observations_pass_and_leaks_are_found(self):
        f, obs = self.observations('s02-warned-delayed-10d', 'staged_revisit')
        self.assertEqual(dv.check_observations_for_leaks(f['scenario'], obs), [])
        bad = deepcopy(obs)
        bad[0]['state']['signals'][0]['text'] = 'Primary PO will be delayed to day 6'
        self.assertTrue(dv.check_observations_for_leaks(f['scenario'], bad))
        bad = deepcopy(obs)
        bad[0]['rules']['delayed_arrival_day'] = 6
        self.assertTrue(dv.check_observations_for_leaks(f['scenario'], bad))
        bad = deepcopy(obs)
        bad[0]['state']['lots'][0]['arrival_day'] = 6
        self.assertTrue(dv.check_observations_for_leaks(f['scenario'], bad))


class IndependenceTests(unittest.TestCase):
    def test_verifier_does_not_import_the_simulator(self):
        src = (ROOT / 'src/supplychainworld/dynamic_verifier_v2.py').read_text()
        names = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                names |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                names.add(('.' * node.level) + (node.module or ''))
        self.assertEqual(names, {'dataclasses'})

    def test_verifier_catches_a_sabotaged_simulator_rule(self):
        # A world with a wrong salvage rule still self-reports a scorecard; the verifier derives its own.
        f = FIX['s02-sudden-5d']
        sabotaged = deepcopy(f['scenario'])
        sabotaged['salvage_per_component'] = 9
        w = OperationalWorldV2(5, scenario=ScenarioV2(**sabotaged))
        ObservableRunnerV2(w).run(scripted_policy_v2('alternate_on_alert'))
        rep = dv.verify_episode(f['scenario'], w.history(), horizon_days=5, scorecard=w.scorecard())
        self.assertFalse(rep.feasible)


if __name__ == '__main__':
    unittest.main()
