"""Strict per-kind submission schema, static rules 1.2.1 (issue #19 fixes, finding 3: submission schema).

Lives beside the frozen 1.2 contract (`schemas_v12.py`); nothing there changes, so the 1.2 tests and fixtures stay
valid. The 1.2.1 addition is only about the SHAPE of a model's answer:

* each answer kind has exactly its own fields, no more and no fewer:
    award          kind, allocations, claimed_total_cost, evidence, flags, clarification_requests, approval_refs
    clarification  kind, field, disposition, evidence
    infeasible     kind, evidence
* an extra field or a missing field is rejected with a message that names the field and the kind;
* the types are not coerced: claimed_total_cost must already be a string, evidence a non-empty list of
  non-empty strings, and a clarification needs a non-empty field and disposition record_and_escalate.

Nothing is repaired, guessed or dropped. A rejected answer gets no credit in the harness, with the messages kept.
Business meaning (cost, feasibility, optimality) is still decided only by the independent 1.2 checker
(`verification_v12`); this module never looks at the world.

`json_schema(kind)` gives the matching tool schema, so a model is offered one tool per kind and an extra field is not
even expressible.
"""
from typing import Any

from pydantic import ValidationError

from .schemas_v12 import parse_submission

VERSION = '1.2.1'
KINDS = ('award', 'clarification', 'infeasible')
FIELDS = {
    'award': ('kind', 'allocations', 'claimed_total_cost', 'evidence', 'flags', 'clarification_requests', 'approval_refs'),
    'clarification': ('kind', 'field', 'disposition', 'evidence'),
    'infeasible': ('kind', 'evidence'),
}


class StrictSubmissionError(ValueError):
    """The answer does not match the 1.2.1 shape. `.problems` lists every reason, one clear message each."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__('; '.join(self.problems))


def _list_of_str(value, name, kind, *, non_empty, problems):
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        problems.append(f'{kind}: {name} must be a list of strings')
    elif non_empty and (not value or any(not x.strip() for x in value)):
        problems.append(f'{kind}: {name} must be a non-empty list of non-empty strings')


def strict_problems(value: Any) -> list[str]:
    """Every reason `value` is not a valid 1.2.1 submission; an empty list means it is valid."""
    if not isinstance(value, dict):
        return ['submission must be a JSON object']
    kind = value.get('kind')
    if not isinstance(kind, str) or kind not in KINDS:
        return [f'kind must be one of {", ".join(KINDS)} (got {kind!r})']
    allowed = FIELDS[kind]
    problems = [f"{kind}: field '{k}' is not allowed (a {kind} takes exactly: {', '.join(allowed)})"
                for k in sorted(set(map(str, value)) - set(allowed))]
    problems += [f"{kind}: missing required field '{k}' (a {kind} takes exactly: {', '.join(allowed)})"
                 for k in allowed if k not in value]
    if problems:
        return problems
    _list_of_str(value['evidence'], 'evidence', kind, non_empty=True, problems=problems)
    if kind == 'award':
        if not isinstance(value['claimed_total_cost'], str) or not value['claimed_total_cost'].strip():
            problems.append('award: claimed_total_cost must be a string such as "123.45"')
        for name in ('flags', 'clarification_requests', 'approval_refs'):
            _list_of_str(value[name], name, kind, non_empty=False, problems=problems)
        if not isinstance(value['allocations'], list) or any(not isinstance(a, dict) for a in value['allocations']):
            problems.append('award: allocations must be a list of {supplier_id, item_id, quantity} objects')
        else:
            for i, a in enumerate(value['allocations']):
                extra = sorted(set(map(str, a)) - {'supplier_id', 'item_id', 'quantity'})
                miss = sorted({'supplier_id', 'item_id', 'quantity'} - set(a))
                problems += [f"award: allocations[{i}] field '{k}' is not allowed" for k in extra]
                problems += [f"award: allocations[{i}] is missing '{k}'" for k in miss]
    elif kind == 'clarification':
        if not isinstance(value['field'], str) or not value['field'].strip():
            problems.append('clarification: field must be a non-empty string naming the missing term or approval')
        if value['disposition'] != 'record_and_escalate':
            problems.append('clarification: disposition must be "record_and_escalate"')
    if problems:
        return problems
    try:
        parse_submission(value)
    except ValidationError as exc:
        return [f"{kind}: {'.'.join(str(p) for p in e['loc']) or 'submission'}: {e['msg']}" for e in exc.errors()]
    return []


def parse_strict_submission(value: Any):
    """Validate against 1.2.1 and return the frozen 1.2 model; raise `StrictSubmissionError` otherwise. Nothing is repaired."""
    problems = strict_problems(value)
    if problems:
        raise StrictSubmissionError(problems)
    return parse_submission(value)


# ------------------------------------------------------------------ tool schemas, one per kind

_STRING_LIST = {'type': 'array', 'items': {'type': 'string'}}
_PROPERTIES = {
    'allocations': {'type': 'array', 'items': {'type': 'object', 'properties': {
        'supplier_id': {'type': 'string'}, 'item_id': {'type': 'string'}, 'quantity': {'type': 'integer', 'minimum': 0}},
        'required': ['supplier_id', 'item_id', 'quantity'], 'additionalProperties': False}},
    'claimed_total_cost': {'type': 'string'},
    'evidence': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1},
    'flags': _STRING_LIST, 'clarification_requests': _STRING_LIST, 'approval_refs': _STRING_LIST,
    'field': {'type': 'string'},
    'disposition': {'type': 'string', 'enum': ['record_and_escalate']},
}
TOOL_NAMES = {'award': 'submit_award', 'clarification': 'submit_clarification', 'infeasible': 'submit_infeasible'}
TOOL_DESCRIPTIONS = {
    'award': 'Submit an award: the supplier allocation you decided. Call exactly once, only for an award. Every listed field is required.',
    'clarification': ('Submit a clarification request when the rules do not allow an award because a needed term is missing. '
                      'Call exactly once, only for a clarification. Every listed field is required.'),
    'infeasible': ('Submit an infeasibility finding when no award can meet the need. Call exactly once, only for an '
                   'infeasible case. Every listed field is required.'),
}


def json_schema(kind):
    """The tool function schema for one kind: exactly its fields, all required, nothing else expressible."""
    props = {'kind': {'type': 'string', 'enum': [kind]}}
    props.update({k: _PROPERTIES[k] for k in FIELDS[kind] if k != 'kind'})
    return {'type': 'function', 'function': {
        'name': TOOL_NAMES[kind], 'description': TOOL_DESCRIPTIONS[kind],
        'parameters': {'type': 'object', 'properties': props, 'required': list(FIELDS[kind]),
                       'additionalProperties': False}}}
