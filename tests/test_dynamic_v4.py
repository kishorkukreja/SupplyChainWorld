import json
import unittest
from copy import deepcopy
from pathlib import Path

from supplychainworld.dynamic_v3 import OperationalWorldV3, ScenarioV3
from supplychainworld.dynamic_v4 import OperationalWorldV4, ScenarioV4

ROOT = Path(__file__).resolve().parents[1]
FIX = {f['fixture_id']: f for f in json.loads((ROOT / 'fixtures/dynamic/v0.4/scenarios.json').read_text())['fixtures']}


def world(fid, **changes):
    f = FIX[fid]
    sc = deepcopy(f['scenario'])
    sc.update(changes)
    return OperationalWorldV4(f['horizon_days'], scenario=ScenarioV4(**sc))


def day(w, qty=None):
    """Release the largest feasible lot, then close the day."""
    s = w.snapshot()
    q = qty if qty is not None else min(4, s['component_on_hand'], max(0, s['open_demand'] - s['finished_on_hand']))
    assert w.release_production(q)['accepted']
    w.close_day()


def run(w, days, recoveries=()):
    """Apply (choice, quantity) recoveries on day 1, then run `days` days with maximal production."""
    for choice, qty in recoveries:
        assert w.choose_recovery(choice, qty)['accepted']
    for _ in range(days):
        day(w)
    return w.scorecard()


class ScenarioValidationTests(unittest.TestCase):
    def test_fixtures_are_valid_and_deterministic(self):
        self.assertEqual(len(FIX), 5)
        for fid in FIX:
            self.assertEqual(world(fid).history(), world(fid).history())

    def test_invalid_scenarios_are_rejected(self):
        base = deepcopy(FIX['s04-warned-delayed-10d']['scenario'])
        mt = deepcopy(FIX['s04-multitier-cancel-10d']['scenario'])
        bad = [dict(base, signal_day=2), dict(base, signal_level=60), dict(base, signal_level='extreme'),
               dict(base, signal_day=None, signal_level='high'), dict(base, delay_outcome='maybe'),
               dict(base, delay_outcome='none'), dict(base, delayed_arrival_day=3), dict(base, surprise=1),
               dict(base, signal_hint_pct=60), dict(base, expedite_card=[[1, 40, 1]]),
               dict(base, expedite_card=[[1, 45, 2]]),               # 45% of USD 10 is not a whole dollar
               dict(base, part_class='bespoke'), dict(base, salvage_pct_by_class={'standard': 60}),
               dict(base, salvage_pct_by_class={'standard': 60, 'custom': 101}), dict(base, base_unit_cost=0),
               dict(base, schema_version='2.0'),
               dict(base, orders=[dict(base['orders'][0], penalty_type='flat')]),
               dict(base, orders=[dict(base['orders'][0], penalty_rate=10001)]),
               dict(base, orders=[dict(base['orders'][0], penalty_cap_pct=101)]),
               dict(base, orders=[{k: v for k, v in base['orders'][0].items() if k != 'penalty_cap_pct'}]),
               dict(base, tiers=[dict(base['tiers'][0], on_shortfall='cancel_after')]),
               dict(mt, tiers=[mt['tiers'][0], {'tier': 'standard', 'weight': 1, 'on_shortfall': 'cancel_after',
                                                'cancel_day': 5}])]
        for sc in bad:
            with self.assertRaises(ValueError):
                ScenarioV4(**sc)
        with self.assertRaises(ValueError):
            OperationalWorldV4(3, scenario=ScenarioV4(**base))  # order due after the horizon
        with self.assertRaises(TypeError):
            OperationalWorldV4(5, scenario={})

    def test_levels_classes_and_terms_are_accepted(self):
        base = deepcopy(FIX['s04-warned-delayed-10d']['scenario'])
        for level in ('low', 'medium', 'high'):
            ScenarioV4(**dict(base, signal_level=level))
        for part in ('standard', 'custom'):
            ScenarioV4(**dict(base, part_class=part))
        for ptype, rate in (('percent_of_value', 150), ('fixed_per_unit', 6), ('per_unit_per_day', 2)):
            ScenarioV4(**dict(base, orders=[dict(base['orders'][0], penalty_type=ptype, penalty_rate=rate,
                                                 penalty_cap_pct=None)]))


