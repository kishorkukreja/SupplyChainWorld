"""Pinned regressions for the S01 v0.6 checker: defects D2 to D6 and the exact-once weakness F4 are CLOSED in v0.6.

`tests/test_s01_audit_regressions.py::OpenDefectsInTheFrozenV04Verifier` pins that they are still open in the frozen
v0.4 and v0.5 checkers and is not edited. These are the unskipped equivalents for v0.6: each case is the same
tampering or garbage that the old classes (D2 to D6) apply, now run against `dynamic_verifier_v6`, plus the same
cases against the v0.4 and v0.5 checkers as a witness that each test would fail there (so the tests are not vacuous).
They are example-based on purpose (pinned cases); the property and fuzz coverage is in test_s01_v6_property.py and
test_s01_v6_fuzz.py.
"""
import unittest
from copy import deepcopy

import support  # noqa: F401
from support.s01_v6 import V6
from supplychainworld.dynamic_v5 import opaque_label
from supplychainworld.dynamic_verifier_v6 import ScenarioError
from support.s01_versions import V4, V5, scripted_transcript


def relabeled(scenario, **over):
    """A scenario with changed visible parameters needs its own opaque label."""
    s = dict(scenario, **over)
    s['scenario_id'] = opaque_label(s)
    return s


def episode(v, policy_index=0, fixture_index=0):
    fixture = v.fixtures()[fixture_index]
    scenario, horizon = fixture['scenario'], fixture['horizon_days']
    transcript, runner = scripted_transcript(v, scenario, horizon, v.policies[policy_index])
    w = runner._world
    return v.scenario_dict(w), horizon, w.history(), w.scorecard(), v.actions(transcript)


class D2OpeningRecords(unittest.TestCase):
    def test_a_clean_episode_is_feasible(self):
        sd, horizon, history, card, actions = episode(V6)
        self.assertEqual(V6.verify(sd, history, horizon, scorecard=card, actions=actions).violations, [])

    def test_forged_opening_state_is_rejected_and_the_old_checkers_accept_it(self):
        for v, expect in ((V6, True), (V4, False), (V5, False)):
            with self.subTest(version=v.tag):
                sd, horizon, history, card, _ = episode(v)
                for kind in ('day_open', 'opening_before_notice'):
                    forged = deepcopy(history)
                    next(e for e in forged if e['kind'] == kind and e['day'] == 2)['state']['component_on_hand'] += 5
                    self.assertEqual(bool(v.verify(sd, forged, horizon, scorecard=card).violations), expect, kind)

    def test_deleted_duplicated_or_moved_opening_records_are_rejected(self):
        sd, horizon, history, card, _ = episode(V6)
        i = next(k for k, e in enumerate(history) if e['kind'] == 'opening_before_notice' and e['day'] == 2)
        j = next(k for k, e in enumerate(history) if e['kind'] == 'day_open' and e['day'] == 2)
        cases = {}
        m = deepcopy(history)
        del m[i]
        cases['delete opening_before_notice'] = m
        m = deepcopy(history)
        del m[j]
        cases['delete day_open'] = m
        m = deepcopy(history)
        m.insert(i, deepcopy(m[i]))
        cases['duplicate opening_before_notice'] = m
        m = deepcopy(history)
        m.insert(j, deepcopy(m[j]))
        cases['duplicate day_open'] = m
        m = deepcopy(history)
        self.assertEqual(m[j + 1]['kind'], 'release')
        m[j], m[j + 1] = m[j + 1], m[j]
        cases['a release precedes its own opening'] = m
        m = deepcopy(history)
        m[i], m[i + 1] = m[i + 1], m[i]
        cases['swap the two neighbours of the opening'] = m
        for name, mutated in cases.items():
            with self.subTest(case=name):
                self.assertTrue(V6.verify(sd, mutated, horizon, scorecard=card).violations)


