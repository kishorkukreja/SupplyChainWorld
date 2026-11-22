"""Harness for the NEXT free-model diagnostic run (issue #19 fixes). Version `eval19-2`.

`eval19.py` and `scripts/run_eval19.py` are frozen for the FIRST diagnostic: their hashes are in
`evidence/issue-19/manifest.json`, so they are not edited here. This module sits beside them, reuses their guard,
budget, throttle, request scan and static case helpers by import, and changes only what the diagnostic found:

1. TASK DEFECT. S01 runs on the v0.5 family (`dynamic_v5`, `agent_runner_v5`, `dynamic_verifier_v5`), whose world
   carries an opaque scenario id. The harness-side id blinding of v0.4 is gone because it is no longer needed:
   the independent v0.5 checks, run on every observation, fail the episode if the world ever shows anything but the
   opaque label.
2. HARNESS GAP. The system prompt and every tool description are BUILT from `agent_runner_v5.RULES`, which has one
   sentence for every rule the world and the runner enforce (including that production cannot exceed open customer
   demand, the per-day call limit and the once-only commitments). A test ties every rejection reason to a sentence.
3. SUBMISSION SCHEMA. The static task offers one tool per answer kind (`schemas_v121`), each with exactly its
   own fields all required, and grades with the strict 1.2.1 shape check first. A malformed answer gets no credit
   and the clear messages are kept; nothing is repaired or coerced.

Nothing here makes a network call by itself. The run script supplies the transport. Free models only, USD 0
ceiling, enforced by the same adapter and guard as before. Nothing here measures general model ability.
"""
import copy
import json
import time

from . import llm_adapter as la
from . import schemas_v121 as strict
from .agent_runner_v5 import RULES, TOOL_RULES
from .eval19 import (BACKOFF_BASE, BACKOFF_CAP, BREAKER_403, BREAKER_429, MAX_OUTPUT_TOKENS, MAX_RETRIES, MIN_INTERVAL_SECONDS,  # noqa: F401
                     PRIVATE_MARKERS, PROBE_CAP, ROSTER_CONDITIONAL, ROSTER_CORE, STATIC_CAP_PER_MODEL, STATIC_REQUEST,
                     S01_DESCRIPTIONS, S01_SYSTEM_PROMPT, STATIC_SYSTEM_PROMPT, TOTAL_REQUEST_CAP, Guard,
                     load_static_cases, sanitize_static, select_static_cases, sha, static_private_strings,
                     static_visible_world)

EVAL_SCHEMA = 'eval19-2'
MANIFEST_SCHEMA = 'eval19-manifest-2'
S01_ORDER = ('s05-sudden-5d', 's05-warned-delayed-10d', 's05-warned-no-delay-10d',
             's05-multitier-cancel-10d', 's05-alt-cheaper-10d')

# --------------------------------------------------------------------------- S01 prompt and tools, built from RULES

S01_SYSTEM_PROMPT_V2 = (
    S01_SYSTEM_PROMPT + '\n\nEvery rule the plant enforces. A call that breaks one is refused, changes nothing and still '
    'counts as a call, so read these before you act:\n' + '\n'.join('- ' + sentence for sentence in RULES.values()))


def s01_descriptions():
    """Tool descriptions: the frozen base text plus the sentence of every rule that tool is subject to."""
    out = {}
    for name, base in S01_DESCRIPTIONS.items():
        rules = ' '.join(RULES[r] for r in TOOL_RULES.get(name, ()))
        out[name] = (base + ' ' + rules).strip()
    return out


S01_DESCRIPTIONS_V2 = s01_descriptions()


def s01_tools(tool_definitions):
    """OpenAI tool schemas for the v0.5 tool profile; descriptions carry the enforced rules."""
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
            'name': spec['name'], 'description': S01_DESCRIPTIONS_V2.get(spec['name'], spec['name']),
            'parameters': {'type': 'object', 'properties': props, 'required': required, 'additionalProperties': False}}})
    return tools


