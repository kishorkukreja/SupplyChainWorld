"""Mutations of recorded S01 histories, claimed scorecards and action logs.

Used by the Hypothesis mutation tests and by scripts/s01_audit_summary.py (which reports kill counts).
A mutation returns (mutated_value, description) or (None, description) when it could not be applied.
`semantic_key` says when two histories are the same record for the verifier's purposes, so that a
mutation which changes nothing that matters (for example dropping a zero-unit production release,
which produces and consumes nothing) is not counted as a surviving mutant.
"""
import json
from copy import deepcopy

OPS = ('drop', 'duplicate', 'swap_adjacent', 'swap_far', 'change_number', 'change_kind', 'flip_accepted', 'shift_day')
KNOWN_KINDS = ('receipt', 'opening_before_notice', 'signal', 'notice', 'day_open', 'recovery', 'release',
               'day_close', 'close_day', 'episode_complete')
KINDS = ('release', 'recovery', 'day_close', 'receipt', 'notice', 'bogus')


def _leaves(node, path=()):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _leaves(v, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _leaves(v, path + (i,))
    else:
        yield path, node


def _set(node, path, value):
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = value


def mutate_history(history, rnd, op=None):
    """Apply one random mutation (drop, duplicate, reorder, change an amount, retype, flip, shift a day)."""
    h = deepcopy(history)
    op = op or rnd.choice(OPS)
    i = rnd.randrange(len(h))
    desc = {'op': op, 'event': h[i]['kind']}
    if op == 'drop':
        del h[i]
    elif op == 'duplicate':
        h.insert(i, deepcopy(h[i]))
    elif op == 'swap_adjacent':
        if i + 1 >= len(h):
            return None, desc
        desc['with'] = h[i + 1]['kind']
        h[i], h[i + 1] = h[i + 1], h[i]
    elif op == 'swap_far':
        j = rnd.randrange(len(h))
        desc['with'] = h[j]['kind']
        h[i], h[j] = h[j], h[i]
    elif op == 'change_number':
        section = rnd.choice(['details', 'state'])
        numbers = [(p, v) for p, v in _leaves(h[i].get(section, {})) if type(v) is int]
        if not numbers:
            return None, desc
        path, value = rnd.choice(numbers)
        new = rnd.choice([value + 1, value - 1, value * 2, 0, -1, value + 7])
        new = value + 1 if new == value else new
        _set(h[i][section], path, new)
        desc.update(section=section, field='.'.join(str(p) for p in path))
    elif op == 'change_kind':
        h[i]['kind'] = rnd.choice(KINDS)
    elif op == 'flip_accepted':
        h[i]['accepted'] = not h[i]['accepted']
    else:
        h[i]['day'] += rnd.choice([-1, 1, 2])
    return h, desc


def semantic_key(history):
    """The history without records the verifier cannot or need not tell apart.

    Removed: records of a kind the verifier does not know, accepted production releases of zero units (they
    produce and consume nothing) and every REJECTED
    command record. A rejected command changes no state, so from the history alone nobody can tell whether it
    was deleted, repeated or moved; the runner transcript and `replay` protect that audit trail instead
    (see test_s01_versions_fuzz.py, damaged transcripts).
    """
    def noise(e):
        if e['kind'] == 'release' and e.get('accepted') is True and (e.get('details') or {}).get('quantity') == 0:
            return True
        if e['kind'] not in KNOWN_KINDS:      # the verifier ignores record kinds it does not know
            return True
        return e['kind'] in ('release', 'recovery', 'close_day') and e.get('accepted') is False
    return json.dumps([e for e in history if not noise(e)], sort_keys=True)


def mutate_scorecard(card, rnd):
    """Change one number in a claimed scorecard."""
    c = deepcopy(card)
    numbers = [(p, v) for p, v in _leaves(c) if type(v) is int]
    if not numbers:
        return None, {'op': 'scorecard'}
    path, value = rnd.choice(numbers)
    _set(c, path, value + rnd.choice([1, -1, 5]))
    return c, {'op': 'scorecard', 'field': '.'.join(str(p) for p in path)}


def mutate_actions(actions, rnd):
    """Drop, duplicate or retarget one entry of a claimed action log."""
    a = deepcopy(actions)
    if not a:
        return None, {'op': 'actions'}
    i = rnd.randrange(len(a))
    op = rnd.choice(['drop', 'duplicate', 'change_argument'])
    if op == 'drop':
        del a[i]
    elif op == 'duplicate':
        a.insert(i, deepcopy(a[i]))
    else:
        args = a[i]['arguments']
        key = next(iter(args), None)
        if key is None or type(args[key]) is not int:
            return None, {'op': 'actions'}
        args[key] += 1
    return a, {'op': 'actions:' + op}