class D3FullState(unittest.TestCase):
    FORGERIES = [(['horizon_days'], 99), (['open_demand'], 123), (['orders', 0, 'due_day'], 1), (['orders', 0, 'quantity'], 1),
                 (['orders', 0, 'unit_days_late'], 77), (['orders', 0, 'days_short'], 9), (['orders', 0, 'tier'], 'zzz'),
                 (['scenario_id'], 'scn-00000000'), (['schema_version'], '5.0'), (['runtime_version'], '4.0'),
                 (['lots', 0, 'received'], True), (['commitments'], [{'x': 1}]), (['notices'], []), (['signals'], [{}])]

    def test_every_forged_state_field_is_rejected(self):
        sd, horizon, history, card, _ = episode(V6, fixture_index=1)
        for path, value in self.FORGERIES:
            with self.subTest(field=path):
                forged = deepcopy(history)
                event = next(e for e in forged if e['kind'] == 'day_close' and e['day'] == 2)
                node = event['state']
                for key in path[:-1]:
                    node = node[key]
                if node[path[-1]] == value:
                    self.skipTest('forgery would not change the value for this episode')
                node[path[-1]] = value
                self.assertTrue(V6.verify(sd, forged, horizon, scorecard=card).violations)

    def test_a_missing_extra_or_retyped_state_key_is_rejected(self):
        sd, horizon, history, card, _ = episode(V6)
        i = next(k for k, e in enumerate(history) if e['kind'] == 'day_close' and e['day'] == 2)
        for name, edit in (('missing', lambda s: s.pop('open_demand')), ('extra', lambda s: s.update(secret_plan=1)),
                           ('bool for int', lambda s: s.update(penalties=False if s['penalties'] == 0 else True)),
                           ('float for int', lambda s: s.update(day=float(s['day'])))):
            with self.subTest(case=name):
                forged = deepcopy(history)
                edit(forged[i]['state'])
                self.assertTrue(V6.verify(sd, forged, horizon, scorecard=card).violations)

    def test_the_schema_and_runtime_version_fields_are_compared(self):
        sd, horizon, history, card, _ = episode(V6)
        for field in ('schema_version', 'runtime_version'):
            forged = deepcopy(history)
            forged[0]['state'][field] = '5.0'
            self.assertTrue(V6.verify(sd, forged, horizon, scorecard=card).violations, field)
        card2 = deepcopy(card)
        card2['schema'] = 'dyn-scorecard-4'
        self.assertIn('scorecard_mismatch', V6.verify(sd, history, horizon, scorecard=card2).codes())
        for field in ('schema_version', 'runtime_version'):
            with self.assertRaises(ValueError):
                V6.verify(dict(sd, **{field: '5.0'}), history, horizon)


class D4NonMappingRecords(unittest.TestCase):
    def test_non_mapping_details_and_state_are_reported_not_crashed_on(self):
        sd, horizon, history, card, _ = episode(V6)
        for kind in ('release', 'recovery', 'receipt', 'day_close', 'notice', 'day_open', 'opening_before_notice', 'signal'):
            for bad in ([None], 5, 'x', float('nan'), [1]):
                for section in ('details', 'state'):
                    with self.subTest(kind=kind, section=section, value=repr(bad)):
                        forged = deepcopy(history)
                        i = next((k for k, e in enumerate(forged) if e['kind'] == kind), None)
                        if i is None:
                            continue
                        forged[i][section] = bad
                        self.assertTrue(V6.verify(sd, forged, horizon, scorecard=card).violations)

    def test_the_frozen_checkers_still_crash_on_the_same_input(self):
        for v in (V4, V5):
            sd, horizon, history, card, _ = episode(v)
            crashed = deepcopy(history)
            next(e for e in crashed if e['kind'] == 'release')['details'] = [None]
            with self.assertRaises(AttributeError):
                v.verify(sd, crashed, horizon, scorecard=card)

    def test_the_history_itself_may_be_garbage(self):
        sd, horizon, _, card, _ = episode(V6)
        for junk in (None, 5, 'x', {}, [None, 5, 'x', [1]]):
            self.assertTrue(V6.verify(sd, junk, horizon, scorecard=card).violations, repr(junk))


class D5MalformedScenario(unittest.TestCase):
    JUNK = (('orders', [1, 2]), ('orders', [{}]), ('orders', [{'tier': 'x'}]), ('orders', 'x'), ('tiers', [5]), ('tiers', [{}]),
            ('tiers', [{'tier': 'k'}]), ('tiers', 7), ('expedite_card', [[1, 2, 3], 7]), ('alternate_card', 'x'),
            ('salvage_pct_by_class', [1]), ('opening_components', 'x'), ('scenario_id', 5), ('signal_level', 'zzz'))

    def test_malformed_scenario_parts_raise_scenario_error_only(self):
        sd, horizon, history, _, _ = episode(V6)
        for field, junk in self.JUNK:
            with self.subTest(field=field, junk=repr(junk)):
                scenario = deepcopy(sd)
                scenario[field] = junk
                with self.assertRaises(ScenarioError):
                    V6.verify(scenario, [], horizon)

    def test_the_frozen_checkers_crash_on_some_of_these(self):
        sd, horizon, _, _, _ = episode(V5)
        crashes = 0
        for field, junk in self.JUNK:
            scenario = deepcopy(sd)
            scenario[field] = junk
            try:
                V5.verify(scenario, [], horizon)
            except ValueError:
                pass
            except Exception:  # noqa: BLE001
                crashes += 1
        self.assertGreater(crashes, 0, 'the witness would be vacuous')

    def test_duplicate_ids_and_extra_fields_are_refused(self):
        sd, horizon, _, _, _ = episode(V6, fixture_index=3)
        dup = deepcopy(sd)
        dup['orders'].append(deepcopy(dup['orders'][0]))
        extra = deepcopy(sd)
        extra['orders'][0]['secret'] = 1
        for scenario in (dup, extra):
            with self.assertRaises(ValueError):
                V6.verify(scenario, [], horizon)


