"""Shared helpers for the tracing tests: 25 mocked S01 v0.6 episodes (no network) and a fake Langfuse client."""
import contextlib
import copy
import functools

import test_eval19_v2 as t2
from supplychainworld import eval19_v3 as ev3
from supplychainworld.agent_runner_v6 import POLICIES_V6
from supplychainworld.dynamic_demo_v6 import load_fixtures


@functools.lru_cache(maxsize=1)
def _episodes():
    out = []
    for policy in POLICIES_V6:
        for fx in load_fixtures():
            base = t2.PolicyModel(policy)
            g = t2.guarded(base, private_strings=[])
            g.model, g.phase = t2.MODEL, 's01'
            raw = ev3.run_s01_episode(fx, t2.MODEL, g, sleep=lambda s: None)
            out.append((policy, raw, ev3.grade_s01(fx, raw)))
    return out


def episodes():
    """Fresh deep copies so a test may damage them."""
    return [(p, copy.deepcopy({k: v for k, v in raw.items() if k != 'world'}) | {'world': raw['world']}, copy.deepcopy(g))
            for p, raw, g in _episodes()]


class FakeClient:
    """Records every call a Langfuse client would get, in order."""

    def __init__(self):
        self.events, self.scores, self.flushes = [], [], 0

    @contextlib.contextmanager
    def start_as_current_observation(self, **kw):
        rec = {'kw': kw, 'updates': []}
        self.events.append(rec)

        class Span:
            def update(_s, **u):
                rec['updates'].append(u)
        yield Span()

    def create_score(self, **kw):
        self.scores.append(kw)

    def flush(self):
        self.flushes += 1


@contextlib.contextmanager
def fake_propagate(**kw):
    FakeClient.last_propagate = kw
    yield
