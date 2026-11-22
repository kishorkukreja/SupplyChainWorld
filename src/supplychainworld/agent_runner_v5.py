"""Tool layer, observable runner, replay, scripted policies and the stated-rules table for S01 v0.5 (issue #19 fixes).

The v0.4 runner and policies are reused unchanged by subclassing and import. What is new:

* `RULES`: ONE written sentence for every rule the world and the runner enforce (finding 2, harness gap: the
  rule that production cannot exceed open customer demand was enforced but never stated to the model). The
  model-facing prompt and tool descriptions in `eval19_v2` are BUILT from this table, so they cannot drift.
* `REJECTION_RULES`: maps every rejection reason the world or the runner can produce (matched by a phrase of the
  reason text) to the rule that explains it. A test reads the source of the world and the runner, finds every
  rejection reason literal, and fails if one is not mapped, and fails if a mapped sentence is missing from the
  prompt or the tool descriptions. A new rejection without a stated rule therefore fails the suite.
* Transcript schema label, accepted world type and replay factory for v0.5.

Scripted policies are not LLMs and prove nothing about model ability. All numbers are PROVISIONAL, needs
practitioner value.
"""
from .agent_runner import _ReplayedAgentError
from .agent_runner_v3 import POLICIES_V3, scripted_policy_v3  # noqa: F401
from .agent_runner_v4 import ObservableRunnerV4
from .dynamic_v5 import OperationalWorldV5

TRANSCRIPT_SCHEMA_V5 = 'dyn06-transcript-5'
POLICIES_V5 = POLICIES_V3
MAX_ATTEMPTS_PER_DAY = 12
MAX_TOTAL_ATTEMPTS = 500

# rule id -> the sentence shown to the model. Plain statements of what is enforced.
RULES = {
    'episode_closed': 'Once the episode phase is complete no further action is accepted.',
    'alert_first': ('Recovery can be bought only after a possible-delay signal or a firm notice is visible in the state.'),
    'recovery_choice': 'A recovery choice is either expedite or alternate.',
    'whole_units': ('Quantities are whole numbers of units: at least 1 for a recovery lot and 0 or more for a '
                    'production release.'),
    'offer_window': ('A recovery offer is open only on days that have a row in its rate card; expedite works only '
                     'while the primary lot has not yet arrived and the expedited arrival is earlier than the '
                     'current one, and alternate works only until its maximum units are bought.'),
    'offer_units': 'A recovery lot cannot be larger than the max_units shown for that offer today.',
    'budget': ('Total recovery spend cannot go above the recovery budget; each unit costs the rate-card premium '
               'for the day you buy it (the base unit cost of a recovery lot is cost-neutral and not counted).'),
    'once_only': ('A recovery purchase cannot be undone and each purchase executes once; a repeated action id is '
                  'refused.'),
    'one_release': 'Production can be released only once per day.',
    'capacity_material': ('A production release cannot be larger than the daily capacity or the components on '
                          'hand.'),
    'demand_cap': ('Production cannot exceed open customer demand: a release plus the finished goods already on '
                   'hand cannot be more than open_demand in the state, so it is refused when it would build '
                   'stock beyond what open orders still need.'),
    'attempt_limit': ('At most %d tool calls other than advance_day are accepted per simulated day; after that '
                      'only advance_day works.' % MAX_ATTEMPTS_PER_DAY),
    'tool_surface': ('Only the listed tools, the listed argument names and the listed read sections exist; '
                     'arguments must be a JSON object; unknown tools, extra arguments and requests for hidden or '
                     'future state are refused.'),
    'scorecard_late': 'The scorecard can be read only once the episode is complete.',
    # Consequences of the world that are not refusals, stated so the model is told the whole rule set.
    'shipping': ('Finished goods ship to orders that are due, highest priority tier first; goods are never shipped '
                 'before an order is due.'),
    'penalties_cancel': ('Late penalties and tier cancellation follow the terms shown in the rules: a penalty '
                         'accrues for each day an order is still short from its due day on, following its '
                         'penalty type and cap, and a cancel_after tier cancels the undelivered units that many '
                         'days after the due day.'),
    'salvage': ('Components left on hand at the end earn the class salvage credit, except units presumed to be '
                'left over from an alternate buy, which earn none.'),
}

