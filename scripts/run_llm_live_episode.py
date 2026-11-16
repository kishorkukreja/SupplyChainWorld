#!/usr/bin/env python3
"""ONE live S01 five-day diagnostic episode through the observable runner (issue #18).

Connectivity/diagnostic run only, not an evaluation. Hard cap of 12 model calls, free-tier model only.
Usage: OPENROUTER_API_KEY=... PYTHONPATH=src python scripts/run_llm_live_episode.py MODEL [out_dir]
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from supplychainworld import llm_adapter as la  # noqa: E402
from supplychainworld.agent_runner import ObservableRunner, replay  # noqa: E402
from supplychainworld.dynamic import OperationalWorld, SupplierDelayScenario  # noqa: E402
from supplychainworld.dynamic_verifier import verify_episode  # noqa: E402

FIXTURE_ID = 's01-five-day'
MAX_CALLS = 12


def main(model, out_dir):
    fixture = next(f for f in json.loads((ROOT / 'fixtures/dynamic/supplier-delay-inputs.json').read_text())['fixtures']
                   if f['fixture_id'] == FIXTURE_ID)
    sink = []

    def make():
        w = OperationalWorld(fixture['horizon_days'], scenario=SupplierDelayScenario(**fixture['scenario']))
        sink.append(w)
        return w

    runner = ObservableRunner(make())
    cfg = la.AdapterConfig(model, max_model_calls=MAX_CALLS, max_output_tokens=2048, max_retries=2)
    out = la.run_llm_episode(runner, cfg)
    world = sink[0]
    transcript = out['transcript']
    actions = [{'day': a['day'], 'kind': {'commit_recovery': 'recovery', 'release_production': 'release'}[a['tool']],
                'arguments': a['arguments'], 'result': a['result']}
               for a in transcript['attempts'] if a['tool'] in ('commit_recovery', 'release_production')]
    # Verification and replay use the recorded world history and the recorded calls, outside the adapter.
    report = verify_episode(fixture['scenario'], world.history(), horizon_days=fixture['horizon_days'],
                            scorecard=world.scorecard() if transcript['status'] == 'complete' else None, actions=actions)
    ok, diffs = replay(transcript, make)
    result = {'schema': 'llm-live-episode-1', 'label': 'connectivity/diagnostic run only, not an evaluation',
              'run_at_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'fixture_id': FIXTURE_ID,
              'manifest': out['manifest'], 'runner_status': out['runner_status'], 'episode_complete': out['episode_complete'],
              'telemetry': out['telemetry'],
              'verifier': {'feasible': report.feasible, 'codes': report.codes()},
              'replay': {'transcript_reproduced': ok, 'differences': diffs},
              'scorecard': transcript['scorecard'], 'transcript': transcript}
    result = la.redact(result, (os.environ.get(la.CREDENTIAL_ENV, ''),))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'live-episode.json').write_text(json.dumps(result, indent=2) + '\n')
    t = result['telemetry']
    print(json.dumps({k: result[k] for k in ('runner_status', 'episode_complete', 'verifier', 'replay', 'scorecard')}))
    print(json.dumps({k: t[k] for k in ('model_calls', 'http_requests', 'retries', 'prompt_tokens', 'completion_tokens',
                                        'total_tokens', 'latency_ms_total', 'cost_usd', 'stop_reason', 'failure')}))
    return result


if __name__ == '__main__':
    main(sys.argv[1], Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / 'evidence/issue-18')
