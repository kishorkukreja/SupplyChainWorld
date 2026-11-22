"""Operational tool layer and observable multi-day runner for S01 (issue #24).

An agent receives only a detached *view* (clock, visible state, visible rules,
tool definitions, last outcome) and returns tool calls. The runner owns the
`OperationalWorld`, validates every call, executes it and keeps a chronological,
replayable transcript of every attempt, accepted or rejected.

Security note: this is an information and authority boundary for well-behaved
in-process policies and for rejecting malformed or probing tool calls. It is NOT
a sandbox against hostile Python code, which could inspect the process.
"""
import json
from copy import deepcopy

from .dynamic import OperationalWorld

TRANSCRIPT_SCHEMA = 'dyn03-transcript-1'

# name -> (authority class, allowed argument names)
TOOLS = {
    'read_state': ('read', ('section',)),
    'read_recovery_offers': ('read', ()),
    'read_scorecard': ('read', ()),
    'commit_recovery': ('commit', ('choice',)),
    'release_production': ('commit', ('quantity',)),
    'advance_day': ('advance', ()),
}
READ_SECTIONS = ('all', 'clock', 'state', 'rules')
# Names and sections that would expose scenario mechanics or other hidden state.
HIDDEN_MARKERS = ('scenario', 'future', 'calendar', 'schedule', 'hidden', 'answer', 'oracle',
                  'history', 'reset', 'seed', 'config', 'expected', 'baseline')


def _is_hidden_probe(text):
    return isinstance(text, str) and any(m in text.lower() for m in HIDDEN_MARKERS)


def _diff(before, after):
    return {k: [before[k], after[k]] for k in after if before.get(k) != after[k]}


class _ReplayedAgentError(Exception):
    pass


