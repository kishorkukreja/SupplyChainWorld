import json
from dataclasses import replace
from pathlib import Path
import unittest

from supplychainworld.baselines import run_baseline
from supplychainworld.dynamic import OperationalWorld, SupplierDelayScenario

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = json.loads((ROOT / 'fixtures/dynamic/supplier-delay-inputs.json').read_text())['fixtures']
EXPECTED = json.loads((ROOT / 'fixtures/dynamic/supplier-delay-expected.json').read_text())['fixtures']


class ScenarioFixtureTests(unittest.TestCase):
    def test_policy_ledgers_and_actual_event_days(self):
        for fixture in FIXTURES:
            cfg = SupplierDelayScenario(**fixture['scenario'])
            truth = EXPECTED[fixture['fixture_id']]
            initial = None
            for name in ('maintain', 'expedite', 'alternate'):
                with self.subTest(fixture=fixture['fixture_id'], policy=name):
                    result = run_baseline(OperationalWorld(fixture['horizon_days'], scenario=cfg), name)
                    if initial is None:
                        initial = result.observations[0]
                    self.assertEqual(initial, result.observations[0])
                    events = result.history
                    close = [e for e in events if e['kind'] == 'day_close']
                    actual = truth['policies'][name]
                    self.assertEqual([e['details']['produced'] for e in close], actual['production'])
                    self.assertEqual([e['details']['shipped'] for e in close], actual['shipments'])
                    self.assertEqual([e['state']['component_on_hand'] for e in close], actual['components'])
                    self.assertEqual([cfg.order_quantity - e['state']['delivered_total'] for e in close if e['day'] >= cfg.order_due_day], actual['backlog_on_assessment'])
                    self.assertEqual(result.scorecard, {'delivered_on_time':actual['on_time'], 'delivered_total':actual['delivered'], 'ending_components':actual['components'][-1], 'incremental_spend':actual['spend'], 'service_penalties':actual['penalties'], 'comparison_cost':actual['cost']})
                    self.assertEqual([e['day'] for e in events if e['kind'] == 'notice'], [truth['event_days']['notice']])
                    receipt_days = {e['details']['order']: e['day'] for e in events if e['kind'] == 'receipt'}
                    self.assertEqual(receipt_days['primary'], truth['event_days'][name + '_primary_receipt'])
                    self.assertEqual(receipt_days.get('alternate'), truth['event_days']['alternate_receipt'] if name == 'alternate' else None)
                    self.assertEqual([a['day'] for a in result.actions if a['kind'] == 'recovery'], [truth['event_days']['notice']])
                    self.assertEqual(len(close), fixture['horizon_days'])
                    self.assertTrue(all(a['result']['accepted'] for a in result.actions))

    def test_no_disruption_normal_operations(self):
        cfg = SupplierDelayScenario(disruption_enabled=False)
        result = run_baseline(OperationalWorld(scenario=cfg), 'maintain')
        self.assertFalse(any(e['kind'] == 'notice' for e in result.history))
        self.assertFalse(any(a['kind'] == 'recovery' for a in result.actions))
        self.assertEqual([e['day'] for e in result.history if e['kind'] == 'receipt'], [2])
        self.assertEqual(result.scorecard['delivered_on_time'], 12)
        self.assertEqual(result.scorecard['comparison_cost'], 0)

    def test_no_hidden_future_notice_or_policy_oracle(self):
        base = SupplierDelayScenario(scenario_id='identical', delay_notice_day=6,
            initially_promised_day=8, delayed_arrival_day=12, recovery_deadline_day=6,
            expedited_arrival_day=8, alternate_arrival_day=8, order_due_day=10)
        other = replace(base, delayed_arrival_day=14)
        a, b = OperationalWorld(15, scenario=base), OperationalWorld(15, scenario=other)
        for day in range(1, 6):
            self.assertEqual(a.observation(), b.observation())
            obs = a.observation()
            self.assertNotIn('recovery_offers', obs['rules'])
            self.assertEqual(obs['state']['primary_arrival_day'], 8)
            self.assertNotIn('expected', json.dumps(obs))
            self.assertFalse(a.choose_recovery('expedite')['accepted'])
            a.close_day(); b.close_day()
        self.assertNotEqual(a.observation(), b.observation())
        self.assertEqual(a.observation()['state']['primary_arrival_day'], 12)
        self.assertEqual(b.observation()['state']['primary_arrival_day'], 14)

    def test_versions_validation_and_initial_opening(self):
        for kwargs in ({'schema_version':'2.0'}, {'runtime_version':'2.0'},
                       {'disruption_enabled':'true'}, {'delay_notice_day': 2},
                       {'order_due_day': 0}, {'opening_components': True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                SupplierDelayScenario(**kwargs)
        w = OperationalWorld()
        self.assertEqual(w.snapshot()['schema_version'], '1.0')
        self.assertEqual(w.snapshot()['runtime_version'], '1.0')
        opening = next(e for e in w.history() if e['kind'] == 'opening_before_notice')
        self.assertEqual(opening['day'], 1)
        self.assertEqual(opening['state']['primary_arrival_day'], 2)
        self.assertEqual(opening['state']['notices'], [])
        self.assertEqual(w.snapshot()['primary_arrival_day'], 4)

    def test_reproducible_full_trace(self):
        cfg = SupplierDelayScenario(delay_notice_day=6, initially_promised_day=8,
            delayed_arrival_day=12, recovery_deadline_day=6, expedited_arrival_day=8,
            alternate_arrival_day=8, order_due_day=10)
        a = run_baseline(OperationalWorld(15, scenario=cfg), 'alternate')
        b = run_baseline(OperationalWorld(15, scenario=cfg), 'alternate')
        self.assertEqual(a, b)


if __name__ == '__main__':
    unittest.main()