class VersionTests(unittest.TestCase):
    def test_v4_scenarios_carry_the_round_three_values(self):
        for f in FIX.values():
            sc = f['scenario']
            self.assertEqual(sc['recovery_budget'], 40)
            self.assertEqual({o['penalty_cap_pct'] for o in sc['orders']}, {20})
            self.assertTrue(all(o['penalty_rate'] in (150, 6) for o in sc['orders']))     # 1.5% a day and the K1 fixed term
        self.assertEqual({o['penalty_rate'] for f in FIX.values() for o in f['scenario']['orders']
                          if o['penalty_type'] == 'percent_of_value'}, {150})

    def test_schema_versions_are_not_interchangeable_with_v03(self):
        sc = deepcopy(FIX['s04-sudden-5d']['scenario'])
        self.assertEqual(ScenarioV4(**sc).schema_version, '4.0')
        self.assertEqual(world('s04-sudden-5d').snapshot()['schema_version'], '4.0')
        self.assertEqual(run(world('s04-sudden-5d'), 5)['schema'], 'dyn-scorecard-4')
        with self.assertRaises(ValueError):
            ScenarioV4(**dict(sc, schema_version='3.0'))
        with self.assertRaises(TypeError):
            OperationalWorldV4(5, scenario=ScenarioV3(**sc))      # a v0.3 scenario object is not a v0.4 scenario

    def test_v03_family_is_unchanged_by_v04(self):
        v3 = {f['fixture_id']: f for f in json.loads((ROOT / 'fixtures/dynamic/v0.3/scenarios.json').read_text())['fixtures']}
        w = OperationalWorldV3(5, scenario=ScenarioV3(**v3['s03-sudden-5d']['scenario']))
        self.assertEqual(w.observation()['rules']['recovery_offers']['alternate']['today']['unit_cost'], 13)


class PricingTests(unittest.TestCase):
    """v0.4 price basis (reviewer: compare premiums only): both expedite and alternate cost a percent premium on the base unit cost."""

    def test_unit_costs_follow_the_base_cost_and_the_premiums(self):
        w = world('s04-sudden-5d')
        offers = w.observation()['rules']['recovery_offers']
        self.assertEqual(offers['expedite']['today'], {'unit_cost': 4, 'premium_pct': 40, 'arrival_day': 2, 'max_units': 8})
        self.assertEqual(offers['alternate']['today'], {'unit_cost': 3, 'premium_pct': 30, 'arrival_day': 2, 'max_units': 8})
        day(w)
        offers = w.observation()['rules']['recovery_offers']
        self.assertEqual((offers['expedite']['today']['unit_cost'], offers['alternate']['today']['unit_cost']), (5, 4))
        self.assertEqual([r['unit_cost'] for r in offers['expedite']['rate_card']], [4, 5])
        self.assertEqual([r['unit_cost'] for r in offers['alternate']['rate_card']], [3, 4])

    def test_changing_the_base_cost_rescales_both_rate_cards(self):
        w = world('s04-sudden-5d', base_unit_cost=20)
        offers = w.observation()['rules']['recovery_offers']
        self.assertEqual((offers['expedite']['today']['unit_cost'], offers['alternate']['today']['unit_cost']), (8, 6))

    def test_premium_only_lot_prices_and_the_primary_lot_still_arrives_after_an_alternate_buy(self):
        w = world('s04-sudden-5d')
        self.assertTrue(w.choose_recovery('expedite', 8)['accepted'])
        self.assertEqual(w.snapshot()['incremental_spend'], 32)           # 8 x (40% of 10)
        a = world('s04-sudden-5d')
        self.assertTrue(a.choose_recovery('alternate', 8)['accepted'])
        self.assertEqual(a.snapshot()['incremental_spend'], 24)           # 8 x (30% of 10): premium only
        lots = {x['lot_id']: x for x in a.snapshot()['lots']}
        self.assertEqual((lots['primary']['quantity'], lots['primary']['arrival_day'], lots['alt1']['quantity']), (8, 4, 8))

    def test_costs_by_recovery_on_the_sudden_scenario_by_hand(self):
        # Order O1: 12 units due day 3, USD 100 a unit; penalty 1.5% of undelivered value per day.
        # Maintain: undelivered at the closes of days 3, 4, 5 is 8, 4, 0 -> 12 + 6 = 18.
        card = run(world('s04-sudden-5d'), 5)['cost']
        self.assertEqual((card['recovery_spend'], card['service_penalties'], card['salvage_credit'], card['net_cost']), (0, 18, 0, 18))
        card = run(world('s04-sudden-5d'), 5, [('expedite', 8)])['cost']
        self.assertEqual((card['recovery_spend'], card['service_penalties'], card['salvage_credit'], card['net_cost']), (32, 0, 0, 32))
        card = run(world('s04-sudden-5d'), 5, [('alternate', 8)])['cost']
        # 8 surplus components at the end are alternate-bought: no salvage credit in v0.4 (unresolved convention).
        self.assertEqual((card['recovery_spend'], card['service_penalties'], card['salvage_credit'], card['net_cost']), (24, 0, 0, 24))
        self.assertEqual((card['expedite_spend'], card['alternate_spend'], card['uncredited_alternate_surplus']), (0, 24, 8))

    def test_rate_card_rises_by_day(self):
        w = world('s04-sudden-5d', recovery_budget=200)
        self.assertTrue(w.choose_recovery('expedite', 4)['accepted'])
        self.assertTrue(w.choose_recovery('alternate', 4)['accepted'])
        day(w)
        self.assertTrue(w.choose_recovery('expedite', 4)['accepted'])
        c = w.snapshot()['commitments']
        self.assertEqual([(x['day'], x['choice'], x['unit_cost'], x['cost']) for x in c],
                         [(1, 'expedite', 4, 16), (1, 'alternate', 3, 12), (2, 'expedite', 5, 20)])
        self.assertEqual(w.snapshot()['incremental_spend'], 48)