class ObservableRunner:
    def __init__(self, world: OperationalWorld, *, granted=('read', 'commit', 'advance'),
                 max_attempts_per_day=12, max_total_attempts=500):
        if not isinstance(world, OperationalWorld):
            raise TypeError('world must be an OperationalWorld')
        for name, value in (('max_attempts_per_day', max_attempts_per_day),
                            ('max_total_attempts', max_total_attempts)):
            if type(value) is not int or value < 1:
                raise ValueError(f'{name} must be a positive integer')
        if not set(granted) <= {'read', 'commit', 'advance'}:
            raise ValueError('unknown authority class')
        self._world = world
        self._granted = tuple(sorted(granted))
        self._per_day = max_attempts_per_day
        self._total = max_total_attempts
        self._reset_log()

    # ----- agent-visible information -----
    def _clock(self, state):
        d, h = state['day'], state['horizon_days']
        return {'current_day': d, 'horizon_days': h, 'days_remaining_after_today': h - d,
                'phase': state['phase'], 'is_final_day': d == h,
                'simulated_time': f"day {d} of {h}, {state['phase']} phase"}

    def tool_definitions(self):
        offers = self._world.observation()['rules'].get('recovery_offers')
        defs = []
        for name, (authority, args) in TOOLS.items():
            spec = {'name': name, 'authority': authority, 'arguments': list(args),
                    'granted': authority in self._granted,
                    'advances_time': name == 'advance_day',
                    'commits_resources': authority == 'commit'}
            if name == 'commit_recovery':
                spec['choices'] = ['maintain', 'expedite', 'alternate']
                spec['deadline_day'] = offers['deadline_day'] if offers else None
                spec['once_only'] = True
            if name == 'release_production':
                spec['once_per_day'] = True
            if name == 'read_scorecard':
                spec['available_when'] = 'episode complete'
            defs.append(spec)
        return defs

    def view(self):
        obs = self._world.observation()
        return {'clock': self._clock(obs['state']), 'state': obs['state'], 'rules': obs['rules'],
                'tools': self.tool_definitions(), 'last_outcome': deepcopy(self._last_outcome)}

    # ----- execution -----
    def _reset_log(self):
        self._attempts = []
        self._action_ids = set()
        self._day_attempts = {}
        self._last_outcome = None
        self._cursor = 0
        self._status = 'not_started'
        self._initial = None

    def _new_events(self):
        events = self._world.history()
        fresh = [{k: e[k] for k in ('day', 'kind', 'details', 'accepted', 'reason')}
                 for e in events[self._cursor:]]
        self._cursor = len(events)
        return fresh

    def _validate(self, call, state):
        """Return (category, reason) when the runner itself must refuse the call."""
        tool, args = call.get('tool'), call.get('arguments', {})
        if not isinstance(tool, str) or tool not in TOOLS:
            if _is_hidden_probe(tool):
                return 'hidden_state', 'tool would expose hidden scenario or future state'
            return 'unknown_tool', 'unknown tool'
        if not isinstance(args, dict):
            return 'invalid_arguments', 'arguments must be an object'
        authority, allowed = TOOLS[tool]
        if authority not in self._granted:
            return 'authority', f'{authority} authority not granted'
        extra = sorted(str(k) for k in args if k not in allowed)
        if extra:
            if any(_is_hidden_probe(k) for k in extra):
                return 'hidden_state', 'argument requests hidden scenario or future state'
            return 'invalid_arguments', 'unexpected arguments: ' + ', '.join(extra)
        try:
            json.dumps(args)
        except (TypeError, ValueError):
            return 'invalid_arguments', 'arguments must be JSON serializable'
        action_id = call.get('action_id')
        if action_id is not None:
            if not isinstance(action_id, str) or not action_id:
                return 'invalid_arguments', 'action_id must be a nonempty string'
            if action_id in self._action_ids:
                return 'repeated_commitment', 'action_id already used; commitments are not retried'
        if tool == 'read_state':
            section = args.get('section', 'all')
            if _is_hidden_probe(section):
                return 'hidden_state', 'section would expose hidden scenario or future state'
            if section not in READ_SECTIONS:
                return 'invalid_arguments', 'unknown section'
        if tool == 'read_scorecard' and state['phase'] != 'complete':
            return 'unavailable', 'scorecard requires completed episode'
        if tool != 'advance_day' and self._day_attempts.get(state['day'], 0) >= self._per_day \
                and state['phase'] == 'action':
            return 'attempt_limit', 'per-day attempt limit reached; advance the day'
        return None

    def _execute(self, call, state):
        tool, args = call['tool'], call.get('arguments', {})
        w = self._world
        if tool == 'read_state':
            v = self.view()
            section = args.get('section', 'all')
            return {'accepted': True, 'data': v if section == 'all' else v[section]}
        if tool == 'read_recovery_offers':
            offers = w.observation()['rules'].get('recovery_offers')
            return {'accepted': True, 'data': {'available': offers is not None, 'offers': offers}}
        if tool == 'read_scorecard':
            return {'accepted': True, 'data': w.scorecard()}
        if tool == 'commit_recovery':
            return w.choose_recovery(args.get('choice'))
        if tool == 'release_production':
            return w.release_production(args.get('quantity'))
        before_day = state['day']
        result = w.close_day()
        if isinstance(result, dict) and result.get('accepted') is False:
            return result
        return {'accepted': True, 'closed_day': before_day}

    @staticmethod
    def _category(reason):
        r = reason or ''
        if 'deadline' in r:
            return 'deadline'
        if 'already committed' in r or 'already released' in r:
            return 'repeated_commitment'
        return 'invalid_action'

    def attempt(self, call):
        """Execute one tool call and append a chronological attempt record."""
        if not isinstance(call, dict):
            call = {'tool': None, 'arguments': {}}
        view_before = self.view()
        state = view_before['state']
        snap_before = deepcopy(state)
        refusal = self._validate(call, state)
        if refusal:
            result = {'accepted': False, 'reason': refusal[1]}
            category = refusal[0]
        else:
            result = self._execute(call, state)
            category = None if result.get('accepted') else self._category(result.get('reason'))
        # A refused call still consumes the attempt budget and the action id.
        action_id = call.get('action_id')
        if isinstance(action_id, str) and action_id:
            self._action_ids.add(action_id)
        self._day_attempts[state['day']] = self._day_attempts.get(state['day'], 0) + 1
        snap_after = self._world.snapshot()
        try:
            arguments = json.loads(json.dumps(call.get('arguments', {})))
        except (TypeError, ValueError):
            arguments = {'unserializable': repr(call.get('arguments'))}
        record = {'seq': len(self._attempts) + 1, 'day': state['day'],
                  'tool': call.get('tool') if isinstance(call.get('tool'), str) else repr(call.get('tool')),
                  'arguments': arguments, 'action_id': action_id if isinstance(action_id, str) else None,
                  'accepted': bool(result.get('accepted')), 'category': category,
                  'reason': result.get('reason'), 'result': deepcopy(result),
                  'view_before': view_before,
                  'state_changes': _diff(snap_before, snap_after),
                  'events': self._new_events()}
        self._attempts.append(record)
        self._last_outcome = {'seq': record['seq'], 'tool': record['tool'], 'accepted': record['accepted'],
                              'category': category, 'reason': record['reason']}
        return record

    def run(self, agent, *, reset=True):
        """Drive `agent(view) -> call | None` until completion or failure.

        Agent exceptions are recorded, not raised, so failure histories survive.
        """
        if reset:
            self._world.reset()
        self._reset_log()
        self._cursor = 0
        self._initial = {'view': self.view(), 'events': self._new_events()}
        self._status = 'running'
        while True:
            if self._world.snapshot()['phase'] == 'complete':
                self._status = 'complete'
                break
            if len(self._attempts) >= self._total:
                self._status = 'attempt_budget_exhausted'
                break
            view = self.view()
            try:
                call = agent(deepcopy(view))
            except Exception as exc:  # noqa: BLE001 - failure history is a requirement
                text = str(exc) if isinstance(exc, _ReplayedAgentError) else f'{type(exc).__name__}: {exc}'
                self._attempts.append({'seq': len(self._attempts) + 1, 'day': view['state']['day'],
                                       'tool': None, 'arguments': {}, 'action_id': None, 'accepted': False,
                                       'category': 'agent_error', 'reason': text, 'result': {'accepted': False, 'reason': text},
                                       'view_before': view, 'state_changes': {}, 'events': []})
                self._status = 'agent_error'
                break
            if call is None:
                self._status = 'agent_stopped'
                break
            self.attempt(call)
        return self.transcript()

    def transcript(self):
        s = self._world.snapshot()
        out = {'schema': TRANSCRIPT_SCHEMA, 'scenario_id': s['scenario_id'], 'horizon_days': s['horizon_days'],
               'granted_authority': list(self._granted), 'limits': {'max_attempts_per_day': self._per_day,
                                                                      'max_total_attempts': self._total},
               'status': self._status, 'initial': deepcopy(self._initial), 'attempts': deepcopy(self._attempts),
               'final_state': s}
        out['scorecard'] = self._world.scorecard() if s['phase'] == 'complete' else None
        return json.loads(json.dumps(out))


