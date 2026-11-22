"""Small free-model diagnostic evaluation harness (issue #19).

Two task families, one harness:

* S01 v0.4 (dynamic): a real model drives `ObservableRunnerV4` through the existing LLM adapter
  (`llm_adapter.LLMAgent`) with a v0.4 tool profile; every episode is independently verified
  (`dynamic_verifier_v4`) and replayed (`replay_v4`).
* Static v1.2 (supplier allocation): the model sees ONLY the visible world plus a fixed rules text and
  answers with one `submit_decision` tool call in the v1.2 submission schema; the answer is graded by the
  independent checker `verification_v12` and compared with the reference solver and greedy heuristic run
  on the same visible world.

Hard rules enforced here: free models only (the adapter guard), $0 spend, a global request cap with
per-phase caps, a per-model circuit breaker for repeated 429/403, throttling, no private data in any
request (blinded scenario id, world-only static prompts, request-body scan), actors act and scorers do not.
Nothing here measures general model ability. No score is combined across metrics.
"""
import copy
import hashlib
import json
import time
from decimal import Decimal
from pathlib import Path

from . import llm_adapter as la

ROOT = Path(__file__).resolve().parents[2]
EVAL_SCHEMA = 'eval19-1'
TOTAL_REQUEST_CAP = 250
PROBE_CAP = 4
STATIC_CAP_PER_MODEL = 25
MIN_INTERVAL_SECONDS = 3.5
BREAKER_429 = 6          # consecutive HTTP 429 responses with no 200 in between
BREAKER_403 = 2          # consecutive HTTP 403 responses with no 200 in between
MAX_OUTPUT_TOKENS = 4096
MAX_RETRIES = 2
BACKOFF_BASE = 5.0
BACKOFF_CAP = 30.0
S01_ORDER = ('s04-sudden-5d', 's04-warned-delayed-10d', 's04-warned-no-delay-10d',
             's04-multitier-cancel-10d', 's04-alt-cheaper-10d')

ROSTER_CORE = ('baidu/ernie-5.5-flash-preview:free', 'nvidia/nemotron-3-ultra-550b-a55b:free',
               'nvidia/nemotron-3.5-super-vl:free')
ROSTER_CONDITIONAL = ('cohere/north-mini-code:free', 'thinkingmachines/inkling-2-small:free')

# Strings that must never appear in any request body.
PRIVATE_MARKERS = ('delay_outcome', 'delayed_arrival_day', 'signal_day', 'notice_day', 'opening_components',
                   'hand_ledger', 'oracle', 'known_wrong', 'optimal_cost', 'valid_alternatives', 'expected_outcome',
                   'expected_submission', 'comparison_by_policy', 'baseline_score')

# --------------------------------------------------------------------------- prompts (frozen)

S01_SYSTEM_PROMPT = (
    "You run a small plant's supply recovery and production for a fixed number of simulated days, using tools. "
    'Each message shows the current visible state, the visible rules (including any recovery offers with their rate '
    'cards and the remaining recovery budget), the clock and the outcome of your last tool call. Use only that '
    'information. Call exactly one tool per reply and do not reply in prose. The state is already included after every '
    'call, so you rarely need the read tools. Time moves only when you call advance_day. Each day you may schedule '
    'production once with release_production (quantity within daily capacity and components on hand) and then you '
    'call advance_day. commit_recovery buys a recovery lot (choice expedite or alternate, quantity in units); it can be '
    'called more than once while offers are shown, cannot be undone, costs and arrives according to the rate card for '
    'the current day, and must fit the remaining recovery budget. Orders have due days, penalties and priority tiers '
    'shown in the rules. Do what you judge best for the plant, weighing recovery spend, late-delivery penalties, order '
    'priority and supply risk. Keep acting until the episode phase is complete.')

S01_DESCRIPTIONS = {
    'read_state': 'Read the visible plant state (optionally one section). Does not advance time.',
    'read_recovery_offers': 'Read currently visible supply recovery offers, if any. Does not advance time.',
    'read_scorecard': 'Read the scorecard. Only available once the episode is complete.',
    'commit_recovery': ('Irreversibly buy a recovery lot. choice is expedite (move the primary lot earlier) or alternate '
                        '(a new supplier lot); quantity is in units. May be called more than once; cost and arrival follow '
                        'the rate card for the current day; must fit the remaining recovery budget.'),
    'release_production': ('Schedule today\'s production run (once per day): quantity of components to convert into '
                           'finished goods when the day closes, at most the daily capacity and the components on hand.'),
    'advance_day': 'Close today and advance simulated time by one day.',
}

