import ast
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import unittest

from supplychainworld import dynamic_verifier as dv
from supplychainworld.baselines import run_baseline
from supplychainworld.dynamic import OperationalWorld, SupplierDelayScenario

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = json.loads((ROOT / 'fixtures/dynamic/supplier-delay-inputs.json').read_text())['fixtures']
HAND = json.loads((ROOT / 'fixtures/dynamic/verifier-hand-ledgers.json').read_text())
LEDGER_KEYS = ('received', 'produced', 'shipped', 'components_close', 'finished_close',
               'delivered_total', 'penalty_total', 'spend_total', 'undelivered_assessed')


def fixture(fid):
    f = next(x for x in FIXTURES if x['fixture_id'] == fid)
    return f['scenario'], f['horizon_days']


def baseline(fid, policy, horizon=None):
    scenario, h = fixture(fid)
    r = run_baseline(OperationalWorld(horizon or h, scenario=SupplierDelayScenario(**scenario)), policy)
    return scenario, horizon or h, r


def verify(scenario, h, r, **kw):
    return dv.verify_episode(scenario, deepcopy(r.history), horizon_days=h, scorecard=deepcopy(r.scorecard), **kw)


def custom_world(fid='s01-five-day'):
    scenario, h = fixture(fid)
    return scenario, h, OperationalWorld(h, scenario=SupplierDelayScenario(**scenario))


def finish(world):
    while world.snapshot()['phase'] != 'complete':
        world.release_production(0)
        world.close_day()


def find(history, kind, nth=0):
    return [e for e in history if e['kind'] == kind][nth]


class HandWorkedLedgerTests(unittest.TestCase):
    def test_verifier_ledger_matches_hand_worked_days_for_every_fixture_and_policy(self):
        for f in FIXTURES:
            for policy in ('maintain', 'expedite', 'alternate'):
                with self.subTest(fixture=f['fixture_id'], policy=policy):
                    scenario, h, r = baseline(f['fixture_id'], policy)
                    rep = verify(scenario, h, r)
                    self.assertTrue(rep.feasible, rep.violations)
                    self.assertTrue(rep.complete)
                    hand = HAND[f['fixture_id']][policy]
                    for key in LEDGER_KEYS:
                        self.assertEqual([row[key] for row in rep.ledger], hand[key], key)
                    self.assertEqual(rep.outcome['comparison_cost'], hand['comparison_cost'])
                    self.assertEqual(rep.metrics['delivered_on_time'], hand['on_time'])
                    self.assertEqual(rep.ignored_self_reports, [])

    def test_events_after_day_five_and_end_of_horizon_are_checked(self):
        scenario, h, r = baseline('s01-fifteen-day-late-events', 'maintain')
        rep = verify(scenario, h, r)
        self.assertEqual((rep.metrics['notice_day'], rep.metrics['primary_receipt_day']), (6, 12))
        self.assertEqual(rep.ledger[-1]['day'], 15)
        # A day-12 receipt claimed on day 11 is premature even though it is past day 5.
        bad = deepcopy(r.history)
        find(bad, 'receipt')['day'] = 11
        rep = dv.verify_episode(scenario, bad, horizon_days=h)
        self.assertFalse(rep.feasible)
        self.assertIn('receipt_timing_or_quantity', rep.codes())
        # Tampering only with the final close (end of horizon) is also caught.
        bad = deepcopy(r.history)
        find(bad, 'episode_complete')['details']['comparison_cost'] = 0
        self.assertIn('ledger_mismatch', dv.verify_episode(scenario, bad, horizon_days=h).codes())
        bad = deepcopy(r.history)
        [e for e in bad if e['kind'] == 'day_close'][-1]['state']['penalties'] = 190
        self.assertIn('ledger_mismatch', dv.verify_episode(scenario, bad, horizon_days=h).codes())


