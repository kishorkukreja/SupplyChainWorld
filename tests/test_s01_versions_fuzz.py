"""S01 audit: fuzz tests on the tool runner, scenario files, transcripts, histories and the verifier of v0.1 to v0.4.

Pattern: feed malformed, out-of-order, duplicated, extreme or adversarial input and assert that the system
(1) never crashes with an unexpected error, (2) rejects it cleanly, (3) leaves the world state unchanged,
(4) shows the agent no hidden scenario field. The early-warning twin tests assert that two worlds which differ
only in a hidden future event (delay or no delay, delayed arrival date, disruption on or off) produce identical
observation streams until the firm notice.
"""
import json
import unittest
from copy import deepcopy

from hypothesis import assume, given, settings, strategies as st

import support  # noqa: F401
from support import fuzz
from support.mutations import semantic_key
from support.s01_versions import (VERSIONS, V1, V2, V3, V4, drive, fixture_or_generated, fixture_scenario, informed_call,
                                  SCENARIO_STRATEGIES, scripted_transcript)

EXPECTED_ERRORS = (ValueError, KeyError, TypeError, StopIteration)


def keys_of(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield str(k)
            yield from keys_of(v)
    elif isinstance(node, list):
        for v in node:
            yield from keys_of(v)


def commit_garbage(version):
    """Malformed commit_recovery calls specific to the version's argument shape."""
    # Invalid by construction: not a positive int within range (wrong type, <= 0, or absurdly large).
    base = st.one_of(st.integers(max_value=0), st.integers(min_value=10**6, max_value=2**70),
                     st.floats(allow_nan=False, allow_infinity=False), st.booleans(), st.none(),
                     st.text(max_size=6), st.lists(st.integers(), max_size=2))
    return st.builds(lambda c, q, a: {'tool': 'commit_recovery', 'arguments': {'choice': c, 'quantity': q}, 'action_id': a},
                     st.one_of(fuzz.json_blobs, st.just('expedite'), st.just('alternate'), st.just('maintain')),
                     base, st.one_of(st.none(), st.just(''), st.integers(), st.lists(st.text(max_size=2), max_size=2)))


def make_runner_cases(v):
    scenarios = fixture_or_generated(v)

    class Cases(unittest.TestCase):
        @given(scenarios, st.one_of(fuzz.malformed_tool_calls(), commit_garbage(v)))
        def test_malformed_calls_are_rejected_state_unchanged_no_hidden_names(self, sc, call):
            scenario, horizon = sc
            runner = v.runner(scenario, horizon)
            before = runner._world.snapshot()
            record = runner.attempt(call)
            self.assertFalse(record['accepted'], record['reason'])
            self.assertIsNotNone(record['category'])
            self.assertEqual(runner._world.snapshot(), before)
            text = json.dumps(record)
            for key in v.hidden_keys:
                self.assertNotIn(key, text)

        @given(scenarios, st.lists(st.one_of(fuzz.malformed_tool_calls(), fuzz.json_blobs, commit_garbage(v)), max_size=25))
        def test_garbage_stream_never_crashes_and_a_valid_episode_still_completes_afterwards(self, sc, calls):
            scenario, horizon = sc
            runner = v.runner(scenario, horizon)
            for call in calls:
                runner.attempt(call)               # must never raise
            json.dumps(runner.transcript())        # the audit trail stays serializable
            # The world is still usable: closing the remaining days completes the episode.
            for _ in range(horizon + 2):
                if runner._world.snapshot()['phase'] == 'complete':
                    break
                runner.attempt({'tool': 'advance_day', 'arguments': {}})
            self.assertEqual(runner._world.snapshot()['phase'], 'complete')

        @given(scenarios, st.data())
        @settings(max_examples=40)
        def test_no_hidden_scenario_field_name_appears_in_any_observation_or_result(self, sc, data):
            scenario, horizon = sc
            transcript, runner = drive(v, scenario, horizon, data)
            seen = [transcript['initial']['view']] + [a['view_before'] for a in transcript['attempts']] + \
                   [a['result'] for a in transcript['attempts']]
            for blob in seen:
                for key in keys_of(blob):
                    for hidden in v.hidden_keys:
                        self.assertNotIn(hidden, key.lower(), f'hidden field {hidden} visible as key {key}')
            # Reading every documented section must not reveal anything the views do not.
            for section in ('all', 'clock', 'state', 'rules'):
                rec = runner.attempt({'tool': 'read_state', 'arguments': {'section': section}})
                for key in keys_of(rec['result']):
                    for hidden in v.hidden_keys:
                        self.assertNotIn(hidden, key.lower())

        @given(scenarios, st.sets(st.sampled_from(['read', 'commit', 'advance'])), st.data())
        def test_calls_that_need_an_authority_that_was_not_granted_are_refused_and_change_nothing(self, sc, granted, data):
            scenario, horizon = sc
            runner = v.runner(scenario, horizon, granted=tuple(granted))
            needs = {'read_state': 'read', 'read_recovery_offers': 'read', 'read_scorecard': 'read',
                     'commit_recovery': 'commit', 'release_production': 'commit', 'advance_day': 'advance'}
            for _ in range(12):
                tool = data.draw(st.sampled_from(sorted(needs)))
                args = {'commit_recovery': {'choice': 'maintain' if not v.multi_commit else 'expedite', 'quantity': 1}
                        if v.multi_commit else {'choice': 'maintain'},
                        'release_production': {'quantity': 1}}.get(tool, {})
                before = runner._world.snapshot()
                record = runner.attempt({'tool': tool, 'arguments': args})
                if needs[tool] not in granted:
                    self.assertFalse(record['accepted'])
                    self.assertEqual(record['category'], 'authority')
                    self.assertEqual(runner._world.snapshot(), before)
                    self.assertEqual(runner.tool_definitions()[list(needs).index(tool)]['granted'], False)

        @given(st.sampled_from(['read_state', 'read_recovery_offers', 'commit_recovery', 'release_production', 'advance_day']),
               fuzz.hidden_probe_names, fuzz.json_blobs)
        def test_probes_for_hidden_state_are_refused_by_name_and_by_argument(self, tool, probe, value):
            runner = v.runner(*fixture_scenario(v, v.fixtures()[0]))
            before = runner._world.snapshot()
            r1 = runner.attempt({'tool': probe, 'arguments': {}})
            r2 = runner.attempt({'tool': tool, 'arguments': {probe: value}})
            for r in (r1, r2):
                self.assertFalse(r['accepted'])
                self.assertEqual(r['category'], 'hidden_state')
            self.assertEqual(runner._world.snapshot(), before)

    Cases.__name__ = Cases.__qualname__ = f'RunnerFuzz_{v.tag.replace(".", "")}'
    return Cases


RunnerFuzz_v01 = make_runner_cases(V1)
RunnerFuzz_v02 = make_runner_cases(V2)
RunnerFuzz_v03 = make_runner_cases(V3)
RunnerFuzz_v04 = make_runner_cases(V4)


# ----------------------------------------------------------------------------- early-warning twins

def with_outcome(v, scenario, delay, delayed_arrival=None):
    s = deepcopy(scenario)
    if v.tag == 'v0.1':
        s['disruption_enabled'] = delay
        if delayed_arrival is not None:
            s['delayed_arrival_day'] = delayed_arrival
    else:
        s['delay_outcome'] = 'delay' if delay else 'none'
        s['delayed_arrival_day'] = (delayed_arrival or scenario.get('delayed_arrival_day') or s['primary_promised_day'] + 2) if delay else None
    return s


def prefix_records(a, b, data, v, horizon, steps=20):
    """Drive twins A and B with the same calls (drawn from A's view); return their attempt record pairs."""
    ra, rb = v.runner(a, horizon), v.runner(b, horizon)
    pairs = []
    for _ in range(steps):
        if ra._world.snapshot()['phase'] == 'complete':
            break
        call = informed_call(v, ra.view(), data)
        pre_a, pre_b = ra.view(), rb.view()
        pairs.append((pre_a, pre_b, ra.attempt(deepcopy(call)), rb.attempt(deepcopy(call))))
    while ra._world.snapshot()['phase'] != 'complete':
        call = {'tool': 'advance_day', 'arguments': {}}
        pre_a, pre_b = ra.view(), rb.view()
        pairs.append((pre_a, pre_b, ra.attempt(deepcopy(call)), rb.attempt(deepcopy(call))))
    return pairs, ra, rb


OBSERVED = ('seq', 'day', 'tool', 'arguments', 'action_id', 'accepted', 'category', 'reason', 'result', 'view_before')


def make_twin_cases(v):
    class Cases(unittest.TestCase):
        def assert_identical_until_notice(self, pairs, label):
            for i, (pre_a, pre_b, rec_a, rec_b) in enumerate(pairs):
                if pre_a['state']['notices'] or pre_b['state']['notices']:
                    break
                self.assertEqual(pre_a, pre_b, f'{label}: views differ before the firm notice (attempt {i})')
                for key in OBSERVED:
                    self.assertEqual(rec_a[key], rec_b[key], f'{label}: {key} differs before the firm notice')

        @given(SCENARIO_STRATEGIES[v.tag], st.data())
        @settings(max_examples=30)
        def test_delay_and_no_delay_twins_have_identical_observations_until_the_firm_notice(self, sc, data):
            scenario, horizon = sc
            a, b = with_outcome(v, scenario, True), with_outcome(v, scenario, False)
            pairs, ra, rb = prefix_records(a, b, data, v, horizon)
            self.assertEqual(ra.transcript()['initial'], rb.transcript()['initial'])
            self.assert_identical_until_notice(pairs, 'delay vs none')

        @given(SCENARIO_STRATEGIES[v.tag], st.integers(1, 4), st.data())
        @settings(max_examples=30)
        def test_the_delayed_arrival_date_is_not_visible_before_the_firm_notice(self, sc, extra, data):
            scenario, horizon = sc
            a = with_outcome(v, scenario, True)
            promised = a['initially_promised_day'] if v.tag == 'v0.1' else a['primary_promised_day']
            later = (a['delayed_arrival_day'] or promised + 1) + extra
            b = with_outcome(v, scenario, True, later)
            pairs, _, _ = prefix_records(a, b, data, v, horizon)
            self.assert_identical_until_notice(pairs, 'delayed arrival day')

        @given(SCENARIO_STRATEGIES[v.tag], st.data())
        @settings(max_examples=25)
        def test_after_the_firm_notice_the_twins_do_differ_so_the_check_is_not_vacuous(self, sc, data):
            scenario, horizon = sc
            a, b = with_outcome(v, scenario, True), with_outcome(v, scenario, False)
            notice = a['delay_notice_day'] if v.tag == 'v0.1' else a['notice_day']
            assume(notice < horizon)
            pairs, ra, rb = prefix_records(a, b, data, v, horizon)
            sa, sb = ra._world.snapshot(), rb._world.snapshot()
            self.assertNotEqual(sa['notices'], sb['notices'])

    Cases.__name__ = Cases.__qualname__ = f'EarlyWarningTwins_{v.tag.replace(".", "")}'
    return Cases


EarlyWarningTwins_v01 = make_twin_cases(V1)
EarlyWarningTwins_v02 = make_twin_cases(V2)
EarlyWarningTwins_v03 = make_twin_cases(V3)
EarlyWarningTwins_v04 = make_twin_cases(V4)


class ExactOnceBoundary(unittest.TestCase):
    """Documented limit (finding F4 in evidence/s01-audit/results.md): in v0.2 to v0.4 a recovery commitment is
    exact-once only when the caller supplies an `action_id`. The tool definition says each commitment needs its own
    id, but the runner does not require one, so re-sending the same call WITHOUT an id is a second, separate purchase."""

    def test_the_same_commit_twice_without_an_action_id_executes_twice_and_with_one_only_once(self):
        for v in (V2, V3, V4):
            with self.subTest(version=v.tag):
                scenario, horizon = fixture_scenario(v, v.fixtures()[0])
                scenario = dict(scenario, recovery_budget=10**6)
                runner = v.runner(scenario, horizon)
                today = runner.view()['rules']['recovery_offers']['expedite']['today']
                call = {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite', 'quantity': 1}}
                self.assertTrue(runner.attempt(deepcopy(call))['accepted'])
                self.assertTrue(runner.attempt(deepcopy(call))['accepted'], 'without an id a retry is a new purchase')
                self.assertEqual(len(runner._world.snapshot()['commitments']), 2)
                keyed = dict(call, action_id='once')
                self.assertTrue(runner.attempt(deepcopy(keyed))['accepted'])
                self.assertFalse(runner.attempt(deepcopy(keyed))['accepted'])
                self.assertEqual(len(runner._world.snapshot()['commitments']), 3)
                self.assertTrue(any('action_id' in str(d) for d in runner.tool_definitions()))   # the contract is stated, not enforced


class NoticeDateIsNotLeakedEither(unittest.TestCase):
    """The future date of the firm notice is hidden too: twins that differ only in it match until the earlier notice."""

    @given(SCENARIO_STRATEGIES['v0.3'], st.data())
    @settings(max_examples=20)
    def test_twins_with_different_notice_days_match_until_the_earlier_notice(self, sc, data):
        scenario, horizon = sc
        assume(scenario['notice_day'] + 1 < scenario['primary_promised_day'])
        a = deepcopy(scenario)
        b = dict(deepcopy(scenario), notice_day=scenario['notice_day'] + 1)
        for v in (V3, V4):
            pairs, _, _ = prefix_records(a, b, data, v, horizon)
            for i, (pre_a, pre_b, rec_a, rec_b) in enumerate(pairs):
                if pre_a['state']['notices'] or pre_b['state']['notices']:
                    break
                self.assertEqual(pre_a, pre_b)
                for key in OBSERVED:
                    self.assertEqual(rec_a[key], rec_b[key])


# ----------------------------------------------------------------------------- scenario / fixture fuzz

junk = st.one_of(fuzz.json_blobs, st.sampled_from([float('nan'), float('inf'), -1, 0, 2**63, -2**63, True, False, None, '', [], {}]))


@st.composite
def damaged_scenarios(draw, scenario):
    s = deepcopy(scenario)
    for _ in range(draw(st.integers(1, 3))):
        kind = draw(st.sampled_from(['delete', 'replace', 'add', 'nested']))
        key = draw(st.sampled_from(sorted(s)))
        if kind == 'delete':
            del s[key]
        elif kind == 'replace':
            s[key] = draw(junk)
        elif kind == 'add':
            s[draw(st.text(min_size=1, max_size=10))] = draw(junk)
        else:
            node = s[key]
            if isinstance(node, list) and node:
                i = draw(st.integers(0, len(node) - 1))
                if isinstance(node[i], dict) and node[i]:
                    k = draw(st.sampled_from(sorted(node[i])))
                    node[i][k] = draw(junk)
                elif isinstance(node[i], list) and node[i]:
                    node[i][draw(st.integers(0, len(node[i]) - 1))] = draw(junk)
                else:
                    node[i] = draw(junk)
            elif isinstance(node, dict) and node:
                node[draw(st.sampled_from(sorted(node)))] = draw(junk)
            else:
                s[key] = draw(junk)
    return s


def _int_leaves(node, path=()):
    if isinstance(node, dict):
        for k, x in node.items():
            yield from _int_leaves(x, path + (k,))
    elif isinstance(node, list):
        for i, x in enumerate(node):
            yield from _int_leaves(x, path + (i,))
    elif type(node) is int:
        yield path


@st.composite
def nudged_scenarios(draw, scenario):
    """Near-valid scenarios: one or two numbers moved to another small value, so many pass validation."""
    s = deepcopy(scenario)
    leaves = sorted(_int_leaves(s), key=str)
    for _ in range(draw(st.integers(1, 2))):
        path = draw(st.sampled_from(leaves))
        node = s
        for k in path[:-1]:
            node = node[k]
        node[path[-1]] = draw(st.integers(0, 12))
    return s


NUDGE_STATS = {'tried': 0, 'accepted': 0}


def make_scenario_fuzz(v):
    base = fixture_scenario(v, v.fixtures()[1])

    class Cases(unittest.TestCase):
        @given(damaged_scenarios(base[0]), st.one_of(st.just(base[1]), junk))
        def test_damaged_scenarios_are_refused_cleanly_or_run_and_verify(self, scenario, horizon):
            try:
                world = v.world(scenario, horizon)
            except EXPECTED_ERRORS:
                return                      # refused cleanly with a plain validation error
            except RecursionError:          # pragma: no cover
                self.fail('recursion on a damaged scenario')
            # Accepted by the simulator: it must run to the end, replay and pass the independent verifier.
            self.assertIsInstance(horizon, int)
            assume(horizon <= 60)
            runner = v.runner_cls(world)
            transcript = runner.run(v.scripted(v.policies[0]))
            self.assertIn(transcript['status'], ('complete', 'attempt_budget_exhausted'))
            if transcript['status'] == 'complete':
                report = v.verify(v.scenario_dict(world), world.history(), horizon, scorecard=world.scorecard())
                self.assertEqual(report.violations, [], 'simulator accepted a scenario the verifier cannot confirm')

        @given(nudged_scenarios(base[0]), st.sampled_from(sorted(range(1, 13))))
        def test_boundary_nudged_scenarios_run_and_verify_when_the_simulator_accepts_them(self, scenario, horizon):
            NUDGE_STATS['tried'] += 1
            try:
                world = v.world(scenario, horizon)
            except EXPECTED_ERRORS:
                return
            NUDGE_STATS['accepted'] += 1
            runner = v.runner_cls(world)
            transcript = runner.run(v.scripted(v.policies[-1]))
            if transcript['status'] != 'complete':
                return              # a scripted policy may stall on an unaffordable offer; not a verifier question
            report = v.verify(v.scenario_dict(world), world.history(), horizon, scorecard=world.scorecard(),
                              actions=v.actions(transcript))
            self.assertEqual(report.violations, [], 'simulator accepted and ran a scenario the verifier rejects')
            ok, diffs = v.replay(transcript, v.factory(v.scenario_dict(world), horizon))
            self.assertTrue(ok, diffs)

        @given(damaged_scenarios(base[0]))
        def test_the_verifier_refuses_damaged_scenarios_with_a_validation_error_only(self, scenario):
            try:
                v.verify(scenario, [], base[1])
            except ValueError:
                return          # a validation error is the clean refusal

    Cases.__name__ = Cases.__qualname__ = f'ScenarioFuzz_{v.tag.replace(".", "")}'
    return Cases


class ZZNudgeCoverage(unittest.TestCase):
    def test_nudged_scenarios_were_actually_accepted_by_the_simulator_often_enough(self):
        self.assertGreater(NUDGE_STATS['accepted'], 40, NUDGE_STATS)


ScenarioFuzz_v01 = make_scenario_fuzz(V1)
ScenarioFuzz_v02 = make_scenario_fuzz(V2)
ScenarioFuzz_v03 = make_scenario_fuzz(V3)
ScenarioFuzz_v04 = make_scenario_fuzz(V4)


class ConstructorFuzz(unittest.TestCase):
    @given(st.sampled_from(sorted(VERSIONS)), junk, junk, junk)
    def test_runner_and_world_constructors_refuse_bad_arguments_cleanly(self, tag, horizon, granted, limit):
        v = VERSIONS[tag]
        scenario, h = fixture_scenario(v, v.fixtures()[0])
        try:
            v.world_cls(horizon, scenario=v.scenario_cls(**scenario))
        except EXPECTED_ERRORS:
            pass
        world = v.world(scenario, h)
        for kw in ({'granted': granted}, {'max_attempts_per_day': limit}, {'max_total_attempts': limit}):
            try:
                v.runner_cls(world, **kw)
            except EXPECTED_ERRORS:
                pass
        for wrong in (None, 5, 'world', object()):
            with self.assertRaises(TypeError):
                v.runner_cls(wrong)


# ----------------------------------------------------------------------------- transcripts and histories

def make_record_fuzz(v):
    scenario, horizon = fixture_scenario(v, v.fixtures()[1])
    transcript, runner = scripted_transcript(v, scenario, horizon, v.policies[-1])
    world = runner._world
    history, card = world.history(), world.scorecard()
    sd = v.scenario_dict(world)
    VERIFIED = ('scenario_id', 'horizon_days', 'status', 'initial', 'final_state', 'scorecard', 'attempts')

    class Cases(unittest.TestCase):
        @given(st.data())
        def test_damaged_transcripts_replay_to_a_refusal_or_a_difference_never_a_silent_pass(self, data):
            damaged = data.draw(fuzz.mutated_transcripts(transcript))
            try:
                ok, diffs = v.replay(damaged, v.factory(scenario, horizon))
            except EXPECTED_ERRORS:
                return
            self.assertEqual(ok, not diffs)
            if ok:
                for key in VERIFIED:
                    self.assertEqual(damaged.get(key), transcript.get(key), f'replay passed a damaged {key}')

        @given(st.lists(fuzz.json_blobs, max_size=6), st.one_of(st.none(), fuzz.json_blobs),
               st.one_of(st.none(), st.lists(fuzz.json_blobs, max_size=4)))
        def test_verifier_survives_garbage_history_scorecard_and_actions(self, hist, card_, actions):
            try:
                report = v.verify(sd, hist, horizon, scorecard=card_, actions=actions)
            except ValueError:
                return
            self.assertFalse(report.feasible and report.complete and not history)
            self.assertIsInstance(report.violations, list)

        @given(fuzz.json_blobs)
        def test_a_history_or_actions_argument_of_the_wrong_type_is_a_type_or_value_error(self, junk):
            for kw in ({'history': junk}, {'actions': junk}):
                try:
                    v.verify(sd, kw.get('history', []), horizon, actions=kw.get('actions'))
                except (ValueError, TypeError):
                    pass

        @given(st.lists(st.fixed_dictionaries({}, optional={
            'day': junk, 'kind': st.one_of(st.sampled_from(['receipt', 'notice', 'signal', 'recovery', 'release', 'day_close', 'close_day',
                                                            'episode_complete', 'day_open', 'opening_before_notice']), junk),
            'details': junk, 'accepted': junk, 'state': junk, 'reason': junk}), max_size=12))
        def test_verifier_survives_event_shaped_garbage_and_never_accepts_it_as_a_complete_episode(self, events):
            try:
                report = v.verify(sd, events, horizon, scorecard=card)
            except ValueError:
                return
            self.assertFalse(report.complete and report.feasible)

        @given(st.data())
        def test_a_history_with_a_hole_or_a_swap_is_never_accepted_as_complete(self, data):
            hist = deepcopy(history)
            i = data.draw(st.integers(0, len(hist) - 2))
            if data.draw(st.booleans()):
                del hist[i]
            else:
                j = data.draw(st.integers(0, len(hist) - 1))
                assume(hist[i]['kind'] != hist[j]['kind'] or hist[i] != hist[j])
                hist[i], hist[j] = hist[j], hist[i]
            assume(semantic_key(hist) != semantic_key(history))
            try:
                report = v.verify(sd, hist, horizon, scorecard=card)
            except ValueError:
                return
            self.assertTrue(report.violations, 'a damaged history was accepted')

    Cases.__name__ = Cases.__qualname__ = f'RecordFuzz_{v.tag.replace(".", "")}'
    return Cases


RecordFuzz_v01 = make_record_fuzz(V1)
RecordFuzz_v02 = make_record_fuzz(V2)
RecordFuzz_v03 = make_record_fuzz(V3)
RecordFuzz_v04 = make_record_fuzz(V4)


class CrossVersionFeed(unittest.TestCase):
    def test_a_transcript_of_one_version_is_refused_by_every_other_versions_replay(self):
        transcripts = {}
        for tag, v in VERSIONS.items():
            scenario, horizon = fixture_scenario(v, v.fixtures()[0])
            transcripts[tag] = (scripted_transcript(v, scenario, horizon, v.policies[0])[0], scenario, horizon)
        for tag, v in VERSIONS.items():
            for other, (t, scenario, horizon) in transcripts.items():
                if other == tag:
                    continue
                with self.subTest(replaying=other, on=tag):
                    with self.assertRaises(ValueError):
                        v.replay(t, v.factory(*fixture_scenario(v, v.fixtures()[0])))


if __name__ == '__main__':
    unittest.main()
