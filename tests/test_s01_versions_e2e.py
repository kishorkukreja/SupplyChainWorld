"""S01 audit: end-to-end tests for v0.1 to v0.4.

Same entry points a real agent or script uses: the JSON tool interface, the runner, the simulator, the
independent verifier and replay, plus the demo scripts that publish the evidence packets. Nothing is mocked
(there is no network in S01).

* every committed fixture x every declared policy: run, verify (claimed scorecard and action log), replay,
  and compare with the hand-worked ledgers committed under fixtures/dynamic;
* a tool-only agent whose every observation and call goes through JSON text;
* the committed transcripts in evidence/ still replay on the current code;
* each demo script regenerates, byte for byte, the evidence files that are committed (determinism).
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import support  # noqa: F401
from support.s01_versions import VERSIONS, V1, V2, V3, V4, fixture_scenario, greedy_release, scripted_transcript

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = {'v0.1': ('issue-26', 'run_dynamic_demo.py', ['--screenshot', 'evidence/screenshots/issue-26-demo-packet.png']),
            'v0.2': ('issue-36', 'run_dynamic_demo_v2.py', []),
            'v0.3': ('issue-36-v03', 'run_dynamic_demo_v3.py', []),
            'v0.4': ('issue-36-v04', 'run_dynamic_demo_v4.py', [])}


def hand_check(tag, fixture_id, policy, report, card):
    """Compare with the committed hand-worked numbers using the version's own comparison helpers."""
    if tag == 'v0.1':
        from supplychainworld.dynamic_demo import ledger_matches_hand, scorecard_matches_expected
        return bool(ledger_matches_hand(fixture_id, policy, report)) and bool(scorecard_matches_expected(fixture_id, policy, card))
    mod = {'v0.2': 'dynamic_demo_v2', 'v0.3': 'dynamic_demo_v3', 'v0.4': 'dynamic_demo_v4'}[tag]
    demo = __import__(f'supplychainworld.{mod}', fromlist=['hand_matches'])
    return all(demo.hand_matches(fixture_id, policy, report, card).values())


class EveryFixtureEveryPolicy(unittest.TestCase):
    def test_run_verify_replay_and_hand_ledgers_for_all_fixtures_and_policies(self):
        count = 0
        for tag, v in VERSIONS.items():
            for f in v.fixtures():
                scenario, horizon = fixture_scenario(v, f)
                for policy in v.policies:
                    with self.subTest(version=tag, fixture=f['fixture_id'], policy=policy):
                        transcript, runner = scripted_transcript(v, scenario, horizon, policy)
                        world = runner._world
                        self.assertEqual(transcript['status'], 'complete')
                        history, card = world.history(), world.scorecard()
                        report = v.verify(v.scenario_dict(world), history, horizon, scorecard=card, actions=v.actions(transcript))
                        self.assertTrue(report.complete)
                        self.assertEqual(report.violations, [])
                        sink = []
                        ok, diffs = v.replay(transcript, v.factory(scenario, horizon, sink))
                        self.assertTrue(ok, diffs)
                        self.assertEqual(sink[-1].history(), history)
                        self.assertEqual(sink[-1].scorecard(), card)
                        self.assertTrue(hand_check(tag, f['fixture_id'], policy, report, card), 'differs from the hand-worked ledger')
                        # The scorecard the agent can read with its own tool is the verified one.
                        again = v.runner_cls(v.world(scenario, horizon))
                        again.run(v.scripted(policy))
                        tool = again.attempt({'tool': 'read_scorecard', 'arguments': {}})
                        self.assertTrue(tool['accepted'])
                        self.assertEqual(tool['result']['data'], card)
                        count += 1
        self.assertEqual(count, sum(len(v.fixtures()) * len(v.policies) for v in VERSIONS.values()))

    def test_v01_policies_order_as_the_written_acceptance_tables_say(self):
        cost = {p: scripted_transcript(V1, *fixture_scenario(V1, V1.fixtures()[0]), p)[0]['scorecard']['comparison_cost']
                for p in V1.policies}
        self.assertEqual(cost, {'maintain': 120, 'expedite': 24, 'alternate': 40})


