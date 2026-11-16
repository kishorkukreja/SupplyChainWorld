#!/usr/bin/env python3
"""Budgeted live connectivity check for the issue #18 LLM adapter.

At most ONE logical request per verified actor model (one retry at most), max_tokens 64, a fixed ping
prompt. Scorer slots and slots whose request format is unverified are skipped, not called.
Writes sanitized results only (status, latency, usage, error class). No keys, no other prompts.

Usage: OPENROUTER_API_KEY=... PYTHONPATH=src python scripts/run_llm_connectivity_check.py [out_dir]
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from supplychainworld import llm_adapter as la  # noqa: E402

PING_MESSAGES = [
    {'role': 'system', 'content': 'You are a connectivity probe. Call the ping tool once.'},
    {'role': 'user', 'content': 'Call the ping tool with message "ok".'},
]
PING_TOOLS = [{'type': 'function', 'function': {
    'name': 'ping', 'description': 'Connectivity probe.',
    'parameters': {'type': 'object', 'properties': {'message': {'type': 'string'}}, 'required': ['message']}}}]
MAX_TOKENS = 64


def probe(model):
    cfg = la.AdapterConfig(model, max_retries=1, timeout_seconds=60.0, max_output_tokens=MAX_TOKENS)
    rec = {'model': model, 'max_tokens': MAX_TOKENS, 'max_retries': 1}
    try:
        res = la.chat_request(cfg, PING_MESSAGES, PING_TOOLS, max_retries=1, max_tokens=MAX_TOKENS)
    except la.AdapterError as exc:
        rec.update(status='failed', error_class=exc.error_class, error=la.redact_text(str(exc))[:300])
        return rec
    body = res['body']
    usage = la.extract_usage(body)
    choice = (body.get('choices') or [{}])[0] if isinstance(body.get('choices'), list) else {}
    msg = choice.get('message') if isinstance(choice, dict) and isinstance(choice.get('message'), dict) else {}
    calls = msg.get('tool_calls') if isinstance(msg.get('tool_calls'), list) else []
    rec.update(status='responded', http_requests=res['http_requests'], retries=res['retries'],
               latency_ms=round(res['latency_ms'], 1), usage=usage, cost_usd=la.call_cost(model, usage, True),
               finish_reason=choice.get('finish_reason') if isinstance(choice, dict) else None,
               tool_call_returned=bool(calls), tool_call_name=(calls[0].get('function') or {}).get('name') if calls else None,
               text_returned=bool(msg.get('content')), returned_model=body.get('model') if isinstance(body.get('model'), str) else None)
    return rec


def main(out_dir):
    roster = json.loads((ROOT / 'config/llm_roster.json').read_text())
    results = []
    for role, spec in roster['roles'].items():
        if spec.get('kind') != 'actor' or not spec.get('model_id'):
            results.append({'role': role, 'model': spec.get('model_id'), 'status': 'skipped',
                            'reason': spec.get('connectivity') or f"kind={spec.get('kind')} is not an acting model"})
    seen = set()
    for model in roster['connectivity_check_roster']:
        if model in seen:
            continue
        seen.add(model)
        roles = [r for r, s in roster['roles'].items() if s.get('model_id') == model or model in s.get('also_verified', [])]
        r = probe(model)
        r['roles'] = roles
        results.append(r)
        print(model, r['status'], r.get('error_class') or '', r.get('latency_ms') or '')
    out = {'schema': 'llm-connectivity-1', 'run_at_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
           'endpoint': la.ENDPOINT, 'note': 'Connectivity and tool-call plumbing only. Not an evaluation of model ability.',
           'credential_env_var_present': bool(os.environ.get(la.CREDENTIAL_ENV)), 'results': results}
    out = la.redact(out, (os.environ.get(la.CREDENTIAL_ENV, ''),))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'connectivity.json').write_text(json.dumps(out, indent=2) + '\n')
    return out


if __name__ == '__main__':
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'evidence/issue-18')