class D6MalformedActionLog(unittest.TestCase):
    def test_malformed_action_log_entries_are_reported_not_crashed_on(self):
        sd, horizon, history, card, good = episode(V6)
        for name, mutate in (('string entry', lambda a: a + ['x']), ('number entry', lambda a: a + [5]),
                             ('result is a bool', lambda a: [dict(a[0], result=True)] + a[1:]),
                             ('arguments is a list', lambda a: [dict(a[0], arguments=[1])] + a[1:]),
                             ('not a list', lambda a: 5), ('none inside', lambda a: [None] + a)):
            with self.subTest(case=name):
                report = V6.verify(sd, history, horizon, scorecard=card, actions=mutate(deepcopy(good)))
                self.assertTrue(report.violations)


class ExactOnceWithoutActionId(unittest.TestCase):
    """F4 closed: a commitment sent without an action_id is refused when repeated; the v0.5 behaviour is pinned beside it."""

    CALL = {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite', 'quantity': 1}}

    def runner(self, v):
        scenario, horizon = v.fixtures()[0]['scenario'], v.fixtures()[0]['horizon_days']
        return v.runner(relabeled(scenario, recovery_budget=10 ** 6), horizon)

    def test_v05_executes_the_repeat_and_v06_refuses_it(self):
        v5 = self.runner(V5)
        self.assertTrue(v5.attempt(deepcopy(self.CALL))['accepted'])
        self.assertTrue(v5.attempt(deepcopy(self.CALL))['accepted'], 'the weakness the audit found in v0.5')
        r = self.runner(V6)
        self.assertTrue(r.attempt(deepcopy(self.CALL))['accepted'])
        again = r.attempt(deepcopy(self.CALL))
        self.assertFalse(again['accepted'])
        self.assertIn('duplicate commitment', again['reason'])
        self.assertEqual(len(r._world.snapshot()['commitments']), 1)

    def test_deliberate_identical_lots_need_distinct_ids_and_an_id_first_then_none_is_also_refused(self):
        r = self.runner(V6)
        self.assertTrue(r.attempt(dict(self.CALL, action_id='lot-a'))['accepted'])
        self.assertTrue(r.attempt(dict(self.CALL, action_id='lot-b'))['accepted'])
        self.assertFalse(r.attempt(dict(self.CALL))['accepted'], 'same content, no id, already bought today')
        self.assertFalse(r.attempt(dict(self.CALL, action_id='lot-a'))['accepted'])
        self.assertEqual(len(r._world.snapshot()['commitments']), 2)

    def test_the_same_purchase_on_a_later_day_is_a_new_purchase(self):
        r = self.runner(V6)
        r.attempt(deepcopy(self.CALL))
        r.attempt({'tool': 'advance_day', 'arguments': {}})
        rec = r.attempt(deepcopy(self.CALL))
        if r._world.snapshot()['phase'] == 'action' and rec['reason'] != 'recovery offer window not open, closed or exhausted today':
            self.assertTrue(rec['accepted'])

    def test_the_reserved_prefix_is_refused_as_an_explicit_id(self):
        r = self.runner(V6)
        rec = r.attempt(dict(self.CALL, action_id='auto-deadbeef'))
        self.assertFalse(rec['accepted'])
        self.assertEqual(len(r._world.snapshot()['commitments']), 0)

    def test_the_checker_catches_a_world_that_executed_the_repeat(self):
        r = self.runner(V6)
        r.attempt(deepcopy(self.CALL))
        for _ in range(8):
            r.attempt({'tool': 'advance_day', 'arguments': {}})
        w = r._world
        history = w.history()
        i = next(k for k, e in enumerate(history) if e['kind'] == 'recovery' and e['accepted'])
        forged = deepcopy(history)
        forged.insert(i + 1, deepcopy(forged[i]))
        sd = V6.scenario_dict(w)
        self.assertIn('duplicate_commitment', V6.verify(sd, forged, 5 if w.snapshot()['horizon_days'] == 5 else w.snapshot()['horizon_days']).codes())

    def test_the_commit_tool_definition_states_the_rule(self):
        spec = next(d for d in self.runner(V6).tool_definitions() if d['name'] == 'commit_recovery')
        self.assertIn('distinct action_id', spec['note'])


if __name__ == '__main__':
    unittest.main()