class PenaltyTests(unittest.TestCase):
    def _maintain_penalty(self, fid='s04-sudden-5d', **order):
        sc = deepcopy(FIX[fid]['scenario'])
        sc['orders'][0].update(order)
        f = FIX[fid]
        w = OperationalWorldV4(f['horizon_days'], scenario=ScenarioV4(**sc))
        for _ in range(f['horizon_days']):
            day(w)
        return w.scorecard()

    def test_each_penalty_contract_term_by_hand(self):
        # Maintain on the sudden scenario: undelivered at the closes of days 3, 4, 5 is 8, 4, 0 units of USD 100.
        pct = self._maintain_penalty(penalty_type='percent_of_value', penalty_rate=150, penalty_cap_pct=None)
        self.assertEqual(pct['cost']['service_penalties'], 18)                 # 8 x 100 x 1.5% + 4 x 100 x 1.5%
        self.assertEqual(pct['service']['unit_days_late'], 12)
        fixed = self._maintain_penalty(penalty_type='fixed_per_unit', penalty_rate=6, penalty_cap_pct=None)
        self.assertEqual(fixed['cost']['service_penalties'], 48)               # 8 undelivered at the due close, once
        per_day = self._maintain_penalty(penalty_type='per_unit_per_day', penalty_rate=10, penalty_cap_pct=None)
        self.assertEqual(per_day['cost']['service_penalties'], 120)            # (8 + 4) x 10

    def test_percent_penalty_rounds_down_to_a_whole_dollar(self):
        w = world('s04-multitier-cancel-10d')
        for _ in range(3):
            day(w)
        close3 = next(e for e in w.history() if e['kind'] == 'day_close' and e['day'] == 3)
        # S1: 8 undelivered x USD 80 x 1.5% = 9.6, charged as 9. K1 fixed: 4 x 6 = 24.
        self.assertEqual(close3['details']['penalties'], {'K1': 24, 'S1': 9})

    def test_total_cap_stops_the_percent_penalty(self):
        # Long-delay scenario, maintain: 8 units late for 5 closes (12 a day), then 4 late (6). Uncapped total 78.
        self.assertEqual(self._maintain_penalty('s04-alt-cheaper-10d')['cost']['service_penalties'], 78)
        # A 5% cap on a USD 1,200 order is USD 60: reached at the close of day 7, nothing after.
        capped = self._maintain_penalty('s04-alt-cheaper-10d', penalty_cap_pct=5)
        self.assertEqual(capped['cost']['service_penalties'], 60)
        self.assertEqual(capped['service']['unit_days_late'], 52)               # lateness is still recorded
        self.assertEqual(capped['service']['orders'][0]['penalty'], 60)
        # Cap 0 means no penalty at all; the scenario default is 20% of order value (USD 240), not reached here.
        self.assertEqual(self._maintain_penalty('s04-alt-cheaper-10d', penalty_cap_pct=0)['cost']['service_penalties'], 0)
        self.assertEqual(FIX['s04-alt-cheaper-10d']['scenario']['orders'][0]['penalty_cap_pct'], 20)

    def test_cap_applies_to_the_other_contract_terms_too(self):
        capped = self._maintain_penalty(penalty_type='per_unit_per_day', penalty_rate=10, penalty_cap_pct=5)
        self.assertEqual(capped['cost']['service_penalties'], 60)              # 5% of USD 1,200 instead of 120

    def test_salvage_depends_on_the_part_class(self):
        # Small order (4 units) so the arriving primary lot is surplus: 8 components left, all primary-sourced.
        small = dict(orders=[dict(FIX['s04-sudden-5d']['scenario']['orders'][0], quantity=4)])
        std = run(world('s04-sudden-5d', **small), 5)['cost']
        cus = run(world('s04-sudden-5d', part_class='custom', **small), 5)['cost']
        self.assertEqual((std['salvage_credit'], std['net_cost']), (48, std['service_penalties'] - 48))
        self.assertEqual((cus['salvage_credit'], cus['net_cost']), (0, cus['service_penalties']))
        self.assertEqual(world('s04-sudden-5d').observation()['rules']['salvage_pct_by_class'], {'standard': 60, 'custom': 0})
        self.assertEqual(world('s04-sudden-5d', salvage_pct_by_class={'standard': 50, 'custom': 10})
                         .observation()['rules']['salvage_per_component'], 5)

    def test_cost_ordering_changes_with_the_scenario(self):
        # Short sudden delay: maintain 18 < alternate 24 < expedite 32 (premiums only, alternate is the cheaper premium).
        short = {n: run(world('s04-sudden-5d'), 5, r)['cost']['net_cost']
                 for n, r in (('maintain', []), ('expedite', [('expedite', 8)]), ('alternate', [('alternate', 8)]))}
        self.assertEqual(short, {'maintain': 18, 'expedite': 32, 'alternate': 24})
        # Long delay with a slow expedite lane: alternate 30 < maintain 78 < expedite 98 on net cost.
        long_ = {n: run(world('s04-alt-cheaper-10d'), 10, r)['cost']['net_cost']
                 for n, r in (('maintain', []), ('expedite', [('expedite', 8)]), ('alternate', [('alternate', 8)]))}
        self.assertEqual(long_, {'maintain': 78, 'expedite': 98, 'alternate': 30})
        # Unlike v0.3 the alternate advantage no longer rests on a salvage assumption: a custom part gives the same cost.
        custom = run(world('s04-alt-cheaper-10d', part_class='custom'), 10, [('alternate', 8)])['cost']
        self.assertEqual((custom['salvage_credit'], custom['net_cost']), (0, 30))
        # Recovery spend alone ranks alternate (3 a unit) below expedite (4 a unit) on every commit day.
        self.assertLess(run(world('s04-alt-cheaper-10d'), 10, [('alternate', 8)])['cost']['recovery_spend'],
                        run(world('s04-alt-cheaper-10d'), 10, [('expedite', 8)])['cost']['recovery_spend'])