def replay(transcript, world_factory):
    """Re-run a recorded observable interaction on a fresh world.

    Returns (ok, differences). The replayed agent only emits the recorded calls
    (and recorded agent failures); everything else, including views, outcomes,
    state changes and the scorecard, must be reproduced by the world itself.
    """
    if transcript.get('schema') != TRANSCRIPT_SCHEMA:
        raise ValueError('unsupported transcript schema')
    attempts = transcript['attempts']
    limits = transcript['limits']
    runner = ObservableRunner(world_factory(), granted=tuple(transcript['granted_authority']),
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
    diffs = []
    for key in ('scenario_id', 'horizon_days', 'status', 'initial', 'final_state', 'scorecard'):
        if again[key] != transcript[key]:
            diffs.append(key)
    if len(again['attempts']) != len(attempts):
        diffs.append('attempt_count')
    for old, new in zip(attempts, again['attempts']):
        if old != new:
            diffs.append(f"attempt {old['seq']}")
    return (not diffs), diffs


def scripted_policy(policy):
    """A scripted (non-LLM) agent that only reads its view. Not a proof of optimality."""
    if policy not in ('maintain', 'expedite', 'alternate'):
        raise ValueError('unknown policy')

    tried = {'recovery': False}   # a refused recovery (for example over budget) is not retried forever

    def agent(view):
        state, rules = view['state'], view['rules']
        offers = rules.get('recovery_offers')
        if state['notices'] and state['recovery'] is None and offers and state['day'] <= offers['deadline_day'] \
                and not tried['recovery']:
            tried['recovery'] = True
            return {'tool': 'commit_recovery', 'arguments': {'choice': policy}}
        if state['scheduled_production'] is None:
            quantity = min(rules['capacity'], state['component_on_hand'], rules['required'] - state['produced_total'])
            return {'tool': 'release_production', 'arguments': {'quantity': quantity}}
        return {'tool': 'advance_day', 'arguments': {}}

    return agent
