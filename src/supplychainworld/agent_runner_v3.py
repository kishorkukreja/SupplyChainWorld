"""Tool layer, observable runner, replay and scripted policies for the S01 v0.3 family (issue #36, round 2).

Additive: `agent_runner.py` (v0.1) is unchanged and this module reuses its runner machinery by
subclassing. The tool names are the v0.1 names; `commit_recovery` gains a `quantity` argument, may
be called several times (each call needs its own `action_id`, a repeat is refused), and accepts
`expedite` or `alternate` (not committing is the maintain policy).

Same security note as v0.1: an information and authority boundary for well-behaved in-process
policies, not a sandbox against hostile code. Scripted policies are not LLMs and prove nothing about
model ability.
"""
import json
from copy import deepcopy

from .agent_runner import (HIDDEN_MARKERS, READ_SECTIONS, ObservableRunner, _ReplayedAgentError,  # noqa: F401
                           _is_hidden_probe)
from .dynamic_v3 import OperationalWorldV3

TRANSCRIPT_SCHEMA_V3 = 'dyn06-transcript-3'
TOOLS_V3 = {
    'read_state': ('read', ('section',)),
    'read_recovery_offers': ('read', ()),
    'read_scorecard': ('read', ()),
    'commit_recovery': ('commit', ('choice', 'quantity')),
    'release_production': ('commit', ('quantity',)),
    'advance_day': ('advance', ()),
}
POLICIES_V3 = ('maintain', 'expedite_on_alert', 'alternate_on_alert', 'combo_on_alert', 'staged_revisit')


class ObservableRunnerV3(ObservableRunner):
    def __init__(self, world: OperationalWorldV3, *, granted=('read', 'commit', 'advance'),
                 max_attempts_per_day=12, max_total_attempts=500):
        if not isinstance(world, OperationalWorldV3):
            raise TypeError('world must be an OperationalWorldV3')
        for name, value in (('max_attempts_per_day', max_attempts_per_day), ('max_total_attempts', max_total_attempts)):
            if type(value) is not int or value < 1:
                raise ValueError(f'{name} must be a positive integer')
        if not set(granted) <= {'read', 'commit', 'advance'}:
            raise ValueError('unknown authority class')
        self._world = world
        self._granted = tuple(sorted(granted))
        self._per_day = max_attempts_per_day
        self._total = max_total_attempts
        self._reset_log()

    def tool_definitions(self):
        defs = []
        for name, (authority, args) in TOOLS_V3.items():
            spec = {'name': name, 'authority': authority, 'arguments': list(args),
                    'granted': authority in self._granted, 'advances_time': name == 'advance_day',
                    'commits_resources': authority == 'commit'}
            if name == 'commit_recovery':
                spec.update(choices=['expedite', 'alternate'], repeatable=True, quantity_in_units=True,
                            note='each commitment needs its own action_id and executes once; price and arrival follow the rate card for the day')
            if name == 'release_production':
                spec['once_per_day'] = True
            if name == 'read_scorecard':
                spec['available_when'] = 'episode complete'
            defs.append(spec)
        return defs

    def _validate(self, call, state):
        tool, args = call.get('tool'), call.get('arguments', {})
        if not isinstance(tool, str) or tool not in TOOLS_V3:
            if _is_hidden_probe(tool):
                return 'hidden_state', 'tool would expose hidden scenario or future state'
            return 'unknown_tool', 'unknown tool'
        if not isinstance(args, dict):
            return 'invalid_arguments', 'arguments must be an object'
        authority, allowed = TOOLS_V3[tool]
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
            return w.choose_recovery(args.get('choice'), args.get('quantity'), commit_id=call.get('action_id'))
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
        if 'window' in r:
            return 'deadline'
        if 'budget' in r:
            return 'budget'
        if 'duplicate' in r or 'already released' in r:
            return 'repeated_commitment'
        return 'invalid_action'

    def transcript(self):
        out = super().transcript()
        out['schema'] = TRANSCRIPT_SCHEMA_V3
        return out


def replay_v3(transcript, world_factory):
    """Re-run a recorded interaction on a fresh v0.3 world; returns (ok, differences)."""
    if transcript.get('schema') != TRANSCRIPT_SCHEMA_V3:
        raise ValueError('unsupported transcript schema')
    attempts, limits = transcript['attempts'], transcript['limits']
    runner = ObservableRunnerV3(world_factory(), granted=tuple(transcript['granted_authority']),
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


# ----------------------------------------------------------------------------- scripted policies

def _alert(state):
    return bool(state['signals'] or state['notices'])


def _firm_delay(state):
    return any(n['kind'] == 'delay_confirmed' for n in state['notices'])


def _affordable(units, offer, budget):
    if not offer:
        return 0
    cap = offer['max_units'] if offer['unit_cost'] == 0 else min(offer['max_units'], budget // offer['unit_cost'])
    return max(0, min(units, cap))


def _plan(policy, view):
    """Recovery commitments to try today, as (choice, quantity), from the visible view only."""
    state, rules = view['state'], view['rules']
    offers = rules.get('recovery_offers')
    if not offers or policy == 'maintain':
        return []
    exp, alt = offers['expedite']['today'], offers['alternate']['today']
    budget = offers['budget_remaining']
    made = state['commitments']
    plan = []
    if policy == 'staged_revisit':
        if not made:
            if exp:
                plan.append(('expedite', _affordable(exp['max_units'] // 2, exp, budget)))
        elif len(made) == 1 and made[0]['day'] < state['day'] and _firm_delay(state) and exp:
            plan.append(('expedite', _affordable(exp['max_units'], exp, budget)))
    elif not made:
        if policy == 'expedite_on_alert' and exp:
            plan.append(('expedite', _affordable(exp['max_units'], exp, budget)))
        elif policy == 'alternate_on_alert' and alt:
            plan.append(('alternate', _affordable(alt['max_units'], alt, budget)))
        elif policy == 'combo_on_alert':
            if exp:
                q = _affordable(exp['max_units'] // 2, exp, budget)
                plan.append(('expedite', q))
                budget -= q * exp['unit_cost']
            if alt:
                plan.append(('alternate', _affordable(alt['max_units'] // 2, alt, budget)))
    return [(c, q) for c, q in plan if q > 0]


def scripted_policy_v3(policy):
    """Scripted (non-LLM) agent that reads only its view. Not a proof of optimality."""
    if policy not in POLICIES_V3:
        raise ValueError('unknown policy')
    memo = {'day': None, 'queue': []}

    def agent(view):
        state, rules = view['state'], view['rules']
        if memo['day'] != state['day']:
            memo['day'] = state['day']
            memo['queue'] = _plan(policy, view)
        if memo['queue']:
            choice, quantity = memo['queue'].pop(0)
            return {'tool': 'commit_recovery', 'arguments': {'choice': choice, 'quantity': quantity}}
        if state['scheduled_production'] is None:
            quantity = min(rules['capacity'], state['component_on_hand'],
                           max(0, state['open_demand'] - state['finished_on_hand']))
            return {'tool': 'release_production', 'arguments': {'quantity': quantity}}
        return {'tool': 'advance_day', 'arguments': {}}

    return agent