STATIC_REQUEST = ('Allocate component purchases for the visible world. Minimize landed cost subject to the visible '
                  'policy and the rules in the system message, or submit a supported exception.')

STATIC_SYSTEM_PROMPT = """You are a procurement analyst for a discrete manufacturer. You get ONE task: a visible world (JSON: items, stock, inbound supply, suppliers, supplier quotes, constraints, policy, approval records) and you must either decide a supplier allocation or, when the rules below do not allow an award, submit an exception. Use only the world shown. Answer by calling submit_decision exactly once. All arithmetic is exact decimal arithmetic: never round money, and never treat a missing price or freight as zero.

Rules (version 1.2, all numbers in the world are provisional working values):

1. Net requirement per item = max(0, demand + safety stock - usable stock - inbound arriving on or before the item due_date - late-inbound credit).
   - Only stock with status "usable" counts; held stock never counts.
   - Safety stock: if safety_stock_override is set use it. Otherwise, if service_level, demand_std and lead_time_periods are given, safety stock is the smallest whole number s with s*s >= (z*demand_std)^2 * lead_time_periods, where z is 1.2816 for service level 0.90, 1.6449 for 0.95, 1.9600 for 0.975 and 2.3263 for 0.99. Otherwise it is 0.
   - Late-inbound credit: inbound arriving 1 to policy.late_inbound_tolerance_days days after the due_date (inclusive) counts floor(quantity * policy.late_inbound_credit) units. Later arrivals count nothing.
2. A quote is eligible only if qualified is true, as_of lies within valid_from..valid_to inclusive, and its arrival_date is on or before the item due_date.
3. An order for a supplier and item must be 0 or a whole multiple of the quote multiple, at least moq and at most capacity. Use each supplier-item pair at most once.
4. Buy at least the net requirement of every item. Buying more than net requirement + excess_allowance is not allowed, except for MOQ excess: if the item has moq_excess_allowed true and the total bought equals the smallest total at or above the net requirement that is reachable with one legal order size (or none) per eligible quote of that item, it is allowed and you must add the flag "moq_excess:<item_id>". If the excess value (excess units x the item goods value / units bought, where excess units = bought - net requirement - excess_allowance) is above policy.moq_excess_approval_threshold, you must also cite in approval_refs the approval_id of a granted record in the world's approvals for that item. At or below the threshold the flag alone is enough. If MOQ forces excess above the allowance and no approval record for the item is in the world, the supported answer is a clarification with field "approvals.moq_excess.<item_id>". If max_excess is set, bought - net requirement must not exceed it.
5. Missing commercial terms. A quote may have a null unit_price or variable_freight. An estimate on the last_known_unit_price / last_known_variable_freight is allowed only when the item is not critical, both terms are available after substituting the last known values, and the line value (quantity x (price + freight)) is at or below constraints.approval_limit (a null limit means no estimate). An estimated line must carry the flag "estimated:<supplier_id>:<item_id>" and list every missing field in clarification_requests as "quotes.<supplier_id>.<item_id>.unit_price" and/or "quotes.<supplier_id>.<item_id>.variable_freight". Ask clarification first: if an eligible quote of an item with a positive net requirement has a missing term and the estimate path does not cover it (item critical, no last known value, no approval limit, or min(capacity, max(net requirement, moq)) x estimated unit cost above the limit), then NO award is acceptable, even if other complete quotes could cover the need. The answer is kind "clarification" with field "quotes.<supplier_id>.<item_id>.<unit_price or variable_freight>" and disposition "record_and_escalate".
6. Total cost = sum over order lines of quantity x (unit_price + variable_freight) plus, for each supplier that receives any quantity, its fixed charge: for fixed_charge_basis "flat" the fixed_charge; for "order_units" or "goods_value" the charge of the highest fixed_charge_table tier whose from_measure is at or below that supplier's total ordered units (or goods value). claimed_total_cost must equal this total exactly. The total must not exceed constraints.budget.
7. Concentration rules in constraints.concentration: "spend_share": no supplier's spend (its goods plus its fixed charge) may exceed limit x total cost. "quantity_share": over the listed item_ids, no supplier's units may exceed limit x total units. "per_item_share": for each listed item (all items if none listed), no supplier's units of that item may exceed limit x the units bought of that item.
8. Objective: among allowed awards, minimize total cost. Answers within a small tolerance of the optimum are treated as equivalent, but cost minimization is still the goal.
9. Infeasible: if for some item the sum, over its eligible quotes, of the largest legal order size is less than the net requirement, no award can meet the need. Submit kind "infeasible" with evidence stating, for each short item, that the eligible order capacity is less than the net requirement (use the words "capacity" and "less than" and give both numbers).

Submission (arguments of submit_decision):
- Award: kind "award", allocations [{supplier_id, item_id, quantity}], claimed_total_cost (string), evidence (non-empty list of short strings), flags, clarification_requests, approval_refs (lists, possibly empty).
- Clarification: kind "clarification", field (the missing quote term or approval request), disposition "record_and_escalate", evidence (non-empty).
- Infeasible: kind "infeasible", evidence (non-empty, see rule 9).
Do not include any other keys."""

