"""Sarvam provider support for the S01 model run (adapter version 2, beside `llm_adapter`, which stays frozen).

Why this exists: `llm_adapter` accepts only free OpenRouter models, and that $0 rule is kept for OpenRouter. Sarvam is a paid API
(owner decision 2026-11-23: its own adapter, a hard cap of INR 1000 across all Sarvam calls). Nothing here relaxes the OpenRouter rule.

How it fits: `SarvamConfig` is an `AdapterConfig` for an allowed Sarvam model id. `SarvamTransport` is a BASE transport. Wrap it in
`eval19.Guard` exactly as the OpenRouter transport is wrapped, so request caps, throttle, leak scan and ledger are unchanged.
The transport (1) drops request fields Sarvam may not accept, (2) refuses any call whose worst-case price could pass the cap,
(3) prices each answer from the tokens Sarvam reports using a pinned price table and writes that estimate into `usage.cost`, so the
existing agent budget check works, and (4) stops for good when Sarvam says credits are exhausted (HTTP 402).

Costs here are ESTIMATES from a pinned table, not Sarvam-reported money. The table is PROVISIONAL (read from docs.sarvam.ai on
2026-11-23, prices exclude GST, so GST is added conservatively, cached-input discounts are ignored). Re-read the page before a run.
No claim about model ability. The API key is read from the environment only and never stored or logged.
"""
import json
import threading

from . import llm_adapter as la

ENDPOINT = 'https://api.sarvam.ai/v2/chat/completions'
CREDENTIAL_ENV = 'SARVAM_API_KEY'
CAP_INR = 1000.0
USD_INR = 85.0                 # pinned only to express the cap in the USD field the agent already checks; it cancels out
GST_FACTOR = 1.18              # PROVISIONAL: listed prices exclude GST
CHARS_PER_TOKEN_WORST = 1.0    # worst-case prompt size estimate: one token per byte of the request body
DROPPED_REQUEST_FIELDS = ('parallel_tool_calls',)
# INR per 1M tokens (input, output). PROVISIONAL, needs a fresh read of the pricing page before each run.
PRICES_INR_PER_M = {
    'sarvam-105b': (10.0, 25.0),
    'glm5.3-flash': (13.5, 45.0),
    'deepseekv4.1-flash-1017': (14.0, 55.0),
}


class SarvamModelNotAllowed(la.ModelNotAllowedError):
    error_class = 'model_not_allowed'


def price_inr(model, prompt_tokens, completion_tokens):
    """Estimated cost in INR (GST included) for the given token counts."""
    pin, pout = PRICES_INR_PER_M[model]
    return (prompt_tokens * pin + completion_tokens * pout) / 1e6 * GST_FACTOR


class SarvamConfig(la.AdapterConfig):
    """AdapterConfig for a Sarvam model. Same limits and checks as the base class, but the model must be in the price table."""

    def __init__(self, model, *, cap_inr=CAP_INR, endpoint=ENDPOINT, **kw):
        if not isinstance(model, str) or model not in PRICES_INR_PER_M:
            raise SarvamModelNotAllowed(f'model id {model!r} refused: not in the Sarvam price table {sorted(PRICES_INR_PER_M)}')
        if not isinstance(cap_inr, (int, float)) or isinstance(cap_inr, bool) or not 0 < cap_inr <= CAP_INR:
            raise ValueError(f'cap_inr must be above 0 and at most {CAP_INR}')
        # the base class refuses non-free ids by design; build it on a stand-in id, then state the truth
        super().__init__('stand-in:free', endpoint=endpoint, cost_ceiling_usd=cap_inr / USD_INR, **kw)
        self.model = model
        self.free_basis = 'paid_capped_inr'
        self.pricing = {'currency': 'INR', 'per_million_tokens_input_output': list(PRICES_INR_PER_M[model]),
                        'gst_factor': GST_FACTOR, 'status': 'PROVISIONAL, read from docs.sarvam.ai 2026-11-23'}
        self.cap_inr = float(cap_inr)


