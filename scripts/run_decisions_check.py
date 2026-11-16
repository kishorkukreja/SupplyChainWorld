#!/usr/bin/env python3
"""Budgeted live connectivity check for the Decisions API client.

At most THREE live requests in total (one yes_no, one ask_many, one route over three options), no retries,
neutral S01-style text supplied by this script (no world, scenario or hidden data). Writes sanitized results
only. This is connectivity evidence, not an evaluation: three calls say nothing about accuracy.

Usage: OPENROUTER_API_KEY=... PYTHONPATH=src python scripts/run_decisions_check.py [out_dir]
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from supplychainworld import decisions_client as dc  # noqa: E402
from supplychainworld import llm_adapter as la  # noqa: E402

MAX_LIVE_REQUESTS = 3
STATE = ('Day 2 of 5 at a small plant. The supplier shipment of component C is late by 2 days. '
         'Stock of component C is 40 units and daily use is 20 units. A recovery order can be committed today.')
ROUTE_OPTIONS = {
    'wait': 'Take no action and wait for the late shipment.',
    'recover': 'Commit the recovery order today.',
    'cancel': 'Cancel the affected production for the week.',
}


def timed(fn):
    t0 = time.monotonic()
    try:
        out = fn()
        return {'status': 'ok', 'latency_ms': round((time.monotonic() - t0) * 1000, 1), 'result': out}
    except la.AdapterError as exc:
        return {'status': 'failed', 'latency_ms': round((time.monotonic() - t0) * 1000, 1),
                'error_class': exc.error_class, 'error': la.redact_text(str(exc))[:300]}


def main(out_dir):
    client = dc.DecisionsClient(max_retries=0, timeout_seconds=60.0)
    results = {}
    results['yes_no'] = timed(lambda: client.yes_no(
        STATE, 'Will component C run out before the shipment arrives?',
        'Stock of C is used up before the shipment arrives.', 'Stock of C lasts until the shipment arrives.'))
    results['ask_many'] = timed(lambda: client.ask_many(STATE, {
        'late': dc.make_question('Is the supplier shipment late?', 'The shipment is late.', 'The shipment is on time.'),
        'recovery_open': dc.make_question('Can a recovery order still be committed today?',
                                          'A recovery order can be committed today.', 'No recovery order can be committed today.'),
    }))
    results['route'] = timed(lambda: client.route(STATE, ROUTE_OPTIONS))
    assert client.http_requests <= MAX_LIVE_REQUESTS
    out = {'schema': 'decisions-connectivity-1', 'run_at_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
           'endpoint': dc.DECISIONS_ENDPOINT, 'model': client.model, 'max_live_requests': MAX_LIVE_REQUESTS,
           'note': 'Connectivity and response-shape check only. Three calls are not an evaluation of accuracy.',
           'credential_env_var_present': bool(os.environ.get(dc.CREDENTIAL_ENV)),
           'state_text_sent': STATE, 'route_options_sent': ROUTE_OPTIONS,
           'client_summary': client.summary(), 'results': results}
    out = la.redact(out, (os.environ.get(dc.CREDENTIAL_ENV, ''),))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'decisions-check.json').write_text(json.dumps(out, indent=2) + '\n')
    for k, v in results.items():
        print(k, v['status'], v.get('error_class') or '', v['latency_ms'])
    return out


if __name__ == '__main__':
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'evidence/decisions-client')
