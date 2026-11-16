"""Real-LLM adapter for the S01 operational tools (issue #18).

The adapter is an `agent(view) -> call` callable for `ObservableRunner.run`. It only
ever sees what the runner shows an agent (`runner.view()`), and every tool call it
makes goes through the runner. It never imports or touches the world, the scenario,
the verifier or any expected outcome.

Provider: OpenRouter, OpenAI-compatible chat completions, free-tier models only.
Standard library only. Secrets are read from the environment and redacted from
everything this module stores. Usage, latency and cost are recorded only as the
provider actually reported them; missing usage is reported as missing, never guessed.
"""
import copy
import hashlib
import json
import os
import re
import socket
import ssl
import time
import urllib.error
import urllib.request

ENDPOINT = 'https://openrouter.ai/api/v1/chat/completions'
CREDENTIAL_ENV = 'OPENROUTER_API_KEY'
MANIFEST_SCHEMA = 'llm-run-manifest-1'
TELEMETRY_SCHEMA = 'llm-telemetry-1'
READ_SECTIONS = ('all', 'clock', 'state', 'rules')

SYSTEM_PROMPT = (
    'You operate a small manufacturing plant through tools, one simulated day at a time. '
    'Each message shows you the current visible state, visible rules and the outcome of your last tool call. '
    'Use only that information. Call exactly one tool per reply and do not reply in prose. '
    'State is already included after every call, so avoid unnecessary read calls. '
    'Time only moves when you call advance_day. Resource commitments (commit_recovery, release_production) '
    'cannot be undone and some have deadlines shown in the rules. '
    'Keep acting until the episode phase is complete.')


class AdapterError(Exception):
    """Base class; the runner records it as an agent_error attempt."""
    error_class = 'adapter_error'


class ModelNotAllowedError(AdapterError):
    error_class = 'model_not_allowed'


class ProviderError(AdapterError):
    error_class = 'provider_error'


class RateLimitedError(ProviderError):
    error_class = 'rate_limited'


class RefusalError(AdapterError):
    error_class = 'refusal'


class ContextLimitError(AdapterError):
    error_class = 'context_limit'


class MalformedResponseError(AdapterError):
    error_class = 'malformed_response'


class NoToolCallError(AdapterError):
    error_class = 'no_tool_call'


# --------------------------------------------------------------------- redaction

_SECRET_PATTERNS = (
    re.compile(r'sk-or-[A-Za-z0-9_\-]{8,}'),
    re.compile(r'sk-[A-Za-z0-9_\-]{16,}'),
    re.compile(r'(?i)(bearer\s+)[A-Za-z0-9._\-~+/=]{8,}'),
    re.compile(r'(?i)("?authorization"?\s*[:=]\s*"?)[^\s",}]+'),
)
REDACTED = '[REDACTED]'


def redact_text(text, extra_secrets=()):
    if not isinstance(text, str):
        return text
    for s in extra_secrets:
        if s and len(s) >= 4:
            text = text.replace(s, REDACTED)
    text = _SECRET_PATTERNS[0].sub(REDACTED, text)
    text = _SECRET_PATTERNS[1].sub(REDACTED, text)
    text = _SECRET_PATTERNS[2].sub(lambda m: m.group(1) + REDACTED, text)
    text = _SECRET_PATTERNS[3].sub(lambda m: m.group(1) + REDACTED, text)
    return text


