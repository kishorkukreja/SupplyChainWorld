"""Pinned regressions for defects found by the S01 audit (evidence/s01-audit/results.md).

Each test was written to FAIL on the code as found, then the code was fixed minimally.
These are example-based on purpose: they pin the exact case a property or fuzz test found.
"""
import unittest

import support  # noqa: F401
from copy import deepcopy

from support.s01_versions import VERSIONS, V1, V2, fixture_scenario, scripted_transcript


class D1VerifierV02RejectsFreeRateCardRow(unittest.TestCase):
    """D1: the v0.2 simulator accepts a rate-card unit cost of 0 but the v0.2 independent verifier
    refused the same scenario with ScenarioError, so a valid episode could not be verified."""

    def test_zero_unit_cost_scenario_that_the_simulator_runs_is_verifiable(self):
        scenario = dict(
            scenario_id='gen-v2', opening_components=0, daily_capacity=1, primary_quantity=0, primary_promised_day=2,
            signal_day=None, signal_hint_pct=None, notice_day=1, delay_outcome='none', delayed_arrival_day=None,
            expedite_curve=[[1, 0, 2]], alternate_curve=[[1, 0, 2]], alternate_max_units=0, recovery_budget=0,
            salvage_per_component=0, tiers=[{'tier': 'gold', 'weight': 1, 'on_shortfall': 'backlog', 'cancel_day': None}],
            orders=[{'order_id': 'O0', 'tier': 'gold', 'quantity': 1, 'due_day': 1, 'unit_value': 0,
                     'penalty_type': 'percent_of_value', 'penalty_rate': 0}])
        runner = V2.runner(scenario, 1)
        runner.run(V2.scripted('maintain'))
        world = runner._world
        report = V2.verify(V2.scenario_dict(world), world.history(), 1, scorecard=world.scorecard())
        self.assertEqual(report.violations, [])


class D2VerifiersIgnoreOpeningEvents(unittest.TestCase):
    """D2: every verifier skipped the `day_open` and `opening_before_notice` records entirely, so a forged
    opening state (which the published state-ledger files are built from) or a deleted/duplicated opening record
    passed as feasible. Found by the history-mutation property tests (evidence/s01-audit/mutation-fuzz-summary.md)."""

    def episode(self, tag):
        v = VERSIONS[tag]
        fixture = v.fixtures()[0]
        scenario, horizon = fixture['scenario'], fixture['horizon_days']
        transcript, runner = scripted_transcript(v, scenario, horizon, v.policies[0])
        world = runner._world
        return v, v.scenario_dict(world), horizon, world.history(), world.scorecard()

    def test_forged_opening_state_is_rejected(self):
        for tag in VERSIONS:
            with self.subTest(version=tag):
                v, scenario, horizon, history, card = self.episode(tag)
                self.assertEqual(v.verify(scenario, history, horizon, scorecard=card).violations, [])
                forged = deepcopy(history)
                opening = next(e for e in forged if e['kind'] == 'day_open' and e['day'] == 2)
                opening['state']['component_on_hand'] += 5
                self.assertTrue(v.verify(scenario, forged, horizon, scorecard=card).violations,
                                'forged day_open state accepted')

    def test_deleted_or_duplicated_opening_records_are_rejected(self):
        for tag in VERSIONS:
            for op in ('delete', 'duplicate'):
                with self.subTest(version=tag, op=op):
                    v, scenario, horizon, history, card = self.episode(tag)
                    mutated = deepcopy(history)
                    i = next(k for k, e in enumerate(mutated) if e['kind'] == 'opening_before_notice' and e['day'] == 2)
                    if op == 'delete':
                        del mutated[i]
                    else:
                        mutated.insert(i, deepcopy(mutated[i]))
                    self.assertTrue(v.verify(scenario, mutated, horizon, scorecard=card).violations)

    def test_reordering_an_opening_record_across_a_close_is_rejected(self):
        for tag in VERSIONS:
            with self.subTest(version=tag):
                v, scenario, horizon, history, card = self.episode(tag)
                mutated = deepcopy(history)
                i = next(k for k, e in enumerate(mutated) if e['kind'] == 'day_open' and e['day'] == 2)
                self.assertEqual(mutated[i + 1]['kind'], 'release')
                mutated[i], mutated[i + 1] = mutated[i + 1], mutated[i]       # a release now precedes its own opening
                self.assertTrue(v.verify(scenario, mutated, horizon, scorecard=card).violations)


