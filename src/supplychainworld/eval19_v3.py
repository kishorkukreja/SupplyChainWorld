"""DRAFT harness materials for the diagnostic AFTER `eval19-2`, on the S01 v0.6 world. Version `eval19-3-draft`.

NOTHING HERE HAS BEEN RUN WITH A MODEL, and this module makes no network call by itself. It is a new file beside
`eval19.py` (frozen: its hashes are in `evidence/issue-19/manifest.json`) and `eval19_v2.py` (the next run's harness),
neither of which is edited. It reuses their guard, budget, throttle, request scan and static helpers by import and
changes only the S01 side:

1. WORLD. S01 runs on the v0.6 family (`dynamic_v6`, `agent_runner_v6`, `dynamic_verifier_v6`): the opaque scenario id of
   v0.5, plus the conventions block in the visible rules, plus exact-once purchases without an action id, plus the rebuilt
   independent checker (audit defects D2 to D6 closed).
2. PROMPT. The system prompt and every tool description are BUILT from `agent_runner_v6.RULES_V6`, which now also states the
   conventions the audit found missing (same-day use of receipts, when shipping starts, serving order, the unit of the
   penalty rate, cancellation). A test ties every v0.6 refusal reason to a stated sentence.
3. STATIC TASK. Unchanged from `eval19-2` (use `eval19_v2` for it).

Free models only, USD 0 ceiling, enforced by the same adapter and guard. Nothing here measures general model ability.
The owner runs the diagnostic later; this draft only fixes what the model would be shown and how the episode is graded.
"""
import hashlib
import json
import time
from pathlib import Path

from . import eval19_v2 as ev2
from . import llm_adapter as la
from .agent_runner_v6 import RULES_V6, TOOL_RULES_V6
from .eval19 import S01_DESCRIPTIONS, S01_SYSTEM_PROMPT, sha

EVAL_SCHEMA = 'eval19-3-draft'
MANIFEST_SCHEMA = 'eval19-manifest-3-draft'
ROOT = Path(__file__).resolve().parents[2]
S01_ORDER_V6 = ('s06-sudden-5d', 's06-warned-delayed-10d', 's06-warned-no-delay-10d', 's06-multitier-cancel-10d',
                's06-alt-cheaper-10d')

S01_SYSTEM_PROMPT_V3 = (
    S01_SYSTEM_PROMPT + '\n\nEvery rule the plant enforces, and how the plant works. A call that breaks a rule is refused, '
    'changes nothing and still counts as a call, so read these before you act:\n'
    + '\n'.join('- ' + sentence for sentence in RULES_V6.values()))


def s01_descriptions():
    """Tool descriptions: the frozen base text plus the sentence of every rule that tool is subject to."""
    return {name: (base + ' ' + ' '.join(RULES_V6[r] for r in TOOL_RULES_V6.get(name, ()))).strip()
            for name, base in S01_DESCRIPTIONS.items()}


S01_DESCRIPTIONS_V3 = s01_descriptions()


def s01_tools(tool_definitions):
    """OpenAI tool schemas for the v0.6 tool profile (same shapes as eval19-2, descriptions from RULES_V6)."""
    tools = ev2.s01_tools(tool_definitions)
    for t in tools:
        t['function']['description'] = S01_DESCRIPTIONS_V3.get(t['function']['name'], t['function']['name'])
        if t['function']['name'] == 'commit_recovery':
            t['function']['parameters']['properties']['action_id'] = {
                'type': 'string', 'description': 'optional; a distinct id for each lot you buy on purpose'}
    return tools


class LLMAgentV6(ev2.LLMAgentV5):
    """The eval19-2 agent with the v0.6 tool profile. Every observation shown to the model is recorded for the leak scan."""

    def __init__(self, config, tool_definitions, **kw):
        super().__init__(config, tool_definitions, **kw)
        self.tools = s01_tools(tool_definitions)
        self._allowed = {t['function']['name'] for t in self.tools}
        m = dict(self.manifest)
        m.pop('manifest_sha256', None)
        m['tool_schemas'] = self.tools
        m['blinding'] = 'none needed: the v0.6 world state carries only an opaque scenario label'
        m['harness_version'] = EVAL_SCHEMA
        m['manifest_sha256'] = sha(m)
        self.manifest = m

    def _one_model_call(self, view):
        """The model offers `action_id` inside the arguments of commit_recovery; the runner takes it as the call's own
        `action_id` (the tool surface the runner enforces has no such argument). Nothing else is changed or repaired."""
        call = super()._one_model_call(view)
        if isinstance(call, dict) and call.get('tool') == 'commit_recovery' and isinstance(call.get('arguments'), dict) \
                and 'action_id' in call['arguments']:
            args = dict(call['arguments'])
            return {'tool': call['tool'], 'arguments': args, 'action_id': args.pop('action_id')} | {'arguments': args}
        return call