def redact(obj, extra_secrets=()):
    """Deep-copy `obj` with secrets removed from every string and secret-bearing key."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if str(k).lower() in ('authorization', 'api_key', 'apikey', 'x-api-key', 'proxy-authorization'):
                out[k] = REDACTED
            else:
                out[k] = redact(v, extra_secrets)
        return out
    if isinstance(obj, (list, tuple)):
        return [redact(v, extra_secrets) for v in obj]
    return redact_text(obj, extra_secrets)


# --------------------------------------------------------------------- config

def zero_priced(pricing):
    """True only when the pricing mapping states exactly '0' (or 0) for both prompt and completion."""
    if not isinstance(pricing, dict):
        return False
    for key in ('prompt', 'completion'):
        v = pricing.get(key)
        if isinstance(v, bool) or v not in ('0', 0, '0.0', '0.00', 0.0):
            return False
    return True


def is_free_model(model, pricing=None):
    return isinstance(model, str) and (model.endswith(':free') or zero_priced(pricing))


def is_confirmed_free(config):
    return config.free_basis in ('id_suffix', 'verified_zero_pricing')


def _positive_int(name, value):
    if type(value) is not int or value < 1:
        raise ValueError(f'{name} must be a positive integer')
    return value


class AdapterConfig:
    """Pinned adapter configuration. Everything here goes into the run manifest."""

    def __init__(self, model, *, cost_ceiling_usd=0.0, max_model_calls=12, max_total_tokens=60000,
                 max_output_tokens=1024, max_context_tokens=None, temperature=0.0, memory_window=8,
                 timeout_seconds=60.0, max_retries=3, backoff_base_seconds=1.0, backoff_cap_seconds=20.0,
                 max_nudges=2, endpoint=ENDPOINT, system_prompt=SYSTEM_PROMPT,
                 pricing=None, role_kind='actor'):
        if role_kind != 'actor':
            raise ModelNotAllowedError(
                f'role kind {role_kind!r} cannot act: only kind "actor" models may drive the runner '
                '(scorers only score and are never routed through the runner)')
        if not isinstance(model, str) or not is_free_model(model, pricing):
            raise ModelNotAllowedError(
                f"model id {model!r} refused: only ids ending in ':free', or ids whose verified OpenRouter "
                "pricing is exactly '0' for prompt and completion, are approved (approved monetary ceiling is $0.00)")
        self.free_basis = 'id_suffix' if model.endswith(':free') else 'verified_zero_pricing'
        self.pricing = dict(pricing) if pricing else None
        if cost_ceiling_usd is None or cost_ceiling_usd < 0:
            raise ValueError('cost_ceiling_usd must be >= 0')
        self.model = model
        self.cost_ceiling_usd = float(cost_ceiling_usd)
        self.max_model_calls = _positive_int('max_model_calls', max_model_calls)
        self.max_total_tokens = _positive_int('max_total_tokens', max_total_tokens)
        self.max_output_tokens = _positive_int('max_output_tokens', max_output_tokens)
        self.max_context_tokens = None if max_context_tokens is None else _positive_int('max_context_tokens', max_context_tokens)
        self.temperature = float(temperature)
        self.memory_window = _positive_int('memory_window', memory_window)
        self.timeout_seconds = float(timeout_seconds)
        if type(max_retries) is not int or max_retries < 0:
            raise ValueError('max_retries must be a non-negative integer')
        self.max_retries = max_retries
        self.backoff_base_seconds = float(backoff_base_seconds)
        self.backoff_cap_seconds = float(backoff_cap_seconds)
        if type(max_nudges) is not int or max_nudges < 0:
            raise ValueError('max_nudges must be a non-negative integer')
        self.max_nudges = max_nudges
        self.endpoint = endpoint
        self.system_prompt = system_prompt


# --------------------------------------------------------------------- tool schemas

def _arg_schema(tool, arg, spec):
    if arg == 'section':
        return {'type': 'string', 'enum': list(READ_SECTIONS), 'description': 'which part of the visible view to read'}
    if arg == 'choice':
        return {'type': 'string', 'enum': list(spec.get('choices', [])), 'description': 'recovery option to commit'}
    if arg == 'quantity':
        return {'type': 'integer', 'minimum': 0, 'description': 'units of finished goods to release today'}
    return {'type': 'string'}


_DESCRIPTIONS = {
    'read_state': 'Read the visible plant state (optionally one section). Does not advance time.',
    'read_recovery_offers': 'Read currently visible supply recovery offers, if any. Does not advance time.',
    'read_scorecard': 'Read the scorecard. Only available once the episode is complete.',
    'commit_recovery': 'Irreversibly commit to one supply recovery option (once only, before its deadline).',
    'release_production': 'Release production for today (once per day, within capacity and material on hand).',
    'advance_day': 'Close today and advance simulated time by one day.',
}


def openai_tools(tool_definitions):
    """Translate runner tool definitions to OpenAI tool schemas (static; no per-step values)."""
    tools = []
    for spec in tool_definitions:
        if not spec.get('granted'):
            continue
        props = {a: _arg_schema(spec['name'], a, spec) for a in spec['arguments']}
        tools.append({'type': 'function', 'function': {
            'name': spec['name'], 'description': _DESCRIPTIONS.get(spec['name'], spec['name']),
            'parameters': {'type': 'object', 'properties': props, 'required': list(spec['arguments']) if spec['name'] != 'read_state' else [],
                           'additionalProperties': False}}})
    return tools


def build_manifest(config, tool_definitions):
    tools = openai_tools(tool_definitions)
    manifest = {
        'schema': MANIFEST_SCHEMA,
        'provider': 'openrouter', 'endpoint': config.endpoint, 'model': config.model,
        'system_prompt': config.system_prompt, 'tool_schemas': tools,
        'request_parameters': {'temperature': config.temperature, 'max_tokens': config.max_output_tokens,
                               'tool_choice': 'auto', 'parallel_tool_calls': False},
        'memory_policy': {'kind': 'rolling_window', 'window_exchanges': config.memory_window,
                          'cross_episode_memory': False,
                          'description': 'system prompt plus the initial observation plus the last N tool exchanges; each tool result is the current visible view and last outcome'},
        'retry_policy': {'retry_on': ['http_429', 'http_5xx', 'network_error'], 'max_retries': config.max_retries,
                         'backoff': 'exponential', 'base_seconds': config.backoff_base_seconds,
                         'cap_seconds': config.backoff_cap_seconds, 'honors_retry_after_up_to_cap': True,
                         'no_retry_on': ['4xx other than 429', 'refusal', 'context limit']},
        'timeout_seconds': config.timeout_seconds,
        'limits': {'max_model_calls': config.max_model_calls, 'max_total_tokens': config.max_total_tokens,
                   'max_context_tokens': config.max_context_tokens, 'max_nudges_for_non_tool_replies': config.max_nudges},
        'spend': {'cost_ceiling_usd': config.cost_ceiling_usd, 'free_only': True, 'free_basis': config.free_basis,
                  'verified_pricing': config.pricing,
                  'cost_rule': "0 only for confirmed ':free' model with usage present; otherwise 'unknown'"},
        'credential': {'env_var': CREDENTIAL_ENV, 'logged': False},
    }
    manifest['manifest_sha256'] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    return manifest


# --------------------------------------------------------------------- transport

def urllib_transport(request, *, timeout):
    """Default transport. `request` = {'url','headers','body'}; returns (status, headers, body_bytes).

    Network failures return status 0. The request (and its Authorization header) is never stored.
    """
    cafile = os.environ.get('SSL_CERT_FILE') or os.environ.get('REQUESTS_CA_BUNDLE') or os.environ.get('CURL_CA_BUNDLE')
    ctx = ssl.create_default_context(cafile=cafile) if cafile else ssl.create_default_context()
    req = urllib.request.Request(request['url'], data=request['body'], headers=request['headers'], method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except Exception:  # noqa: BLE001
            body = b''
        return exc.code, dict(exc.headers or {}), body
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, ssl.SSLError, OSError) as exc:
        return 0, {}, json.dumps({'error': {'message': f'{type(exc).__name__}'}}).encode()


_CONTEXT_RE = re.compile(r'(?i)(context[_ ]length|context window|maximum context|too many tokens|prompt is too long|token limit)')


def _error_text(body):
    try:
        data = json.loads(body.decode('utf-8', 'replace'))
        err = data.get('error') if isinstance(data, dict) else None
        if isinstance(err, dict):
            return str(err.get('message', ''))[:300], err.get('code')
        if isinstance(err, str):
            return err[:300], None
    except (ValueError, AttributeError):
        pass
    return (body[:300].decode('utf-8', 'replace') if isinstance(body, (bytes, bytearray)) else str(body)[:300]), None


def chat_request(config, messages, tools, *, transport=None, api_key=None, sleep=time.sleep, clock=time.monotonic,
                 max_retries=None, max_tokens=None, use_tools=True):
    """One logical chat completion with bounded retries.

    Returns {'body': parsed_json, 'status': int, 'latency_ms': float, 'http_requests': int, 'retries': [..]}.
    Raises AdapterError subclasses for non-recoverable outcomes. Retry waiting is not counted in latency of
    the final successful request; `total_latency_ms` covers the whole logical call.
    """
    transport = transport or (lambda req: urllib_transport(req, timeout=config.timeout_seconds))
    api_key = api_key if api_key is not None else os.environ.get(CREDENTIAL_ENV, '')
    payload = {'model': config.model, 'messages': messages, 'temperature': config.temperature,
               'max_tokens': max_tokens or config.max_output_tokens}
    if use_tools and tools:
        payload.update(tools=tools, tool_choice='auto', parallel_tool_calls=False)
    request = {'url': config.endpoint, 'body': json.dumps(payload).encode(),
               'headers': {'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'}}
    limit = config.max_retries if max_retries is None else max_retries
    retries, requests_made, t_all = [], 0, clock()
    while True:
        t0 = clock()
        status, headers, raw = transport(request)
        latency = (clock() - t0) * 1000.0
        requests_made += 1
        retry_after = None
        for k, v in (headers or {}).items():
            if str(k).lower() == 'retry-after':
                try:
                    retry_after = float(v)
                except (TypeError, ValueError):
                    retry_after = None
        body, err_text, err_code = None, '', None
        try:
            body = json.loads(raw.decode('utf-8', 'replace')) if raw else None
        except ValueError:
            body = None
        if status == 200 and isinstance(body, dict) and 'error' in body and not body.get('choices'):
            err_text, err_code = _error_text(raw)
            if isinstance(err_code, int):
                status = err_code
            else:
                status = 502
        elif status != 200:
            err_text, err_code = _error_text(raw)
        if status == 200:
            if not isinstance(body, dict):
                raise MalformedResponseError('provider returned 200 with a non-JSON body')
            return {'body': body, 'status': 200, 'latency_ms': latency, 'http_requests': requests_made,
                    'retries': retries, 'total_latency_ms': (clock() - t_all) * 1000.0}
        retryable = status in (0, 429) or 500 <= status < 600
        if status in (400, 413) and _CONTEXT_RE.search(err_text or ''):
            raise ContextLimitError(f'provider reported context limit (HTTP {status})')
        if not retryable:
            raise ProviderError(f'HTTP {status}: {err_text}')
        if len(retries) >= limit:
            cls = RateLimitedError if status == 429 else ProviderError
            raise cls(f'HTTP {status} after {len(retries)} retries: {err_text}')
        wait = min(config.backoff_cap_seconds, config.backoff_base_seconds * (2 ** len(retries)))
        if retry_after is not None:
            wait = min(config.backoff_cap_seconds, max(wait, retry_after))
        retries.append({'after_status': status, 'wait_seconds': wait})
        sleep(wait)


# --------------------------------------------------------------------- usage and cost

def extract_usage(body):
    """Return a usage dict only with fields the provider actually reported, else None."""
    u = body.get('usage') if isinstance(body, dict) else None
    if not isinstance(u, dict):
        return None
    out = {}
    for k in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
        if type(u.get(k)) is int and u[k] >= 0:
            out[k] = u[k]
    if 'total_tokens' not in out and 'prompt_tokens' in out and 'completion_tokens' in out:
        out['total_tokens'] = out['prompt_tokens'] + out['completion_tokens']
    if isinstance(u.get('cost'), (int, float)) and not isinstance(u.get('cost'), bool) and u['cost'] >= 0:
        out['reported_cost_usd'] = float(u['cost'])
    return out or None


def call_cost(model, usage, confirmed_free=None):
    """Cost in USD or the string 'unknown'. Never inferred for non-free models or missing usage."""
    if not usage:
        return 'unknown'
    if 'reported_cost_usd' in usage:
        return usage['reported_cost_usd']
    if confirmed_free if confirmed_free is not None else model.endswith(':free'):
        return 0.0
    return 'unknown'


# --------------------------------------------------------------------- the agent

_RETRY = object()


class LLMAgent:
    """Stateful `agent(view) -> call | None` backed by a real model through `chat_request`."""

    def __init__(self, config, tool_definitions, *, transport=None, api_key=None, sleep=time.sleep,
                 clock=time.monotonic):
        self.config = config
        self._transport = transport
        self._api_key = api_key if api_key is not None else os.environ.get(CREDENTIAL_ENV, '')
        self._sleep, self._clock = sleep, clock
        self.tools = openai_tools(tool_definitions)
        self.manifest = build_manifest(config, tool_definitions)
        self._allowed = {t['function']['name'] for t in self.tools}
        self._initial = None
        self._exchanges = []          # list of (assistant_message, tool_message)
        self._pending = None          # assistant message awaiting its tool result
        self._nudge = None
        self._nudges = 0
        self.calls = []               # per logical model call telemetry
        self.stop_reason = None
        self.failure = None

    # ----- message construction
    @staticmethod
    def _observation(view):
        return {'clock': view['clock'], 'state': view['state'], 'rules': view['rules'],
                'last_outcome': view['last_outcome']}

    def _messages(self, view):
        msgs = [{'role': 'system', 'content': self.config.system_prompt}]
        initial = json.dumps({'observation': self._initial})
        msgs.append({'role': 'user', 'content': 'Initial observation: ' + initial})
        window = self._exchanges[-self.config.memory_window:]
        for a, t in window:
            msgs.append(a)
            msgs.append(t)
        if self._nudge:
            msgs.append({'role': 'user', 'content': self._nudge})
        return msgs

    def _fail(self, exc):
        self.failure = {'error_class': exc.error_class, 'message': redact_text(str(exc), (self._api_key,))}
        self.stop_reason = 'error:' + exc.error_class
        raise exc

    def _totals(self):
        known = [c['usage'] for c in self.calls if c['usage'] and 'total_tokens' in c['usage']]
        return sum(u['total_tokens'] for u in known)

    def _known_cost(self):
        return sum(c['cost_usd'] for c in self.calls if isinstance(c['cost_usd'], (int, float)))

    # ----- the runner entry point
    def __call__(self, view):
        obs = self._observation(view)
        if self._initial is None:
            self._initial = obs
        elif self._pending is not None:
            result = {'last_outcome': obs['last_outcome'], 'clock': obs['clock'], 'state': obs['state'], 'rules': obs['rules']}
            self._exchanges.append((self._pending['assistant'], {'role': 'tool', 'tool_call_id': self._pending['id'],
                                                                 'content': json.dumps(result)}))
            self._pending = None
        # budgets (checked before spending anything)
        if len(self.calls) >= self.config.max_model_calls:
            self.stop_reason = 'model_call_limit'
            return None
        if self._totals() >= self.config.max_total_tokens:
            self.stop_reason = 'token_limit'
            return None
        if self._known_cost() > self.config.cost_ceiling_usd:
            self.stop_reason = 'cost_ceiling'
            return None
        while True:
            call = self._one_model_call(view)
            if call is _RETRY:
                continue
            return call

    def _one_model_call(self, view):
        cfg = self.config
        if len(self.calls) >= cfg.max_model_calls:
            self.stop_reason = 'model_call_limit'
            return None
        messages = self._messages(view)
        try:
            res = chat_request(cfg, messages, self.tools, transport=self._transport, api_key=self._api_key,
                               sleep=self._sleep, clock=self._clock)
        except AdapterError as exc:
            self.calls.append({'seq': len(self.calls) + 1, 'status': 'error', 'error_class': exc.error_class,
                               'usage': None, 'cost_usd': 'unknown', 'latency_ms': None, 'finish_reason': None})
            self._fail(exc)
        body = res['body']
        usage = extract_usage(body)
        cost = call_cost(cfg.model, usage, is_confirmed_free(cfg))
        rec = {'seq': len(self.calls) + 1, 'status': 'ok', 'http_status': res['status'], 'http_requests': res['http_requests'],
               'retries': res['retries'], 'latency_ms': round(res['latency_ms'], 1),
               'total_latency_ms': round(res['total_latency_ms'], 1), 'usage': usage, 'cost_usd': cost,
               'finish_reason': None, 'returned_model': body.get('model') if isinstance(body.get('model'), str) else None}
        self.calls.append(rec)
        if cfg.max_context_tokens and usage and usage.get('prompt_tokens', 0) > cfg.max_context_tokens:
            self.stop_reason = 'context_limit_configured'
            return None
        choices = body.get('choices')
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict) \
                or not isinstance(choices[0].get('message'), dict):
            rec['status'] = 'error'
            rec['error_class'] = 'malformed_response'
            self._fail(MalformedResponseError('response has no choices[0].message'))
        choice = choices[0]
        msg = choice['message']
        rec['finish_reason'] = choice.get('finish_reason')
        if msg.get('refusal') or choice.get('finish_reason') == 'content_filter':
            rec['status'] = 'error'
            rec['error_class'] = 'refusal'
            self._fail(RefusalError('model refused or response was filtered'))
        tool_calls = msg.get('tool_calls')
        if not isinstance(tool_calls, list) or not tool_calls:
            rec['status'] = 'no_tool_call'
            rec['text_chars'] = len(msg.get('content') or '') if isinstance(msg.get('content'), str) else 0
            if choice.get('finish_reason') == 'length':
                rec['note'] = 'output truncated by max_tokens'
            if self._nudges >= cfg.max_nudges:
                self.stop_reason = 'no_tool_call'
                self.failure = {'error_class': 'no_tool_call', 'message': 'model did not call a tool after nudges'}
                return None
            self._nudges += 1
            self._nudge = 'Reply with exactly one tool call and no prose.'
            return _RETRY
        self._nudge = None
        self._nudges = 0   # the nudge budget applies to consecutive non-tool replies
        first =tool_calls[0] if isinstance(tool_calls[0], dict) else {}
        fn = first.get('function') if isinstance(first.get('function'), dict) else {}
        name, raw_args = fn.get('name'), fn.get('arguments', '')
        call_id = first.get('id') if isinstance(first.get('id'), str) and first.get('id') else f'call_{len(self.calls)}'
        rec['tool_calls_returned'] = len(tool_calls)
        rec['tool'] = name if isinstance(name, str) else None
        # Keep the assistant message with only the one call we execute, so tool pairing stays valid.
        assistant = {'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': call_id, 'type': 'function', 'function': {'name': name if isinstance(name, str) else '', 'arguments': raw_args if isinstance(raw_args, str) else json.dumps(raw_args)}}]}
        self._pending = {'assistant': assistant, 'id': call_id}
        if isinstance(raw_args, dict):
            args = raw_args
        elif isinstance(raw_args, str):
            try:
                args = json.loads(raw_args) if raw_args.strip() else {}
            except ValueError:
                args = redact_text(raw_args[:200], (self._api_key,))
                rec['malformed_arguments'] = True
        else:
            args = {}
            rec['malformed_arguments'] = True
        # Malformed values are forwarded as-is so the runner rejects and audits them; nothing is repaired.
        return {'tool': name, 'arguments': args}

    def telemetry(self):
        return summarize_telemetry(self)


def summarize_telemetry(agent):
    calls = agent.calls
    ok = [c for c in calls if c.get('usage')]
    total = sum(c['usage'].get('total_tokens', 0) for c in ok)
    costs = [c['cost_usd'] for c in calls]
    if costs and all(isinstance(c, (int, float)) for c in costs):
        cost_total = sum(costs)
    elif not costs:
        cost_total = 0.0
    else:
        cost_total = 'unknown'
    out = {'schema': TELEMETRY_SCHEMA, 'model': agent.config.model, 'model_calls': len(calls),
           'http_requests': sum(c.get('http_requests', 0) for c in calls),
           'retries': sum(len(c.get('retries', [])) for c in calls),
           'usage_complete': bool(calls) and len(ok) == len(calls),
           'calls_with_usage': len(ok),
           'prompt_tokens': sum(c['usage'].get('prompt_tokens', 0) for c in ok),
           'completion_tokens': sum(c['usage'].get('completion_tokens', 0) for c in ok),
           'total_tokens': total,
           'latency_ms_total': round(sum(c['latency_ms'] for c in calls if c.get('latency_ms') is not None), 1),
           'cost_usd': cost_total, 'cost_ceiling_usd': agent.config.cost_ceiling_usd,
           'stop_reason': agent.stop_reason, 'failure': agent.failure, 'calls': calls}
    return redact(out, (agent._api_key,))


def run_llm_episode(runner, config, *, transport=None, api_key=None, sleep=time.sleep, clock=time.monotonic):
    """Run one episode with a real model through `runner`. Returns the runner transcript plus adapter records.

    The runner is reset by `runner.run`; the adapter reads only `runner.view()` data given to it.
    """
    runner._world.reset()
    agent = LLMAgent(config, runner.tool_definitions(), transport=transport, api_key=api_key, sleep=sleep, clock=clock)
    transcript = runner.run(agent, reset=False)
    return {'manifest': agent.manifest, 'transcript': redact(transcript, (agent._api_key,)),
            'telemetry': agent.telemetry(), 'runner_status': transcript['status'],
            'episode_complete': transcript['status'] == 'complete'}