SUBMIT_TOOL = {'type': 'function', 'function': {
    'name': 'submit_decision',
    'description': 'Submit the final decision for the task: an award, a clarification request, or an infeasibility finding. Call once.',
    'parameters': {
        'type': 'object',
        'properties': {
            'kind': {'type': 'string', 'enum': ['award', 'clarification', 'infeasible']},
            'allocations': {'type': 'array', 'items': {'type': 'object', 'properties': {
                'supplier_id': {'type': 'string'}, 'item_id': {'type': 'string'}, 'quantity': {'type': 'integer', 'minimum': 0}},
                'required': ['supplier_id', 'item_id', 'quantity'], 'additionalProperties': False}},
            'claimed_total_cost': {'type': 'string'},
            'evidence': {'type': 'array', 'items': {'type': 'string'}},
            'flags': {'type': 'array', 'items': {'type': 'string'}},
            'clarification_requests': {'type': 'array', 'items': {'type': 'string'}},
            'approval_refs': {'type': 'array', 'items': {'type': 'string'}},
            'field': {'type': 'string'},
            'disposition': {'type': 'string', 'enum': ['record_and_escalate']}},
        'required': ['kind', 'evidence'], 'additionalProperties': False}}}


def sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


# --------------------------------------------------------------------------- budget, breaker, throttle

class Guard:
    """Transport wrapper: global and per-phase request caps, per-model breaker, throttle, ledger, leak scan.

    `base` is a transport callable (request -> (status, headers, body_bytes)). It is the only place a request is
    counted, so retries count against the cap. A refused call returns HTTP 418 (non-retryable) and sets a flag.
    """

    def __init__(self, base, *, total_cap=TOTAL_REQUEST_CAP, phase_caps=None, sleep=time.sleep, clock=time.monotonic,
                 min_interval=MIN_INTERVAL_SECONDS, ledger_path=None, private_strings=()):
        self.base = base
        self.total_cap = total_cap
        self.phase_caps = dict(phase_caps or {})
        self.sleep, self.clock, self.min_interval = sleep, clock, min_interval
        self.ledger_path = ledger_path
        self.private_strings = list(private_strings)
        self.used_total = 0
        self.used_phase = {}
        self.phase = 'probe'
        self.model = None
        self.stopped = {}              # model -> reason
        self.consec = {}               # model -> {'429': n, '403': n}
        self.refused = None            # last refusal reason
        self.leak_flags = []
        self._last = None
        self.requests = []             # per-request meta (no bodies)

    # -- accounting helpers
    def remaining(self, phase):
        cap = self.phase_caps.get(phase, self.total_cap)
        return max(0, min(cap - self.used_phase.get(phase, 0), self.total_cap - self.used_total))

    def _refuse(self, reason):
        self.refused = reason
        return 418, {}, json.dumps({'error': {'message': reason, 'code': 418}}).encode()

    def scan(self, text):
        hits = [m for m in PRIVATE_MARKERS if m in text]
        hits += [s for s in self.private_strings if s and s in text]
        return hits

    def __call__(self, request):
        model = self.model
        if model in self.stopped:
            return self._refuse('model stopped: ' + self.stopped[model])
        if self.remaining(self.phase) <= 0:
            return self._refuse('request cap reached for phase ' + self.phase)
        body_text = request['body'].decode('utf-8', 'replace') if isinstance(request['body'], (bytes, bytearray)) else str(request['body'])
        hits = self.scan(body_text)
        if hits:
            self.leak_flags.append({'model': model, 'phase': self.phase, 'hits': hits})
            return self._refuse('private marker in request body; request not sent')
        if self._last is not None:
            wait = self.min_interval - (self.clock() - self._last)
            if wait > 0:
                self.sleep(wait)
        self.used_total += 1
        self.used_phase[self.phase] = self.used_phase.get(self.phase, 0) + 1
        t0 = self.clock()
        status, headers, raw = self.base(request)
        self._last = self.clock()
        eff = status
        if status == 200:
            try:
                data = json.loads(raw.decode('utf-8', 'replace'))
                if isinstance(data, dict) and 'error' in data and not data.get('choices'):
                    err = data['error']
                    code = err.get('code') if isinstance(err, dict) else None
                    eff = code if isinstance(code, int) else 502
            except ValueError:
                pass
        c = self.consec.setdefault(model, {'429': 0, '403': 0})
        if eff == 200:
            c['429'] = c['403'] = 0
        elif eff == 429:
            c['429'] += 1
        elif eff == 403:
            c['403'] += 1
        if c['429'] >= BREAKER_429:
            self.stopped[model] = f'{c["429"]} consecutive HTTP 429'
        if c['403'] >= BREAKER_403:
            self.stopped[model] = f'{c["403"]} consecutive HTTP 403'
        meta = {'seq': self.used_total, 'model': model, 'phase': self.phase, 'http_status': status,
                'effective_status': eff, 'latency_ms': round((self._last - t0) * 1000.0, 1)}
        self.requests.append(meta)
        if self.ledger_path:
            with open(self.ledger_path, 'a') as fh:
                fh.write(json.dumps(meta) + '\n')
        return status, headers, raw


