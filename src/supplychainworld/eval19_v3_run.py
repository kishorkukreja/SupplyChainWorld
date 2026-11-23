"""eval19-3 run orchestration: six models, five S01 v0.6 scenarios, repeats. Version `eval19-3-run-1`.

This module only ORCHESTRATES. It adds no new rule for the world, the prompt, the checker or the adapters: the S01 v0.6 episode
and its grading come from `eval19_v3`, the OpenRouter route is `llm_adapter` behind `eval19.Guard` (free-only, USD 0), and the
Sarvam route is `sarvam_adapter` (paid, one INR cap for the whole run) behind its own `Guard`. Nothing here makes a network call
unless the caller passes live base transports, and the script that does so refuses to run before the plan is committed.

What it adds:
* a roster file reader that refuses anything outside the two allowed routes;
* a PLAN (the pre-registration) with the models, scenarios, repeats, caps, rules and file hashes, hashed as a whole;
* a fixed queue order (repeat, then scenario, then model) so a stopped run is balanced across models;
* a resumable run: one private record per episode, ledgers rebuilt from disk so a restart cannot exceed any cap;
* optional Langfuse export of each finished episode through `tracing.trace_episode` (never raises, off by default).

All business numbers are PROVISIONAL, needs practitioner value. Software tests only: nothing here claims model ability.
"""
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from . import eval19 as ev
from . import eval19_v2 as ev2
from . import eval19_v3 as ev3
from . import llm_adapter as la
from . import sarvam_adapter as sa
from . import tracing

ROOT = Path(__file__).resolve().parents[2]
RUN_SCHEMA = 'eval19-3-run-1'
PLAN_SCHEMA = 'eval19-3-plan-1'
ROSTER_PATH = ROOT / 'config' / 'eval19_v3_roster.json'
PLAN_PATH = ROOT / 'evidence' / 'eval19-3' / 'plan.json'
PROVIDERS = ('openrouter', 'sarvam')
DEFAULT_REPEATS = 2
MAX_REPEATS = 5
OPENROUTER_REQUEST_CAP = 2000    # guard cap on HTTP requests, retries included; the plan states the worst case
SARVAM_REQUEST_CAP = 2000
HARNESS_FILES = (
    'src/supplychainworld/eval19_v3_run.py', 'src/supplychainworld/eval19_v3.py', 'src/supplychainworld/eval19_v2.py',
    'src/supplychainworld/eval19.py', 'src/supplychainworld/llm_adapter.py', 'src/supplychainworld/sarvam_adapter.py',
    'src/supplychainworld/tracing.py', 'src/supplychainworld/agent_runner_v6.py', 'src/supplychainworld/dynamic_v6.py',
    'src/supplychainworld/dynamic_verifier_v6.py', 'src/supplychainworld/dynamic_demo_v6.py',
    'scripts/run_eval19_v3.py', 'config/eval19_v3_roster.json')
FIXTURE_FILES = ('fixtures/dynamic/v0.6/scenarios.json', 'fixtures/dynamic/v0.6/hand-ledgers.json')


class RosterError(ValueError):
    """The roster file is outside the allowed routes or malformed."""


class PreflightError(RuntimeError):
    """A run was refused before any model call."""


def _sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def file_hash(rel, root=ROOT):
    return _sha_bytes((Path(root) / rel).read_bytes())


# --------------------------------------------------------------------------- roster

def validate_roster(roster):
    """Return the model list or raise RosterError. OpenRouter ids must be ':free'; Sarvam ids must be in the price table."""
    if not isinstance(roster, dict) or not isinstance(roster.get('models'), list) or not roster['models']:
        raise RosterError('roster has no models')
    seen, out = set(), []
    for m in roster['models']:
        if not isinstance(m, dict) or not isinstance(m.get('id'), str) or m.get('provider') not in PROVIDERS:
            raise RosterError('each model needs a string id and a provider in %s' % (PROVIDERS,))
        if m.get('role') != 'actor':
            raise RosterError('only actors act; %r has role %r' % (m['id'], m.get('role')))
        if m['id'] in seen:
            raise RosterError('duplicate model id %r' % m['id'])
        seen.add(m['id'])
        if m['provider'] == 'openrouter' and not m['id'].endswith(':free'):
            raise RosterError('OpenRouter ids must end in :free (USD 0 rule): %r' % m['id'])
        if m['provider'] == 'sarvam' and m['id'] not in sa.PRICES_INR_PER_M:
            raise RosterError('Sarvam id %r is not in the pinned price table' % m['id'])
        out.append(dict(m))
    return out


