"""Langfuse tracing for recorded S01 episodes (version 1). OFF by default.

Post-hoc: a finished episode (the `raw` record from `eval19_v3.run_s01_episode` plus its `grade` from `grade_s01`) is
turned into a plain-data trace PLAN, and the plan is sent to Langfuse. Nothing here runs inside the world, the runner,
the checker or the model adapter, so tracing cannot change a run, a verdict or a replay. The saved run files stay the
record of truth; Langfuse is a viewer on top.

Trace shape (Langfuse observation types): one `agent` observation per episode; under it, in order, a `generation` for each
model call and a `tool` observation for the tool call it made. Checker results are scores, never blended into one number.

Safety: tracing is on only when SCW_LANGFUSE=1 and the Langfuse keys and host are set in the environment. This module never
reads, prints or stores a key value. Only fields of the agent-visible record are used (`raw['world']`, the simulator's private
state, is never read). Strings pass through `sanitize`, and a plan that contains any caller-supplied private string is refused.

Known limits: observations are sent after the episode, so Langfuse timestamps are export time; real latency is kept in each
generation's metadata. Business numbers in scores are PROVISIONAL, needs practitioner value. No claim about model ability.
"""
import hashlib
import json
import os
import re

PLAN_SCHEMA = 'scw-trace-plan-1'
ENABLE_ENV = 'SCW_LANGFUSE'
REQUIRED_ENV = ('LANGFUSE_PUBLIC_KEY', 'LANGFUSE_SECRET_KEY', 'LANGFUSE_BASE_URL')
ROOT_NAME = 'run-s01-episode'
MAX_STRING = 20000
REDACTED = '[redacted]'
_DENY_KEYS = frozenset({'api_key', 'apikey', 'x-api-key', 'authorization', 'secret', 'secret_key', 'password', 'credential'})
_SECRET_RE = re.compile(r'(?:sk|pk)-lf-[\w-]+|sk-or-[\w-]+|Bearer\s+[\w.\-]+', re.I)


class TraceLeakError(ValueError):
    """A trace plan contained a string the caller said must never leave the machine."""


class TracingUnavailable(RuntimeError):
    """Tracing was asked for but the optional `langfuse` package is not installed."""


def sanitize(obj, secrets=()):
    """Copy of `obj` with secret-looking strings replaced, credential-named keys dropped and long strings cut."""
    if isinstance(obj, dict):
        return {str(k): sanitize(v, secrets) for k, v in obj.items() if str(k).lower() not in _DENY_KEYS}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v, secrets) for v in obj]
    if isinstance(obj, str):
        s = _SECRET_RE.sub(REDACTED, obj)
        for sec in secrets:
            if sec and len(sec) >= 4:
                s = s.replace(sec, REDACTED)
        return s if len(s) <= MAX_STRING else s[:MAX_STRING] + '...[cut]'
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    return sanitize(str(obj), secrets)


def _digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def trace_id_for(raw, run_label=''):
    """Deterministic 32-hex trace id: the same recorded run exported twice lands on the same trace, not a duplicate."""
    t = raw['transcript']
    return _digest([str(run_label), raw['fixture_id'], raw['model'], t['attempts']])[:32]


def _ascii(text, limit=200):
    return ''.join(c if 32 <= ord(c) < 127 else '_' for c in str(text))[:limit]


def _usage(call):
    u = call.get('usage') or {}
    out = {k: int(u[src]) for k, src in (('input', 'prompt_tokens'), ('output', 'completion_tokens'), ('total', 'total_tokens'))
           if isinstance(u.get(src), (int, float)) and not isinstance(u.get(src), bool)}
    return out or None


