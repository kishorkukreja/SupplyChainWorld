"""S01 audit: the independent verifier accepts every valid run and rejects every mutated one.

Valid runs: generated scenarios and generated tool-call sequences (and the committed fixtures with every
declared policy). Mutations of the recorded history: drop, duplicate, reorder (adjacent and far), change
an amount in an event or a state, retype an event, flip accepted, shift a day; plus changes to the claimed
scorecard and to the claimed action log. A mutant that is not rejected is a failure unless the mutation
changed nothing the record means (`semantic_key`: an accepted zero-unit release produces nothing).

Kill counts for the committed fixtures are reported by scripts/s01_audit_summary.py.
"""
import json
import unittest

from hypothesis import given, settings, strategies as st

import support  # noqa: F401
from support.mutations import mutate_actions, mutate_history, mutate_scorecard, semantic_key
from support.s01_versions import VERSIONS, V1, V2, V3, V4, V5, drive, fixture_or_generated


def rejected(v, scenario, history, horizon, **kw):
    """True when the verifier reports a violation (or refuses the input) for the mutated record."""
    try:
        report = v.verify(scenario, history, horizon, **kw)
    except Exception as exc:   # noqa: BLE001 - the verifier may refuse a structurally broken record
        from supplychainworld.dynamic_verifier import ScenarioError  # same class name in every version
        return isinstance(exc, (ValueError, KeyError, TypeError)) or isinstance(exc, ScenarioError)
    return bool(report.violations)


def accepted_actions(actions):
    return json.dumps([a for a in actions if (a.get('result') or {}).get('accepted') is True], sort_keys=True)


def make_cases(v):
    scenarios = fixture_or_generated(v)

    class Cases(unittest.TestCase):
        @given(scenarios, st.data(), st.randoms(use_true_random=False))
        @settings(max_examples=40)
        def test_valid_runs_are_accepted_and_every_history_mutant_is_rejected(self, sc, data, rnd):
            scenario, horizon = sc
            transcript, runner = drive(v, scenario, horizon, data)
            world = runner._world
            history, card = world.history(), world.scorecard()
            sd = v.scenario_dict(world)
            self.assertEqual(v.verify(sd, history, horizon, scorecard=card, actions=v.actions(transcript)).violations, [])
            for _ in range(12):
                mutant, desc = mutate_history(history, rnd)
                if mutant is None or semantic_key(mutant) == semantic_key(history):
                    continue
                self.assertTrue(rejected(v, sd, mutant, horizon, scorecard=card), f'mutant survived: {desc}')

        @given(scenarios, st.data(), st.randoms(use_true_random=False))
        @settings(max_examples=30)
        def test_changed_scorecard_or_action_log_is_rejected(self, sc, data, rnd):
            scenario, horizon = sc
            transcript, runner = drive(v, scenario, horizon, data)
            world = runner._world
            history, card, sd = world.history(), world.scorecard(), v.scenario_dict(world)
            actions = v.actions(transcript)
            for _ in range(4):
                lie, desc = mutate_scorecard(card, rnd)
                if lie is not None:
                    self.assertTrue(rejected(v, sd, history, horizon, scorecard=lie), f'forged scorecard accepted: {desc}')
                bad, desc = mutate_actions(actions, rnd)
                if bad is not None and accepted_actions(bad) != accepted_actions(actions):
                    self.assertTrue(rejected(v, sd, history, horizon, scorecard=card, actions=bad),
                                    f'forged action log accepted: {desc}')

        @given(scenarios, st.data())
        @settings(max_examples=20)
        def test_self_reported_pass_flags_never_change_the_verdict(self, sc, data):
            scenario, horizon = sc
            transcript, runner = drive(v, scenario, horizon, data)
            world = runner._world
            history, card, sd = world.history(), world.scorecard(), v.scenario_dict(world)
            clean = v.verify(sd, history, horizon, scorecard=card)
            flagged = [dict(e, passed=True, valid=True, verified=True) for e in history]
            lying = v.verify(sd, flagged, horizon, scorecard={**card, 'passed': True})
            self.assertEqual(clean.violations, lying.violations)
            self.assertTrue(lying.ignored_self_reports)
            # And a flag claiming success cannot rescue a broken record.
            broken = json.loads(json.dumps(flagged))
            broken[-1]['state']['day'] += 3
            self.assertTrue(rejected(v, sd, broken, horizon, scorecard=card))

    Cases.__name__ = Cases.__qualname__ = f'VerifierMutation_{v.tag.replace(".", "")}'
    return Cases


VerifierMutation_v01 = make_cases(V1)
VerifierMutation_v02 = make_cases(V2)
VerifierMutation_v03 = make_cases(V3)
VerifierMutation_v04 = make_cases(V4)
VerifierMutation_v05 = make_cases(V5)


if __name__ == '__main__':
    unittest.main()