def load_roster(path=ROSTER_PATH):
    roster = json.loads(Path(path).read_text())
    return validate_roster(roster)


# --------------------------------------------------------------------------- plan

def fixtures():
    from .dynamic_demo_v6 import load_fixtures
    by = {f['fixture_id']: f for f in load_fixtures()}
    return [by[i] for i in ev3.S01_ORDER_V6]


def build_queue(models, scenario_ids, repeats):
    """Fixed order: for each repeat, for each scenario, for each model. A partial run stays balanced across models."""
    if not isinstance(repeats, int) or isinstance(repeats, bool) or not 1 <= repeats <= MAX_REPEATS:
        raise ValueError('repeats must be an integer from 1 to %d' % MAX_REPEATS)
    return [{'repeat': r, 'fixture_id': s, 'model': m['id'], 'provider': m['provider']}
            for r in range(1, repeats + 1) for s in scenario_ids for m in models]


def worst_case_requests(models, fx, repeats):
    """Upper bound on model calls: each episode may use at most 6 x horizon_days calls (the per-episode limit), per provider."""
    out = {p: 0 for p in PROVIDERS}
    for m in models:
        out[m['provider']] += repeats * sum(6 * f['horizon_days'] for f in fx)
    return out


def sha_plan(plan):
    body = {k: v for k, v in plan.items() if k != 'plan_sha256'}
    return _sha_bytes(json.dumps(body, sort_keys=True, default=str).encode())


