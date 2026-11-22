"""S01 v0.6: property tests (Hypothesis) on the simulator, runner, replay and the rebuilt independent checker.

v0.6 is run through the SAME generic property suites the earlier versions use (`Properties_*` from
test_s01_versions_property: conservation, no negative stock, budget, one release a day, rejected commands change
nothing, time moves forward, penalties and cancellations follow the written contract, replay reproduces the run, the
checker agrees; `VerifierMutation_*` from test_s01_verifier_mutation_property: the checker accepts every valid run and
rejects every mutated one). Nothing is skipped for v0.6: the opening records, the full state and the malformed-record
cases (defects D2 to D6) are all exercised. Then the properties that are specific to v0.6:

* exact-once WITHOUT an action id: any accepted recovery re-sent, with or without an id, is refused and changes nothing;
* the id derived for an id-less commitment is a pure function of day, choice and quantity;
* the conventions block is the same for every scenario that has the same visible parameters, so the hidden outcome
  cannot show in it, and it never carries outcome wording;
* the checker rejects a world that would execute a repeated id-less purchase.
"""
import unittest
from copy import deepcopy

from hypothesis import given, settings, strategies as st

import support  # noqa: F401
import test_s01_verifier_mutation_property as tm
import test_s01_versions_property as tp
from supplychainworld import dynamic_v6 as d6
from supplychainworld import dynamic_verifier_v6 as vf6
from support.s01_v6 import V6, SCENARIOS_V6
from support.s01_versions import drive, fixture_or_generated, informed_call

Properties_v06 = tp.make_cases(V6)
VerifierMutation_v06 = tm.make_cases(V6)


class ExactOnceWithoutAnActionId(unittest.TestCase):
    scenarios = fixture_or_generated(V6)

    @given(scenarios, st.data())
    @settings(max_examples=60)
    def test_an_accepted_commitment_re_sent_with_or_without_an_id_is_refused_and_changes_nothing(self, sc, data):
        scenario, horizon = sc
        runner = V6.runner(scenario, horizon)
        world = runner._world
        for _ in range(30):
            if world.snapshot()['phase'] == 'complete':
                break
            call = informed_call(V6, runner.view(), data)
            if call['tool'] == 'commit_recovery' and data.draw(st.booleans()):
                call.pop('action_id', None)             # half of the commitments are sent without an id
            rec = runner.attempt(call)
            if rec['accepted'] and call['tool'] == 'commit_recovery':
                before = world.snapshot()
                again = runner.attempt(deepcopy(call))
                self.assertFalse(again['accepted'], 'a commitment executed twice')
                self.assertEqual(world.snapshot(), before)
                if 'action_id' in call:               # a new id with the same content is a deliberate second lot
                    pass
        commits = world.snapshot()['commitments']
        self.assertEqual(len({x['commit_id'] for x in commits}), len(commits))

    @given(st.integers(1, 20), st.sampled_from(['expedite', 'alternate']), st.integers(1, 50))
    def test_the_derived_key_depends_only_on_day_choice_and_quantity(self, day, choice, qty):
        key = d6.derived_commit_key(day, choice, qty)
        self.assertRegex(key, r'^auto-[0-9a-f]{8}$')
        self.assertEqual(key, d6.derived_commit_key(day, choice, qty))
        self.assertEqual(key, vf6.derived_key(day, choice, qty))        # the checker's own implementation agrees
        self.assertNotEqual(key, d6.derived_commit_key(day + 1, choice, qty))

    @given(SCENARIOS_V6, st.data())
    @settings(max_examples=40)
    def test_the_checker_rejects_a_recorded_repeat_of_an_idless_purchase(self, sc, data):
        """A world that executed the repeat (here: the record is forged) is caught by the independent checker."""
        scenario, horizon = sc
        transcript, runner = drive(V6, scenario, horizon, data, steps=30)
        world = runner._world
        history = world.history()
        i = next((k for k, e in enumerate(history) if e['kind'] == 'recovery' and e['accepted']
                  and str(e['details'].get('commit_id', '')).startswith('auto-')), None)
        if i is None:
            return
        forged = deepcopy(history)
        forged.insert(i + 1, deepcopy(forged[i]))
        report = V6.verify(V6.scenario_dict(world), forged, horizon)
        self.assertTrue(report.violations)


class ConventionsBlock(unittest.TestCase):
    @given(SCENARIOS_V6, st.data())
    @settings(max_examples=60)
    def test_the_block_is_identical_for_hidden_outcome_twins_and_carries_no_outcome_wording(self, sc, data):
        from supplychainworld.dynamic_verifier_v6 import OUTCOME_WORDS
        scenario, horizon = sc
        twin = dict(scenario, delay_outcome='none' if scenario['delay_outcome'] == 'delay' else 'delay',
                    delayed_arrival_day=None if scenario['delay_outcome'] == 'delay' else scenario['primary_promised_day'] + 2)
        blocks = []
        for s in (scenario, twin):
            try:
                blocks.append(V6.runner(s, horizon).view()['rules']['conventions'])
            except ValueError:
                return                                          # the twin is not a valid scenario (e.g. no room)
        self.assertEqual(blocks[0], blocks[1])
        text = repr(blocks[0]).lower()
        for word in OUTCOME_WORDS:
            self.assertNotIn(word, text)

    @given(SCENARIOS_V6, st.data())
    @settings(max_examples=30)
    def test_the_block_is_on_every_observation_and_never_changes_during_an_episode(self, sc, data):
        scenario, horizon = sc
        transcript, runner = drive(V6, scenario, horizon, data, steps=15)
        first = transcript['initial']['view']['rules']['conventions']
        for a in transcript['attempts']:
            self.assertEqual(a['view_before']['rules']['conventions'], first)


if __name__ == '__main__':
    unittest.main()
