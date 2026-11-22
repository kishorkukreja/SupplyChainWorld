#!/usr/bin/env python3
"""Issue #19 free-model diagnostic: manifest, live run (resumable), sanitized report.

  PYTHONPATH=src python scripts/run_eval19.py manifest [--out evidence/issue-19/manifest.json]
  OPENROUTER_API_KEY=... PYTHONPATH=src python scripts/run_eval19.py run --state DIR
  PYTHONPATH=src python scripts/run_eval19.py report --state DIR [--out evidence/issue-19]

The key is read only from the environment (the sandbox proxy injects the real one); it is never printed or stored.
Full private records stay in --state (outside the repository); only sanitized records are written under evidence/.
"""
import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from supplychainworld import eval19 as ev  # noqa: E402
from supplychainworld import llm_adapter as la  # noqa: E402

HARNESS_FILES = ('src/supplychainworld/eval19.py', 'src/supplychainworld/llm_adapter.py', 'scripts/run_eval19.py',
                 'src/supplychainworld/verification_v12.py', 'src/supplychainworld/solvers_v12.py',
                 'src/supplychainworld/dynamic_verifier_v4.py', 'src/supplychainworld/dynamic_v4.py',
                 'src/supplychainworld/agent_runner_v4.py', 'config/llm_roster.json')
FIXTURE_FILES = ('fixtures/dynamic/v0.4/scenarios.json',)
METRIC_NOTE = ('Reported separately, never combined into one score: S01 cost (net_cost, recovery_spend, penalties), service '
               '(otif_orders_met, on_time_units, unit_days_late), tier impact, downstream (cancelled value), supply risk. '
               'Static: schema validity, outcome kind, hard failures, feasibility, objective gap label, exception handling.')


def file_hash(rel):
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def fixtures():
    from supplychainworld.dynamic_demo_v4 import load_fixtures
    by = {f['fixture_id']: f for f in load_fixtures()}
    return [by[i] for i in ev.S01_ORDER]