def s01_config(model, horizon_days, **over):
    return ev2.s01_config(model, horizon_days, **{'system_prompt': S01_SYSTEM_PROMPT_V3, **over})


def run_s01_episode(fixture, model, transport, *, config_over=None, api_key='proxy-injected',
                    sleep=time.sleep, clock=time.monotonic):
    """Run one live (or mocked) S01 v0.6 episode through the observable runner. Returns the raw private record."""
    from .agent_runner_v6 import ObservableRunnerV6
    from .dynamic_demo_v6 import factory
    sink = []
    runner = ObservableRunnerV6(factory(fixture, sink)())
    cfg = s01_config(model, fixture['horizon_days'], **(config_over or {}))
    runner._world.reset()
    agent = LLMAgentV6(cfg, runner.tool_definitions(), transport=transport, api_key=api_key, sleep=sleep, clock=clock)
    transcript = runner.run(agent, reset=False)
    return {'fixture_id': fixture['fixture_id'], 'model': model, 'manifest': agent.manifest,
            'transcript': la.redact(transcript, (api_key,)), 'telemetry': agent.telemetry(),
            'observed': agent.observed, 'world': sink[0]}


def grade_s01(fixture, raw):
    """Independent v0.6 checking, replay and leak scan of one recorded S01 episode (same fields as eval19-2)."""
    from .agent_runner_v6 import replay_v6
    from .dynamic_demo_v4 import METRICS, _get
    from .dynamic_demo_v6 import actions_of, factory
    from .dynamic_verifier_v6 import check_observations_for_leaks, verify_episode
    t, world = raw['transcript'], raw['world']
    complete = t['status'] == 'complete'
    scenario, horizon = fixture['scenario'], fixture['horizon_days']
    report = verify_episode(scenario, world.history(), horizon_days=horizon,
                            scorecard=world.scorecard() if complete else None, actions=actions_of(t))
    ok, diffs = replay_v6(t, factory(fixture))
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
        'verifier_feasible': report.feasible, 'verifier_complete': report.complete, 'hard_violation_codes': report.codes(),
        'replay_reproduced': ok, 'replay_differences': diffs,
        'observation_leaks': leaks, 'metrics': metrics, 'scorecard': card}


CHANGES = (
    'WORLD: S01 runs on the v0.6 family: opaque scenario label (as v0.5), a conventions block in the visible rules, '
    'exact-once purchases also without an action id, and the rebuilt independent checker (audit defects D2 to D6 closed).',
    'PROMPT: the S01 system prompt and tool descriptions are built from agent_runner_v6.RULES_V6, which adds one sentence per '
    'convention (same-day use of receipts, when production completes, when shipping starts and in what order, the unit of the '
    'penalty rate, penalty cap, cancellation, repeated purchases, what is only a plan before a firm notice).',
    'STATIC TASK: unchanged from eval19-2.')


def draft_manifest():
    """A DRAFT manifest for the next run on v0.6. It is not pre-registered and no model has been called."""
    files = ('src/supplychainworld/eval19_v3.py', 'src/supplychainworld/eval19_v2.py', 'src/supplychainworld/dynamic_v6.py',
             'src/supplychainworld/agent_runner_v6.py', 'src/supplychainworld/dynamic_verifier_v6.py',
             'src/supplychainworld/dynamic_demo_v6.py', 'fixtures/dynamic/v0.6/scenarios.json',
             'fixtures/dynamic/v0.6/hand-ledgers.json')
    body = {'schema': MANIFEST_SCHEMA, 'harness_version': EVAL_SCHEMA,
            'status': 'DRAFT, not run, not pre-registered; no model call has been made with this harness',
            'predecessors': {'first_diagnostic': 'evidence/issue-19/manifest.json (frozen; its hashes are unchanged)',
                             'next_run_harness': 'eval19-2 (src/supplychainworld/eval19_v2.py)'},
            'changes_from_eval19_2': list(CHANGES),
            'harness_sha256': {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in files},
            'prompts': {'s01_system_prompt': S01_SYSTEM_PROMPT_V3, 's01_tool_descriptions': S01_DESCRIPTIONS_V3},
            's01_scenarios': list(S01_ORDER_V6),
            'spend': {'approved_ceiling_usd': 0.0, 'paid_calls': 'none; free-tier models only through the existing adapter'},
            'limits': 'unchanged from eval19-2 (same guard, request caps and throttle imported from eval19)',
            'claims': 'software tests only; no model ability, generalization or training value is claimed; all business numbers PROVISIONAL'}
    body['manifest_sha256'] = sha(body)
    return body


def dumps_manifest():
    return json.dumps(draft_manifest(), indent=1, sort_keys=True) + '\n'