class SarvamSpend:
    """Running total in INR across every Sarvam call of a run. Rebuilt from its ledger so a restart cannot exceed the cap."""

    def __init__(self, cap_inr=CAP_INR, ledger_path=None):
        if not isinstance(cap_inr, (int, float)) or isinstance(cap_inr, bool) or not 0 < cap_inr <= CAP_INR:
            raise ValueError(f'cap_inr must be above 0 and at most {CAP_INR}')
        self.cap_inr, self.ledger_path = float(cap_inr), ledger_path
        self.spent_inr, self.calls, self.exhausted, self.log = 0.0, 0, None, []
        self._lock = threading.Lock()
        if ledger_path:
            try:
                with open(ledger_path) as fh:
                    for line in fh:
                        rec = json.loads(line)
                        self.spent_inr += rec['cost_inr']
                        self.calls += 1
                        if rec.get('event') in ('credits_exhausted', 'cap_reached', 'provider_exceeded_limits'):
                            self.exhausted = rec['event']
            except FileNotFoundError:
                pass

    def room_for(self, worst_inr):
        return self.exhausted is None and self.spent_inr + worst_inr <= self.cap_inr

    def record(self, model, cost_inr, basis, prompt_tokens=None, completion_tokens=None, event=None):
        rec = {'seq': self.calls + 1, 'model': model, 'cost_inr': round(cost_inr, 8), 'basis': basis,
               'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens}
        if event:
            rec['event'] = event
            self.exhausted = event
        with self._lock:
            self.spent_inr += rec['cost_inr']
            self.calls += 1
            if self.spent_inr >= self.cap_inr and self.exhausted is None:
                self.exhausted = rec['event'] = rec.get('event') or 'cap_reached'
            self.log.append(rec)
            if self.ledger_path:
                with open(self.ledger_path, 'a') as fh:
                    fh.write(json.dumps(rec) + '\n')
        return rec


def _count(v):
    return v if type(v) is int and 0 <= v < 10 ** 9 else None


class SarvamTransport:
    """Base transport for Sarvam. Call it with a request dict; it returns (status, headers, body_bytes)."""

    def __init__(self, base, spend):
        self.base, self.spend = base, spend

    @staticmethod
    def _refuse(status, message):
        return status, {}, json.dumps({'error': {'message': message, 'code': status}}).encode()

    def __call__(self, request):
        try:
            body = json.loads(request['body'])
            model = body['model']
            max_tokens = body.get('max_tokens')
        except (ValueError, KeyError, TypeError):
            return self._refuse(400, 'sarvam transport: request body is not a chat request; not sent')
        if model not in PRICES_INR_PER_M:
            return self._refuse(403, 'sarvam transport: model not in the price table; not sent')
        if _count(max_tokens) is None or max_tokens < 1:
            return self._refuse(400, 'sarvam transport: max_tokens missing or invalid; not sent')
        prompt_chars = len(request['body'])
        worst = price_inr(model, prompt_chars / CHARS_PER_TOKEN_WORST, max_tokens)
        if not self.spend.room_for(worst):
            return self._refuse(402, 'sarvam spend cap: a call could pass the cap or credits are exhausted; not sent')
        for field in DROPPED_REQUEST_FIELDS:
            body.pop(field, None)
        sent = dict(request, body=json.dumps(body).encode())
        status, headers, raw = self.base(sent)
        if status == 402:
            self.spend.record(model, 0.0, 'provider_402', event='credits_exhausted')
            return status, headers, raw
        if status != 200:
            return status, headers, raw
        try:
            data = json.loads(raw.decode('utf-8', 'replace'))
        except ValueError:
            data = None
        if not isinstance(data, dict) or 'error' in data and not data.get('choices'):
            return status, headers, raw
        usage = data.get('usage') if isinstance(data.get('usage'), dict) else {}
        pt, ct = _count(usage.get('prompt_tokens')), _count(usage.get('completion_tokens'))
        if pt is None or ct is None:  # no trustworthy usage: charge the worst case rather than guess low
            cost, basis = worst, 'worst_case_no_usage'
        else:
            cost, basis = price_inr(model, pt, ct), 'usage'
        # The cap holds as long as the provider bills no more than the request allowed. If it reports more, count what it
        # reports and stop every later call, so the overshoot is at most this one call and is visible in the ledger.
        over = basis == 'usage' and (ct > max_tokens or pt > prompt_chars / CHARS_PER_TOKEN_WORST)
        self.spend.record(model, cost, 'usage_exceeds_request_limits' if over else basis, pt, ct,
                          event='provider_exceeded_limits' if over else None)
        usage = dict(usage, cost=cost / USD_INR, cost_inr=cost, cost_basis='estimated from pinned INR price table')
        data['usage'] = usage
        return status, headers, json.dumps(data).encode()


def agent_manifest_fields(config):
    """The provider, spend and credential parts of a run manifest for a Sarvam model (the base builder says openrouter)."""
    return {
        'provider': 'sarvam', 'endpoint': config.endpoint,
        'spend': {'cap_inr': config.cap_inr, 'currency': 'INR', 'free_only': False, 'free_basis': config.free_basis,
                  'price_table_inr_per_million_input_output': {k: list(v) for k, v in PRICES_INR_PER_M.items()},
                  'gst_factor': GST_FACTOR, 'worst_case_chars_per_token': CHARS_PER_TOKEN_WORST,
                  'cost_rule': 'estimated from reported token counts and the pinned table; worst case charged when usage is missing; '
                               'PROVISIONAL prices; the cap is shared by all Sarvam calls of the run'},
        'credential': {'env_var': CREDENTIAL_ENV, 'logged': False}}


# --------------------------------------------------------------------------- S01 v0.6 episode on a Sarvam model

def s01_config(model, horizon_days, *, cap_inr=CAP_INR, **over):
    """Same limits and prompt as the OpenRouter S01 v0.6 config (`eval19_v3`), on a Sarvam model."""
    from . import eval19_v2 as ev2
    from . import eval19_v3 as ev3
    kw = dict(max_model_calls=6 * horizon_days, max_total_tokens=400000, max_output_tokens=ev2.MAX_OUTPUT_TOKENS,
              temperature=0.0, memory_window=8, timeout_seconds=90.0, max_retries=ev2.MAX_RETRIES,
              backoff_base_seconds=ev2.BACKOFF_BASE, backoff_cap_seconds=ev2.BACKOFF_CAP, max_nudges=2,
              system_prompt=ev3.S01_SYSTEM_PROMPT_V3)
    kw.update(over)
    return SarvamConfig(model, cap_inr=cap_inr, **kw)


def run_s01_episode(fixture, model, transport, *, cap_inr=CAP_INR, config_over=None, api_key='proxy-injected',
                    sleep=None, clock=None):
    """Run one S01 v0.6 episode on a Sarvam model through `transport` (a Guard around a SarvamTransport, or a mock).

    Returns the same raw private record as `eval19_v3.run_s01_episode`; grade it with `eval19_v3.grade_s01`."""
    import time
    from . import eval19_v3 as ev3
    from .agent_runner_v6 import ObservableRunnerV6
    from .dynamic_demo_v6 import factory
    from .eval19 import sha

    class SarvamAgentV6(ev3.LLMAgentV6):
        def __init__(self, config, tool_definitions, **kw):
            super().__init__(config, tool_definitions, **kw)
            m = dict(self.manifest)
            m.pop('manifest_sha256', None)
            m.update(agent_manifest_fields(config))
            m['harness_version'] = 'eval19-3-draft+sarvam-1'
            m['manifest_sha256'] = sha(m)
            self.manifest = m

    sleep, clock = sleep or time.sleep, clock or time.monotonic
    sink = []
    runner = ObservableRunnerV6(factory(fixture, sink)())
    cfg = s01_config(model, fixture['horizon_days'], cap_inr=cap_inr, **(config_over or {}))
    runner._world.reset()
    agent = SarvamAgentV6(cfg, runner.tool_definitions(), transport=transport, api_key=api_key, sleep=sleep, clock=clock)
    transcript = runner.run(agent, reset=False)
    return {'fixture_id': fixture['fixture_id'], 'model': model, 'manifest': agent.manifest,
            'transcript': la.redact(transcript, (api_key,)), 'telemetry': agent.telemetry(),
            'observed': agent.observed, 'world': sink[0]}
