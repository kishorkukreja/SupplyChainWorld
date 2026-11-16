"""Client for OpenRouter's (alpha) Decisions API: the 'decision_system1' scorer slot.

Endpoint: POST https://openrouter.ai/api/alpha/decisions (not chat/completions).
Verified request shape for respan/span-01-lite:
    {"model": ..., "state": "<plain text>", "questions": {key: {"type": "noul",
      "instructions": "<yes/no question>", "criteria": {"true": "...", "false": "..."}}}}
Verified response shape:
    {"answers": {key: {"type": "noul", "noul": <float 0..1, probability of true>}},
     "usage": {"input_tokens": .., "output_tokens": .., "cost": ..}, ...}

Limitations: Respan accepts only 'noul' (yes/no) questions. Anything else is rejected here before
any request is made. The API is alpha, so shapes may change; unexpected shapes raise
DecisionsResponseError and are never turned into answers.

Scorer only: this module never touches the world, scenario, verifier or ObservableRunner. The only
content sent is the caller-supplied `state` string plus the question text. Standard library only;
transport is injectable for tests; secrets are redacted from everything stored; free-only guard and a
$0 ceiling are enforced (a reported non-zero cost stops further use of the client).
"""
import json
import math
import os
import time
from pathlib import Path

from .llm_adapter import (AdapterError, ModelNotAllowedError, ProviderError, RateLimitedError,
                          redact, redact_text, urllib_transport, zero_priced, _error_text)

DECISIONS_ENDPOINT = 'https://openrouter.ai/api/alpha/decisions'
CREDENTIAL_ENV = 'OPENROUTER_API_KEY'
DEFAULT_ROLE = 'decision_system1'
SUPPORTED_QUESTION_TYPE = 'noul'
ROSTER_PATH = Path(__file__).resolve().parents[2] / 'config' / 'llm_roster.json'


class DecisionsError(AdapterError):
    error_class = 'decisions_error'


class UnsupportedQuestionError(DecisionsError):
    error_class = 'unsupported_question'


class DecisionsResponseError(DecisionsError):
    """Missing fields, wrong types or out-of-range values in a provider response."""
    error_class = 'malformed_decisions_response'


class CostCeilingError(DecisionsError):
    error_class = 'cost_ceiling'


def load_scorer_spec(role=DEFAULT_ROLE, roster=None):
    """Return (model_id, spec) from the roster; free-only guard: kind 'scorer' and verified zero pricing."""
    if roster is None:
        roster = json.loads(ROSTER_PATH.read_text())
    spec = (roster.get('roles') or {}).get(role)
    if not isinstance(spec, dict):
        raise ModelNotAllowedError(f'role {role!r} not in roster')
    check_scorer_spec(spec)
    return spec['model_id'], spec


def check_scorer_spec(spec):
    if spec.get('kind') != 'scorer':
        raise ModelNotAllowedError('decisions client accepts only roster roles of kind "scorer"')
    if not isinstance(spec.get('model_id'), str) or not spec['model_id']:
        raise ModelNotAllowedError('roster role has no model_id')
    if not (spec['model_id'].endswith(':free') or zero_priced(spec.get('verified_pricing'))):
        raise ModelNotAllowedError(f"{spec['model_id']} is not verified as zero-priced; refusing")


def make_question(instructions, true_criteria, false_criteria):
    for name, v in (('instructions', instructions), ('true_criteria', true_criteria), ('false_criteria', false_criteria)):
        if not isinstance(v, str) or not v.strip():
            raise UnsupportedQuestionError(f'{name} must be a non-empty plain string')
    return {'type': SUPPORTED_QUESTION_TYPE, 'instructions': instructions,
            'criteria': {'true': true_criteria, 'false': false_criteria}}


def _validate_question(key, q):
    if not isinstance(key, str) or not key:
        raise UnsupportedQuestionError('question keys must be non-empty strings')
    if not isinstance(q, dict) or q.get('type') != SUPPORTED_QUESTION_TYPE:
        got = q.get('type') if isinstance(q, dict) else q
        raise UnsupportedQuestionError(
            f'question {key!r}: this model accepts only type "noul" (yes/no); got {got!r}')
    crit = q.get('criteria')
    if not isinstance(crit, dict) or set(crit) != {'true', 'false'}:
        raise UnsupportedQuestionError(f'question {key!r}: criteria must be an object with exactly "true" and "false" keys')
    make_question(q.get('instructions'), crit['true'], crit['false'])