def build_manifest():
    from supplychainworld.agent_runner_v4 import POLICIES_V4, ObservableRunnerV4
    from supplychainworld.dynamic_demo_v4 import factory
    fx = fixtures()
    defs = ObservableRunnerV4(factory(fx[0])()).tool_definitions()
    cases = ev.load_static_cases()
    selected = ev.select_static_cases(cases)
    m = {
        'schema': 'eval19-manifest-1',
        'issue': 'kishorkukreja/SupplyChainWorld#19',
        'purpose': 'Small diagnostic on free OpenRouter models: find task, grader, harness and model defects. Not a benchmark, not a leaderboard, no claim about general ability, no support for training value.',
        'preregistered_before_any_model_attempt': True,
        'readiness_decision': ('Issue #17 comment 2026-11-22: GO for development-set model evaluation with limits; owner-practitioner, '
                               'not an independent review; every number provisional; covers a small free-model diagnostic only, '
                               'not teacher collection, training, benchmark or capability claims.'),
        'spend': {'approved_ceiling_usd': 0.0, 'free_only': True,
                  'guard': 'llm_adapter.AdapterConfig refuses any model id not ending in :free (or verified zero pricing); cost is 0 only for :free models with usage present, else unknown'},
        'credential': 'OPENROUTER_API_KEY read from the environment only (sandbox proxy injects it); never printed, logged or stored',
        'roster': {
            'core': list(ev.ROSTER_CORE),
            'core_basis': 'actor models that returned a tool call in the issue #18 connectivity check (evidence/issue-18/connectivity.json)',
            'conditional': list(ev.ROSTER_CONDITIONAL),
            'conditional_rule': ('One probe request each, no retries, max_tokens %d, one trivial tool (ping). Included in the roster only if the '
                                 'reply contains a tool call. thinkingmachines/inkling-2-small returned HTTP 403 outside agentic harnesses in #18; '
                                 'it is included only if the probe now returns a tool call. cohere/north-mini-code produced no tool call at '
                                 'max_tokens 64 in #18; the probe uses the larger cap.' % ev.MAX_OUTPUT_TOKENS),
            'scorer_not_used': 'respan/span-01-lite is a scorer (kind scorer): it never acts and is not called here',
            'model_versions': 'OpenRouter model ids exactly as listed; the provider returned-model field is recorded per call; no further version is exposed',
        },
        'development_set': {
            's01_v0.4': {'scenarios': [{'fixture_id': f['fixture_id'], 'horizon_days': f['horizon_days'], 'disruption_class': f['disruption_class']} for f in fx],
                         'fixture_file_sha256': {p: file_hash(p) for p in FIXTURE_FILES},
                         'repeats': ('Design intent: up to 3 repeats per scenario per model. Infeasible under the %d request cap (one repeat of all 5 scenarios '
                                     'is roughly 90 to 150 requests per model). Preregistered instead: ONE attempt per scenario per model, run in the order below '
                                     'until the S01 request allowance is spent. Unrun episodes are reported as not run. No variance or consistency claim is made.' % ev.TOTAL_REQUEST_CAP),
                         'queue_order': 'for scenario in order: for model in roster order (episode skipped if the model is stopped or the remaining S01 allowance is below 2 x horizon requests)',
                         'scripted_baselines': list(POLICIES_V4)},
            'static_v1.2': {'family_size': len(cases), 'selection_rule': ev.select_static_cases.__doc__.strip(),
                            'selected_case_ids': selected, 'n': len(selected),
                            'selected_expected_outcomes': {k: sum(1 for i in selected if cases[i]['expected']['expected_outcome'] == k)
                                                           for k in ('award', 'clarification', 'infeasible')},
                            'fixture_dir_sha256': hashlib.sha256(''.join(file_hash('fixtures/reference_cases_v1_2/%s.json' % i) for i in sorted(cases)).encode()).hexdigest(),
                            'repeats': 'one attempt per case per model (a second request only to nudge a missing or malformed tool call)',
                            'sealed_test_partition': 'none exists for these families; not touched'},
        },
        'tool_profile': {
            's01': {'tools': ev.s01_tools(defs), 'authority': 'read, commit, advance (all granted); one tool call per reply; parallel tool calls off; only the first tool call of a reply is executed',
                    'blinding': 'the world state exposes a scenario_id naming the outcome class (for example warned-delayed); every observation shown to a model replaces it with an opaque alias'},
            'static': {'tools': [ev.SUBMIT_TOOL], 'authority': 'one submit_decision call; no read tools; the model sees only the visible world and the rules text'},
        },
        'prompts': {'s01_system_prompt': ev.S01_SYSTEM_PROMPT, 'static_system_prompt': ev.STATIC_SYSTEM_PROMPT,
                    'static_request': ev.STATIC_REQUEST,
                    'static_user_message': 'static_request + the case world as compact JSON (world object only: no expected, purpose, task, review, calculation or known_wrong fields)',
                    'no_tuning_rule': 'Prompts, tools and limits are frozen at this commit. They are not tuned to individual failures. A genuine harness bug may be fixed and the affected runs rerun, with the fix, the reason and the before/after both disclosed.'},
        'limits': {
            'total_request_cap': ev.TOTAL_REQUEST_CAP,
            'cap_counts': 'every HTTP request including retries and probes',
            'phase_caps': {'probe': ev.PROBE_CAP, 'static': '%d x number of rostered models' % ev.STATIC_CAP_PER_MODEL,
                           's01': 'total cap minus probe cap minus static cap'},
            's01_per_episode': {'max_model_calls': '6 x horizon_days', 'max_total_tokens': 400000, 'max_output_tokens': ev.MAX_OUTPUT_TOKENS,
                                'memory_window_exchanges': 8, 'max_consecutive_non_tool_replies': 2, 'temperature': 0.0, 'timeout_seconds': 90},
            'static_per_case': {'max_logical_calls': 2, 'max_output_tokens': ev.MAX_OUTPUT_TOKENS, 'temperature': 0.0, 'timeout_seconds': 120},
            'throttle': 'at least %.1f seconds between any two requests' % ev.MIN_INTERVAL_SECONDS,
        },
        'retry_rules': {'retry_on': ['HTTP 429', 'HTTP 5xx', 'network error'], 'max_retries_per_logical_call': ev.MAX_RETRIES,
                        'backoff': 'exponential, base %.0f s, cap %.0f s, honors Retry-After up to the cap' % (ev.BACKOFF_BASE, ev.BACKOFF_CAP),
                        'no_retry': '4xx other than 429, refusals, context limit',
                        'breaker': 'a model is stopped for the rest of the run after %d consecutive HTTP 429 responses or %d consecutive HTTP 403 responses with no 200 in between; the stop and its reason are reported; it is never faked or retried later' % (ev.BREAKER_429, ev.BREAKER_403)},
        'grading': {
            's01': 'independent verifier dynamic_verifier_v4.verify_episode on the recorded history, claimed scorecard and action log; replay_v4 on a fresh world; check_observations_for_leaks on every observation shown',
            'static': 'independent checker verification_v12.verify with the case expected outcome, reference cost and task measures (used only by the grader)',
            'actors_vs_scorers': 'only models of kind actor act; the respan scorer is not used',
        },
        'baselines': {
            's01': 'five scripted policies (maintain, expedite_on_alert, alternate_on_alert, combo_on_alert, staged_revisit) on the same scenarios, metrics side by side; they read the same visible view; they are not LLMs',
            'static': 'reference solver (exhaustive search, solve_reference) and greedy heuristic (solve_heuristic) run on the same visible World object, graded by the same checker. Permitted compute differs: the reference solver enumerates exhaustively, the heuristic is greedy, models get one answer with no tools.'},
        'metrics': {'note': METRIC_NOTE,
                    'per_model': ['completion', 'valid vs invalid actions', 'hard violations (verifier codes / checker failures)', 'feasible results',
                                  'cost vs scripted baselines (separate from service and risk)', 'clarification/escalation behavior (static)',
                                  'replay integrity (S01)', 'retries and failures', 'latency', 'tokens', 'provider cost (0 for :free)'],
                    'no_single_score': True, 'no_leaderboard': True},
        'failure_triage': 'Each failure is classified as task, grader, harness or model defect from inspected evidence (the recorded record, the checker output, the prompt text). Triage after the freeze does not change prompts.',
        'recommendation_rule': 'go/repair/stop for teacher collection (#20) is a judgment from the findings; training-use terms for every free model are UNCHECKED and nothing here supports training value.',
        'harness_sha256': {p: file_hash(p) for p in HARNESS_FILES},
        'git_head_at_freeze': os.popen('git -C %s rev-parse HEAD' % ROOT).read().strip(),
        'frozen_at_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }
    m['manifest_sha256'] = ev.sha(m)
    return m


# ------------------------------------------------------------------ live run

PROBE_TOOL = {'type': 'function', 'function': {'name': 'ping', 'description': 'Reply by calling this tool once.',
                                                'parameters': {'type': 'object', 'properties': {'note': {'type': 'string'}},
                                                               'required': [], 'additionalProperties': False}}}


def load_json(p, default=None):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return default


def save_json(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, indent=1, default=str) + '\n')


