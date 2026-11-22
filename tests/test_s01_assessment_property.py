"""S01.3 special assessment: do the tool observations let an agent assess production and delivery exposure?

The scenario map (section 4) says a scripted baseline does not prove S01.3. These tests ask the question
directly. At every decision point (the opening view of any day) an assessor that sees ONLY the agent-visible view
(`support/s01_assess.py`) computes, for each recovery option, the units at risk, the earliest feasible delivery
day and the penalties. The ground truth is the episode actually executed through the runner under that option
and re-derived by the independent verifier from the commands (never the simulator's own numbers).

Findings these tests pin (details in evidence/s01-audit/s01-3-assessment.md):
* v0.2 to v0.4: every quantity is observable and, once the firm notice is visible (or the disruption turns out
  not to happen), the assessment equals the verifier's ground truth over generated scenarios. Before a firm
  notice of a real delay, the visible information can only bound the exposure (optimistic and worst case).
* v0.1: the primary PO quantity is not in any observation, so two scenarios that differ only in it look identical
  until the receipt but have different outcomes. The observations are insufficient for exact assessment.
* Several rules an assessor needs (same-day receipt use, shipping start, penalty units) are not stated in any
  observation; wrong guesses give wrong answers (witness tests below).
"""
import unittest
from copy import deepcopy

from hypothesis import assume, given, settings, strategies as st

import support  # noqa: F401
from support.s01_assess import Conventions, V2_CONVENTIONS, V34_CONVENTIONS, assess, option_call
from support.s01_versions import V1, V2, V3, V4, V5, fixture_scenario, greedy_release, v1_scenarios

STATS = {}
OPTIONS = ('maintain', 'expedite_max', 'alternate_max')
CONV = {'v0.2': V2_CONVENTIONS, 'v0.3': V34_CONVENTIONS, 'v0.4': V34_CONVENTIONS, 'v0.5': V34_CONVENTIONS}


_CACHE = {}


def counterfactual(v, scenario, horizon, day, option):
    key = (v.tag, repr(sorted(scenario.items())), horizon, day, option)
    if key not in _CACHE:
        _CACHE[key] = _counterfactual(v, scenario, horizon, day, option)
    return deepcopy(_CACHE[key][0]), _CACHE[key][1]


def _counterfactual(v, scenario, horizon, day, option):
    """Execute the episode through the runner, taking `option` on `day`, then verify it independently.

    Returns (decision_view, verifier_report). Production is the greedy rule in every run.
    """
    runner = v.runner(scenario, horizon)
    box, done = {}, {'committed': False}

    def agent(view):
        today = view['state']['day']
        if today == day and 'view' not in box:
            box['view'] = deepcopy(view)
        if today == day and not done['committed']:
            done['committed'] = True
            call = option_call(box['view'], option)
            if call:
                return call
        if view['state']['scheduled_production'] is None:
            return {'tool': 'release_production', 'arguments': {'quantity': greedy_release(view)}}
        return {'tool': 'advance_day', 'arguments': {}}

    transcript = runner.run(agent)
    assert transcript['status'] == 'complete'
    world = runner._world
    report = v.verify(v.scenario_dict(world), world.history(), horizon, scorecard=world.scorecard(),
                      actions=v.actions(transcript))
    assert report.violations == [], report.violations
    return box['view'], report


def truth(report):
    card = report.scorecard
    orders = card['service']['orders']
    total = sum(o['ordered'] for o in orders)
    return {'shortfall_by_order': {o['order_id']: o['ordered'] - o['on_time_units'] for o in orders},
            'units_at_risk': sum(o['ordered'] - o['on_time_units'] for o in orders),
            'earliest_feasible_delivery': next((r['day'] for r in report.ledger
                                                if r['delivered_total'] + r['cancelled_total'] == total), None),
            'penalties': card['cost']['service_penalties'], 'recovery_spend': card['cost']['recovery_spend']}


def agent_only(view):
    """What an agent is given: nothing but clock, state, rules and tool definitions."""
    return {k: deepcopy(view[k]) for k in ('clock', 'state', 'rules', 'tools')}


