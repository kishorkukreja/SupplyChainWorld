#!/usr/bin/env python3
"""Issue #19 diagnostic, NEXT run (harness version eval19-2): manifest, live run (resumable), sanitized report.

The first diagnostic's harness (`eval19.py`, `scripts/run_eval19.py`) is frozen and untouched, so its run record in
evidence/issue-19/ stays valid. This script reuses that run script's live loop and report by import and swaps in
`eval19_v2` (S01 v0.5 world with an opaque scenario id, the stated-rules prompt and tool descriptions, the per-kind
strict submission schema). Only the manifest is new, with bumped version and hash fields.

  PYTHONPATH=src python scripts/run_eval19_v2.py manifest [--out evidence/issue-19-run2/manifest.json]
  OPENROUTER_API_KEY=... PYTHONPATH=src python scripts/run_eval19_v2.py run --state DIR
  PYTHONPATH=src python scripts/run_eval19_v2.py report --state DIR [--out evidence/issue-19-run2]

NOT RUN in the fixes work: the owner reruns the diagnostic later, with more models, after preregistering the manifest
this script writes (commit it on its own before any model call; the roster below is a placeholder the owner sets).
The key is read only from the environment; it is never printed or stored.
"""
import argparse
import copy
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

import run_eval19 as base  # noqa: E402
from supplychainworld import eval19_v2 as ev2  # noqa: E402

HARNESS_FILES = ('src/supplychainworld/eval19_v2.py', 'src/supplychainworld/llm_adapter.py', 'scripts/run_eval19_v2.py',
                 'scripts/run_eval19.py', 'src/supplychainworld/eval19.py',
                 'src/supplychainworld/verification_v12.py', 'src/supplychainworld/solvers_v12.py',
                 'src/supplychainworld/schemas_v12.py', 'src/supplychainworld/schemas_v121.py',
                 'src/supplychainworld/dynamic_v5.py', 'src/supplychainworld/agent_runner_v5.py',
                 'src/supplychainworld/dynamic_verifier_v5.py', 'src/supplychainworld/dynamic_demo_v5.py',
                 'src/supplychainworld/dynamic_verifier_v4.py', 'config/llm_roster.json')
FIXTURE_FILES = ('fixtures/dynamic/v0.5/scenarios.json', 'fixtures/dynamic/v0.5/hand-ledgers.json')
PREDECESSOR = 'evidence/issue-19/manifest.json'
# Sections of the first manifest that are unchanged by the three fixes and are carried over as they were.
CARRIED = ('spend', 'credential', 'limits', 'retry_rules', 'metrics', 'baselines', 'failure_triage', 'recommendation_rule',
           'readiness_decision')
CHANGES = (
    'TASK DEFECT: S01 runs on the v0.5 family. The world state carries an opaque scenario label (scn- and 8 hex characters '
    'derived from the visible parameters, outcome excluded) instead of a name such as warned-delayed. The harness-side '
    'blinding alias is gone; the independent v0.5 leak scan fails any episode whose observations show anything else.',
    'HARNESS GAP: the S01 system prompt and every S01 tool description are built from agent_runner_v5.RULES, one sentence for '
    'every enforced rule, including that production cannot exceed open customer demand. A test ties every rejection reason to '
    'a stated sentence.',
    'SUBMISSION SCHEMA: the static task offers one tool per answer kind (submit_award, submit_clarification, submit_infeasible), '
    'each with exactly its own fields all required, and grades with the strict 1.2.1 shape check before the independent 1.2 '
    'checker. Extra or missing fields are rejected with a clear message and no credit. Nothing is repaired.')


def fixtures():
    from supplychainworld.dynamic_demo_v5 import load_fixtures
    by = {f['fixture_id']: f for f in load_fixtures()}
    return [by[i] for i in ev2.S01_ORDER]