# phrase found in the reason text -> rule id. Matched as a substring of the reason literal found in the source.
REJECTION_RULES = (
    ('episode is closed', 'episode_closed'),
    ('no disruption alert yet', 'alert_first'),
    ('unknown recovery option', 'recovery_choice'),
    ('quantity must be a positive integer', 'whole_units'),
    ('quantity must be a nonnegative integer', 'whole_units'),
    ('duplicate commitment', 'once_only'),
    ('recovery offer window not open', 'offer_window'),
    ('quantity exceeds units available', 'offer_units'),
    ('recovery budget exceeded', 'budget'),
    ('daily production already released', 'one_release'),
    ('capacity or available material exceeded', 'capacity_material'),
    ('production exceeds open customer demand', 'demand_cap'),
    ('per-day attempt limit reached', 'attempt_limit'),
    ('scorecard requires completed episode', 'scorecard_late'),
    ('action_id already used', 'once_only'),
    ('action_id must be a nonempty string', 'tool_surface'),
    ('tool would expose hidden', 'tool_surface'),
    ('argument requests hidden', 'tool_surface'),
    ('section would expose hidden', 'tool_surface'),
    ('unknown tool', 'tool_surface'),
    ('arguments must be an object', 'tool_surface'),
    ('authority not granted', 'tool_surface'),
    ('unexpected arguments', 'tool_surface'),
    ('arguments must be JSON serializable', 'tool_surface'),
    ('unknown section', 'tool_surface'),
)
# Rules each tool description carries (in this order), besides the base text.
TOOL_RULES = {
    'read_state': ('tool_surface',),
    'read_recovery_offers': (),
    'read_scorecard': ('scorecard_late',),
    'commit_recovery': ('alert_first', 'recovery_choice', 'whole_units', 'offer_window', 'offer_units', 'budget',
                        'once_only'),
    'release_production': ('one_release', 'capacity_material', 'demand_cap', 'whole_units'),
    'advance_day': ('attempt_limit',),
}


def rule_for_reason(reason):
    """The rule id that explains a rejection reason text, or None when no rule is mapped."""
    for phrase, rule in REJECTION_RULES:
        if phrase in reason:
            return rule
    return None


class ObservableRunnerV5(ObservableRunnerV4):
    def __init__(self, world: OperationalWorldV5, *, granted=('read', 'commit', 'advance'),
                 max_attempts_per_day=MAX_ATTEMPTS_PER_DAY, max_total_attempts=MAX_TOTAL_ATTEMPTS):
        if not isinstance(world, OperationalWorldV5):
            raise TypeError('world must be an OperationalWorldV5')
        super().__init__(world, granted=granted, max_attempts_per_day=max_attempts_per_day,
                         max_total_attempts=max_total_attempts)

    def tool_definitions(self):
        defs = super().tool_definitions()
        for spec in defs:
            spec['rules'] = list(TOOL_RULES.get(spec['name'], ()))
        return defs

    def transcript(self):
        out = super().transcript()
        out['schema'] = TRANSCRIPT_SCHEMA_V5
        return out


def scripted_policy_v5(policy):
    return scripted_policy_v3(policy)


def replay_v5(transcript, world_factory):
    """Re-run a recorded interaction on a fresh v0.5 world; returns (ok, differences)."""
    if transcript.get('schema') != TRANSCRIPT_SCHEMA_V5:
        raise ValueError('unsupported transcript schema')
    attempts, limits = transcript['attempts'], transcript['limits']
    runner = ObservableRunnerV5(world_factory(), granted=tuple(transcript['granted_authority']),
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