class SurplusConventionTests(unittest.TestCase):
    """UNRESOLVED ASSUMPTION (reviewer has not answered): the base cost of a recovery lot is cost-neutral and
    surplus created by an alternate buy earns no salvage, so buying surplus can never pay for itself."""

    SMALL = dict(orders=[dict(FIX['s04-sudden-5d']['scenario']['orders'][0], quantity=4)])

    def test_a_policy_cannot_profit_from_buying_surplus(self):
        # Worst case for the convention: salvage worth the full base cost (100%), order small enough that the
        # alternate units are pure surplus. Buying them must cost the premium and earn nothing.
        pct = {'standard': 100, 'custom': 100}
        base = run(world('s04-sudden-5d', salvage_pct_by_class=pct, **self.SMALL), 5)['cost']
        for qty in range(1, 9):
            card = run(world('s04-sudden-5d', salvage_pct_by_class=pct, **self.SMALL), 5, [('alternate', qty)])['cost']
            self.assertEqual(card['alternate_spend'], 3 * qty)
            self.assertEqual(card['salvage_credit'], base['salvage_credit'])         # no windfall from the new units
            self.assertEqual(card['uncredited_alternate_surplus'], qty)
            self.assertEqual(card['net_cost'], base['net_cost'] + 3 * qty)           # strictly worse than doing nothing
            self.assertGreater(card['net_cost'], base['net_cost'])

    def test_salvage_never_exceeds_what_maintaining_would_earn_for_any_alternate_quantity(self):
        for fid in FIX:
            f = FIX[fid]
            for pct in (60, 100):
                sc = {'salvage_pct_by_class': {'standard': pct, 'custom': pct}}
                base = run(world(fid, **sc), f['horizon_days'])['cost']['salvage_credit']
                for qty in range(1, 9):
                    got = run(world(fid, **sc), f['horizon_days'], [('alternate', qty)])['cost']['salvage_credit']
                    self.assertLessEqual(got, base, (fid, pct, qty))

    def test_primary_surplus_still_earns_salvage_and_alternate_surplus_does_not(self):
        card = run(world('s04-sudden-5d', **self.SMALL), 5, [('alternate', 8)])['cost']
        # 16 components left: 8 from the primary lot (credited at 60% of USD 10) and 8 presumed alternate (not credited).
        self.assertEqual((card['salvage_eligible_components'], card['uncredited_alternate_surplus'], card['salvage_credit']),
                         (8, 8, 48))

    def test_a_cheaper_alternate_premium_than_expedite_does_not_make_surplus_profitable(self):
        w = world('s04-sudden-5d', **self.SMALL)
        offers = w.observation()['rules']['recovery_offers']
        self.assertLess(offers['alternate']['today']['unit_cost'], offers['expedite']['today']['unit_cost'])
        self.assertIn('no salvage', offers['alternate']['basis'])
        self.assertIn('cost-neutral', offers['alternate']['basis'])


