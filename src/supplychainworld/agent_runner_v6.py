"""Tool layer, observable runner, replay, scripted policies and the stated-rules table for S01 v0.6 (issue #19).

The v0.5 runner and policies are reused by subclassing and import. New in v0.6:

* `RULES_V6`: the v0.5 table with the exact-once rule restated for the no-action-id case, plus one sentence per
  convention of the world's `conventions` block (`dynamic_v6.CONVENTION_STATEMENTS`), so the model-facing prompt and
  the agent-visible block say the same thing and are built from one source.
* `REJECTION_RULES_V6`: every refusal reason the v0.6 world or runner can produce maps to a stated rule (a test reads
  the source of the v0.6 world and runner, finds every reason literal, and fails if one is unmapped or its sentence is
  missing from the prompt or the tool descriptions).
* Transcript schema label, accepted world type and replay for v0.6.

Scripted policies are not LLMs and prove nothing about model ability. All numbers are PROVISIONAL, needs practitioner value.
"""
from .agent_runner import _ReplayedAgentError
from .agent_runner_v5 import (MAX_ATTEMPTS_PER_DAY, MAX_TOTAL_ATTEMPTS, POLICIES_V5, REJECTION_RULES, RULES,  # noqa: F401
                              TOOL_RULES, ObservableRunnerV5, scripted_policy_v5)
from .dynamic_v6 import AUTO_PREFIX, CONVENTION_STATEMENTS, OperationalWorldV6

TRANSCRIPT_SCHEMA_V6 = 'dyn06-transcript-6'
POLICIES_V6 = POLICIES_V5

RULES_V6 = dict(RULES)
RULES_V6['once_only'] = (
    'A recovery purchase cannot be undone and each purchase executes once: a repeated action id is refused, and so is '
    'the same purchase (same day, choice and quantity) repeated on the same day without a distinct action id. Send a '
    'distinct action_id for each lot you buy on purpose; ids starting with %s are reserved.' % AUTO_PREFIX)
# Conventions: one rule entry per convention sentence. They are consequences of the world, not refusals.
CONVENTION_RULE_IDS = tuple('convention_' + k for k in CONVENTION_STATEMENTS)
for _k, _sentence in CONVENTION_STATEMENTS.items():
    RULES_V6['convention_' + _k] = _sentence

REJECTION_RULES_V6 = (
    ('the same purchase was already made today', 'once_only'),
    ('prefix auto- is reserved', 'once_only'),
) + tuple(REJECTION_RULES)
TOOL_RULES_V6 = dict(TOOL_RULES)
TOOL_RULES_V6['read_state'] = TOOL_RULES['read_state'] + CONVENTION_RULE_IDS


def rule_for_reason_v6(reason):
    """The rule id that explains a v0.6 rejection reason text, or None when no rule is mapped."""
    for phrase, rule in REJECTION_RULES_V6:
        if phrase in reason:
            return rule
    return None


class ObservableRunnerV6(ObservableRunnerV5):
    def __init__(self, world: OperationalWorldV6, *, granted=('read', 'commit', 'advance'),
                 max_attempts_per_day=MAX_ATTEMPTS_PER_DAY, max_total_attempts=MAX_TOTAL_ATTEMPTS):
        if not isinstance(world, OperationalWorldV6):
            raise TypeError('world must be an OperationalWorldV6')
        super().__init__(world, granted=granted, max_attempts_per_day=max_attempts_per_day,
                         max_total_attempts=max_total_attempts)

    def tool_definitions(self):
        defs = super().tool_definitions()
        for spec in defs:
            spec['rules'] = list(TOOL_RULES_V6.get(spec['name'], ()))
            if spec['name'] == 'commit_recovery':
                spec['note'] = ('each purchase executes once; send a distinct action_id for each lot you buy on purpose '
                                '(the same purchase repeated on one day without one is refused); price and arrival '
                                'follow the rate card for the day')
        return defs

    def transcript(self):
        out = super().transcript()
        out['schema'] = TRANSCRIPT_SCHEMA_V6
        return out


def scripted_policy_v6(policy):
    return scripted_policy_v5(policy)


def replay_v6(transcript, world_factory):
    """Re-run a recorded interaction on a fresh v0.6 world; returns (ok, differences)."""
    if transcript.get('schema') != TRANSCRIPT_SCHEMA_V6:
        raise ValueError('unsupported transcript schema')
    attempts, limits = transcript['attempts'], transcript['limits']
    runner = ObservableRunnerV6(world_factory(), granted=tuple(transcript['granted_authority']),
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
