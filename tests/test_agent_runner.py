import json
from copy import deepcopy
from pathlib import Path
import unittest

from supplychainworld.agent_runner import ObservableRunner, replay, scripted_policy
from supplychainworld.dynamic import OperationalWorld, SupplierDelayScenario

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = {f['fixture_id']: f for f in
            json.loads((ROOT / 'fixtures/dynamic/supplier-delay-inputs.json').read_text())['fixtures']}


def make(fixture_id=None, **kw):
    if fixture_id is None:
        return OperationalWorld()
    f = FIXTURES[fixture_id]
    return OperationalWorld(f['horizon_days'], scenario=SupplierDelayScenario(**f['scenario']))


def scripted(*calls):
    it = iter(calls)
    return lambda view: next(it, None)


class ToolAndClockTests(unittest.TestCase):
    def test_view_exposes_horizon_clock_and_tool_rules(self):
        for fid, horizon in (('s01-five-day', 5), ('s01-fifteen-day-late-events', 15)):
            with self.subTest(fixture=fid):
                r = ObservableRunner(make(fid))
                r._world.reset()
                v = r.view()
                self.assertEqual(v['clock']['horizon_days'], horizon)
                self.assertEqual(v['clock']['current_day'], 1)
                self.assertEqual(v['clock']['days_remaining_after_today'], horizon - 1)
                names = {t['name']: t for t in v['tools']}
                self.assertEqual(set(names), {'read_state', 'read_recovery_offers', 'read_scorecard',
                                              'commit_recovery', 'release_production', 'advance_day'})
                self.assertTrue(names['advance_day']['advances_time'])
                self.assertTrue(names['commit_recovery']['once_only'])

    def test_deadline_visible_only_after_notice_and_enforced(self):
        r = ObservableRunner(make('s01-fifteen-day-late-events'))
        t = r.run(scripted(*[{'tool': 'read_recovery_offers'}, {'tool': 'advance_day'}]))
        self.assertFalse(t['attempts'][0]['result']['data']['available'])
        self.assertIsNone(t['attempts'][0]['view_before']['tools'][3]['deadline_day'])
        # advance to day 6 (notice day, deadline day 6), then miss it by advancing
        calls = [{'tool': 'advance_day'}] * 5 + [{'tool': 'read_recovery_offers'}, {'tool': 'advance_day'},
                                                  {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite'}}]
        t = r.run(scripted(*calls))
        offers = t['attempts'][5]['result']['data']
        self.assertTrue(offers['available'])
        self.assertEqual(offers['offers']['deadline_day'], 6)
        late = t['attempts'][-1]
        self.assertFalse(late['accepted'])
        self.assertEqual(late['category'], 'deadline')
        self.assertEqual(late['state_changes'], {})
        self.assertEqual(late['view_before']['clock']['current_day'], 7)

    def test_read_does_not_advance_or_charge(self):
        r = ObservableRunner(make())
        t = r.run(scripted({'tool': 'read_state'}, {'tool': 'read_state', 'arguments': {'section': 'clock'}},
                           {'tool': 'read_recovery_offers'}))
        self.assertTrue(all(a['accepted'] and a['state_changes'] == {} for a in t['attempts']))
        self.assertEqual(t['final_state']['day'], 1)
        self.assertEqual(t['final_state']['incremental_spend'], 0)
        self.assertEqual(t['status'], 'agent_stopped')

    def test_authority_classes_enforced(self):
        r = ObservableRunner(make(), granted=('read',))
        t = r.run(scripted({'tool': 'read_state'}, {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite'}},
                           {'tool': 'release_production', 'arguments': {'quantity': 4}}, {'tool': 'advance_day'}))
        self.assertEqual([a['category'] for a in t['attempts']], [None, 'authority', 'authority', 'authority'])
        self.assertEqual(t['final_state']['day'], 1)
        self.assertEqual(t['final_state']['incremental_spend'], 0)
        with self.assertRaises(ValueError):
            ObservableRunner(make(), granted=('root',))


class RejectionTests(unittest.TestCase):
    def reject(self, calls, categories, fid=None):
        r = ObservableRunner(make(fid))
        t = r.run(scripted(*calls))
        self.assertEqual([a['category'] for a in t['attempts']], categories)
        for a in t['attempts']:
            if not a['accepted']:
                self.assertEqual(a['state_changes'], {})
                self.assertTrue(all(not e['accepted'] for e in a['events']))
        return t

    def test_hidden_state_leaks_rejected(self):
        probes = [{'tool': 'read_scenario'}, {'tool': 'get_future_events'}, {'tool': 'history'},
                  {'tool': 'read_state', 'arguments': {'section': 'scenario'}},
                  {'tool': 'read_state', 'arguments': {'section': 'future_events'}},
                  {'tool': 'read_state', 'arguments': {'include_hidden_schedule': True}},
                  {'tool': 'reset'}]
        t = self.reject(probes, ['hidden_state'] * len(probes))
        self.assertEqual(t['final_state']['day'], 1)

    def test_views_never_contain_hidden_mechanics(self):
        t = ObservableRunner(make('s01-fifteen-day-late-events')).run(scripted_policy('expedite'))
        dump = json.dumps([a['view_before'] for a in t['attempts'] if a['day'] < 6])
        for leak in ('delayed_arrival_day', 'delay_notice_day', 'expedited_arrival_day', 'Primary PO delayed', 'scenario_config'):
            self.assertNotIn(leak, dump)
        pre = [a['view_before'] for a in t['attempts'] if a['day'] < 6]
        self.assertTrue(all(v['state']['primary_arrival_day'] == 8 and not v['state']['notices'] and
                            'recovery_offers' not in v['rules'] for v in pre))

    def test_invalid_actions_rejected_without_mutation(self):
        calls = [{'tool': 'release_production', 'arguments': {'quantity': q}} for q in (True, -1, 5, 0.5, '4')]
        calls += [{'tool': 'commit_recovery', 'arguments': {'choice': 'bogus'}},
                  {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite', 'extra': 1}},
                  {'tool': 'nonexistent'}, {'tool': 'advance_day', 'arguments': {'x': 1}},
                  {'tool': 'release_production', 'arguments': []}, {'tool': 7}, 'not a dict',
                  {'tool': 'release_production', 'arguments': {'quantity': object()}}]
        cats = ['invalid_action'] * 5 + ['invalid_action', 'invalid_arguments', 'unknown_tool',
                                         'invalid_arguments', 'invalid_arguments', 'unknown_tool',
                                         'unknown_tool', 'invalid_arguments']
        self.reject(calls, cats)

    def test_production_without_material_or_overproduction_rejected(self):
        t = ObservableRunner(make()).run(scripted(
            {'tool': 'release_production', 'arguments': {'quantity': 4}}, {'tool': 'advance_day'},
            {'tool': 'release_production', 'arguments': {'quantity': 1}}))
        self.assertEqual([a['accepted'] for a in t['attempts']], [True, True, False])
        self.assertEqual(t['attempts'][2]['reason'], 'capacity or available material exceeded')
        self.assertEqual(t['final_state']['component_on_hand'], 0)

    def test_repeated_commitments_rejected_no_duplicate_charge(self):
        t = self.reject([{'tool': 'commit_recovery', 'arguments': {'choice': 'alternate'}},
                         {'tool': 'commit_recovery', 'arguments': {'choice': 'alternate'}},
                         {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite'}},
                         {'tool': 'release_production', 'arguments': {'quantity': 4}},
                         {'tool': 'release_production', 'arguments': {'quantity': 4}}],
                        [None, 'repeated_commitment', 'repeated_commitment', None, 'repeated_commitment'])
        self.assertEqual(t['final_state']['incremental_spend'], 40)

    def test_reused_action_id_rejected(self):
        t = self.reject([{'tool': 'release_production', 'arguments': {'quantity': 2}, 'action_id': 'a1'},
                         {'tool': 'release_production', 'arguments': {'quantity': 2}, 'action_id': 'a1'},
                         {'tool': 'read_state', 'action_id': 'a1'},
                         {'tool': 'read_state', 'action_id': ''}],
                        [None, 'repeated_commitment', 'repeated_commitment', 'invalid_arguments'])
        self.assertEqual(t['final_state']['scheduled_production'], 2)

    def test_over_budget_recovery_rejected(self):
        w = OperationalWorld(scenario=SupplierDelayScenario(recovery_budget=30))
        t = ObservableRunner(w).run(scripted({'tool': 'commit_recovery', 'arguments': {'choice': 'alternate'}},
                                             {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite'}}))
        self.assertEqual(t['attempts'][0]['reason'], 'recovery budget exceeded')
        self.assertTrue(t['attempts'][1]['accepted'])

    def test_scorecard_unavailable_until_complete(self):
        t = self.reject([{'tool': 'read_scorecard'}], ['unavailable'])
        self.assertIsNone(t['scorecard'])

    def test_premature_or_closed_actions_rejected(self):
        r = ObservableRunner(make())
        t = r.run(scripted_policy('expedite'))
        self.assertEqual(t['status'], 'complete')
        self.assertEqual(r.attempt({'tool': 'advance_day'})['accepted'], False)
        self.assertFalse(r.attempt({'tool': 'release_production', 'arguments': {'quantity': 0}})['accepted'])
        self.assertTrue(r.attempt({'tool': 'read_scorecard'})['accepted'])

    def test_per_day_attempt_limit(self):
        r = ObservableRunner(make(), max_attempts_per_day=3)
        t = r.run(scripted(*[{'tool': 'read_state'}] * 4 + [{'tool': 'advance_day'}]))
        self.assertEqual([a['category'] for a in t['attempts']], [None] * 3 + ['attempt_limit', None])
        self.assertEqual(t['final_state']['day'], 2)
        with self.assertRaises(ValueError):
            ObservableRunner(make(), max_attempts_per_day=0)

    def test_total_attempt_budget_stops_runaway_agent(self):
        t = ObservableRunner(make(), max_total_attempts=5, max_attempts_per_day=50).run(lambda v: {'tool': 'read_state'})
        self.assertEqual(t['status'], 'attempt_budget_exhausted')
        self.assertEqual(len(t['attempts']), 5)


class EpisodeTests(unittest.TestCase):
    def test_scripted_policies_match_known_ledgers_on_5_and_15_days(self):
        expected = {'maintain': 120, 'expedite': 24, 'alternate': 40}
        expected15 = {'maintain': 200, 'expedite': 24, 'alternate': 40}
        for fid, costs, horizon in (('s01-five-day', expected, 5), ('s01-fifteen-day-late-events', expected15, 15)):
            for policy, cost in costs.items():
                with self.subTest(fixture=fid, policy=policy):
                    t = ObservableRunner(make(fid)).run(scripted_policy(policy))
                    self.assertEqual(t['status'], 'complete')
                    self.assertEqual(t['scorecard']['comparison_cost'], cost)
                    advances = [a for a in t['attempts'] if a['tool'] == 'advance_day']
                    self.assertEqual([a['day'] for a in advances], list(range(1, horizon + 1)))
                    self.assertTrue(all(a['accepted'] for a in t['attempts']))

    def test_transcript_is_chronological_with_outcomes_and_state_changes(self):
        t = ObservableRunner(make()).run(scripted_policy('expedite'))
        self.assertEqual([a['seq'] for a in t['attempts']], list(range(1, len(t['attempts']) + 1)))
        days = [a['day'] for a in t['attempts']]
        self.assertEqual(days, sorted(days))
        rec = t['attempts'][0]
        self.assertEqual(rec['tool'], 'commit_recovery')
        self.assertEqual(rec['state_changes']['incremental_spend'], [0, 24])
        self.assertEqual(rec['state_changes']['primary_arrival_day'], [4, 2])
        self.assertTrue(any(e['kind'] == 'notice' for e in t['initial']['events']))
        self.assertIn('Primary PO delayed', t['initial']['view']['state']['notices'][0])
        day2_open = next(a for a in t['attempts'] if a['tool'] == 'advance_day' and a['day'] == 1)
        self.assertIn('receipt', [e['kind'] for e in day2_open['events']])
        self.assertEqual(day2_open['state_changes']['component_on_hand'], [4, 8])

    def test_recovery_changes_actual_future_events(self):
        receipts = {}
        for policy in ('maintain', 'expedite', 'alternate'):
            t = ObservableRunner(make()).run(scripted_policy(policy))
            receipts[policy] = sorted((e['day'], e['details']['order']) for a in t['attempts']
                                      for e in a['events'] if e['kind'] == 'receipt')
        self.assertEqual(receipts['maintain'], [(4, 'primary')])
        self.assertEqual(receipts['expedite'], [(2, 'primary')])
        self.assertEqual(receipts['alternate'], [(2, 'alternate'), (4, 'primary')])
        # Same agent view before the decision, different realized future after it.
        t15 = ObservableRunner(make('s01-fifteen-day-late-events')).run(scripted_policy('expedite'))
        days = [e['day'] for a in t15['attempts'] for e in a['events'] if e['kind'] == 'receipt']
        self.assertEqual(days, [8])

    def test_replay_reproduces_complete_interaction(self):
        for fid in (None, 's01-fifteen-day-late-events'):
            for policy in ('maintain', 'alternate'):
                with self.subTest(fixture=fid, policy=policy):
                    t = ObservableRunner(make(fid)).run(scripted_policy(policy))
                    wire = json.loads(json.dumps(t))
                    ok, diffs = replay(wire, lambda: make(fid))
                    self.assertTrue(ok, diffs)

    def test_replay_includes_rejections_and_detects_tampering(self):
        calls = [{'tool': 'read_scenario'}, {'tool': 'release_production', 'arguments': {'quantity': 9}},
                 {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite'}},
                 {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite'}},
                 {'tool': 'release_production', 'arguments': {'quantity': 4}}]
        t = ObservableRunner(make()).run(scripted(*calls))
        self.assertTrue(replay(t, make)[0])
        bad = deepcopy(t)
        bad['attempts'][2]['arguments']['choice'] = 'alternate'
        ok, diffs = replay(bad, make)
        self.assertFalse(ok)
        self.assertTrue(diffs)
        bad = deepcopy(t)
        bad['scorecard'] = {'comparison_cost': 0}
        self.assertFalse(replay(bad, make)[0])
        with self.assertRaises(ValueError):
            replay({'schema': 'other'}, make)

    def test_agent_failure_history_preserved_and_replays(self):
        n = {'i': 0}

        def flaky(view):
            n['i'] += 1
            if n['i'] == 4:
                raise RuntimeError('model call failed')
            return scripted_policy('expedite')(view)

        t = ObservableRunner(make()).run(flaky)
        self.assertEqual(t['status'], 'agent_error')
        self.assertEqual(t['attempts'][-1]['category'], 'agent_error')
        self.assertIn('RuntimeError: model call failed', t['attempts'][-1]['reason'])
        self.assertEqual(len(t['attempts']), 4)
        self.assertEqual(t['attempts'][0]['state_changes']['incremental_spend'], [0, 24])
        self.assertIsNone(t['scorecard'])
        self.assertTrue(replay(t, make)[0])

    def test_failed_episode_with_rejections_keeps_rejected_attempts(self):
        def agent(view):
            if view['state']['day'] == 1:
                return {'tool': 'release_production', 'arguments': {'quantity': 99}}
            return None
        t = ObservableRunner(make(), max_total_attempts=3).run(lambda v: {'tool': 'release_production', 'arguments': {'quantity': 99}})
        self.assertEqual(t['status'], 'attempt_budget_exhausted')
        self.assertEqual([a['accepted'] for a in t['attempts']], [False] * 3)

    def test_agent_view_is_detached_from_world(self):
        r = ObservableRunner(make())
        r._world.reset()
        v = r.view()
        v['state']['notices'].append('forged')
        v['rules']['required'] = 0
        self.assertNotIn('forged', r.view()['state']['notices'])
        self.assertEqual(r.view()['rules']['required'], 12)
        def tamper(view):
            view['state']['component_on_hand'] = 999
            return None
        r.run(tamper)
        self.assertEqual(r._world.snapshot()['component_on_hand'], 4)

    def test_constructor_validation(self):
        with self.assertRaises(TypeError):
            ObservableRunner(object())
        with self.assertRaises(ValueError):
            scripted_policy('bogus')


if __name__ == '__main__':
    unittest.main()
