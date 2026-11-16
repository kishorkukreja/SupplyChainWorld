import json
import unittest
from copy import deepcopy
from pathlib import Path

from supplychainworld.baselines import run_baseline
from supplychainworld.dynamic import OperationalWorld
from supplychainworld.dynamic_v2 import OperationalWorldV2, ScenarioV2

ROOT = Path(__file__).resolve().parents[1]
FIX = {f['fixture_id']: f for f in json.loads((ROOT / 'fixtures/dynamic/v0.2/scenarios.json').read_text())['fixtures']}


def world(fid, **changes):
    f = FIX[fid]
    sc = deepcopy(f['scenario'])
    sc.update(changes)
    return OperationalWorldV2(f['horizon_days'], scenario=ScenarioV2(**sc))


def day(w, qty=None):
    """Release the largest feasible lot, then close the day."""
    s = w.snapshot()
    q = qty if qty is not None else min(4, s['component_on_hand'], max(0, s['open_demand'] - s['finished_on_hand']))
    assert w.release_production(q)['accepted']
    w.close_day()


class ScenarioValidationTests(unittest.TestCase):
    def test_fixtures_are_valid_and_deterministic(self):
        self.assertEqual(len(FIX), 4)
        for fid in FIX:
            self.assertEqual(world(fid).history(), world(fid).history())

    def test_invalid_scenarios_are_rejected(self):
        base = deepcopy(FIX['s02-warned-delayed-10d']['scenario'])
        bad = [dict(base, signal_day=2), dict(base, signal_hint_pct=101), dict(base, delay_outcome='maybe'),
               dict(base, delay_outcome='none'), dict(base, delayed_arrival_day=3), dict(base, surprise=1),
               dict(base, expedite_curve=[[1, 3, 1]]), dict(base, schema_version='1.0'),
               dict(base, orders=[dict(base['orders'][0], penalty_type='flat')]),
               dict(base, orders=[dict(base['orders'][0], penalty_rate=101)]),
               dict(base, tiers=[dict(base['tiers'][0], on_shortfall='cancel_after')])]
        for sc in bad:
            with self.assertRaises(ValueError):
                ScenarioV2(**sc)
        with self.assertRaises(ValueError):
            OperationalWorldV2(3, scenario=ScenarioV2(**base))  # order due after the horizon
        with self.assertRaises(TypeError):
            OperationalWorldV2(5, scenario={})


class ParityAndPenaltyTests(unittest.TestCase):
    def test_full_lot_choices_match_the_v01_costs(self):
        # v0.1 hand-worked 5-day costs 120 / 24 / 40 are reproduced by whole-lot v0.2 commitments (salvage aside).
        v1 = {p: run_baseline(OperationalWorld(5), p).scorecard['comparison_cost'] for p in ('maintain', 'expedite', 'alternate')}
        self.assertEqual(v1, {'maintain': 120, 'expedite': 24, 'alternate': 40})
        w = world('s02-sudden-5d')
        for _ in range(5):
            day(w)
        self.assertEqual(w.scorecard()['cost']['net_cost'], 120)
        w = world('s02-sudden-5d')
        self.assertTrue(w.choose_recovery('expedite', 8)['accepted'])
        for _ in range(5):
            day(w)
        self.assertEqual(w.scorecard()['cost']['net_cost'], 24)
        w = world('s02-sudden-5d')
        self.assertTrue(w.choose_recovery('alternate', 8)['accepted'])
        for _ in range(5):
            day(w)
        c = w.scorecard()['cost']
        self.assertEqual((c['recovery_spend'], c['service_penalties'], c['salvage_credit'], c['net_cost']), (40, 0, 16, 24))

    def _maintain_penalty(self, **order):
        sc = deepcopy(FIX['s02-sudden-5d']['scenario'])
        sc['orders'][0].update(order)
        w = OperationalWorldV2(5, scenario=ScenarioV2(**sc))
        for _ in range(5):
            day(w)
        return w.scorecard()

    def test_each_penalty_contract_term_by_hand(self):
        # Maintain: undelivered at closes of days 3, 4, 5 is 8, 4, 0 units; unit value 10.
        per_day = self._maintain_penalty(penalty_type='per_unit_per_day', penalty_rate=10)
        self.assertEqual(per_day['cost']['service_penalties'], 120)            # (8 + 4) x 10
        fixed = self._maintain_penalty(penalty_type='fixed_per_unit', penalty_rate=6)
        self.assertEqual(fixed['cost']['service_penalties'], 48)               # 8 undelivered at the due close, once
        pct = self._maintain_penalty(penalty_type='percent_of_value', penalty_rate=10)
        self.assertEqual(pct['cost']['service_penalties'], 12)                 # 8 x 10 x 10% + 4 x 10 x 10%
        self.assertEqual(pct['service']['unit_days_late'], 12)

    def test_salvage_rate_changes_only_the_salvage_credit(self):
        w = world('s02-sudden-5d', salvage_per_component=5)
        w.choose_recovery('alternate', 8)
        for _ in range(5):
            day(w)
        c = w.scorecard()['cost']
        self.assertEqual((c['salvage_credit'], c['net_cost']), (40, 0))