class LLMAgentV5(la.LLMAgent):
    """`LLMAgent` with the v0.5 tool profile. No scenario blinding: the v0.5 world already shows only an opaque label.
    Every observation shown to the model is recorded so the independent leak scan can check it afterwards."""

    def __init__(self, config, tool_definitions, **kw):
        super().__init__(config, tool_definitions, **kw)
        self.tools = s01_tools(tool_definitions)
        self._allowed = {t['function']['name'] for t in self.tools}
        m = dict(self.manifest)
        m.pop('manifest_sha256', None)
        m['tool_schemas'] = self.tools
        m['blinding'] = 'none needed: the v0.5 world state carries only an opaque scenario label'
        m['harness_version'] = EVAL_SCHEMA
        m['manifest_sha256'] = sha(m)
        self.manifest = m
        self.observed = []

    def _observation(self, view):  # noqa: D401 - overrides a staticmethod
        state = copy.deepcopy(view['state'])
        obs = {'clock': view['clock'], 'state': state, 'rules': view['rules'], 'last_outcome': view['last_outcome']}
        self.observed.append({'state': copy.deepcopy(state), 'rules': copy.deepcopy(view['rules']),
                              'last_outcome': copy.deepcopy(view['last_outcome'])})
        return obs


def s01_config(model, horizon_days, **over):
    kw = dict(max_model_calls=6 * horizon_days, max_total_tokens=400000, max_output_tokens=MAX_OUTPUT_TOKENS,
              temperature=0.0, memory_window=8, timeout_seconds=90.0, max_retries=MAX_RETRIES,
              backoff_base_seconds=BACKOFF_BASE, backoff_cap_seconds=BACKOFF_CAP, max_nudges=2,
              system_prompt=S01_SYSTEM_PROMPT_V2)
    kw.update(over)
    return la.AdapterConfig(model, **kw)


def run_s01_episode(fixture, model, transport, *, config_over=None, api_key='proxy-injected',
                    sleep=time.sleep, clock=time.monotonic):
    """Run one live (or mocked) S01 v0.5 episode through the observable runner. Returns the raw private record."""
    from .agent_runner_v5 import ObservableRunnerV5
    from .dynamic_demo_v5 import factory
    sink = []
    runner = ObservableRunnerV5(factory(fixture, sink)())
    cfg = s01_config(model, fixture['horizon_days'], **(config_over or {}))
    runner._world.reset()
    agent = LLMAgentV5(cfg, runner.tool_definitions(), transport=transport, api_key=api_key, sleep=sleep, clock=clock)
    transcript = runner.run(agent, reset=False)
    return {'fixture_id': fixture['fixture_id'], 'model': model, 'manifest': agent.manifest,
            'transcript': la.redact(transcript, (api_key,)), 'telemetry': agent.telemetry(),
            'observed': agent.observed, 'world': sink[0]}


def grade_s01(fixture, raw):
    """Independent v0.5 verification, replay and leak scan of one recorded S01 episode."""
    from .agent_runner_v5 import replay_v5
    from .dynamic_demo_v4 import METRICS, _get
    from .dynamic_demo_v5 import actions_of, factory
    from .dynamic_verifier_v5 import check_observations_for_leaks, verify_episode
    t, world = raw['transcript'], raw['world']
    complete = t['status'] == 'complete'
    scenario, horizon = fixture['scenario'], fixture['horizon_days']
    report = verify_episode(scenario, world.history(), horizon_days=horizon,
                            scorecard=world.scorecard() if complete else None, actions=actions_of(t))
    ok, diffs = replay_v5(t, factory(fixture))
    leaks = check_observations_for_leaks(scenario, raw['observed'])
    attempts = t['attempts']
    cats, tools = {}, {}
    for a in attempts:
        if not a['accepted']:
            cats[a['category']] = cats.get(a['category'], 0) + 1
        tools[a['tool']] = tools.get(a['tool'], 0) + 1
    card = t['scorecard']
    metrics = {m: _get(card, path) for m, (path, _, _) in METRICS.items()} if card else None
    return {
        'status': t['status'], 'completed': complete, 'attempts': len(attempts),
        'valid_actions': sum(1 for a in attempts if a['accepted']),
        'invalid_actions': sum(1 for a in attempts if not a['accepted'] and a['category'] != 'agent_error'),
        'agent_errors': sum(1 for a in attempts if a['category'] == 'agent_error'),
        'invalid_by_category': cats, 'tool_use': tools,
        'recovery_commitments': [{'day': a['day'], 'choice': a['arguments'].get('choice'), 'quantity': a['arguments'].get('quantity'),
                                  'accepted': a['accepted'], 'reason': a['reason']}
                                 for a in attempts if a['tool'] == 'commit_recovery'],
        'verifier_feasible': report.feasible, 'verifier_complete': report.complete, 'hard_violation_codes': report.codes(),
        'replay_reproduced': ok, 'replay_differences': diffs,
        'observation_leaks': leaks, 'metrics': metrics, 'scorecard': card}