# --------------------------------------------------------------------------- S01 v0.4

def s01_tools(tool_definitions):
    """OpenAI tool schemas for the v0.4 tool profile (correct commit_recovery and production descriptions)."""
    tools = []
    for spec in tool_definitions:
        if not spec.get('granted'):
            continue
        props = {}
        for a in spec['arguments']:
            if a == 'section':
                props[a] = {'type': 'string', 'enum': list(la.READ_SECTIONS), 'description': 'which part of the visible view to read'}
            elif a == 'choice':
                props[a] = {'type': 'string', 'enum': list(spec.get('choices', [])), 'description': 'recovery option'}
            elif a == 'quantity' and spec['name'] == 'commit_recovery':
                props[a] = {'type': 'integer', 'minimum': 1, 'description': 'units to buy in this recovery lot'}
            elif a == 'quantity':
                props[a] = {'type': 'integer', 'minimum': 0, 'description': 'units to release into production today'}
            else:
                props[a] = {'type': 'string'}
        required = [] if spec['name'] == 'read_state' else list(spec['arguments'])
        tools.append({'type': 'function', 'function': {
            'name': spec['name'], 'description': S01_DESCRIPTIONS.get(spec['name'], spec['name']),
            'parameters': {'type': 'object', 'properties': props, 'required': required, 'additionalProperties': False}}})
    return tools


class LLMAgentV4(la.LLMAgent):
    """`LLMAgent` with the v0.4 tool profile and a blinded scenario id (the world state exposes a scenario_id whose
    text names the outcome class, for example 'warned-delayed'; that is never shown to the model)."""

    def __init__(self, config, tool_definitions, *, alias='scenario-01', **kw):
        super().__init__(config, tool_definitions, **kw)
        self._alias = alias
        self.tools = s01_tools(tool_definitions)
        self._allowed = {t['function']['name'] for t in self.tools}
        m = dict(self.manifest)
        m.pop('manifest_sha256', None)
        m['tool_schemas'] = self.tools
        m['blinding'] = 'state.scenario_id replaced by an opaque alias in every observation'
        m['manifest_sha256'] = sha(m)
        self.manifest = m
        self.observed = []

    def _observation(self, view):  # noqa: D401 - overrides a staticmethod
        state = copy.deepcopy(view['state'])
        if 'scenario_id' in state:
            state['scenario_id'] = self._alias
        obs = {'clock': view['clock'], 'state': state, 'rules': view['rules'], 'last_outcome': view['last_outcome']}
        self.observed.append({'state': copy.deepcopy(state), 'rules': copy.deepcopy(view['rules'])})
        return obs