class UnobservedMetricTests(unittest.TestCase):
    def test_short_horizons_report_none_not_zero(self):
        scenario, h, r = baseline('s01-five-day', 'maintain', horizon=2)
        m = verify(scenario, h, r).metrics
        self.assertFalse(m['due_day_observed'])
        self.assertIsNone(m['delivered_on_time'])
        self.assertIsNone(m['primary_receipt_day'])
        self.assertEqual(m['penalty_assessments'], [])
        self.assertEqual(m['delivered_total'], 0)   # observed and genuinely zero
        scenario, h, r = baseline('s01-fifteen-day-late-events', 'maintain', horizon=9)
        rep = verify(scenario, h, r)
        self.assertEqual(rep.metrics['notice_day'], 6)
        self.assertIsNone(rep.metrics['delivered_on_time'])
        self.assertIsNone(rep.metrics['primary_receipt_day'])
        self.assertEqual(rep.outcome['comparison_cost'], 0)  # complete, observed zero cost so far
        self.assertEqual(rep.outcome['service_penalties'], 0)

    def test_incomplete_episode_leaves_outcome_unobserved(self):
        scenario, h, r = baseline('s01-five-day', 'expedite')
        cut = [e for e in r.history if e['day'] <= 2 and e['kind'] != 'episode_complete']
        rep = dv.verify_episode(scenario, cut, horizon_days=h)
        self.assertFalse(rep.complete)
        self.assertIsNone(rep.outcome['comparison_cost'])
        self.assertEqual(rep.metrics['days_closed'], 2)
        # a scorecard for an unfinished episode is rejected
        rep = dv.verify_episode(scenario, cut, horizon_days=h, scorecard=r.scorecard)
        self.assertIn('scorecard_for_incomplete_episode', rep.codes())

    def test_no_disruption_has_no_notice(self):
        cfg = SupplierDelayScenario(disruption_enabled=False)
        r = run_baseline(OperationalWorld(scenario=cfg), 'maintain')
        rep = dv.verify_episode(cfg, r.history, horizon_days=5, scorecard=r.scorecard)
        self.assertTrue(rep.feasible, rep.violations)
        self.assertIsNone(rep.metrics['notice_day'])
        self.assertEqual(rep.metrics['primary_receipt_day'], 2)
        self.assertEqual(rep.outcome['comparison_cost'], 0)


class FeasibleButCostlyTests(unittest.TestCase):
    def test_costlier_alternatives_are_feasible_and_quality_is_separate(self):
        costs = {}
        for policy in ('maintain', 'expedite', 'alternate'):
            scenario, h, r = baseline('s01-five-day', policy)
            rep = verify(scenario, h, r)
            self.assertTrue(rep.feasible, (policy, rep.violations))
            costs[policy] = rep.outcome['comparison_cost']
        self.assertEqual(costs, {'maintain': 120, 'expedite': 24, 'alternate': 40})

    def test_hand_driven_slow_production_is_feasible_but_worse(self):
        scenario, h, w = custom_world()
        w.choose_recovery('expedite')
        for q in (2, 2, 4, 4, 0):
            w.release_production(q)
            w.close_day()
        rep = dv.verify_episode(scenario, w.history(), horizon_days=h, scorecard=w.scorecard())
        self.assertTrue(rep.feasible, rep.violations)
        self.assertEqual(rep.metrics['delivered_total'], 12)
        # Hand work: close day3 ships 8 (4 undelivered x USD10 = 40); day4 ships the last 4.
        self.assertEqual([r['produced'] for r in rep.ledger], [2, 2, 4, 4, 0])
        self.assertEqual([r['shipped'] for r in rep.ledger], [0, 0, 8, 4, 0])
        self.assertEqual([r['undelivered_assessed'] for r in rep.ledger], [None, None, 4, 0, 0])
        self.assertEqual(rep.outcome['comparison_cost'], 24 + 40)  # spend 24 + penalties 40
        self.assertGreater(rep.outcome['comparison_cost'], 24)

    def test_simulator_rejections_are_feasible_and_leave_state_unchanged(self):
        scenario, h, w = custom_world()
        self.assertFalse(w.release_production(9)['accepted'])
        self.assertFalse(w.choose_recovery('bogus')['accepted'])
        w.choose_recovery('maintain')
        self.assertFalse(w.choose_recovery('expedite')['accepted'])
        w.release_production(4)
        self.assertFalse(w.release_production(1)['accepted'])
        w.close_day()
        finish(w)
        rep = dv.verify_episode(scenario, w.history(), horizon_days=h, scorecard=w.scorecard())
        self.assertTrue(rep.feasible, rep.violations)