def s01_baselines(fixtures):
    """Scripted S01 policies (not LLMs) per v0.5 scenario, metrics reported separately. Same world, same visible info."""
    from .agent_runner_v5 import POLICIES_V5
    from .dynamic_demo_v4 import METRICS, _get
    from .dynamic_demo_v5 import run_episode
    out = {}
    for f in fixtures:
        out[f['fixture_id']] = {}
        for p in POLICIES_V5:
            ep = run_episode(f, p)
            out[f['fixture_id']][p] = {m: _get(ep['scorecard'], path) for m, (path, _, _) in METRICS.items()}
    return out


# --------------------------------------------------------------------------- static v1.2 with the 1.2.1 strict shape

_OLD_SUBMISSION_BLOCK = STATIC_SYSTEM_PROMPT[STATIC_SYSTEM_PROMPT.index('Submission (arguments of submit_decision):'):]
_NEW_SUBMISSION_BLOCK = (
    'Submission. Call exactly one of three tools, the one for your answer; each takes exactly the fields listed and all of '
    'them are required (an extra or a missing field is rejected and gets no credit):\n'
    '- submit_award: kind "award", allocations [{supplier_id, item_id, quantity}], claimed_total_cost (string), evidence '
    '(non-empty list of short strings), flags, clarification_requests, approval_refs (lists of strings, possibly empty).\n'
    '- submit_clarification: kind "clarification", field (the missing quote term or approval request), disposition '
    '"record_and_escalate", evidence (non-empty list). Nothing else: no allocations, no claimed_total_cost, no flags.\n'
    '- submit_infeasible: kind "infeasible", evidence (non-empty list, see rule 9). Nothing else.\n'
    'Do not include any other keys. Nothing you send is repaired or reinterpreted.')
STATIC_SYSTEM_PROMPT_V2 = (STATIC_SYSTEM_PROMPT.replace('Answer by calling submit_decision exactly once.',
                                                        'Answer by calling exactly one submission tool, once.')
                           .replace(_OLD_SUBMISSION_BLOCK, _NEW_SUBMISSION_BLOCK))
SUBMIT_TOOLS = [strict.json_schema(k) for k in strict.KINDS]
TOOL_KIND = {v: k for k, v in strict.TOOL_NAMES.items()}


def static_messages(case):
    user = STATIC_REQUEST + '\n\nVisible world (JSON):\n' + json.dumps(static_visible_world(case), separators=(',', ':'))
    return [{'role': 'system', 'content': STATIC_SYSTEM_PROMPT_V2}, {'role': 'user', 'content': user}]


def static_config(model):
    return la.AdapterConfig(model, max_model_calls=2, max_output_tokens=MAX_OUTPUT_TOKENS, temperature=0.0,
                            timeout_seconds=120.0, max_retries=MAX_RETRIES, backoff_base_seconds=BACKOFF_BASE,
                            backoff_cap_seconds=BACKOFF_CAP, system_prompt=STATIC_SYSTEM_PROMPT_V2)


def static_manifest(model):
    cfg = static_config(model)
    return {'schema': EVAL_SCHEMA, 'task': 'static-v1.2+strict-1.2.1', 'model': model,
            'system_prompt_sha256': sha(STATIC_SYSTEM_PROMPT_V2), 'tool_schemas': SUBMIT_TOOLS,
            'request_parameters': {'temperature': 0.0, 'max_tokens': MAX_OUTPUT_TOKENS, 'tool_choice': 'auto'},
            'limits': {'max_logical_calls_per_case': 2, 'nudges': 1, 'max_retries': cfg.max_retries},
            'free_basis': cfg.free_basis}