def s01_config(model, horizon_days, **over):
    kw = dict(max_model_calls=6 * horizon_days, max_total_tokens=400000, max_output_tokens=MAX_OUTPUT_TOKENS,
              temperature=0.0, memory_window=8, timeout_seconds=90.0, max_retries=MAX_RETRIES,
              backoff_base_seconds=BACKOFF_BASE, backoff_cap_seconds=BACKOFF_CAP, max_nudges=2,
              system_prompt=S01_SYSTEM_PROMPT)
    kw.update(over)
    return la.AdapterConfig(model, **kw)


def run_s01_episode(fixture, model, transport, *, alias='scenario-01', config_over=None, api_key='proxy-injected',
                    sleep=time.sleep, clock=time.monotonic):
    """Run one live (or mocked) S01 v0.4 episode through the observable runner. Returns the raw private record."""
    from .agent_runner_v4 import ObservableRunnerV4
    from .dynamic_demo_v4 import factory
    sink = []
    runner = ObservableRunnerV4(factory(fixture, sink)())
    cfg = s01_config(model, fixture['horizon_days'], **(config_over or {}))
    runner._world.reset()
    agent = LLMAgentV4(cfg, runner.tool_definitions(), alias=alias, transport=transport, api_key=api_key,
                       sleep=sleep, clock=clock)
    transcript = runner.run(agent, reset=False)
    return {'fixture_id': fixture['fixture_id'], 'model': model, 'manifest': agent.manifest,
            'transcript': la.redact(transcript, (api_key,)), 'telemetry': agent.telemetry(),
            'observed': agent.observed, 'world': sink[0]}


def grade_s01(fixture, raw):
    """Independent verification and replay of one recorded S01 episode. Plain data in, plain data out."""
    from .agent_runner_v4 import replay_v4
    from .dynamic_demo_v4 import METRICS, _get, factory
    from .dynamic_verifier_v4 import check_observations_for_leaks, verify_episode
    t, world = raw['transcript'], raw['world']
    complete = t['status'] == 'complete'
    actions = [{'day': a['day'], 'kind': {'commit_recovery': 'recovery', 'release_production': 'release'}[a['tool']],
                'arguments': a['arguments'], 'result': a['result']}
               for a in t['attempts'] if a['tool'] in ('commit_recovery', 'release_production')]
    scenario, horizon = fixture['scenario'], fixture['horizon_days']
    report = verify_episode(scenario, world.history(), horizon_days=horizon,
                            scorecard=world.scorecard() if complete else None, actions=actions)
    ok, diffs = replay_v4(t, factory(fixture))
    leaks = check_observations_for_leaks(scenario, raw['observed'])
    attempts = t['attempts']
    cats = {}
    for a in attempts:
        if not a['accepted']:
            cats[a['category']] = cats.get(a['category'], 0) + 1
    tools = {}
    for a in attempts:
        tools[a['tool']] = tools.get(a['tool'], 0) + 1
    card = t['scorecard']
    metrics = {m: _get(card, path) for m, (path, _, _) in METRICS.items()} if card else None
    return {
        'status': t['status'], 'completed': complete, 'attempts': len(attempts),
        'valid_actions': sum(1 for a in attempts if a['accepted']), 'invalid_actions': sum(1 for a in attempts if not a['accepted'] and a['category'] != 'agent_error'),
        'agent_errors': sum(1 for a in attempts if a['category'] == 'agent_error'),
        'invalid_by_category': cats, 'tool_use': tools,
        'recovery_commitments': [{'day': a['day'], 'choice': a['arguments'].get('choice'), 'quantity': a['arguments'].get('quantity'),
                                  'accepted': a['accepted'], 'reason': a['reason']}
                                 for a in attempts if a['tool'] == 'commit_recovery'],
        'verifier_feasible': report.feasible, 'verifier_complete': report.complete, 'hard_violation_codes': report.codes(),
        'replay_reproduced': ok, 'replay_differences': diffs,
        'observation_leaks': leaks, 'metrics': metrics, 'scorecard': card}


def s01_baselines(fixtures):
    """Scripted S01 policies (not LLMs) per scenario, metrics reported separately. Same world, same visible info."""
    from .agent_runner_v4 import POLICIES_V4
    from .dynamic_demo_v4 import METRICS, _get, run_episode
    out = {}
    for f in fixtures:
        out[f['fixture_id']] = {}
        for p in POLICIES_V4:
            ep = run_episode(f, p)
            out[f['fixture_id']][p] = {m: _get(ep['scorecard'], path) for m, (path, _, _) in METRICS.items()}
    return out