def make_guard(state):
    ledger = state / 'ledger.jsonl'
    g = ev.Guard(lambda req: la.urllib_transport(req, timeout=120.0), ledger_path=str(ledger))
    # rebuild counters from the ledger so a restart cannot exceed the cap
    if ledger.exists():
        for line in ledger.read_text().splitlines():
            r = json.loads(line)
            g.used_total += 1
            g.used_phase[r['phase']] = g.used_phase.get(r['phase'], 0) + 1
    stopped = load_json(state / 'stopped.json', {})
    g.stopped.update(stopped)
    return g


def probe(g, state):
    path = state / 'probe.json'
    done = load_json(path, {})
    for model in ev.ROSTER_CONDITIONAL:
        if model in done:
            continue
        g.model, g.phase = model, 'probe'
        cfg = la.AdapterConfig(model, max_output_tokens=ev.MAX_OUTPUT_TOKENS, max_retries=0, timeout_seconds=120.0,
                               system_prompt='Call the ping tool once.')
        msgs = [{'role': 'system', 'content': 'Call the ping tool once. Do not reply in prose.'},
                {'role': 'user', 'content': 'Ping now.'}]
        rec = {'model': model}
        t0 = time.monotonic()
        try:
            res = la.chat_request(cfg, msgs, [PROBE_TOOL], transport=g, api_key=os.environ.get(la.CREDENTIAL_ENV, ''), max_retries=0)
            body = res['body']
            ch = (body.get('choices') or [{}])[0]
            tcs = (ch.get('message') or {}).get('tool_calls')
            rec.update(http=200, tool_call=bool(tcs), finish_reason=ch.get('finish_reason'), usage=la.extract_usage(body),
                       latency_ms=round(res['latency_ms'], 1))
        except la.AdapterError as exc:
            rec.update(http='error', tool_call=False, error_class=exc.error_class, message=la.redact_text(str(exc))[:300])
        rec['elapsed_s'] = round(time.monotonic() - t0, 1)
        done[model] = rec
        save_json(path, done)
        print('probe', model, json.dumps(rec), flush=True)
    return done


