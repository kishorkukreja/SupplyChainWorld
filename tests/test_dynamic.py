import unittest

from supplychainworld.dynamic import OperationalWorld


class OperationalWorldTests(unittest.TestCase):
    def run_policy(self, policy, releases):
        w = OperationalWorld()
        self.assertIn('delayed', w.snapshot()['notices'][0])
        self.assertTrue(w.choose_recovery(policy)['accepted'])
        closes = []
        for quantity in releases:
            self.assertTrue(w.release_production(quantity)['accepted'])
            w.close_day()
            closes.append(next(e['state'] for e in reversed(w.history()) if e['kind'] == 'day_close'))
        return w, closes

    def test_three_policies_match_hand_worked_ledger(self):
        cases = {
            'maintain': ([4, 0, 0, 4, 4], [4, 4, 4, 8, 12], [0, 0, 4, 8, 12], [0, 0, 0, 4, 0], 120),
            'expedite': ([4, 4, 4, 0, 0], [4, 8, 12, 12, 12], [0, 0, 12, 12, 12], [0, 4, 0, 0, 0], 24),
            'alternate': ([4, 4, 4, 0, 0], [4, 8, 12, 12, 12], [0, 0, 12, 12, 12], [0, 4, 0, 8, 8], 40),
        }
        for policy, (releases, produced, delivered, components, total_cost) in cases.items():
            with self.subTest(policy=policy):
                w, closes = self.run_policy(policy, releases)
                self.assertEqual([x['produced_total'] for x in closes], produced)
                self.assertEqual([x['delivered_total'] for x in closes], delivered)
                self.assertEqual([x['component_on_hand'] for x in closes], components)
                self.assertEqual(w.scorecard()['comparison_cost'], total_cost)
                self.assertEqual(w.scorecard()['delivered_on_time'], 4 if policy == 'maintain' else 12)
                self.assertEqual(sum(e['details']['quantity'] for e in w.history() if e['kind'] == 'receipt' and e['details']['order'] == 'primary'), 8)

    def test_invalid_commands_do_not_change_operational_state(self):
        w = OperationalWorld()
        for q in (True, -1, 5, 0.5):
            before = w.snapshot()
            self.assertFalse(w.release_production(q)['accepted'])
            self.assertEqual(w.snapshot(), before)
        self.assertTrue(w.choose_recovery('alternate')['accepted'])
        before = w.snapshot()
        self.assertFalse(w.choose_recovery('expedite')['accepted'])
        self.assertEqual(w.snapshot(), before)
        self.assertTrue(w.release_production(4)['accepted'])
        before = w.snapshot()
        self.assertFalse(w.release_production(1)['accepted'])
        self.assertEqual(w.snapshot(), before)
        self.assertEqual(len([e for e in w.history() if not e['accepted']]), 6)

    def test_late_recovery_and_early_scorecard_rejected(self):
        w = OperationalWorld()
        with self.assertRaises(ValueError):
            w.scorecard()
        w.close_day()
        before = w.snapshot()
        self.assertFalse(w.choose_recovery('expedite')['accepted'])
        self.assertEqual(w.snapshot(), before)

    def test_deterministic_reset_and_detached_observations(self):
        w = OperationalWorld()
        initial = w.snapshot()
        view = w.snapshot()
        view['notices'].append('not real')
        self.assertEqual(w.snapshot(), initial)
        w.choose_recovery('expedite')
        w.release_production(4)
        w.close_day()
        first = w.history()
        w.reset()
        w.choose_recovery('expedite')
        w.release_production(4)
        w.close_day()
        self.assertEqual(w.history(), first)
        first.clear()
        self.assertTrue(w.history())

    def test_completed_episode_cannot_be_advanced_or_acted_upon(self):
        w, _ = self.run_policy('expedite', [4, 4, 4, 0, 0])
        before = w.snapshot()
        self.assertFalse(w.close_day()['accepted'])
        self.assertFalse(w.release_production(0)['accepted'])
        self.assertEqual(w.snapshot(), before)


if __name__ == '__main__':
    unittest.main()