class RecoveryTests(unittest.TestCase):
    def test_partial_expedite_splits_the_lot(self):
        w = world('s04-sudden-5d')
        self.assertTrue(w.choose_recovery('expedite', 3)['accepted'])
        lots = {x['lot_id']: x for x in w.snapshot()['lots']}
        self.assertEqual((lots['primary']['quantity'], lots['primary']['arrival_day']), (5, 4))
        self.assertEqual((lots['exp1']['quantity'], lots['exp1']['arrival_day']), (3, 2))
        self.assertEqual(w.snapshot()['incremental_spend'], 12)

    def test_budget_is_enforced_across_commitments(self):
        w = world('s04-sudden-5d')
        self.assertTrue(w.choose_recovery('expedite', 8)['accepted'])      # 32
        before = w.snapshot()
        for q in (8, 3):                                                   # 32 + 24 and 32 + 9 exceed the budget of 40
            r = w.choose_recovery('alternate', q)
            self.assertEqual((r['accepted'], 'budget' in r['reason']), (False, True))
        self.assertEqual(w.snapshot(), before)
        self.assertTrue(w.choose_recovery('alternate', 2)['accepted'])     # 32 + 6 = 38

    def test_each_commitment_executes_once(self):
        w = world('s04-sudden-5d')
        self.assertTrue(w.choose_recovery('alternate', 2, commit_id='x1')['accepted'])
        before = w.snapshot()
        r = w.choose_recovery('alternate', 2, commit_id='x1')
        self.assertFalse(r['accepted'])
        self.assertIn('duplicate', r['reason'])
        self.assertEqual(w.snapshot(), before)
        self.assertEqual(w.snapshot()['incremental_spend'], 6)
        for _ in range(5):
            day(w)
        receipts = [e for e in w.history() if e['kind'] == 'receipt' and e['details']['lot'] == 'alt1']
        self.assertEqual(len(receipts), 1)

    def test_invalid_recovery_is_rejected_without_mutation(self):
        w = world('s04-sudden-5d')
        before = w.snapshot()
        for args in (('maintain', 1), ('expedite', 0), ('expedite', -1), ('expedite', 1.5), ('expedite', 9),
                     ('alternate', 9), ('buy', 1), ('expedite', None)):
            self.assertFalse(w.choose_recovery(*args)['accepted'], args)
        self.assertEqual(w.snapshot(), before)
        self.assertEqual(sum(1 for e in w.history() if e['kind'] == 'recovery' and not e['accepted']), 8)

    def test_window_closes_and_expedite_needs_a_benefit(self):
        w = world('s04-sudden-5d')
        day(w)
        day(w, 0)  # day 2 closes with nothing released
        r = w.choose_recovery('alternate', 1)  # day 3: no rate-card row
        self.assertFalse(r['accepted'])
        self.assertIn('window', r['reason'])
        # Warned, no delay: on day 2 an expedite would arrive no earlier than the confirmed day 3.
        n = world('s04-warned-no-delay-10d')
        day(n)
        self.assertFalse(n.choose_recovery('expedite', 1)['accepted'])
        self.assertTrue(n.choose_recovery('alternate', 1)['accepted'])

    def test_a_slow_expedite_lane_is_refused_when_it_would_not_beat_the_delayed_arrival(self):
        w = world('s04-alt-cheaper-10d', expedite_card=[[1, 40, 9], [2, 50, 9]])      # no earlier than day 9
        self.assertFalse(w.choose_recovery('expedite', 1)['accepted'])
        self.assertTrue(w.choose_recovery('alternate', 1)['accepted'])

    def test_alternate_supplier_availability_is_cumulative(self):
        w = world('s04-warned-delayed-10d', recovery_budget=400)
        self.assertTrue(w.choose_recovery('alternate', 5)['accepted'])
        self.assertFalse(w.choose_recovery('alternate', 4)['accepted'])
        self.assertTrue(w.choose_recovery('alternate', 3)['accepted'])
        self.assertFalse(w.choose_recovery('alternate', 1)['accepted'])

    def test_production_and_closed_episode_rules(self):
        w = world('s04-sudden-5d')
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
    def test_tier_weights_are_five_to_one(self):
        self.assertEqual({t['tier']: t['weight'] for t in FIX['s04-multitier-cancel-10d']['scenario']['tiers']},
                         {'key': 5, 'standard': 1})

    def test_standard_tier_cancels_six_days_after_its_due_date_while_key_tier_backlogs(self):
        w = world('s04-multitier-cancel-10d')
        for _ in range(10):
            day(w)
        card, s = w.scorecard(), w.snapshot()
        orders = {o['order_id']: o for o in s['orders']}
        self.assertEqual((orders['K1']['status'], orders['K1']['delivered'], orders['K1']['cancelled']), ('complete', 8, 0))
        self.assertEqual((orders['S1']['status'], orders['S1']['delivered'], orders['S1']['cancelled']), ('cancelled', 4, 4))
        by_day = {e['day']: e['details']['cancelled'] for e in w.history() if e['kind'] == 'day_close'}
        self.assertEqual({d: c for d, c in by_day.items() if c}, {9: {'S1': 4}})       # due day 3 + 6, not day 5
        self.assertEqual(card['downstream'], {'cancelled_units': 4, 'cancelled_order_value': 320, 'undelivered_at_end': 0})
        # Penalty is assessed on the cancellation close and never after it.
        close9 = next(e for e in w.history() if e['kind'] == 'day_close' and e['day'] == 9)
        self.assertEqual(close9['state']['penalties'], s['penalties'])
        self.assertEqual((s['penalties'], card['cost']['net_cost']), (67, 67))          # K1 24 + S1 43
        self.assertEqual(card['tier_impact']['priority_weighted_unit_days_late'], 5 * 8 + 1 * 40)

    def test_cancellation_follows_each_orders_own_due_date(self):
        sc = deepcopy(FIX['s04-multitier-cancel-10d']['scenario'])
        sc['orders'][1].update(due_day=4)           # S1 now falls due on day 4: cancel at the close of day 10
        w = OperationalWorldV4(10, scenario=ScenarioV4(**sc))
        for _ in range(10):
            day(w)
        by_day = {e['day']: e['details']['cancelled'] for e in w.history() if e['kind'] == 'day_close'}
        self.assertEqual({d: c for d, c in by_day.items() if c}, {10: {'S1': 4}})

    def test_key_tier_ships_first_when_stock_is_short(self):
        w = world('s04-multitier-cancel-10d')
        w.choose_recovery('expedite', 8)
        for _ in range(3):
            day(w)
        close3 = next(e for e in w.history() if e['kind'] == 'day_close' and e['day'] == 3)
        self.assertEqual(close3['details']['shipments'], {'K1': 8, 'S1': 4})

    def test_tier_blocks_do_not_collapse_into_one_number(self):
        w = world('s04-multitier-cancel-10d')
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
            world('s04-sudden-5d').scorecard()