class RecoveryTests(unittest.TestCase):
    def test_partial_expedite_splits_the_lot(self):
        w = world('s02-sudden-5d')
        self.assertTrue(w.choose_recovery('expedite', 3)['accepted'])
        lots = {x['lot_id']: x for x in w.snapshot()['lots']}
        self.assertEqual((lots['primary']['quantity'], lots['primary']['arrival_day']), (5, 4))
        self.assertEqual((lots['exp1']['quantity'], lots['exp1']['arrival_day']), (3, 2))
        self.assertEqual(w.snapshot()['incremental_spend'], 9)

    def test_combined_actions_and_revisit_at_rising_cost(self):
        w = world('s02-sudden-5d', recovery_budget=100)
        self.assertTrue(w.choose_recovery('expedite', 4)['accepted'])      # 4 x 3
        self.assertTrue(w.choose_recovery('alternate', 4)['accepted'])     # 4 x 5
        day(w)
        self.assertTrue(w.choose_recovery('expedite', 4)['accepted'])      # revisit on day 2: 4 x 4
        c = w.snapshot()['commitments']
        self.assertEqual([(x['day'], x['choice'], x['unit_cost'], x['cost']) for x in c],
                         [(1, 'expedite', 3, 12), (1, 'alternate', 5, 20), (2, 'expedite', 4, 16)])
        self.assertEqual(w.snapshot()['incremental_spend'], 48)

    def test_budget_is_enforced_across_commitments(self):
        w = world('s02-sudden-5d')
        self.assertTrue(w.choose_recovery('expedite', 8)['accepted'])      # 24
        before = w.snapshot()
        r = w.choose_recovery('alternate', 4)                              # +20 = 44 > 40
        self.assertEqual((r['accepted'], 'budget' in r['reason']), (False, True))
        self.assertEqual(w.snapshot(), before)
        self.assertTrue(w.choose_recovery('alternate', 3)['accepted'])     # +15 = 39

    def test_each_commitment_executes_once(self):
        w = world('s02-sudden-5d')
        self.assertTrue(w.choose_recovery('alternate', 2, commit_id='x1')['accepted'])
        before = w.snapshot()
        r = w.choose_recovery('alternate', 2, commit_id='x1')
        self.assertFalse(r['accepted'])
        self.assertIn('duplicate', r['reason'])
        self.assertEqual(w.snapshot(), before)
        self.assertEqual(w.snapshot()['incremental_spend'], 10)
        for _ in range(5):
            day(w)
        receipts = [e for e in w.history() if e['kind'] == 'receipt' and e['details']['lot'] == 'alt1']
        self.assertEqual(len(receipts), 1)

    def test_invalid_recovery_is_rejected_without_mutation(self):
        w = world('s02-sudden-5d')
        before = w.snapshot()
        for args in (('maintain', 1), ('expedite', 0), ('expedite', -1), ('expedite', 1.5), ('expedite', 9),
                     ('alternate', 9), ('buy', 1), ('expedite', None)):
            self.assertFalse(w.choose_recovery(*args)['accepted'], args)
        self.assertEqual(w.snapshot(), before)
        self.assertEqual(sum(1 for e in w.history() if e['kind'] == 'recovery' and not e['accepted']), 8)

    def test_window_closes_and_expedite_needs_a_benefit(self):
        w = world('s02-sudden-5d')
        day(w)
        day(w, 0)  # day 2 closes with nothing released
        r = w.choose_recovery('alternate', 1)  # day 3: no rate-card row
        self.assertFalse(r['accepted'])
        self.assertIn('window', r['reason'])
        # Warned, no delay: on day 2 an expedite would arrive no earlier than the confirmed day 3.
        n = world('s02-warned-no-delay-10d')
        day(n)
        self.assertFalse(n.choose_recovery('expedite', 1)['accepted'])
        self.assertTrue(n.choose_recovery('alternate', 1)['accepted'])

    def test_alternate_supplier_availability_is_cumulative(self):
        w = world('s02-warned-delayed-10d', recovery_budget=200)
        self.assertTrue(w.choose_recovery('alternate', 5)['accepted'])
        self.assertFalse(w.choose_recovery('alternate', 4)['accepted'])
        self.assertTrue(w.choose_recovery('alternate', 3)['accepted'])
        self.assertFalse(w.choose_recovery('alternate', 1)['accepted'])

    def test_production_and_closed_episode_rules(self):
        w = world('s02-sudden-5d')
        self.assertFalse(w.release_production(5)['accepted'])      # capacity 4
        self.assertFalse(w.release_production(-1)['accepted'])
        self.assertTrue(w.release_production(4)['accepted'])
        self.assertFalse(w.release_production(1)['accepted'])      # already released
        w.close_day()
        self.assertFalse(w.release_production(1)['accepted'])      # no components
        for _ in range(4):
            day(w, 0)
        self.assertEqual(w.snapshot()['phase'], 'complete')
        for call in (lambda: w.close_day(), lambda: w.release_production(0), lambda: w.choose_recovery('alternate', 1)):
            self.assertFalse(call()['accepted'])