def _scores(grade):
    """One score per checker fact. Never combined into a single number."""
    out = []

    def add(name, value, kind, comment=''):
        if value is None:
            return
        out.append({'name': name, 'value': (1 if value else 0) if kind == 'BOOLEAN' else value, 'data_type': kind,
                    'comment': comment})

    add('completed', grade['completed'], 'BOOLEAN')
    add('verifier_feasible', grade['verifier_feasible'], 'BOOLEAN', 'independent v0.6 checker')
    add('replay_reproduced', grade['replay_reproduced'], 'BOOLEAN')
    add('observation_leak_free', not grade['observation_leaks'], 'BOOLEAN')
    add('hard_violations', len(grade['hard_violation_codes']), 'NUMERIC')
    add('invalid_actions', grade['invalid_actions'], 'NUMERIC')
    add('agent_errors', grade['agent_errors'], 'NUMERIC')
    for name, value in (grade.get('metrics') or {}).items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            add('metric_' + name, value, 'NUMERIC', 'PROVISIONAL, needs practitioner value')
    return out


def build_trace_plan(raw, grade, *, run_label='', environment='development', private_strings=()):
    """Plain-data plan for one episode. Raises TraceLeakError if any of `private_strings` would be sent."""
    t, manifest = raw['transcript'], raw['manifest']
    attempts, calls, observed = t['attempts'], raw['telemetry']['calls'], raw['observed']
    window = int((manifest.get('memory_policy') or {}).get('window_exchanges') or 8)

    def assistant(a):
        # OpenAI message format: a tool call renders as a card only inside an assistant message's tool_calls,
        # with the arguments as a JSON-encoded string and an id that the tool result repeats.
        return {'role': 'assistant', 'content': None,
                'tool_calls': [{'id': 'call-%s' % a['seq'], 'type': 'function',
                                'function': {'name': a['tool'] or 'invalid', 'arguments': json.dumps(a['arguments'])}}]}

    def seen_before(i):
        """What the model was shown at step i: system prompt, initial observation, last `window` exchanges."""
        msgs = [{'role': 'system', 'content': manifest['system_prompt']}]
        if observed:
            msgs.append({'role': 'user', 'content': 'Initial observation: ' + json.dumps({'observation': observed[0]})})
        for j in range(max(0, i - window), i):
            msgs.append(assistant(attempts[j]))
            if j + 1 < len(observed):
                msgs.append({'role': 'tool', 'tool_call_id': 'call-%s' % attempts[j]['seq'],
                             'content': json.dumps(observed[j + 1])})
        return msgs

    children = []
    for i, a in enumerate(attempts):
        call = calls[i] if i < len(calls) else None
        if call is not None:
            children.append({
                'type': 'generation', 'name': 'choose-action', 'model': raw['model'], 'input': seen_before(i),
                'output': assistant(a),
                'usage_details': _usage(call),
                'cost_details': {'total': call['cost_usd']} if isinstance(call.get('cost_usd'), (int, float)) else None,
                'level': None if call.get('status') in (None, 'ok') else 'ERROR',
                'metadata': {'seq': a['seq'], 'day': a['day'], 'finish_reason': call.get('finish_reason'),
                             'latency_ms': call.get('latency_ms'), 'http_status': call.get('http_status'),
                             'retries': len(call.get('retries') or [])}})
        children.append({
            'type': 'tool', 'name': 'apply-tool-call', 'input': a['arguments'],
            'output': {'accepted': a['accepted'], 'category': a['category'], 'reason': a['reason'],
                       'state_changes': a.get('state_changes'), 'events': a.get('events')},
            'level': None if a['accepted'] else 'WARNING', 'status_message': None if a['accepted'] else a['reason'],
            'metadata': {'seq': a['seq'], 'day': a['day'], 'action_id': a['action_id'], 'tool': a['tool'] or 'invalid',
                         'tool_call_id': 'call-%s' % a['seq']}})
    trace_id = trace_id_for(raw, run_label)
    tags = ['s01', 'harness:' + str(manifest['harness_version']), 'status:' + str(t['status'])]
    if grade['observation_leaks']:
        tags.append('observation-leak')
    plan = {
        'schema': PLAN_SCHEMA, 'trace_id': trace_id, 'session_id': _ascii(run_label or trace_id),
        'environment': environment, 'tags': tags,
        'root': {
            'type': 'agent', 'name': ROOT_NAME,
            'input': {'fixture_id': raw['fixture_id'], 'horizon_days': t['horizon_days'], 'initial': t['initial']},
            'output': {'status': t['status'], 'attempts': grade['attempts'], 'valid_actions': grade['valid_actions'],
                       'invalid_actions': grade['invalid_actions'], 'verifier_feasible': grade['verifier_feasible'],
                       'replay_reproduced': grade['replay_reproduced'], 'metrics': grade.get('metrics')},
            'metadata': {'fixture_id': raw['fixture_id'], 'model': raw['model'],
                         'harness_version': manifest['harness_version'], 'manifest_sha256': manifest['manifest_sha256'],
                         'run_label': str(run_label), 'memory_policy': manifest['memory_policy'],
                         'note': 'sent after the run; latency is in each generation metadata'}},
        'children': children, 'scores': _scores(grade)}
    plan = sanitize(plan)
    text = json.dumps(plan)  # refuse rather than redact: a private string in a trace means a bug upstream
    for n, s in enumerate(private_strings):
        if s and s in text:
            raise TraceLeakError('private string #%d would be sent' % n)
    return plan