# --------------------------------------------------------------------------- static v1.2

def load_static_cases(root=ROOT):
    d = Path(root) / 'fixtures/reference_cases_v1_2'
    return {p.stem: json.loads(p.read_text()) for p in sorted(d.glob('ref-*.json'))}


def select_static_cases(cases):
    """Frozen selection rule: every non-award case (clarification and infeasible), plus every second award case in
    sorted case-id order starting with the first (positions 0, 2, 4, ...). Deterministic, no randomness."""
    ids = sorted(cases)
    exceptions = [i for i in ids if cases[i]['expected']['expected_outcome'] != 'award']
    awards = [i for i in ids if cases[i]['expected']['expected_outcome'] == 'award']
    return sorted(exceptions + awards[0::2])


def static_visible_world(case):
    """The ONLY case data a model sees: the world object as stored. No expected, purpose, calculation, review,
    task or known_wrong fields."""
    return copy.deepcopy(case['world'])


def static_messages(case):
    user = STATIC_REQUEST + '\n\nVisible world (JSON):\n' + json.dumps(static_visible_world(case), separators=(',', ':'))
    return [{'role': 'system', 'content': STATIC_SYSTEM_PROMPT}, {'role': 'user', 'content': user}]


def static_private_strings(case):
    """Case-specific private texts that must never be sent (used by the request-body scan)."""
    out = [case['purpose'], case['expected'].get('calculation', '')]
    out += [kw.get('reason', '') for kw in case.get('known_wrong', []) if isinstance(kw, dict)]
    return [s for s in out if isinstance(s, str) and len(s) > 12]


def static_config(model):
    return la.AdapterConfig(model, max_model_calls=2, max_output_tokens=MAX_OUTPUT_TOKENS, temperature=0.0,
                            timeout_seconds=120.0, max_retries=MAX_RETRIES, backoff_base_seconds=BACKOFF_BASE,
                            backoff_cap_seconds=BACKOFF_CAP, system_prompt=STATIC_SYSTEM_PROMPT)


def static_manifest(model):
    cfg = static_config(model)
    m = {'schema': EVAL_SCHEMA, 'task': 'static-v1.2', 'model': model, 'system_prompt_sha256': sha(STATIC_SYSTEM_PROMPT),
         'tool_schemas': [SUBMIT_TOOL], 'request_parameters': {'temperature': 0.0, 'max_tokens': MAX_OUTPUT_TOKENS, 'tool_choice': 'auto'},
         'limits': {'max_logical_calls_per_case': 2, 'nudges': 1, 'max_retries': cfg.max_retries},
         'free_basis': cfg.free_basis}
    return m


def run_static_case(case, model, transport, *, api_key='proxy-injected', sleep=time.sleep, clock=time.monotonic):
    """One static task: at most two logical calls (the second only when the first returned no usable tool call).

    Returns a private record with the parsed submission (or None) and per-call telemetry.
    """
    cfg = static_config(model)
    messages = static_messages(case)
    calls, submission, failure, status = [], None, None, 'no_submission'
    nudged = False
    while len(calls) < 2:
        try:
            res = la.chat_request(cfg, messages, [SUBMIT_TOOL], transport=transport, api_key=api_key, sleep=sleep, clock=clock)
        except la.AdapterError as exc:
            calls.append({'status': 'error', 'error_class': exc.error_class, 'usage': None, 'cost_usd': 'unknown', 'latency_ms': None})
            failure = {'error_class': exc.error_class, 'message': la.redact_text(str(exc), (api_key,))}
            status = 'error:' + exc.error_class
            break
        body = res['body']
        usage = la.extract_usage(body)
        rec = {'status': 'ok', 'http_requests': res['http_requests'], 'retries': res['retries'],
               'latency_ms': round(res['latency_ms'], 1), 'total_latency_ms': round(res['total_latency_ms'], 1),
               'usage': usage, 'cost_usd': la.call_cost(model, usage, True), 'finish_reason': None,
               'returned_model': body.get('model') if isinstance(body.get('model'), str) else None}
        calls.append(rec)
        choices = body.get('choices')
        msg = choices[0].get('message') if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
        if not isinstance(msg, dict):
            rec['status'] = 'malformed_response'
            status, failure = 'error:malformed_response', {'error_class': 'malformed_response', 'message': 'no choices[0].message'}
            break
        rec['finish_reason'] = choices[0].get('finish_reason')
        tcs = msg.get('tool_calls')
        parsed = None
        if isinstance(tcs, list) and tcs and isinstance(tcs[0], dict):
            fn = tcs[0].get('function') if isinstance(tcs[0].get('function'), dict) else {}
            rec['tool'] = fn.get('name')
            raw = fn.get('arguments', '')
            if fn.get('name') == 'submit_decision':
                if isinstance(raw, dict):
                    parsed = raw
                else:
                    try:
                        parsed = json.loads(raw) if isinstance(raw, str) and raw.strip() else None
                    except ValueError:
                        rec['malformed_arguments'] = True
        else:
            rec['status'] = 'no_tool_call'
        if isinstance(parsed, dict):
            submission, status = parsed, 'submitted'
            break
        if nudged:
            status = 'no_usable_submission'
            break
        nudged = True
        messages = messages + [{'role': 'user', 'content': 'Reply by calling submit_decision once, with valid JSON arguments and no prose.'}]
    return {'case_id': case['case_id'], 'model': model, 'status': status, 'submission': submission, 'failure': failure,
            'calls': calls}