def compare(test, v, scenario, horizon, day, option):
    """Assess from the view alone and compare with ground truth. Returns True if a comparison was made."""
    view, report = counterfactual(v, scenario, horizon, day, option)
    seen = agent_only(view)
    est = assess(seen, option, conv=CONV[v.tag])
    if est is None:
        return False
    real = truth(report)
    if real['earliest_feasible_delivery'] is not None:     # delivery completed before today is simply "done by today"
        real['earliest_feasible_delivery'] = max(real['earliest_feasible_delivery'], day)
    firm = bool(seen['state']['notices']) or scenario['delay_outcome'] == 'none'
    label = f'{v.tag} day {day} {option}'
    STATS[(v.tag, 'exact' if firm else 'bounded', option)] = STATS.get((v.tag, 'exact' if firm else 'bounded', option), 0) + 1
    if firm:
        for key in ('shortfall_by_order', 'units_at_risk', 'earliest_feasible_delivery', 'penalties', 'recovery_spend'):
            test.assertEqual(est[key], real[key], f'{label}: {key}')
    else:   # a delay is only warned: the visible plan bounds the truth from both sides
        worst = assess(seen, option, conv=CONV[v.tag], worst_case=True)
        test.assertLessEqual(est['units_at_risk'], real['units_at_risk'], f'{label}: optimistic bound')
        test.assertGreaterEqual(worst['units_at_risk'], real['units_at_risk'], f'{label}: worst-case bound')
        test.assertEqual(est['recovery_spend'], real['recovery_spend'], f'{label}: spend')
    return True


def make_cases(v):
    from support.s01_versions import SCENARIO_STRATEGIES

    class Cases(unittest.TestCase):
        @given(SCENARIO_STRATEGIES[v.tag], st.data())
        @settings(max_examples=40)
        def test_assessment_from_observations_matches_the_verifier_on_generated_scenarios(self, sc, data):
            scenario, horizon = sc
            day = data.draw(st.integers(1, horizon))
            option = data.draw(st.sampled_from(OPTIONS))
            compare(self, v, scenario, horizon, day, option)

        def test_every_fixture_every_decision_day_every_option(self):
            made = 0
            for f in v.fixtures():
                scenario, horizon = fixture_scenario(v, f)
                for day in range(1, horizon + 1):
                    for option in OPTIONS:
                        with self.subTest(fixture=f['fixture_id'], day=day, option=option):
                            made += compare(self, v, scenario, horizon, day, option)
            self.assertGreater(made, 20, 'the fixtures must exercise recovery options, not only maintain')

        def test_zz_the_generated_runs_made_exact_and_bounded_comparisons_for_every_option(self):
            for kind in ('exact', 'bounded'):
                for option in OPTIONS:
                    self.assertGreater(STATS.get((v.tag, kind, option), 0), 0, f'no {kind} comparison for {option}')

        @given(SCENARIO_STRATEGIES[v.tag], st.data())
        @settings(max_examples=25)
        def test_the_firm_notice_changes_what_the_agent_sees_but_the_warning_does_not(self, sc, data):
            """Before the firm notice the visible lot arrival is the promise, so a delayed twin is not revealed early."""
            scenario, horizon = sc
            assume(scenario['delay_outcome'] == 'delay' and scenario['notice_day'] > 1)
            day = data.draw(st.integers(1, scenario['notice_day'] - 1))
            view, _ = counterfactual(v, scenario, horizon, day, 'maintain')
            primary = next(x for x in view['state']['lots'] if x['lot_id'] == 'primary')
            self.assertEqual(primary['arrival_day'], scenario['primary_promised_day'])
            self.assertEqual(view['state']['notices'], [])

    Cases.__name__ = Cases.__qualname__ = f'Assessment_{v.tag.replace(".", "")}'
    return Cases


Assessment_v02 = make_cases(V2)
Assessment_v03 = make_cases(V3)
Assessment_v04 = make_cases(V4)
Assessment_v05 = make_cases(V5)


