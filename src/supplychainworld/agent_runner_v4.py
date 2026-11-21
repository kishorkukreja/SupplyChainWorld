"""Tool layer, observable runner, replay and scripted policies for the S01 v0.4 family (issue #36, round 3).

The v0.3 runner and scripted policies are reused unchanged (the five declared policies read only the
visible view, so the premium-only alternate price needs no policy change). Only the transcript schema
label, the accepted world type and the replay factory type differ. Scripted policies are not LLMs and
prove nothing about model ability. All numbers are PROVISIONAL, needs practitioner value.
"""
from .agent_runner import _ReplayedAgentError
from .agent_runner_v3 import POLICIES_V3, ObservableRunnerV3, scripted_policy_v3
from .dynamic_v4 import OperationalWorldV4

TRANSCRIPT_SCHEMA_V4 = 'dyn06-transcript-4'
POLICIES_V4 = POLICIES_V3


class ObservableRunnerV4(ObservableRunnerV3):
    def __init__(self, world: OperationalWorldV4, **kw):
        if not isinstance(world, OperationalWorldV4):
            raise TypeError('world must be an OperationalWorldV4')
        super().__init__(world, **kw)

    def transcript(self):
        out = super().transcript()
        out['schema'] = TRANSCRIPT_SCHEMA_V4
        return out


def scripted_policy_v4(policy):
    return scripted_policy_v3(policy)


def replay_v4(transcript, world_factory):
    """Re-run a recorded interaction on a fresh v0.4 world; returns (ok, differences)."""
    if transcript.get('schema') != TRANSCRIPT_SCHEMA_V4:
        raise ValueError('unsupported transcript schema')
    attempts, limits = transcript['attempts'], transcript['limits']
    runner = ObservableRunnerV4(world_factory(), granted=tuple(transcript['granted_authority']),
                                max_attempts_per_day=limits['max_attempts_per_day'],
                                max_total_attempts=limits['max_total_attempts'])
    cursor = iter(attempts)

    def agent(_view):
        rec = next(cursor, None)
        if rec is None:
            return None
        if rec['category'] == 'agent_error':
            raise _ReplayedAgentError(rec['reason'])
        call = {'tool': rec['tool'], 'arguments': rec['arguments']}
        if rec['action_id'] is not None:
            call['action_id'] = rec['action_id']
        return call

    again = runner.run(agent)
    diffs = [k for k in ('scenario_id', 'horizon_days', 'status', 'initial', 'final_state', 'scorecard')
             if again[k] != transcript[k]]
    if len(again['attempts']) != len(attempts):
        diffs.append('attempt_count')
    diffs += [f"attempt {o['seq']}" for o, n in zip(attempts, again['attempts']) if o != n]
    return (not diffs), diffs