def tracing_client(env=None, factory=None):
    """A Langfuse client, or None when tracing is off. Off unless SCW_LANGFUSE=1 and keys and host are set."""
    env = os.environ if env is None else env
    if env.get(ENABLE_ENV) != '1' or not all(env.get(k) for k in REQUIRED_ENV):
        return None
    if factory is None:
        try:
            from langfuse import Langfuse as factory
        except ImportError as exc:
            raise TracingUnavailable('install the trace extra: pip install -e ".[trace]"') from exc
    return factory(environment=env.get('LANGFUSE_TRACING_ENVIRONMENT', 'development'))


def _kwargs(spec, skip=('type', 'children')):
    return {k: v for k, v in spec.items() if k not in skip and v is not None}


def export_plan(plan, client, *, propagate=None):
    """Send a plan through a Langfuse client. `propagate` is `langfuse.propagate_attributes` unless a test supplies one."""
    if propagate is None:
        from langfuse import propagate_attributes as propagate
    root = plan['root']
    meta = {k: _ascii(v) for k, v in root['metadata'].items() if k in ('fixture_id', 'model', 'harness_version', 'run_label')}
    with propagate(session_id=plan['session_id'], tags=plan['tags'], trace_name=root['name'], metadata=meta,
                   environment=plan['environment']):
        with client.start_as_current_observation(trace_context={'trace_id': plan['trace_id']}, as_type=root['type'],
                                                 **_kwargs(root, ('type', 'output'))) as span:
            for child in plan['children']:
                with client.start_as_current_observation(as_type=child['type'], **_kwargs(child)):
                    pass
            span.update(output=root['output'])
    for s in plan['scores']:
        client.create_score(name=s['name'], value=s['value'], trace_id=plan['trace_id'], data_type=s['data_type'],
                            comment=s['comment'] or None, score_id=plan['trace_id'] + '-' + s['name'])
    client.flush()
    return plan['trace_id']


def trace_episode(raw, grade, client, *, run_label='', private_strings=(), propagate=None):
    """Export one episode if tracing is on. Never raises: a Langfuse problem must not cost a finished run."""
    if client is None:
        return {'exported': False, 'reason': 'tracing off'}
    try:
        plan = build_trace_plan(raw, grade, run_label=run_label, private_strings=private_strings)
        return {'exported': True, 'trace_id': export_plan(plan, client, propagate=propagate)}
    except Exception as exc:  # noqa: BLE001 - only the class name is kept, a message could carry request data
        return {'exported': False, 'reason': 'error', 'error_class': type(exc).__name__}