def build_plan(*, repeats=DEFAULT_REPEATS, roster_path=ROSTER_PATH, cap_inr=sa.CAP_INR, git_head=None, now=None, root=ROOT):
    models = load_roster(roster_path)
    fx = fixtures()
    queue = build_queue(models, [f['fixture_id'] for f in fx], repeats)
    worst = worst_case_requests(models, fx, repeats)
    if not isinstance(cap_inr, (int, float)) or isinstance(cap_inr, bool) or not 0 < cap_inr <= sa.CAP_INR:
        raise ValueError('cap_inr must be above 0 and at most %s' % sa.CAP_INR)
    plan = {
        'schema': PLAN_SCHEMA, 'harness_version': 'eval19-3', 'run_schema': RUN_SCHEMA,
        'status': ('PLAN. Commit this file on its own, with nothing else in the commit, BEFORE any model call. A plan committed '
                   'after a call is not a pre-registration. The run script refuses to start unless this file is committed and unchanged.'),
        'purpose': ('Diagnostic on the S01 v0.6 world with six models: find task, grader, harness and model defects, and see how the '
                    'independent checker marks real runs. Not a benchmark, not a leaderboard, no claim about general model ability, '
                    'no support for training value.'),
        'owner_decisions': ['2026-11-23: eval19-3 S01 run goes before the Harbor setup',
                            '2026-11-23: Sarvam has its own adapter; the $0 rule applies to OpenRouter only',
                            '2026-11-23: Sarvam hard cap INR 10000 for the whole run',
                            '2026-11-23: GLM is glm5.3-flash unless the owner asks for the full glm5.3',
                            '2026-11-23: 2 repeats per scenario per model'],
        'models': [{k: m[k] for k in ('id', 'provider', 'label') if k in m} for m in models],
        'scenarios': [{'fixture_id': f['fixture_id'], 'horizon_days': f['horizon_days'],
                       'disruption_class': f['disruption_class']} for f in fx],
        'repeats': repeats,
        'episodes_total': len(queue),
        'episodes_by_provider': {p: sum(1 for q in queue if q['provider'] == p) for p in PROVIDERS},
        'queue_order': 'for repeat in 1..R: for scenario in the order above: for model in the roster order',
        'queue': queue,
        'world_and_grading': {
            'world': 'S01 v0.6 (opaque scenario label, conventions block in the rules, exact-once purchases)',
            'prompt': 'eval19_v3.S01_SYSTEM_PROMPT_V3 and tool descriptions built from agent_runner_v6.RULES_V6, unchanged and frozen',
            'grading': ('independent checker dynamic_verifier_v6.verify_episode on the recorded history, claimed scorecard and action '
                        'log; replay_v6 on a fresh world; check_observations_for_leaks on every observation shown'),
            'metrics': 'reported separately and never combined into one score: completion, valid and invalid actions, hard '
                       'violations, feasibility, replay, cost, service, tier impact, tokens, latency, retries, provider cost',
            'no_single_score': True, 'no_leaderboard': True},
        'limits': {
            's01_per_episode': {'max_model_calls': '6 x horizon_days', 'max_total_tokens': 400000, 'max_output_tokens': ev2.MAX_OUTPUT_TOKENS,
                                'memory_window_exchanges': 8, 'max_consecutive_non_tool_replies': 2, 'temperature': 0.0,
                                'timeout_seconds': 90},
            'worst_case_model_calls': worst,
            'request_caps': {'openrouter': OPENROUTER_REQUEST_CAP, 'sarvam': SARVAM_REQUEST_CAP,
                             'counts': 'every HTTP request including retries'},
            'throttle': 'at least %.1f seconds between any two requests on a route' % ev.MIN_INTERVAL_SECONDS,
            'retry': {'max_retries_per_logical_call': ev.MAX_RETRIES, 'on': ['HTTP 429', 'HTTP 5xx', 'network error']},
            'breaker': ('a model is stopped for the rest of the run after %d consecutive HTTP 429 or %d consecutive HTTP 403 '
                        'responses; stops are reported, never hidden or retried later' % (ev.BREAKER_429, ev.BREAKER_403)),
            'daily_limits': ('OpenRouter free models have daily request limits that are NOT checked here. A model that hits them is '
                             'stopped by the breaker and its remaining episodes are reported as not run. The run is resumable, so '
                             'the owner may continue it on another day; the order and caps do not change.')},
        'spend': {
            'openrouter': {'ceiling_usd': 0.0, 'rule': 'free-tier only: llm_adapter refuses any id that does not end in :free'},
            'sarvam': {'hard_cap_inr': float(cap_inr), 'currency': 'INR', 'shared_by': 'all Sarvam models in the run',
                       'price_table_inr_per_million_input_output': {k: list(v) for k, v in sa.PRICES_INR_PER_M.items()},
                       'gst_factor': sa.GST_FACTOR,
                       'status': 'PROVISIONAL, prices read 2026-11-23, re-read the pricing page before the run',
                       'rule': 'every call reserves its worst case before it is sent; unknown billing is counted at the worst case; '
                               'the run stops when a call could pass the cap'}},
        'credentials': {'openrouter': 'OPENROUTER_API_KEY, injected by the sandbox proxy; the script reads it only from the environment',
                        'sarvam': 'SARVAM_API_KEY from the environment; never printed, logged, stored or committed'},
        'tracing': {'tool': 'Langfuse, post-hoc export of each finished episode through tracing.trace_episode',
                    'on_only_if': 'SCW_LANGFUSE=1 and the Langfuse keys and host are set; a tracing failure never costs a finished run',
                    'source_of_truth': 'the private run files, not Langfuse'},
        'no_tuning_rule': ('Prompts, tools and limits are frozen at this commit. They are not tuned to individual failures. A '
                           'genuine harness bug may be fixed and the affected runs rerun, with the fix, the reason and before and '
                           'after both disclosed.'),
        'not_checked_before_the_run': [
            'whether Sarvam accepts the tool-call request shape and returns token usage (the check subcommand does this, in a session that has the key)',
            'whether reasoning tokens are included in completion_tokens on the Sarvam models',
            'OpenRouter free-model daily limits',
            'training-use terms of every provider (Sarvam, Nemotron, Ernie, Gemma): nothing here supports training use'],
        'review_status': 'owner review only, not independent practitioner review; every business number is PROVISIONAL, needs practitioner value',
        'harness_sha256': {p: file_hash(p, root) for p in HARNESS_FILES},
        'fixture_sha256': {p: file_hash(p, root) for p in FIXTURE_FILES},
        'git_head_at_generation': git_head or '',
        'generated_at_utc': (now or datetime.now(timezone.utc)).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }
    plan['plan_sha256'] = sha_plan(plan)
    return plan