def _rank_check_kind(sub):
    return sub.get('kind') if isinstance(sub, dict) else None


def grade_static(case, submission):
    """Grade one submission (dict or None) with the independent v1.2 checker. Private expected data is used only here."""
    from .verification_v12 import verify
    exp = case['expected']
    if submission is None:
        return {'graded': False, 'reason': 'no submission'}
    res = verify(case['world'], submission, expected_outcome=exp['expected_outcome'], reference_cost=exp.get('optimal_cost'),
                 task_measures=case['task'].get('concentration_measures', []))
    fails = list(res.critical_failures)
    schema_valid = 'schema_validation' not in fails
    hard = [f for f in fails if f != 'expected_outcome']
    kind = _rank_check_kind(submission)
    return {'graded': True, 'schema_valid': schema_valid, 'kind': kind, 'expected_kind': exp['expected_outcome'],
            'outcome_matches': kind == exp['expected_outcome'], 'accepted': res.accepted,
            'hard_failures': hard, 'feasible': schema_valid and not hard,
            'independent_cost': None if res.independent_cost is None else str(res.independent_cost),
            'optimality': res.optimality, 'objective_gap': None if res.objective_gap is None else str(res.objective_gap),
            'objective_gap_pct': None if res.objective_gap_pct is None else str(res.objective_gap_pct)}


def static_baseline(case, which):
    """Reference solver or greedy heuristic on the same visible world, graded by the same checker."""
    from .schemas_v12 import World
    from .solvers_v12 import solve_heuristic, solve_reference
    world = World.model_validate(case['world'])
    res = solve_reference(world, time_limit_seconds=20.0) if which == 'reference' else solve_heuristic(world)
    try:
        sub = res.submission().model_dump(mode='json')
    except ValueError:
        return {'solver_status': res.status, 'graded': False, 'reason': 'solver produced no final submission'}
    out = grade_static(case, sub)
    out['solver_status'] = res.status
    return out


def sanitize_static(raw, grade):
    sub = raw['submission']
    if isinstance(sub, dict):
        sub = copy.deepcopy(sub)
        if isinstance(sub.get('evidence'), list):
            sub['evidence'] = [str(e)[:300] for e in sub['evidence']][:6]
    ok = [c for c in raw['calls'] if c.get('usage')]
    return {'case_id': raw['case_id'], 'model': raw['model'], 'status': raw['status'], 'failure': raw['failure'],
            'logical_calls': len(raw['calls']), 'http_requests': sum(c.get('http_requests', 0) for c in raw['calls']),
            'retries': sum(len(c.get('retries', [])) for c in raw['calls']),
            'prompt_tokens': sum(c['usage'].get('prompt_tokens', 0) for c in ok),
            'completion_tokens': sum(c['usage'].get('completion_tokens', 0) for c in ok),
            'usage_complete': bool(raw['calls']) and len(ok) == len(raw['calls']),
            'latency_ms_total': round(sum(c['latency_ms'] for c in raw['calls'] if c.get('latency_ms') is not None), 1),
            'cost_usd': 0.0 if raw['calls'] and all(c.get('cost_usd') == 0.0 for c in raw['calls']) else 'unknown',
            'finish_reasons': [c.get('finish_reason') for c in raw['calls']],
            'submission': sub, 'grade': grade}
