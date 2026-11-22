"""Hypothesis generators for fuzz tests: malformed and adversarial inputs.

All strategies are plain Hypothesis strategies, so tests combine them with
`@given(...)`. Generators named `*_invalid_*` are invalid by construction: the
runner must reject them, which lets a test assert `accepted is False` rather
than only "did not crash".
"""
import json
from copy import deepcopy

from hypothesis import strategies as st

TOOL_NAMES = ('read_state', 'read_recovery_offers', 'read_scorecard',
              'commit_recovery', 'release_production', 'advance_day')
HIDDEN_WORDS = ('scenario', 'future', 'calendar', 'schedule', 'hidden', 'answer',
                'oracle', 'history', 'reset', 'seed', 'config', 'expected', 'baseline')

# Any JSON-serializable value, including nested containers and odd numbers.
json_scalars = st.one_of(
    st.none(), st.booleans(),
    st.integers(min_value=-2**70, max_value=2**70),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=20))
json_blobs = st.recursive(
    json_scalars,
    lambda inner: st.one_of(st.lists(inner, max_size=4),
                            st.dictionaries(st.text(max_size=8), inner, max_size=4)),
    max_leaves=12)

# Python values that are NOT valid JSON (the runner must refuse, not crash).
non_json_values = st.sampled_from([float('nan'), float('inf'), -float('inf'), {1, 2}, b'x', object, ...])

# Integers that are wrong for a quantity: negative, huge, or the wrong type.
bad_quantities = st.one_of(
    st.integers(max_value=-1),
    st.integers(min_value=10**6, max_value=2**70),
    st.floats(allow_nan=False, allow_infinity=False), st.booleans(), st.none(),
    st.text(max_size=5), st.lists(st.integers(), max_size=2))

hidden_probe_names = st.builds(lambda w, pre, post: pre + w + post,
                               st.sampled_from(HIDDEN_WORDS), st.sampled_from(['', 'get_', 'read_']),
                               st.sampled_from(['', '_now', 'X']))
unknown_tools = st.one_of(st.text(max_size=12).filter(lambda t: t not in TOOL_NAMES), hidden_probe_names)


def _call(tool, arguments, **extra):
    return {'tool': tool, **({} if arguments is None else {'arguments': arguments}), **extra}


@st.composite
def malformed_tool_calls(draw):
    """A tool-call-shaped value that the runner must refuse (never accepted)."""
    kind = draw(st.sampled_from(['unknown_tool', 'non_dict_args', 'extra_args',
                                 'bad_quantity', 'bad_choice', 'hidden_arg', 'bad_action_id',
                                 'not_a_dict', 'bad_section']))
    if kind == 'unknown_tool':
        return _call(draw(unknown_tools), draw(st.one_of(st.none(), st.dictionaries(st.text(max_size=5), json_blobs, max_size=3))))
    if kind == 'non_dict_args':
        return _call(draw(st.sampled_from(TOOL_NAMES)),
                     draw(st.one_of(st.lists(json_blobs, max_size=3), st.text(max_size=5), st.integers(), st.booleans())))
    if kind == 'extra_args':
        key = draw(st.text(min_size=1, max_size=8).filter(lambda k: k not in ('quantity', 'choice', 'section')))
        return _call(draw(st.sampled_from(TOOL_NAMES)), {key: draw(json_blobs)})
    if kind == 'bad_quantity':
        return _call('release_production', {'quantity': draw(bad_quantities)})
    if kind == 'bad_choice':
        return _call('commit_recovery', {'choice': draw(st.one_of(
            st.text(max_size=10).filter(lambda c: c not in ('maintain', 'expedite', 'alternate')),
            st.integers(), st.none(), st.lists(st.text(max_size=3), max_size=2)))})
    if kind == 'hidden_arg':
        return _call(draw(st.sampled_from(TOOL_NAMES)), {draw(hidden_probe_names): draw(json_blobs)})
    if kind == 'bad_action_id':
        return _call('advance_day', {}, action_id=draw(st.one_of(st.just(''), st.integers(), st.lists(st.text(max_size=2), max_size=2))))
    if kind == 'bad_section':
        return _call('read_state', {'section': draw(st.one_of(hidden_probe_names, st.integers(), st.text(max_size=8).filter(lambda s: s not in ('all', 'clock', 'state', 'rules'))))})
    return draw(st.one_of(st.none(), st.integers(), st.text(max_size=5), st.lists(json_blobs, max_size=3)))


@st.composite
def valid_call_sequences(draw, max_len=40):
    """Well-formed tool calls with random arguments. The world may still reject
    them (wrong day, over capacity, repeated commit); that is the point."""
    one_call = st.one_of(
        st.builds(lambda c: {'tool': 'commit_recovery', 'arguments': {'choice': c}},
                  st.sampled_from(['maintain', 'expedite', 'alternate'])),
        st.builds(lambda q: {'tool': 'release_production', 'arguments': {'quantity': q}},
                  st.integers(min_value=0, max_value=6)),
        st.just({'tool': 'advance_day', 'arguments': {}}),
        st.just({'tool': 'read_state', 'arguments': {}}),
        st.just({'tool': 'read_recovery_offers', 'arguments': {}}))
    return draw(st.lists(one_call, max_size=max_len))


def mutate_transcript(transcript, draw):
    """Return a damaged deep copy of a recorded transcript (using a `draw` function).

    Mutations: delete a key, replace a value with a JSON blob, drop or duplicate
    or reorder attempts, or truncate. Used to check replay/verifier reject cleanly.
    """
    t = deepcopy(transcript)
    attempts = t.get('attempts', [])
    kind = draw(st.sampled_from(['drop_key', 'replace_value', 'drop_attempt', 'dup_attempt',
                                 'swap_attempts', 'truncate']))
    if kind == 'drop_key':
        key = draw(st.sampled_from(sorted(t)))
        del t[key]
    elif kind == 'replace_value':
        key = draw(st.sampled_from(sorted(t)))
        t[key] = draw(json_blobs)
    elif attempts:
        i = draw(st.integers(min_value=0, max_value=len(attempts) - 1))
        if kind == 'drop_attempt':
            del attempts[i]
        elif kind == 'dup_attempt':
            attempts.insert(i, deepcopy(attempts[i]))
        elif kind == 'swap_attempts' and len(attempts) > 1:
            j = (i + 1) % len(attempts)
            attempts[i], attempts[j] = attempts[j], attempts[i]
        elif kind == 'truncate':
            del attempts[i:]
    return json.loads(json.dumps(t))


@st.composite
def mutated_transcripts(draw, transcript):
    """Strategy form of `mutate_transcript` for a given recorded transcript."""
    return mutate_transcript(transcript, draw)