def check_plan(plan, root=ROOT):
    """Raise PreflightError unless the plan is internally consistent and the frozen files still match its hashes."""
    if not isinstance(plan, dict) or plan.get('schema') != PLAN_SCHEMA:
        raise PreflightError('not an eval19-3 plan')
    if plan.get('plan_sha256') != sha_plan(plan):
        raise PreflightError('plan hash does not match its content')
    for kind in ('harness_sha256', 'fixture_sha256'):
        for rel, want in plan[kind].items():
            try:
                got = file_hash(rel, root)
            except OSError:
                raise PreflightError('missing file named in the plan: %s' % rel) from None
            if got != want:
                raise PreflightError('file changed after the plan was written: %s' % rel)
    for m in plan['models']:
        validate_roster({'models': [dict(m, role='actor')]})
    return plan


def git_committed_clean(path, root=ROOT):
    """True if `path` is tracked and has no uncommitted change. Uses git only; no network."""
    import subprocess
    rel = os.path.relpath(str(path), str(root))
    try:
        tracked = subprocess.run(['git', '-C', str(root), 'ls-files', '--error-unmatch', rel], capture_output=True)
        dirty = subprocess.run(['git', '-C', str(root), 'status', '--porcelain', '--', rel], capture_output=True, text=True)
    except OSError:
        return False
    return tracked.returncode == 0 and dirty.returncode == 0 and not dirty.stdout.strip()


# --------------------------------------------------------------------------- run

def _load_json(p, default=None):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return default


def _save_json(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(p) + '.tmp')
    tmp.write_text(json.dumps(obj, indent=1, default=str) + '\n')
    os.replace(tmp, p)


def episode_file(state, rep, fixture_id, model):
    return Path(state) / 's01' / ('r%d__%s__%s.json' % (rep, fixture_id, model.replace('/', '_')))


class Rig:
    """The two routes of one run: a Guard per provider (request caps, breaker, throttle, ledger, leak scan) and the Sarvam spend ledger."""

    def __init__(self, state, base_transports, *, cap_inr=sa.CAP_INR, sleep=time.sleep, clock=time.monotonic,
                 min_interval=ev.MIN_INTERVAL_SECONDS, private_strings=()):
        state = Path(state)
        state.mkdir(parents=True, exist_ok=True)
        self.state = state
        self.spend = sa.SarvamSpend(cap_inr, ledger_path=str(state / 'sarvam_spend.jsonl'))
        caps = {'openrouter': OPENROUTER_REQUEST_CAP, 'sarvam': SARVAM_REQUEST_CAP}
        self.guards = {}
        for p in PROVIDERS:
            base = base_transports[p]
            if p == 'sarvam':
                base = sa.SarvamTransport(base, self.spend)
            g = ev.Guard(base, total_cap=caps[p], phase_caps={'s01': caps[p], 'probe': caps[p]}, sleep=sleep, clock=clock,
                         min_interval=min_interval, ledger_path=str(state / ('ledger_%s.jsonl' % p)), private_strings=private_strings)
            self._rebuild(g, state / ('ledger_%s.jsonl' % p))
            self.guards[p] = g
        stopped = _load_json(state / 'stopped.json', {})
        for p in PROVIDERS:
            self.guards[p].stopped.update(stopped)  # a stop names one model, so it only matters to that model's route

    @staticmethod
    def _rebuild(g, ledger):
        """Rebuild request counters from the ledger so a restart cannot exceed a cap."""
        if ledger.exists():
            for line in ledger.read_text().splitlines():
                if line.strip():
                    r = json.loads(line)
                    g.used_total += 1
                    g.used_phase[r['phase']] = g.used_phase.get(r['phase'], 0) + 1

    def save_stops(self):
        stops = {}
        for g in self.guards.values():
            stops.update(g.stopped)
        _save_json(self.state / 'stopped.json', stops)