def run(state):
    state.mkdir(parents=True, exist_ok=True)
    g = make_guard(state)
    probes = probe(g, state)
    roster = list(ev.ROSTER_CORE) + [m for m in ev.ROSTER_CONDITIONAL if probes.get(m, {}).get('tool_call')]
    static_cap = ev.STATIC_CAP_PER_MODEL * len(roster)
    g.phase_caps = {'probe': ev.PROBE_CAP, 'static': static_cap, 's01': ev.TOTAL_REQUEST_CAP - ev.PROBE_CAP - static_cap}
    save_json(state / 'roster.json', {'roster': roster, 'phase_caps': g.phase_caps})
    fx = fixtures()
    g.private_strings = [f['fixture_id'] for f in fx]
    key = os.environ.get(la.CREDENTIAL_ENV, '')
    # ---- S01
    for f in fx:
        for model in roster:
            out = state / 's01' / ('%s__%s.json' % (f['fixture_id'], model.replace('/', '_')))
            if out.exists():
                continue
            g.model, g.phase = model, 's01'
            need = 2 * f['horizon_days']
            if model in g.stopped:
                save_json(out, {'fixture_id': f['fixture_id'], 'model': model, 'not_run': 'model stopped: ' + g.stopped[model]})
                continue
            if g.remaining('s01') < need:
                save_json(out, {'fixture_id': f['fixture_id'], 'model': model, 'not_run': 'S01 request allowance exhausted (%d left, %d needed)' % (g.remaining('s01'), need)})
                continue
            before = g.used_phase.get('s01', 0)
            raw = ev.run_s01_episode(f, model, g, api_key=key)
            grade = ev.grade_s01(f, raw)
            rec = {'fixture_id': f['fixture_id'], 'model': model, 'requests_used': g.used_phase.get('s01', 0) - before,
                   'manifest_sha256': raw['manifest']['manifest_sha256'], 'telemetry': raw['telemetry'], 'grade': grade,
                   'transcript': raw['transcript'], 'refused': g.refused, 'leak_flags': g.leak_flags}
            g.refused = None
            save_json(out, rec)
            save_json(state / 'stopped.json', g.stopped)
            print('s01', f['fixture_id'], model, grade['status'], 'feasible', grade['verifier_feasible'], 'req', rec['requests_used'],
                  'used', g.used_total, flush=True)
    # ---- static
    cases = ev.load_static_cases()
    selected = ev.select_static_cases(cases)
    for model in roster:
        for cid in selected:
            out = state / 'static' / ('%s__%s.json' % (cid, model.replace('/', '_')))
            if out.exists():
                continue
            g.model, g.phase = model, 'static'
            if model in g.stopped:
                save_json(out, {'case_id': cid, 'model': model, 'not_run': 'model stopped: ' + g.stopped[model]})
                continue
            if g.remaining('static') < 2:
                save_json(out, {'case_id': cid, 'model': model, 'not_run': 'static request allowance exhausted'})
                continue
            g.private_strings = [f['fixture_id'] for f in fx] + ev.static_private_strings(cases[cid])
            raw = ev.run_static_case(cases[cid], model, g, api_key=key)
            grade = ev.grade_static(cases[cid], raw['submission'])
            raw.update(grade=grade, refused=g.refused, leak_flags=g.leak_flags)
            g.refused = None
            save_json(out, raw)
            save_json(state / 'stopped.json', g.stopped)
            print('static', cid, model, raw['status'], 'accepted', grade.get('accepted'), 'used', g.used_total, flush=True)
    save_json(state / 'done.json', {'used_total': g.used_total, 'used_phase': g.used_phase, 'stopped': g.stopped})
    print('done', g.used_total, g.used_phase, g.stopped, flush=True)