class D3VerifiersSkipPartOfTheClaimedState(unittest.TestCase):
    """D3: the verifiers compared only a subset of each claimed state. Forging horizon_days, open_demand, an
    order's quantity/due_day/unit_days_late/days_short (v0.2 to v0.4) or horizon_days/notices (v0.1) in a recorded
    state passed as feasible."""

    FORGERIES = {
        'v0.1': [(['horizon_days'], 99), (['notices'], [])],
        'v0.2': [(['horizon_days'], 99), (['open_demand'], 123), (['orders', 0, 'due_day'], 1),
                 (['orders', 0, 'quantity'], 1), (['orders', 0, 'unit_days_late'], 77), (['orders', 0, 'days_short'], 9)],
    }
    FORGERIES['v0.3'] = FORGERIES['v0.4'] = FORGERIES['v0.2']

    def test_forged_state_fields_are_rejected(self):
        for tag, forgeries in self.FORGERIES.items():
            v = VERSIONS[tag]
            fixture = v.fixtures()[0]
            scenario, horizon = fixture['scenario'], fixture['horizon_days']
            _, runner = scripted_transcript(v, scenario, horizon, v.policies[0])
            world = runner._world
            history, card = world.history(), world.scorecard()
            for path, value in forgeries:
                with self.subTest(version=tag, field=path):
                    forged = deepcopy(history)
                    event = next(e for e in forged if e['kind'] == 'day_close' and e['day'] == 2)
                    node = event['state']
                    for key in path[:-1]:
                        node = node[key]
                    self.assertNotEqual(node[path[-1]], value, 'forgery must change the value')
                    node[path[-1]] = value
                    self.assertTrue(v.verify(v.scenario_dict(world), forged, horizon, scorecard=card).violations)


class D4VerifiersCrashOnNonMappingEventDetails(unittest.TestCase):
    """D4: a recorded event whose `details` is a list, string or number made every verifier die with
    AttributeError ('... object has no attribute get') instead of reporting a malformed record."""

    def test_non_mapping_details_are_reported_not_crashed_on(self):
        for tag, v in VERSIONS.items():
            fixture = v.fixtures()[0]
            scenario, horizon = fixture['scenario'], fixture['horizon_days']
            _, runner = scripted_transcript(v, scenario, horizon, v.policies[0])
            world = runner._world
            history, card = world.history(), world.scorecard()
            for kind in ('release', 'recovery', 'receipt', 'day_close', 'notice'):
                for bad in ([None], 5, 'x'):
                    with self.subTest(version=tag, kind=kind, details=bad):
                        forged = deepcopy(history)
                        i = next((k for k, e in enumerate(forged) if e['kind'] == kind), None)
                        if i is None:
                            continue
                        forged[i]['details'] = bad
                        report = v.verify(v.scenario_dict(world), forged, horizon, scorecard=card)
                        self.assertTrue(report.violations)

    def test_non_mapping_state_is_reported_not_crashed_on(self):
        for tag, v in VERSIONS.items():
            fixture = v.fixtures()[0]
            scenario, horizon = fixture['scenario'], fixture['horizon_days']
            _, runner = scripted_transcript(v, scenario, horizon, v.policies[0])
            world = runner._world
            history, card = world.history(), world.scorecard()
            for kind in ('release', 'recovery', 'receipt', 'day_close', 'notice'):
                for bad in (float('nan'), 5, 'x', [1]):
                    with self.subTest(version=tag, kind=kind, state=bad):
                        forged = deepcopy(history)
                        i = next((k for k, e in enumerate(forged) if e['kind'] == kind), None)
                        if i is None:
                            continue
                        forged[i]['state'] = bad
                        self.assertTrue(v.verify(v.scenario_dict(world), forged, horizon, scorecard=card).violations)


