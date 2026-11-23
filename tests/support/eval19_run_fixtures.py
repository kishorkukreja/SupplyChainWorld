"""Shared helpers for the eval19-3 run tests: a plan whose queue is cut down for speed, and mocked provider transports."""
import functools
import json

import test_eval19_v2 as t2
from supplychainworld import eval19_v3_run as er

KEY = 'sk-TESTKEY-0123456789abcdef'


@functools.lru_cache(maxsize=1)
def _full_plan():
    return er.build_plan(git_head='test', now=None)


def full_plan():
    return json.loads(json.dumps(_full_plan()))


def small_plan(models=None, fixtures=None, repeats=None):
    """The real plan with its queue filtered, hash recomputed. For tests only: a real run uses the committed full plan."""
    plan = full_plan()
    plan['queue'] = [q for q in plan['queue']
                     if (models is None or q['model'] in models) and (fixtures is None or q['fixture_id'] in fixtures)
                     and (repeats is None or q['repeat'] <= repeats)]
    plan['episodes_total'] = len(plan['queue'])
    plan['plan_sha256'] = er.sha_plan(plan)
    return plan


def mock_routes(policy='combo_on_alert'):
    """One PolicyModel per provider so a test can read what each route was sent."""
    return {'openrouter': t2.PolicyModel(policy), 'sarvam': t2.PolicyModel(policy)}


def constant(status, body=b''):
    return lambda request: (status, {}, body)


def seen_headers(routes):
    return routes