class TierAndCancellationTests(unittest.TestCase):
    def test_standard_tier_cancels_while_key_tier_backlogs(self):
        w = world('s02-multitier-cancel-10d')
        for _ in range(10):
            day(w)
        card, s = w.scorecard(), w.snapshot()
        orders = {o['order_id']: o for o in s['orders']}
        self.assertEqual((orders['K1']['status'], orders['K1']['delivered'], orders['K1']['cancelled']), ('complete', 8, 0))
        self.assertEqual((orders['S1']['status'], orders['S1']['delivered'], orders['S1']['cancelled']), ('cancelled', 0, 8))
        close5 = next(e for e in w.history() if e['kind'] == 'day_close' and e['day'] == 5)
        self.assertEqual(close5['details']['cancelled'], {'S1': 8})
        self.assertEqual(card['downstream'], {'cancelled_units': 8, 'cancelled_order_value': 160, 'undelivered_at_end': 0})
        # No penalty is assessed after the cancellation close.
        self.assertEqual(close5['state']['penalties'], s['penalties'])

    def test_key_tier_ships_first_when_stock_is_short(self):
        w = world('s02-multitier-cancel-10d')
        w.choose_recovery('expedite', 8)
        for _ in range(3):
            day(w)
        close3 = next(e for e in w.history() if e['kind'] == 'day_close' and e['day'] == 3)
        self.assertEqual(close3['details']['shipments'], {'K1': 8, 'S1': 4})

    def test_tier_blocks_do_not_collapse_into_one_number(self):
        w = world('s02-multitier-cancel-10d')
        for _ in range(10):
            day(w)
        card = w.scorecard()
        self.assertEqual(set(card), {'schema', 'cost', 'service', 'tier_impact', 'downstream', 'supply_risk', 'values_status'})
        self.assertEqual(set(card['tier_impact']['by_tier']), {'key', 'standard'})
        self.assertIn('PROVISIONAL', card['values_status'])
        flat = json.dumps(card).lower()
        for banned in ('overall', 'total_score', 'composite', 'best_policy', 'winner'):
            self.assertNotIn(banned, flat)

    def test_scorecard_requires_a_completed_episode(self):
        with self.assertRaises(ValueError):
            world('s02-sudden-5d').scorecard()


class SignalTests(unittest.TestCase):
    def _until_notice(self, fid):
        w = world(fid)
        obs = [w.observation()]
        day(w)
        obs.append(w.observation())
        return obs[0], obs[1]

    def test_warned_pair_is_identical_until_the_firm_notice(self):
        a0, _ = self._until_notice('s02-warned-delayed-10d')
        b0, _ = self._until_notice('s02-warned-no-delay-10d')
        for o in (a0, b0):
            o['state'].pop('scenario_id')
        self.assertEqual(a0, b0)
        self.assertEqual(a0['state']['signals'][0]['hint_pct'], 60)
        self.assertEqual(a0['state']['notices'], [])

    def test_resolution_differs_only_at_the_firm_notice(self):
        _, a1 = self._until_notice('s02-warned-delayed-10d')
        _, b1 = self._until_notice('s02-warned-no-delay-10d')
        self.assertEqual(a1['state']['notices'][0]['kind'], 'delay_confirmed')
        self.assertEqual(b1['state']['notices'][0]['kind'], 'on_time_confirmed')

    def test_signal_text_never_names_an_outcome(self):
        o, _ = self._until_notice('s02-warned-delayed-10d')
        text = json.dumps(o).lower()
        for w in ('delay_confirmed', 'revised', 'on_time_confirmed', 'will be delayed'):
            self.assertNotIn(w, text)

    def test_sudden_scenarios_have_no_signal_and_offers_follow_the_alert(self):
        s = world('s02-sudden-5d').observation()
        self.assertEqual(s['state']['signals'], [])
        self.assertIn('recovery_offers', s['rules'])     # the notice is already visible on day 1
        w = world('s02-warned-delayed-10d')
        self.assertIn('recovery_offers', w.observation()['rules'])  # the signal itself opens the rate card

    def test_premature_recovery_before_any_alert_is_rejected(self):
        w = world('s02-sudden-5d', notice_day=2, primary_promised_day=4, delayed_arrival_day=6,
                  expedite_curve=[[1, 3, 2], [2, 4, 3], [3, 5, 5]], alternate_curve=[[1, 5, 2], [2, 6, 3], [3, 7, 5]])
        r = w.choose_recovery('alternate', 1)
        self.assertFalse(r['accepted'])
        self.assertIn('no disruption alert', r['reason'])
        self.assertNotIn('recovery_offers', w.observation()['rules'])

    def test_snapshots_are_detached(self):
        w = world('s02-sudden-5d')
        snap = w.snapshot()
        snap['component_on_hand'] = 99
        snap['lots'][0]['quantity'] = 99
        w.history()
        self.assertEqual(w.snapshot()['component_on_hand'], 4)
        self.assertEqual(w.snapshot()['lots'][0]['quantity'], 8)


if __name__ == '__main__':
    unittest.main()