def run_static_case(case, model, transport, *, api_key='proxy-injected', sleep=time.sleep, clock=time.monotonic):
    """One static task: at most two logical calls (the second only when the first returned no usable tool call).

    Returns a private record with the raw arguments of the answer (or None), the tool that carried them, and
    per-call telemetry. Arguments are passed on exactly as the model sent them.
    """
    cfg = static_config(model)
    messages = static_messages(case)
    calls, submission, failure, status, used_tool = [], None, None, 'no_submission', None
    nudged = False
    while len(calls) < 2:
        try:
            res = la.chat_request(cfg, messages, SUBMIT_TOOLS, transport=transport, api_key=api_key, sleep=sleep, clock=clock)
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
            if fn.get('name') in TOOL_KIND:
                if isinstance(raw, dict):
                    parsed = raw
                else:
                    try:
                        parsed = json.loads(raw) if isinstance(raw, str) and raw.strip() else None
                    except ValueError:
                        rec['malformed_arguments'] = True
                used_tool = fn.get('name')
        else:
            rec['status'] = 'no_tool_call'
        if isinstance(parsed, dict):
            kind = parsed.get('kind')
            if isinstance(kind, str) and kind in strict.KINDS and strict.TOOL_NAMES[kind] != used_tool:
                # The tool says one thing and the answer another. Nothing is guessed: no submission, clear message.
                status = 'tool_kind_mismatch'
                failure = {'error_class': 'tool_kind_mismatch',
                           'message': f'tool {used_tool} was called with kind {kind!r}; the kind must match the tool'}
                break
            submission, status = parsed, 'submitted'
            break
        if nudged:
            status = 'no_usable_submission'
            break
        nudged = True
        messages = messages + [{'role': 'user', 'content': 'Reply by calling one submission tool once, with valid JSON arguments and no prose.'}]
    return {'case_id': case['case_id'], 'model': model, 'status': status, 'submission': submission, 'tool': used_tool,
            'failure': failure, 'calls': calls}


def grade_static(case, submission):
    """Strict 1.2.1 shape check first (no repair), then the independent 1.2 checker. Private data used only here."""
    from .verification_v12 import verify
    exp = case['expected']
    if submission is None:
        return {'graded': False, 'reason': 'no submission'}
    kind = submission.get('kind') if isinstance(submission, dict) else None
    problems = strict.strict_problems(submission)
    if problems:
        return {'graded': True, 'schema_valid': False, 'strict_problems': problems, 'kind': kind,
                'expected_kind': exp['expected_outcome'], 'outcome_matches': kind == exp['expected_outcome'],
                'accepted': False, 'hard_failures': ['strict_schema'], 'feasible': False, 'independent_cost': None,
                'optimality': None, 'objective_gap': None, 'objective_gap_pct': None}
    res = verify(case['world'], submission, expected_outcome=exp['expected_outcome'], reference_cost=exp.get('optimal_cost'),
                 task_measures=case['task'].get('concentration_measures', []))
    fails = list(res.critical_failures)
    schema_valid = 'schema_validation' not in fails
    hard = [f for f in fails if f != 'expected_outcome']
    return {'graded': True, 'schema_valid': schema_valid, 'strict_problems': [], 'kind': kind,
            'expected_kind': exp['expected_outcome'], 'outcome_matches': kind == exp['expected_outcome'],
            'accepted': res.accepted, 'hard_failures': hard, 'feasible': schema_valid and not hard,
            'independent_cost': None if res.independent_cost is None else str(res.independent_cost),
            'optimality': res.optimality, 'objective_gap': None if res.objective_gap is None else str(res.objective_gap),
            'objective_gap_pct': None if res.objective_gap_pct is None else str(res.objective_gap_pct)}


def static_baseline(case, which):
    """Reference solver or greedy heuristic on the same visible world, graded by the same strict-then-independent path."""
    from .schemas_v12 import World
    from .solvers_v12 import solve_heuristic, solve_reference
    world = World.model_validate(case['world'])
    res = solve_reference(world, time_limit_seconds=20.0) if which == 'reference' else solve_heuristic(world)
    try:
        sub = res.submission().model_dump(mode='json')
    except ValueError:
        return {'solver_status': res.status, 'graded': False, 'reason': 'solver produced no final submission'}
    # The solver's own pydantic dump carries bookkeeping the 1.2.1 shape does not allow (schema_version, empty
    # optional fields). This is our solver, not a model answer: keep exactly the per-kind fields before grading.
    sub = {k: sub[k] for k in strict.FIELDS[sub['kind']] if k in sub}
    if isinstance(sub.get('allocations'), list):
        sub['allocations'] = [{k: a[k] for k in ('supplier_id', 'item_id', 'quantity')} for a in sub['allocations']]
    out = grade_static(case, sub)
    out['solver_status'] = res.status
    return out