def _prob(value, key):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise DecisionsResponseError(f'answer {key!r} is not a probability in [0, 1]')
    return float(value)


def _num(u, k):
    v = u.get(k)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 else None


class DecisionsClient:
    def __init__(self, model=None, spec=None, *, transport=None, api_key=None, endpoint=DECISIONS_ENDPOINT,
                 max_retries=2, backoff_base_seconds=1.0, backoff_cap_seconds=8.0, timeout_seconds=60.0,
                 sleep=time.sleep, roster=None, role=DEFAULT_ROLE):
        if spec is None:
            model, spec = load_scorer_spec(role, roster)
        else:
            check_scorer_spec(spec)
            model = model or spec['model_id']
            if model != spec['model_id']:
                raise ModelNotAllowedError('model does not match roster spec')
        if type(max_retries) is not int or max_retries < 0:
            raise ValueError('max_retries must be a non-negative integer')
        self.model, self.endpoint = model, endpoint
        self.max_retries, self.sleep = max_retries, sleep
        self.backoff_base, self.backoff_cap = backoff_base_seconds, backoff_cap_seconds
        self.transport = transport or (lambda req: urllib_transport(req, timeout=timeout_seconds))
        self._api_key = api_key if api_key is not None else os.environ.get(CREDENTIAL_ENV, '')
        self.http_requests = 0
        self.total_cost_usd = 0.0
        self.unknown_cost_calls = 0
        self.usage_total = {'input_tokens': 0, 'output_tokens': 0}
        self.calls = []

    # ------------------------------------------------------------ transport
    def _post(self, payload):
        if self.total_cost_usd > 0:
            raise CostCeilingError('approved ceiling is $0 and a non-zero cost was reported; client disabled')
        request = {'url': self.endpoint, 'body': json.dumps(payload).encode(),
                   'headers': {'Content-Type': 'application/json', 'Authorization': f'Bearer {self._api_key}'}}
        retries = 0
        while True:
            status, headers, raw = self.transport(request)
            self.http_requests += 1
            if status == 200:
                try:
                    body = json.loads(raw.decode('utf-8', 'replace')) if raw else None
                except ValueError:
                    body = None
                if not isinstance(body, dict):
                    raise DecisionsResponseError('200 with a non-JSON-object body')
                if 'error' in body and 'answers' not in body:
                    raise ProviderError('provider error in 200 body: ' + self._safe(_error_text(raw)[0]))
                return body, retries
            text = self._safe(_error_text(raw)[0] if raw else '')
            if status in (0, 429) or 500 <= status < 600:
                if retries >= self.max_retries:
                    cls = RateLimitedError if status == 429 else ProviderError
                    raise cls(f'HTTP {status} after {retries} retries: {text}')
                wait = min(self.backoff_cap, self.backoff_base * (2 ** retries))
                for k, v in (headers or {}).items():
                    if str(k).lower() == 'retry-after':
                        try:
                            wait = min(self.backoff_cap, max(wait, float(v)))
                        except (TypeError, ValueError):
                            pass
                retries += 1
                self.sleep(wait)
                continue
            raise ProviderError(f'HTTP {status}: {text}')  # 400 and other 4xx are not retried

    def _safe(self, text):
        return redact_text(str(text), (self._api_key,))[:300]

    # ------------------------------------------------------------ API
    def ask_many(self, state, questions):
        """Several noul questions in one request. Returns {'answers': {key: p}, 'usage', 'cost_usd', ...}."""
        if not isinstance(state, str) or not state.strip():
            raise UnsupportedQuestionError('state must be a non-empty plain string')
        if not isinstance(questions, dict) or not questions:
            raise UnsupportedQuestionError('questions must be a non-empty dict')
        for k, q in questions.items():
            _validate_question(k, q)
        body, retries = self._post({'model': self.model, 'state': state, 'questions': questions})
        answers = body.get('answers')
        if not isinstance(answers, dict):
            raise DecisionsResponseError('response has no "answers" object')
        probs = {}
        for k in questions:
            a = answers.get(k)
            if not isinstance(a, dict) or a.get('type') != SUPPORTED_QUESTION_TYPE or 'noul' not in a:
                raise DecisionsResponseError(f'answer {k!r} missing or not a noul answer')
            probs[k] = _prob(a['noul'], k)
        usage, cost = self._account(body)
        rec = {'answers': probs, 'usage': usage, 'cost_usd': cost, 'retries': retries,
               'returned_model': body.get('model') if isinstance(body.get('model'), str) else None}
        self.calls.append({'questions': sorted(questions), 'usage': usage, 'cost_usd': cost, 'retries': retries})
        return rec

    def _account(self, body):
        u = body.get('usage')
        if not isinstance(u, dict):
            self.unknown_cost_calls += 1
            return None, 'unknown'
        usage = {k: u[k] for k in ('input_tokens', 'output_tokens') if type(u.get(k)) is int and u[k] >= 0}
        for k in usage:
            self.usage_total[k] += usage[k]
        cost = _num(u, 'cost')
        if cost is None:
            self.unknown_cost_calls += 1
            return usage or None, 'unknown'
        usage['cost'] = cost
        self.total_cost_usd += cost
        if cost > 0:
            raise CostCeilingError(f'provider reported non-zero cost {cost}; $0 ceiling exceeded')
        return usage, cost

    def yes_no(self, state, instructions, true_criteria, false_criteria, threshold=0.5):
        """One yes/no question. Returns probability (of true), boolean (probability >= threshold), usage, cost."""
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0.0 <= threshold <= 1.0:
            raise ValueError('threshold must be in [0, 1]')
        q = make_question(instructions, true_criteria, false_criteria)
        r = self.ask_many(state, {'q': q})
        p = r['answers']['q']
        return {'probability': p, 'answer': p >= threshold, 'threshold': threshold, 'usage': r['usage'],
                'cost_usd': r['cost_usd'], 'retries': r['retries']}

    def route(self, state, options, threshold=0.5, margin=0.1):
        """A router built on yes/no scoring: one independent noul question per option, one request.

        `options` is {name: description}. Returns per-option probabilities (they are independent and do
        NOT sum to 1), the argmax, and `ambiguous`=True when no option reaches `threshold` or the top two
        are within `margin`. `choice` is the argmax name, or None when no option reaches the threshold.
        This is not a native multiple-choice API call: the model only accepts noul questions.
        """
        if not isinstance(options, dict) or len(options) < 2:
            raise UnsupportedQuestionError('options must be a dict of at least two name: description entries')
        questions = {}
        for name, desc in options.items():
            if not isinstance(name, str) or not name or not isinstance(desc, str) or not desc.strip():
                raise UnsupportedQuestionError('option names and descriptions must be non-empty strings')
            questions[name] = make_question(
                f'Is this option the right one to choose: {name}: {desc}', f'The option "{name}" fits the situation.',
                f'The option "{name}" does not fit the situation.')
        r = self.ask_many(state, questions)
        probs = r['answers']
        ranked = sorted(probs, key=lambda k: (-probs[k], k))
        top, second = ranked[0], ranked[1]
        gap = probs[top] - probs[second]
        none_above = probs[top] < threshold
        return {'probabilities': probs, 'argmax': top, 'choice': None if none_above else top,
                'top_two_gap': gap, 'ambiguous': bool(none_above or gap < margin), 'threshold': threshold,
                'margin': margin, 'probabilities_sum_to_one': False, 'usage': r['usage'],
                'cost_usd': r['cost_usd'], 'retries': r['retries']}

    def summary(self):
        return redact({'model': self.model, 'http_requests': self.http_requests, 'successful_calls': len(self.calls),
                       'usage_total': self.usage_total, 'total_cost_usd': self.total_cost_usd,
                       'unknown_cost_calls': self.unknown_cost_calls}, (self._api_key,))