# ------------------------------------------------------------------ report

def fnum(x):
    return x if isinstance(x, (int, float)) else None


def report(state, out):
    from supplychainworld.dynamic_demo_v4 import METRICS
    probes = load_json(state / 'probe.json', {})
    roster = load_json(state / 'roster.json', {}).get('roster', [])
    stopped = load_json(state / 'stopped.json', {})
    fx = {f['fixture_id']: f for f in fixtures()}
    cases = ev.load_static_cases()
    selected = ev.select_static_cases(cases)
    (out / 'runs').mkdir(parents=True, exist_ok=True)
    base_s01 = ev.s01_baselines(list(fx.values()))
    ledger = [json.loads(x) for x in (state / 'ledger.jsonl').read_text().splitlines()] if (state / 'ledger.jsonl').exists() else []
    per_model = {m: {'model': m, 's01': {'episodes_run': 0, 'completed': 0, 'verifier_feasible': 0, 'replay_reproduced': 0, 'valid_actions': 0,
                                         'invalid_actions': 0, 'agent_errors': 0, 'hard_violation_codes': {}, 'not_run': []},
                     'static': {'cases_run': 0, 'submitted': 0, 'schema_valid': 0, 'accepted': 0, 'feasible': 0, 'outcome_matches': 0,
                                'hard_failure_codes': {}, 'award_objective': {}, 'exception_cases': 0, 'exception_accepted': 0,
                                'false_exception_on_award': 0, 'wrong_award_on_exception': 0, 'not_run': 0},
                     'requests': 0, 'retries': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'latency_ms': 0.0, 'cost_usd': 0.0,
                     'cost_unknown_calls': 0, 'http_status_counts': {}, 'stopped_by_breaker': stopped.get(m)} for m in roster}
    for r in ledger:
        pm = per_model.get(r['model'])
        if pm is not None:
            pm['requests'] += 1
            k = str(r['http_status'])
            pm['http_status_counts'][k] = pm['http_status_counts'].get(k, 0) + 1
    s01_rows = []
    for p in sorted((state / 's01').glob('*.json')):
        rec = load_json(p)
        pm = per_model[rec['model']]
        if 'not_run' in rec:
            pm['s01']['not_run'].append({'fixture_id': rec['fixture_id'], 'reason': rec['not_run']})
            s01_rows.append({'fixture_id': rec['fixture_id'], 'model': rec['model'], 'not_run': rec['not_run']})
            continue
        g, t = rec['grade'], rec['telemetry']
        s = pm['s01']
        s['episodes_run'] += 1
        s['completed'] += g['completed']
        s['verifier_feasible'] += bool(g['verifier_feasible'])
        s['replay_reproduced'] += bool(g['replay_reproduced'])
        s['valid_actions'] += g['valid_actions']
        s['invalid_actions'] += g['invalid_actions']
        s['agent_errors'] += g['agent_errors']
        for c in g['hard_violation_codes']:
            s['hard_violation_codes'][c] = s['hard_violation_codes'].get(c, 0) + 1
        pm['retries'] += t['retries']
        pm['prompt_tokens'] += t['prompt_tokens']
        pm['completion_tokens'] += t['completion_tokens']
        pm['latency_ms'] += t['latency_ms_total']
        if isinstance(t['cost_usd'], (int, float)):
            pm['cost_usd'] += t['cost_usd']
        else:
            pm['cost_unknown_calls'] += 1
        calls = [{'finish_reason': c.get('finish_reason'), 'status': c.get('status'), 'tool': c.get('tool'), 'latency_ms': c.get('latency_ms'),
                  'retries': len(c.get('retries', [])), 'tokens': (c.get('usage') or {}).get('total_tokens'), 'error_class': c.get('error_class'),
                  'returned_model': c.get('returned_model')} for c in t['calls']]
        clean = {'fixture_id': rec['fixture_id'], 'model': rec['model'], 'requests_used': rec['requests_used'],
                 'manifest_sha256': rec['manifest_sha256'], 'status': g['status'], 'completed': g['completed'], 'attempts': g['attempts'],
                 'valid_actions': g['valid_actions'], 'invalid_actions': g['invalid_actions'], 'agent_errors': g['agent_errors'],
                 'invalid_by_category': g['invalid_by_category'], 'tool_use': g['tool_use'], 'recovery_commitments': g['recovery_commitments'],
                 'verifier_feasible': g['verifier_feasible'], 'hard_violation_codes': g['hard_violation_codes'],
                 'replay_reproduced': g['replay_reproduced'], 'observation_leaks': g['observation_leaks'], 'metrics': g['metrics'],
                 'telemetry': {k: t[k] for k in ('model_calls', 'http_requests', 'retries', 'usage_complete', 'prompt_tokens', 'completion_tokens',
                                                 'total_tokens', 'latency_ms_total', 'cost_usd', 'stop_reason', 'failure')},
                 'calls': calls, 'leak_flags': rec['leak_flags']}
        save_json(out / 'runs' / ('s01__%s__%s.json' % (rec['fixture_id'], rec['model'].replace('/', '_'))), clean)
        s01_rows.append({k: clean[k] for k in ('fixture_id', 'model', 'status', 'completed', 'valid_actions', 'invalid_actions', 'verifier_feasible',
                                              'hard_violation_codes', 'replay_reproduced', 'metrics')} |
                        {'requests_used': clean['requests_used'], 'commitments': [(c['day'], c['choice'], c['quantity'], c['accepted']) for c in clean['recovery_commitments']]})
    static_rows = []
    for p in sorted((state / 'static').glob('*.json')):
        rec = load_json(p)
        pm = per_model[rec['model']]
        if 'not_run' in rec:
            pm['static']['not_run'] += 1
            continue
        case = cases[rec['case_id']]
        clean = ev.sanitize_static(rec, rec['grade'])
        save_json(out / 'runs' / ('static__%s__%s.json' % (rec['case_id'], rec['model'].replace('/', '_'))), clean)
        s, gr = pm['static'], rec['grade']
        s['cases_run'] += 1
        pm['retries'] += clean['retries']
        pm['prompt_tokens'] += clean['prompt_tokens']
        pm['completion_tokens'] += clean['completion_tokens']
        pm['latency_ms'] += clean['latency_ms_total']
        if isinstance(clean['cost_usd'], (int, float)):
            pm['cost_usd'] += clean['cost_usd']
        else:
            pm['cost_unknown_calls'] += 1
        expected = case['expected']['expected_outcome']
        if gr.get('graded'):
            s['submitted'] += 1
            s['schema_valid'] += gr['schema_valid']
            s['accepted'] += gr['accepted']
            s['feasible'] += gr['feasible']
            s['outcome_matches'] += gr['outcome_matches']
            for c in gr['hard_failures']:
                s['hard_failure_codes'][c] = s['hard_failure_codes'].get(c, 0) + 1
            if expected == 'award' and gr['kind'] == 'award' and gr['optimality']:
                s['award_objective'][gr['optimality']] = s['award_objective'].get(gr['optimality'], 0) + 1
            if expected != 'award':
                s['exception_cases'] += 1
                s['exception_accepted'] += gr['accepted']
                if gr['kind'] == 'award':
                    s['wrong_award_on_exception'] += 1
            elif gr['kind'] in ('clarification', 'infeasible'):
                s['false_exception_on_award'] += 1
        elif expected != 'award':
            s['exception_cases'] += 1
        static_rows.append({'case_id': rec['case_id'], 'model': rec['model'], 'expected': expected, 'status': rec['status'],
                            'kind': gr.get('kind'), 'schema_valid': gr.get('schema_valid'), 'accepted': gr.get('accepted'),
                            'hard_failures': gr.get('hard_failures'), 'optimality': gr.get('optimality'), 'objective_gap': gr.get('objective_gap')})
    base_static = {}
    for cid in selected:
        base_static[cid] = {'expected': cases[cid]['expected']['expected_outcome'],
                            'reference': static_baseline_row(cases[cid], 'reference'), 'heuristic': static_baseline_row(cases[cid], 'heuristic')}
    comparison = {}
    for fid, rows in base_s01.items():
        comparison[fid] = {'scripted_policies': rows,
                           'models': {r['model']: (r['metrics'] if r.get('metrics') else None) for r in s01_rows if r['fixture_id'] == fid and 'not_run' not in r}}
    card = {'schema': 'eval19-scorecard-1', 'label': 'diagnostic on free models, development set only; not a benchmark; no leaderboard; no single score',
            'metric_note': METRIC_NOTE, 'probes': probes, 'roster': roster, 'per_model': per_model, 's01_runs': s01_rows,
            's01_comparison_to_scripted': comparison, 'static_runs': static_rows, 'static_baselines': base_static,
            'request_totals': {'ledger_requests': len(ledger), 'cap': ev.TOTAL_REQUEST_CAP,
                               'by_phase': {ph: sum(1 for r in ledger if r['phase'] == ph) for ph in ('probe', 's01', 'static')}}}
    save_json(out / 'scorecard.json', card)
    # copy the request ledger (no bodies, no keys)
    (out / 'request-ledger.jsonl').write_text('\n'.join(json.dumps(r) for r in ledger) + '\n')
    print(json.dumps({m: {'s01': v['s01'], 'static': v['static']} for m, v in per_model.items()}, indent=1)[:6000])


def static_baseline_row(case, which):
    r = ev.static_baseline(case, which)
    return {k: r.get(k) for k in ('solver_status', 'graded', 'accepted', 'kind', 'optimality', 'objective_gap', 'hard_failures', 'independent_cost')}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['manifest', 'run', 'report'])
    ap.add_argument('--out')
    ap.add_argument('--state')
    a = ap.parse_args()
    if a.cmd == 'manifest':
        out = Path(a.out) if a.out else ROOT / 'evidence/issue-19/manifest.json'
        save_json(out, build_manifest())
        print('wrote', out)
    elif a.cmd == 'run':
        run(Path(a.state))
    else:
        report(Path(a.state), Path(a.out) if a.out else ROOT / 'evidence/issue-19')


if __name__ == '__main__':
    main()