def strip(obs):
    obs = deepcopy(obs)
    obs['state'].pop('scenario_id')
    return obs


class SignalTests(unittest.TestCase):
    def test_warned_pair_declares_the_same_level_and_differs_only_in_the_hidden_outcome(self):
        a, b = FIX['s04-warned-delayed-10d']['scenario'], FIX['s04-warned-no-delay-10d']['scenario']
        self.assertEqual(a['signal_level'], b['signal_level'])
        self.assertIn(a['signal_level'], ('low', 'medium', 'high'))
        differing = {k for k in a if a[k] != b[k]}
        self.assertEqual(differing, {'scenario_id', 'delay_outcome', 'delayed_arrival_day'})

    def test_observation_streams_are_identical_until_the_firm_notice(self):
        # Same commands in both worlds; compare every observation up to, and excluding, the notice.
        wa, wb = world('s04-warned-delayed-10d'), world('s04-warned-no-delay-10d')
        sa, sb = [strip(wa.observation())], [strip(wb.observation())]
        for w, out in ((wa, sa), (wb, sb)):
            self.assertTrue(w.choose_recovery('expedite', 4)['accepted'])
            out.append(strip(w.observation()))
            self.assertTrue(w.release_production(4)['accepted'])
            out.append(strip(w.observation()))
        self.assertEqual(sa, sb)
        self.assertTrue(all(not o['state']['notices'] for o in sa))
        self.assertEqual(sa[0]['state']['signals'][0]['level'], 'medium')
        wa.close_day()
        wb.close_day()
        self.assertEqual(wa.snapshot()['notices'][0]['kind'], 'delay_confirmed')
        self.assertEqual(wb.snapshot()['notices'][0]['kind'], 'on_time_confirmed')
        self.assertNotEqual(strip(wa.observation()), strip(wb.observation()))

    def test_flipping_only_the_outcome_never_changes_what_is_shown_before_the_notice(self):
        base = deepcopy(FIX['s04-warned-delayed-10d']['scenario'])
        seen = []
        for outcome, arrival in (('delay', 6), ('delay', 9), ('none', None)):
            w = OperationalWorldV4(10, scenario=ScenarioV4(**dict(base, delay_outcome=outcome, delayed_arrival_day=arrival)))
            seen.append(json.dumps(strip(w.observation()), sort_keys=True))
        self.assertEqual(len(set(seen)), 1)

    def test_signal_carries_only_a_qualitative_level(self):
        o = world('s04-warned-delayed-10d').observation()
        sig = o['state']['signals'][0]
        self.assertEqual(set(sig), {'day', 'level', 'text'})
        self.assertEqual(sig['level'], 'medium')
        self.assertNotIn('%', json.dumps(sig))
        self.assertNotIn('hint_pct', json.dumps(o))
        event = next(e for e in world('s04-warned-delayed-10d').history() if e['kind'] == 'signal')
        self.assertEqual(event['details'], {'level': 'medium'})

    def test_signal_text_never_names_an_outcome(self):
        text = json.dumps(world('s04-warned-delayed-10d').observation()).lower()
        for w in ('delay_confirmed', 'revised', 'on_time_confirmed', 'will be delayed'):
            self.assertNotIn(w, text)

    def test_sudden_scenarios_have_no_signal_and_offers_follow_the_alert(self):
        s = world('s04-sudden-5d').observation()
        self.assertEqual(s['state']['signals'], [])
        self.assertIn('recovery_offers', s['rules'])     # the notice is already visible on day 1
        w = world('s04-warned-delayed-10d')
        self.assertIn('recovery_offers', w.observation()['rules'])  # the signal itself opens the rate card

    def test_premature_recovery_before_any_alert_is_rejected(self):
        w = world('s04-sudden-5d', notice_day=2, primary_promised_day=4, delayed_arrival_day=6,
                  expedite_card=[[1, 40, 2], [2, 50, 3], [3, 60, 5]], alternate_card=[[1, 30, 2], [2, 40, 3], [3, 50, 5]])
        r = w.choose_recovery('alternate', 1)
        self.assertFalse(r['accepted'])
        self.assertIn('no disruption alert', r['reason'])
        self.assertNotIn('recovery_offers', w.observation()['rules'])

    def test_snapshots_are_detached(self):
        w = world('s04-sudden-5d')
        snap = w.snapshot()
        snap['component_on_hand'] = 99
        snap['lots'][0]['quantity'] = 99
        w.history()
        self.assertEqual(w.snapshot()['component_on_hand'], 4)
        self.assertEqual(w.snapshot()['lots'][0]['quantity'], 8)


if __name__ == '__main__':
    unittest.main()