def run(plan, state, base_transports, *, keys=None, trace_client=None, cap_inr=None, sleep=time.sleep, clock=time.monotonic,
        min_interval=ev.MIN_INTERVAL_SECONDS, out=print, root=ROOT, limit=None):
    """Run the queue of `plan` into `state`. Resumable. `base_transports` maps provider -> transport callable.

    `limit` stops after that many episodes (a smoke run); the order does not change. Returns a summary dict."""
    check_plan(plan, root)
    keys = keys or {}
    fx = {f['fixture_id']: f for f in fixtures()}
    cap = float(cap_inr if cap_inr is not None else plan['spend']['sarvam']['hard_cap_inr'])
    if cap > plan['spend']['sarvam']['hard_cap_inr']:
        raise PreflightError('cap above the plan')
    rig = Rig(state, base_transports, cap_inr=cap, sleep=sleep, clock=clock, min_interval=min_interval,
              private_strings=list(fx))
    _save_json(Path(state) / 'plan_used.json', {'plan_sha256': plan['plan_sha256'], 'run_schema': RUN_SCHEMA})
    done = ran = 0
    for q in plan['queue']:
        f, model, provider = fx[q['fixture_id']], q['model'], q['provider']
        path = episode_file(state, q['repeat'], q['fixture_id'], model)
        if path.exists():
            continue
        if limit is not None and ran >= limit:
            break
        g = rig.guards[provider]
        g.model, g.phase = model, 's01'
        base = {'repeat': q['repeat'], 'fixture_id': q['fixture_id'], 'model': model, 'provider': provider}
        need = 2 * f['horizon_days']
        if model in g.stopped:
            _save_json(path, dict(base, not_run='model stopped: ' + g.stopped[model]))
            continue
        if g.remaining('s01') < need:
            _save_json(path, dict(base, not_run='request allowance exhausted (%d left, %d needed)' % (g.remaining('s01'), need)))
            continue
        if provider == 'sarvam' and (rig.spend.exhausted or rig.spend.spent_inr >= rig.spend.cap_inr):
            _save_json(path, dict(base, not_run='Sarvam stop: %s' % (rig.spend.exhausted or 'cap reached')))
            continue
        before_req, before_inr = g.used_phase.get('s01', 0), rig.spend.spent_inr
        key = keys.get(provider, 'proxy-injected')
        try:
            if provider == 'sarvam':
                raw = sa.run_s01_episode(f, model, g, cap_inr=cap, api_key=key, sleep=sleep, clock=clock)
            else:
                raw = ev3.run_s01_episode(f, model, g, api_key=key, sleep=sleep, clock=clock)
            grade = ev3.grade_s01(f, raw)
        except Exception as exc:  # noqa: BLE001 - only the class name is kept; a message could carry request data
            _save_json(path, dict(base, not_run='harness error: ' + type(exc).__name__))
            ran += 1
            continue
        label = 'eval19-3/r%d' % q['repeat']
        trace = tracing.trace_episode(raw, grade, trace_client, run_label=label)
        rec = dict(base, requests_used=g.used_phase.get('s01', 0) - before_req,
                   sarvam_inr_this_episode=round(rig.spend.spent_inr - before_inr, 6) if provider == 'sarvam' else None,
                   manifest_sha256=raw['manifest']['manifest_sha256'], telemetry=raw['telemetry'], grade=grade,
                   transcript=raw['transcript'], observed_count=len(raw['observed']), refused=g.refused,
                   leak_flags=list(g.leak_flags), trace=trace)
        g.refused = None
        _save_json(path, rec)
        rig.save_stops()
        ran += 1
        done += 1
        out('r%d %s %s %s feasible=%s req=%d' % (q['repeat'], q['fixture_id'], model, grade['status'],
                                               grade['verifier_feasible'], rec['requests_used']))
    summary = {'episodes_run_now': ran, 'sarvam_inr_spent_total': round(rig.spend.spent_inr, 6),
               'requests': {p: g.used_total for p, g in rig.guards.items()}, 'stopped': {m: r for g in rig.guards.values() for m, r in g.stopped.items()}}
    _save_json(Path(state) / 'progress.json', summary)
    return summary