class AdversarialTests(unittest.TestCase):
    def assert_flags(self, scenario, h, history, code, **kw):
        rep = dv.verify_episode(scenario, history, horizon_days=h, **kw)
        self.assertFalse(rep.feasible)
        self.assertIn(code, rep.codes(), rep.violations)
        return rep

    def test_premature_receipt(self):
        scenario, h, r = baseline('s01-five-day', 'expedite')
        bad = deepcopy(r.history)
        rec = find(bad, 'receipt')
        rec['day'] = 1
        rec['state']['day'] = 1
        self.assert_flags(scenario, h, bad, 'receipt_timing_or_quantity')
        # components appearing in a state before any receipt break conservation too
        bad = deepcopy(r.history)
        first_close = find(bad, 'day_close')
        first_close['state']['component_on_hand'] += 8
        rep = self.assert_flags(scenario, h, bad, 'component_conservation')
        self.assertIn('ledger_mismatch', rep.codes())

    def test_extra_or_missing_receipt(self):
        scenario, h, r = baseline('s01-five-day', 'maintain')
        bad = deepcopy(r.history)
        bad.insert(bad.index(find(bad, 'receipt')) + 1, deepcopy(find(bad, 'receipt')))
        self.assert_flags(scenario, h, bad, 'ledger_mismatch')
        bad = [e for e in r.history if e['kind'] != 'receipt']
        self.assert_flags(scenario, h, bad, 'receipt_timing_or_quantity')

    def test_excess_production_and_production_without_material(self):
        scenario, h, w = custom_world()
        w.choose_recovery('maintain')
        w.release_production(4)           # valid
        self.assertFalse(w.release_production(5)['accepted'])
        w.close_day()
        w.release_production(4)           # day 2: no components, rejected
        w.close_day()
        history = w.history()
        # (a) forge acceptance of over-capacity release on day 1's repeated attempt
        bad = deepcopy(history)
        rejected = next(e for e in bad if e['kind'] == 'release' and not e['accepted'] and e['details']['quantity'] == 5)
        rejected['accepted'] = True
        self.assert_flags(scenario, h, bad, 'duplicate_release')
        # (b) release of 5 as the only release of a day
        scenario2, h2, w2 = custom_world()
        w2.release_production(5)
        bad = w2.history()
        find(bad, 'release')['accepted'] = True
        self.assert_flags(scenario2, h2, bad, 'over_capacity')
        # (c) production without material on day 2
        bad = deepcopy(history)
        no_mat = next(e for e in bad if e['kind'] == 'release' and e['day'] == 2)
        no_mat['accepted'] = True
        self.assertFalse(history[bad.index(no_mat)]['accepted'])
        self.assert_flags(scenario, h, bad, 'insufficient_material')
        # (d) overproduction beyond the 12-unit order
        s3, h3, w3 = custom_world('s01-five-day')
        w3.choose_recovery('alternate')   # leaves spare components, so only the order cap binds
        for _ in range(3):
            w3.release_production(4)
            w3.close_day()
        w3.release_production(4)
        bad = w3.history()
        last = [e for e in bad if e['kind'] == 'release'][-1]
        self.assertFalse(last['accepted'])
        last['accepted'] = True
        self.assert_flags(s3, h3, bad, 'excess_production')

    def test_incorrect_cost(self):
        scenario, h, r = baseline('s01-five-day', 'maintain')
        sc = deepcopy(r.scorecard)
        sc['comparison_cost'] = 100
        self.assert_flags(scenario, h, deepcopy(r.history), 'scorecard_mismatch', scorecard=sc)
        sc = deepcopy(r.scorecard)
        sc['service_penalties'] = 0
        sc['comparison_cost'] = 0
        rep = self.assert_flags(scenario, h, deepcopy(r.history), 'scorecard_mismatch', scorecard=sc)
        self.assertEqual(rep.outcome['comparison_cost'], 120)   # verifier reports its own figure
        bad = deepcopy(r.history)
        find(bad, 'episode_complete')['details']['comparison_cost'] = 24
        self.assert_flags(scenario, h, bad, 'ledger_mismatch')
        # charging for recovery without making a recovery, then under-charging one
        scenario, h, r = baseline('s01-five-day', 'alternate')
        bad = deepcopy(r.history)
        for e in bad:
            if e['state']['incremental_spend'] == 40:
                e['state']['incremental_spend'] = 24
        self.assert_flags(scenario, h, bad, 'ledger_mismatch')

    def test_duplicate_commitment(self):
        scenario, h, w = custom_world()
        w.choose_recovery('expedite')
        self.assertFalse(w.choose_recovery('alternate')['accepted'])
        w.release_production(4)
        w.close_day()
        finish(w)
        bad = w.history()
        dup = next(e for e in bad if e['kind'] == 'recovery' and not e['accepted'])
        dup['accepted'] = True
        dup['state']['incremental_spend'] = 64
        dup['state']['recovery'] = 'alternate'
        self.assert_flags(scenario, h, bad, 'duplicate_commitment')

    def test_premature_late_and_over_budget_recovery(self):
        s = dict(fixture('s01-five-day')[0], recovery_budget=30)
        r = run_baseline(OperationalWorld(5, scenario=SupplierDelayScenario(**s)), 'maintain')
        # fixture budget 30 forbids the alternate (40): forged acceptance is caught
        w = OperationalWorld(5, scenario=SupplierDelayScenario(**s))
        self.assertFalse(w.choose_recovery('alternate')['accepted'])
        finish(w)
        bad = w.history()
        find(bad, 'recovery')['accepted'] = True
        self.assert_flags(s, 5, bad, 'budget_exceeded')
        # late recovery on day 2
        scenario, h, w = custom_world()
        w.release_production(4)
        w.close_day()
        self.assertFalse(w.choose_recovery('expedite')['accepted'])
        finish(w)
        bad = w.history()
        find(bad, 'recovery')['accepted'] = True
        self.assert_flags(scenario, h, bad, 'late_recovery')
        # premature: before the notice event exists (15-day fixture, day 1)
        scenario, h, w = custom_world('s01-fifteen-day-late-events')
        self.assertFalse(w.choose_recovery('expedite')['accepted'])
        finish(w)
        bad = w.history()
        find(bad, 'recovery')['accepted'] = True
        self.assert_flags(scenario, h, bad, 'premature_recovery')
        self.assertTrue(r.scorecard)

    def test_tampering_with_states_events_and_flags(self):
        scenario, h, r = baseline('s01-fifteen-day-late-events', 'expedite')
        mutations = {
            'inventory': lambda hist: find(hist, 'day_close', 8)['state'].__setitem__('component_on_hand', 9),
            'finished': lambda hist: find(hist, 'day_close', 0)['state'].__setitem__('finished_on_hand', 5),
            'shipment': lambda hist: find(hist, 'day_close', 9)['details'].__setitem__('shipped', 13),
            'delivered': lambda hist: find(hist, 'day_close', 9)['state'].__setitem__('delivered_total', 11),
            'deleted_close': lambda hist: hist.remove(find(hist, 'day_close', 3)),
            'forged_notice_day': lambda hist: find(hist, 'notice').__setitem__('day', 3),
            'arrival_rewrite': lambda hist: find(hist, 'recovery')['state'].__setitem__('primary_arrival_day', 7),
            'phase': lambda hist: find(hist, 'day_close', 5)['state'].__setitem__('phase', 'complete'),
        }
        for name, mutate in mutations.items():
            with self.subTest(name):
                bad = deepcopy(r.history)
                mutate(bad)
                rep = dv.verify_episode(scenario, bad, horizon_days=h)
                self.assertFalse(rep.feasible)

    def test_self_reported_pass_status_is_ignored(self):
        scenario, h, r = baseline('s01-five-day', 'maintain')
        bad = deepcopy(r.history)
        find(bad, 'day_close', 2)['state']['penalties'] = 0
        for e in bad:
            e['passed'] = True
        sc = dict(r.scorecard, passed=True, verified=True)
        rep = dv.verify_episode(scenario, bad, horizon_days=h, scorecard=sc)
        self.assertFalse(rep.feasible)
        self.assertEqual(rep.ignored_self_reports, ['passed', 'verified'])
        # and a feasible trace is not made infeasible by false claims
        good = dv.verify_episode(scenario, r.history, horizon_days=h,
                                 scorecard=dict(r.scorecard, passed=False))
        self.assertTrue(good.feasible)

    def test_action_log_must_agree_with_history(self):
        scenario, h, r = baseline('s01-five-day', 'expedite')
        self.assertTrue(verify(scenario, h, r, actions=deepcopy(r.actions)).feasible)
        actions = deepcopy(r.actions)
        next(a for a in actions if a['kind'] == 'recovery')['arguments']['choice'] = 'maintain'
        rep = dv.verify_episode(scenario, r.history, horizon_days=h, actions=actions)
        self.assertIn('action_log_mismatch', rep.codes())

    def test_malformed_input_is_reported_not_trusted(self):
        scenario, h, r = baseline('s01-five-day', 'maintain')
        bad = deepcopy(r.history)
        find(bad, 'release')['accepted'] = 'yes'
        self.assertIn('malformed_event', dv.verify_episode(scenario, bad, horizon_days=h).codes())
        with self.assertRaises(dv.ScenarioError):
            dv.verify_episode(dict(scenario, daily_capacity=-1), r.history, horizon_days=h)
        with self.assertRaises(dv.ScenarioError):
            dv.verify_episode(dict(scenario, surprise=1), r.history, horizon_days=h)
        with self.assertRaises(dv.ScenarioError):
            dv.verify_episode(scenario, r.history, horizon_days=0)