class JsonOnlyToolAgent(unittest.TestCase):
    """An agent that only sees JSON text and answers with JSON text, like a model behind an adapter."""

    def run_agent(self, v, scenario, horizon):
        runner = v.runner(scenario, horizon)

        def agent(view):
            seen = json.loads(json.dumps(view))                       # everything the agent knows arrives as JSON
            offers = seen['rules'].get('recovery_offers')
            state = seen['state']
            if offers and not state.get('commitments') and state.get('recovery') is None and v.multi_commit is False:
                call = {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite'}}
            elif offers and v.multi_commit and not state['commitments'] and offers['expedite']['today']:
                call = {'tool': 'commit_recovery', 'arguments': {'choice': 'expedite', 'quantity': offers['expedite']['today']['max_units']},
                        'action_id': 'json-1'}
            elif state['scheduled_production'] is None:
                call = {'tool': 'release_production', 'arguments': {'quantity': greedy_release(seen)}}
            else:
                call = {'tool': 'advance_day', 'arguments': {}}
            return json.loads(json.dumps(call))
        return runner.run(agent), runner

    def test_a_json_only_agent_completes_every_fixture_and_the_result_verifies(self):
        for tag, v in VERSIONS.items():
            for f in v.fixtures():
                with self.subTest(version=tag, fixture=f['fixture_id']):
                    scenario, horizon = fixture_scenario(v, f)
                    transcript, runner = self.run_agent(v, scenario, horizon)
                    self.assertEqual(transcript['status'], 'complete')
                    world = runner._world
                    report = v.verify(v.scenario_dict(world), world.history(), horizon, scorecard=world.scorecard(),
                                      actions=v.actions(transcript))
                    self.assertEqual(report.violations, [])
                    ok, diffs = v.replay(json.loads(json.dumps(transcript)), v.factory(scenario, horizon))
                    self.assertTrue(ok, diffs)

    def test_reads_do_not_change_the_world_and_do_not_use_attempts_of_the_clock(self):
        for tag, v in VERSIONS.items():
            with self.subTest(version=tag):
                runner = v.runner(*fixture_scenario(v, v.fixtures()[0]))
                before = runner._world.snapshot()
                for call in ({'tool': 'read_state', 'arguments': {}}, {'tool': 'read_state', 'arguments': {'section': 'clock'}},
                             {'tool': 'read_state', 'arguments': {'section': 'rules'}}, {'tool': 'read_recovery_offers', 'arguments': {}}):
                    self.assertTrue(runner.attempt(call)['accepted'])
                self.assertEqual(runner._world.snapshot(), before)
                self.assertEqual(runner.view()['clock']['current_day'], 1)


class CommittedEvidenceStillReplays(unittest.TestCase):
    def test_committed_transcripts_replay_and_match_committed_scorecards(self):
        for tag, (directory, _, _) in EVIDENCE.items():
            v = VERSIONS[tag]
            transcripts = json.loads((ROOT / 'evidence' / directory / 'transcripts.json').read_text())
            fixtures = {f['fixture_id']: f for f in v.fixtures()}
            n = 0
            for fid, by_policy in transcripts.items():
                scenario, horizon = fixture_scenario(v, fixtures[fid])
                for policy, transcript in by_policy.items():
                    with self.subTest(version=tag, fixture=fid, policy=policy):
                        ok, diffs = v.replay(deepcopy(transcript), v.factory(scenario, horizon))
                        self.assertTrue(ok, diffs)
                        n += 1
            self.assertEqual(n, len(fixtures) * len(v.policies))


class DemoScriptsRegenerateCommittedEvidence(unittest.TestCase):
    def test_every_generated_file_equals_the_committed_file(self):
        for tag, (directory, script, extra) in EVIDENCE.items():
            with self.subTest(version=tag), tempfile.TemporaryDirectory() as tmp:
                env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'), PYTHONHASHSEED='0')
                done = subprocess.run([sys.executable, str(ROOT / 'scripts' / script), '--out', tmp, *extra], cwd=ROOT, env=env,
                                      capture_output=True, text=True, timeout=300)
                self.assertEqual(done.returncode, 0, done.stderr)
                made = sorted(p.name for p in Path(tmp).iterdir())
                self.assertGreater(len(made), 8)
                for name in made:
                    committed = ROOT / 'evidence' / directory / name
                    self.assertTrue(committed.exists(), f'{directory}/{name} is not committed')
                    self.assertEqual((Path(tmp) / name).read_bytes(), committed.read_bytes(),
                                     f'{directory}/{name} differs from what the script generates now')


if __name__ == '__main__':
    unittest.main()