class ConventionsAreNotInTheObservation(unittest.TestCase):
    """The numbers are visible but the rules that turn them into outcomes are not stated in any observation.

    Each wrong reading of an unstated rule gives a wrong answer on a committed fixture, so a model that only reads
    the observation can be misled. This is reported as a documentation/observation gap, not as a simulator defect.
    """

    def test_a_wrong_guess_about_an_unstated_rule_changes_the_answer(self):
        wrong = {
            'receipts usable only from the next day': Conventions(receipt_usable_same_day=False),
            'goods shipped as soon as they exist': Conventions(ship_from_due_day=False),
        }
        for v in (V2, V3, V4):
            for name, conv in wrong.items():
                differs = False
                for f in v.fixtures():
                    scenario, horizon = fixture_scenario(v, f)
                    for day in range(1, horizon + 1):
                        for option in OPTIONS:
                            view, report = counterfactual(v, scenario, horizon, day, option)
                            seen = agent_only(view)
                            est = assess(seen, option, conv=conv if v is not V2 else Conventions(
                                percent_divisor=100, **{k: getattr(conv, k) for k in ('receipt_usable_same_day', 'ship_from_due_day')}))
                            if est is None:
                                continue
                            real = truth(report)
                            if (est['units_at_risk'], est['earliest_feasible_delivery']) != (
                                    real['units_at_risk'], real['earliest_feasible_delivery']):
                                differs = True
                if not differs:
                    self.fail(f'{v.tag}: reading "{name}" never changed the assessment; the rule would not be load-bearing')

    def test_penalty_rate_units_differ_between_versions_and_are_not_in_the_observation(self):
        # The same visible penalty_type 'percent_of_value' with the same-looking rate means percent in v0.2 and
        # basis points in v0.3/v0.4. Nothing in the observation says which.
        for v in (V2, V3):
            scenario, horizon = fixture_scenario(v, next(f for f in v.fixtures() if 'multitier' in f['fixture_id']))
            view, report = counterfactual(v, scenario, horizon, 1, 'maintain')
            seen = agent_only(view)
            text = repr(seen['rules']).lower() + repr(seen['tools']).lower()
            for word in ('basis point', 'bps', 'percent per', 'per day late'):
                self.assertNotIn(word, text)
            right = assess(seen, 'maintain', conv=CONV[v.tag])['penalties']
            other = assess(seen, 'maintain', conv=V2_CONVENTIONS if v is V3 else V34_CONVENTIONS)['penalties']
            self.assertEqual(right, truth(report)['penalties'])
            self.assertNotEqual(right, other, 'the wrong unit must change the penalty, or this fixture proves nothing')


class V01ObservationsAreInsufficient(unittest.TestCase):
    """v0.1 never shows the primary PO quantity, so exposure before the receipt cannot be determined."""

    @given(v1_scenarios(), st.integers(1, 6))
    @settings(max_examples=100)
    def test_scenarios_differing_only_in_the_primary_quantity_look_identical_until_the_receipt(self, sc, delta):
        scenario, horizon = sc
        twin = dict(scenario, primary_quantity=scenario['primary_quantity'] + delta)
        streams = []
        for s in (scenario, twin):
            runner = V1.runner(s, horizon)
            seen = []

            def agent(view, seen=seen):
                if view['state']['primary_received']:
                    return {'tool': 'advance_day', 'arguments': {}} if view['state']['scheduled_production'] is not None \
                        else {'tool': 'release_production', 'arguments': {'quantity': 0}}
                seen.append(agent_only(view))
                if view['state']['scheduled_production'] is None:
                    return {'tool': 'release_production', 'arguments': {'quantity': greedy_release(view)}}
                return {'tool': 'advance_day', 'arguments': {}}
            transcript = runner.run(agent)
            streams.append((seen, transcript['scorecard']))
        (a, card_a), (b, card_b) = streams
        self.assertEqual(a, b, 'a view before the receipt exposed the primary PO quantity')
        # Non-vacuity is checked separately by the witness below (the outcomes can differ).

    def test_witness_the_two_scenarios_have_different_outcomes(self):
        scenario, horizon = fixture_scenario(V1, V1.fixtures()[0])
        results = []
        for qty in (8, 14):
            runner = V1.runner(dict(scenario, primary_quantity=qty), horizon)
            results.append(runner.run(V1.scripted('maintain'))['scorecard'])
        self.assertNotEqual(results[0], results[1])

    def test_no_observation_field_carries_the_primary_quantity(self):
        scenario, horizon = fixture_scenario(V1, V1.fixtures()[0])
        runner = V1.runner(scenario, horizon)
        view = runner.view()
        self.assertNotIn('primary_quantity', repr(view))
        # No state or rule key at all holds a quantity of the inbound primary PO (only the alternate offer has one).
        keys = [k for part in (view['state'], view['rules']) for k in part]
        self.assertEqual([k for k in keys if 'quantity' in k], [])
        scenario_after = V1.runner(dict(scenario, delay_notice_day=1), horizon)
        scenario_after.attempt({'tool': 'advance_day', 'arguments': {}})
        offers = scenario_after.view()['rules']['recovery_offers']
        self.assertEqual([k for k in offers if 'primary' in k], [])


if __name__ == '__main__':
    unittest.main()