class IndependenceTests(unittest.TestCase):
    def test_verifier_does_not_import_the_simulator(self):
        src = (ROOT / 'src/supplychainworld/dynamic_verifier.py').read_text()
        names = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                names |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                names.add(('.' * node.level) + (node.module or ''))
        self.assertFalse([n for n in names if 'dynamic' in n.replace('dynamic_verifier', '') or 'baselines' in n], names)

    def test_verifier_catches_a_sabotaged_simulator_rule(self):
        # A world whose penalty rule is wrong but which still self-reports a scorecard.
        scenario, h = fixture('s01-five-day')
        w = OperationalWorld(h, scenario=SupplierDelayScenario(**dict(scenario, daily_backlog_penalty=5)))
        r = run_baseline(w, 'maintain')
        rep = dv.verify_episode(scenario, r.history, horizon_days=h, scorecard=r.scorecard)
        self.assertFalse(rep.feasible)
        self.assertEqual(r.scorecard['comparison_cost'], 60)
        self.assertEqual(rep.outcome['comparison_cost'], 120)

    def test_dataclass_scenario_input_equals_mapping_input(self):
        scenario, h, r = baseline('s01-five-day', 'alternate')
        cfg = SupplierDelayScenario(**scenario)
        a = dv.verify_episode(cfg, r.history, horizon_days=h)
        b = dv.verify_episode(scenario, r.history, horizon_days=h)
        self.assertEqual((a.feasible, a.ledger), (b.feasible, b.ledger))
        self.assertEqual(replace(cfg).scenario_id, cfg.scenario_id)


if __name__ == '__main__':
    unittest.main()