class D5VerifiersCrashOnMalformedScenarioParts(unittest.TestCase):
    """D5: a scenario whose `orders` or `tiers` hold non-mappings (or whose entries lack fields) made the v0.2 to
    v0.4 verifiers raise TypeError, KeyError or AttributeError instead of the documented ScenarioError."""

    def test_malformed_scenario_parts_raise_scenario_error_only(self):
        for tag in ('v0.2', 'v0.3', 'v0.4'):
            v = VERSIONS[tag]
            fixture = v.fixtures()[0]
            base, horizon = fixture['scenario'], fixture['horizon_days']
            for field, junk in (('orders', [1, 2]), ('orders', [{}]), ('orders', [{'tier': 'x'}]), ('tiers', [5]),
                                ('tiers', [{}]), ('tiers', [{'tier': 'k'}]), ('expedite_curve' if tag == 'v0.2' else 'expedite_card', [[1, 2, 3], 7])):
                with self.subTest(version=tag, field=field, junk=junk):
                    scenario = deepcopy(base)
                    scenario[field] = junk
                    try:
                        v.verify(scenario, [], horizon)
                    except ValueError:
                        pass          # ScenarioError is a ValueError: the documented clean refusal


class D6VerifiersCrashOnMalformedActionLog(unittest.TestCase):
    """D6: a claimed action log with a non-mapping entry (or a non-mapping `result` or `arguments`) made every
    verifier raise AttributeError instead of reporting a malformed record."""

    def test_malformed_action_log_entries_are_reported_not_crashed_on(self):
        for tag, v in VERSIONS.items():
            fixture = v.fixtures()[0]
            scenario, horizon = fixture['scenario'], fixture['horizon_days']
            transcript, runner = scripted_transcript(v, scenario, horizon, v.policies[0])
            world = runner._world
            good = v.actions(transcript)
            for name, mutate in (('string entry', lambda a: a + ['x']), ('number entry', lambda a: a + [5]),
                                 ('result is a bool', lambda a: [dict(a[0], result=True)] + a[1:]),
                                 ('arguments is a list', lambda a: [dict(a[0], arguments=[1])] + a[1:])):
                with self.subTest(version=tag, case=name):
                    report = v.verify(v.scenario_dict(world), world.history(), horizon, scorecard=world.scorecard(),
                                      actions=mutate(deepcopy(good)))
                    self.assertTrue(report.violations)


class D7V01ScriptedPolicyStallsWhenTheRecoveryIsUnaffordable(unittest.TestCase):
    """D7: the v0.1 scripted `expedite` and `alternate` policies re-sent a refused recovery forever, so with a budget
    below the price the episode never left day 1 and ended as `attempt_budget_exhausted` after 500 calls.
    (v0.2 to v0.4 scripted policies already stop after one refusal.)"""

    def test_an_unaffordable_recovery_is_tried_once_and_the_episode_still_completes(self):
        scenario, horizon = fixture_scenario(V1, V1.fixtures()[0])
        scenario = dict(scenario, recovery_budget=10)          # expedite costs 24, alternate 40
        for policy in ('expedite', 'alternate'):
            with self.subTest(policy=policy):
                runner = V1.runner(scenario, horizon)
                transcript = runner.run(V1.scripted(policy))
                self.assertEqual(transcript['status'], 'complete')
                refused = [a for a in transcript['attempts'] if a['tool'] == 'commit_recovery']
                self.assertEqual(len(refused), 1)
                self.assertFalse(refused[0]['accepted'])


if __name__ == '__main__':
    unittest.main()
