#!/usr/bin/env python3
"""eval19-3: plan (pre-registration), live Sarvam check, run (resumable), summary.

  PYTHONPATH=src python scripts/run_eval19_v3.py plan [--repeats 2] [--out evidence/eval19-3/plan.json]
  SARVAM_API_KEY=... PYTHONPATH=src python scripts/run_eval19_v3.py check --state DIR --live
  PYTHONPATH=src python scripts/run_eval19_v3.py run --state DIR --live [--limit N]
  PYTHONPATH=src python scripts/run_eval19_v3.py summary --state DIR

`plan` makes no model call. Commit the plan file ON ITS OWN before any other subcommand that talks to a model. `check` and `run`
need --live and refuse to start unless the plan is committed and unchanged and every frozen file still matches its hash.
Keys are read only from the environment and never printed or stored. Private records stay in --state (outside the repository).
Business numbers are PROVISIONAL, needs practitioner value.
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from supplychainworld import eval19_v3_run as er  # noqa: E402
from supplychainworld import llm_adapter as la  # noqa: E402
from supplychainworld import sarvam_adapter as sa  # noqa: E402
from supplychainworld import tracing  # noqa: E402


def live_transport():
    return lambda req: la.urllib_transport(req, timeout=120.0)


def preflight(plan_path):
    plan = json.loads(Path(plan_path).read_text())
    er.check_plan(plan)
    if not er.git_committed_clean(plan_path):
        raise er.PreflightError('the plan file is not committed, or has uncommitted changes: commit it on its own first')
    return plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['plan', 'check', 'run', 'summary'])
    ap.add_argument('--state')
    ap.add_argument('--out')
    ap.add_argument('--plan', default=str(er.PLAN_PATH))
    ap.add_argument('--repeats', type=int, default=er.DEFAULT_REPEATS)
    ap.add_argument('--limit', type=int)
    ap.add_argument('--live', action='store_true', help='allow real model calls')
    a = ap.parse_args()
    if a.cmd == 'plan':
        head = os.popen('git -C %s rev-parse HEAD' % ROOT).read().strip()
        plan = er.build_plan(repeats=a.repeats, git_head=head)
        out = Path(a.out) if a.out else er.PLAN_PATH
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(plan, indent=1, sort_keys=True) + '\n')
        print('wrote', out, 'episodes', plan['episodes_total'], plan['episodes_by_provider'])
        return
    if not a.state:
        sys.exit('--state is required')
    if a.cmd == 'summary':
        print(json.dumps(er.summarize(a.state), indent=1))
        return
    if not a.live:
        sys.exit('refusing: this makes real model calls; pass --live after the plan is committed')
    plan = preflight(a.plan)
    skey = os.environ.get(sa.CREDENTIAL_ENV, '')
    if not skey:
        sys.exit('SARVAM_API_KEY is not set in this session (start a new session after adding it)')
    if a.cmd == 'check':
        res = er.check_sarvam(a.state, live_transport(), key=skey, cap_inr=plan['spend']['sarvam']['hard_cap_inr'])
        print(json.dumps(res, indent=1))
        return
    summary = er.run(plan, a.state, {'openrouter': live_transport(), 'sarvam': live_transport()},
                     keys={'sarvam': skey}, trace_client=tracing.tracing_client(), limit=a.limit)
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