def build_manifest():
    from supplychainworld.agent_runner_v5 import POLICIES_V5, ObservableRunnerV5
    from supplychainworld.dynamic_demo_v5 import factory
    old = json.loads((ROOT / PREDECESSOR).read_text())
    fx = fixtures()
    defs = ObservableRunnerV5(factory(fx[0])()).tool_definitions()
    cases = ev2.load_static_cases()
    selected = ev2.select_static_cases(cases)
    m = {
        'schema': ev2.MANIFEST_SCHEMA,
        'harness_version': ev2.EVAL_SCHEMA,
        'issue': old['issue'],
        'preregistration_status': ('DRAFT. Commit this file on its own, with the roster set by the owner, BEFORE any model call. '
                                   'A manifest committed after a call is not a preregistration.'),
        'preregistered_before_any_model_attempt': False,
        'purpose': old['purpose'],
        'predecessor': {'manifest': PREDECESSOR, 'manifest_schema': old['schema'], 'manifest_sha256': old['manifest_sha256'],
                        'harness_sha256': old['harness_sha256'],
                        'note': 'The first run record stays valid because none of its frozen files were edited; this is a new harness version.'},
        'changes_from_predecessor': list(CHANGES),
        'roster': {'core': list(ev2.ROSTER_CORE), 'conditional': list(ev2.ROSTER_CONDITIONAL),
                   'note': 'PLACEHOLDER: the first run roster. The owner sets the roster (more models) before freezing. Free models only.'},
        'development_set': {
            's01_v0.5': {'scenarios': [{'fixture_id': f['fixture_id'], 'horizon_days': f['horizon_days'],
                                        'disruption_class': f['disruption_class'], 'scenario_label': f['scenario']['scenario_id']}
                                       for f in fx],
                         'fixture_file_sha256': {p: base.file_hash(p) for p in FIXTURE_FILES},
                         'repeats': 'to be set by the owner when freezing (the first run was one attempt per scenario per model)',
                         'scripted_baselines': list(POLICIES_V5)},
            'static_v1.2': {'family_size': len(cases), 'selection_rule': ev2.select_static_cases.__doc__.strip(),
                            'selected_case_ids': selected, 'n': len(selected),
                            'fixture_dir_sha256': hashlib.sha256(''.join(
                                base.file_hash('fixtures/reference_cases_v1_2/%s.json' % i) for i in sorted(cases)).encode()).hexdigest()},
        },
        'tool_profile': {
            's01': {'tools': ev2.s01_tools(defs), 'blinding': 'none: the v0.5 world exposes only an opaque scenario label'},
            'static': {'tools': ev2.SUBMIT_TOOLS, 'authority': 'one submission tool call (one tool per answer kind); no read tools'}},
        'prompts': {'s01_system_prompt': ev2.S01_SYSTEM_PROMPT_V2, 'static_system_prompt': ev2.STATIC_SYSTEM_PROMPT_V2,
                    'static_request': ev2.STATIC_REQUEST,
                    'rules_table': 'src/supplychainworld/agent_runner_v5.py RULES (one sentence per enforced rule)'},
        'grading': {
            's01': 'independent verifier dynamic_verifier_v5.verify_episode on the recorded history, claimed scorecard and action log; '
                   'replay_v5 on a fresh world; check_observations_for_leaks (v0.5, scans every string before the firm notice) on every observation shown',
            'static': 'strict shape check schemas_v121 first (no repair), then independent checker verification_v12.verify (used only by the grader)'},
        'harness_sha256': {p: base.file_hash(p) for p in HARNESS_FILES},
        'git_head_at_generation': os.popen('git -C %s rev-parse HEAD' % ROOT).read().strip(),
        'generated_at_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }
    for key in CARRIED:
        m[key] = copy.deepcopy(old[key])
    m['manifest_sha256'] = ev2.sha(m)
    return m


# Swap the new harness into the first run script's loop and report; only the pieces below differ.
base.ev = ev2
base.fixtures = fixtures
base.build_manifest = build_manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['manifest', 'run', 'report'])
    ap.add_argument('--out')
    ap.add_argument('--state')
    a = ap.parse_args()
    if a.cmd == 'manifest':
        out = Path(a.out) if a.out else ROOT / 'evidence/issue-19-run2/manifest.json'
        base.save_json(out, build_manifest())
        print('wrote', out)
    elif a.cmd == 'run':
        base.run(Path(a.state))
    else:
        base.report(Path(a.state), Path(a.out) if a.out else ROOT / 'evidence/issue-19-run2')


if __name__ == '__main__':
    main()