def summarize(state):
    """Plain table of what the state directory holds: per model, episodes finished, completed, feasible, replayed, not run."""
    rows = {}
    for p in sorted((Path(state) / 's01').glob('*.json')):
        r = _load_json(p, {})
        m = rows.setdefault(r.get('model', '?'), {'episodes': 0, 'completed': 0, 'feasible': 0, 'replayed': 0, 'leaks': 0, 'not_run': 0})
        if 'not_run' in r:
            m['not_run'] += 1
            continue
        g = r['grade']
        m['episodes'] += 1
        m['completed'] += bool(g['completed'])
        m['feasible'] += bool(g['verifier_feasible'])
        m['replayed'] += bool(g['replay_reproduced'])
        m['leaks'] += bool(g['observation_leaks'])
    return rows


# --------------------------------------------------------------------------- live check (needs the key; run in a session that has it)

PING_TOOL = {'type': 'function', 'function': {'name': 'ping', 'description': 'Reply by calling this tool once.',
                                               'parameters': {'type': 'object', 'properties': {'note': {'type': 'string'}},
                                                              'required': [], 'additionalProperties': False}}}


def check_sarvam(state, base_transport, models=None, *, key, cap_inr=sa.CAP_INR, sleep=time.sleep, clock=time.monotonic):
    """One small call per Sarvam model through the real adapter, Guard and spend ledger. Returns a record per model."""
    spend = sa.SarvamSpend(cap_inr, ledger_path=str(Path(state) / 'sarvam_spend.jsonl'))
    g = ev.Guard(sa.SarvamTransport(base_transport, spend), total_cap=len(sa.PRICES_INR_PER_M) * 2, sleep=sleep, clock=clock,
                 min_interval=ev.MIN_INTERVAL_SECONDS, ledger_path=str(Path(state) / 'ledger_check.jsonl'))
    out = {}
    for model in models or sorted(sa.PRICES_INR_PER_M):
        g.model, g.phase = model, 'probe'
        cfg = sa.SarvamConfig(model, cap_inr=cap_inr, max_output_tokens=256, max_retries=0, timeout_seconds=60.0,
                              system_prompt='Call the ping tool once.')
        msgs = [{'role': 'system', 'content': 'Call the ping tool once. Do not reply in prose.'},
                {'role': 'user', 'content': 'Ping now.'}]
        rec = {'model': model}
        try:
            res = la.chat_request(cfg, msgs, [PING_TOOL], transport=g, api_key=key, max_retries=0)
            ch = (res['body'].get('choices') or [{}])[0]
            rec.update(http=200, tool_call=bool((ch.get('message') or {}).get('tool_calls')), finish_reason=ch.get('finish_reason'),
                       usage=la.extract_usage(res['body']))
        except la.AdapterError as exc:
            rec.update(http='error', tool_call=False, error_class=exc.error_class, message=la.redact_text(str(exc), (key,))[:300])
        out[model] = rec
    _save_json(Path(state) / 'check_sarvam.json', {'results': out, 'inr_spent': round(spend.spent_inr, 6)})
    return out
