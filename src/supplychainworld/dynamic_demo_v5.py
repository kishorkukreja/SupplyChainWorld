"""Whole-family check for the S01 v0.5 family (issue #19 fixes, finding 1: opaque scenario id).

Runs the five declared scripted policies on each of the five scenarios (25 episodes) through the observable
tool runner and reports, per episode, whether the simulator, the independent v0.5 verifier and the hand-worked
ledgers agree, whether the transcript replays exactly, whether the observation leak scan is clean, and whether the
paired warned scenarios look identical to the agent until the firm notice. Nothing here is combined into a
ranking. Scripted policies are not LLMs and prove nothing about model ability. All numbers PROVISIONAL, needs
practitioner value.
"""
import json
from pathlib import Path

from .agent_runner_v5 import POLICIES_V5, ObservableRunnerV5, replay_v5, scripted_policy_v5
from .dynamic_demo_v4 import METRICS, _get, hand_matches  # noqa: F401
from .dynamic_v5 import OperationalWorldV5, ScenarioV5
from .dynamic_verifier_v5 import check_observations_for_leaks, verify_episode

ROOT = Path(__file__).resolve().parents[2]
PAIR = ('s05-warned-delayed-10d', 's05-warned-no-delay-10d')


def load_fixtures(root=ROOT):
    return json.loads((Path(root) / 'fixtures/dynamic/v0.5/scenarios.json').read_text())['fixtures']


def load_hand(root=ROOT):
    return json.loads((Path(root) / 'fixtures/dynamic/v0.5/hand-ledgers.json').read_text())['fixtures']


def factory(fixture, sink=None):
    def make():
        w = OperationalWorldV5(fixture['horizon_days'], scenario=ScenarioV5(**fixture['scenario']))
        if sink is not None:
            sink.append(w)
        return w
    return make


def actions_of(transcript):
    return [{'day': a['day'], 'kind': {'commit_recovery': 'recovery', 'release_production': 'release'}[a['tool']],
             'arguments': a['arguments'], 'result': a['result']}
            for a in transcript['attempts'] if a['tool'] in ('commit_recovery', 'release_production')]


def observations_of(transcript):
    return [{'state': a['view_before']['state'], 'rules': a['view_before']['rules'],
             'last_outcome': a['view_before']['last_outcome']} for a in transcript['attempts']]


def prefix_before_firm_notice(transcript):
    """Everything the agent saw and got back before any firm notice was visible. The scenario id is KEPT: in v0.5 it
    is part of what the agent sees, so it must itself be identical for the paired scenarios."""
    return [{'view': {k: a['view_before'][k] for k in ('state', 'rules', 'clock', 'last_outcome')},
             'call': {'tool': a['tool'], 'arguments': a['arguments']}, 'result': a['result']}
            for a in transcript['attempts'] if not a['view_before']['state']['notices']]


def run_episode(fixture, policy, hand=None):
    world = factory(fixture)()
    transcript = ObservableRunnerV5(world).run(scripted_policy_v5(policy))
    history, card = world.history(), world.scorecard()
    scenario, horizon = fixture['scenario'], fixture['horizon_days']
    report = verify_episode(scenario, history, horizon_days=horizon, scorecard=card, actions=actions_of(transcript))
    sink = []
    ok, diffs = replay_v5(transcript, factory(fixture, sink))
    again = sink[-1]
    return {'fixture_id': fixture['fixture_id'], 'policy': policy, 'transcript': transcript, 'history': history,
            'scorecard': card, 'report': report,
            'hand': hand_matches(fixture['fixture_id'], policy, report, card, hand or load_hand()),
            'leaks': check_observations_for_leaks(scenario, observations_of(transcript)),
            'replay': {'transcript_reproduced': ok, 'differences': diffs,
                       'state_sequence_identical': again.history() == history,
                       'replayed_scorecard_identical': again.scorecard() == card}}


def run_all():
    hand = load_hand()
    return {f['fixture_id']: {p: run_episode(f, p, hand) for p in POLICIES_V5} for f in load_fixtures()}


def paired_identical(episodes):
    """Warned-and-delayed and warned-and-no-delay look identical to the agent until the firm notice."""
    out = {}
    for p in POLICIES_V5:
        a = prefix_before_firm_notice(episodes[PAIR[0]][p]['transcript'])
        b = prefix_before_firm_notice(episodes[PAIR[1]][p]['transcript'])
        out[p] = bool(a) and a == b
    return out


def summarize(episodes):
    """One row per episode, plus the totals the evidence file reports."""
    rows = []
    for fid, by_policy in episodes.items():
        for p, ep in by_policy.items():
            rows.append({'fixture': fid, 'policy': p, 'verifier_feasible': ep['report'].feasible,
                         'matches_hand_ledger': all(ep['hand'].values()),
                         'replay_reproduced': ep['replay']['transcript_reproduced']
                         and ep['replay']['state_sequence_identical'] and ep['replay']['replayed_scorecard_identical'],
                         'leak_scan_clean': not ep['leaks'], 'net_cost': ep['scorecard']['cost']['net_cost']})
    paired = paired_identical(episodes)
    return {'episodes': len(rows), 'all_verifier_feasible': all(r['verifier_feasible'] for r in rows),
            'all_match_hand_ledgers': all(r['matches_hand_ledger'] for r in rows),
            'all_replay_reproduced': all(r['replay_reproduced'] for r in rows),
            'all_leak_scans_clean': all(r['leak_scan_clean'] for r in rows),
            'paired_scenarios_identical_before_notice': paired, 'rows': rows}
