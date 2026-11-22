"""Saving failing examples as regression fixtures.

Workflow (details in docs/testing.md):
1. A property or fuzz test wraps its checks in
   `with record_on_failure('test_name', example):`. With SCW_SAVE_FAILURES=1 a
   failing example is written to tests/regressions/pending/<test_name>.json.
   Hypothesis replays the smallest failing example last, so the file ends up
   holding the minimal one.
2. After fixing the bug, `promote('test_name')` moves it to
   tests/regressions/<test_name>-<hash>.json, which is committed.
3. The test (or a sibling) calls `load_regressions('test_name')` and replays each
   saved example as an ordinary, permanent test case.

Examples must be JSON-serializable. Nothing is written unless asked to.
"""
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path

REGRESSION_DIR = Path(__file__).resolve().parents[1] / 'regressions'
PENDING_DIR = REGRESSION_DIR / 'pending'


def _dump(example):
    return json.dumps(example, sort_keys=True, indent=1) + '\n'


@contextmanager
def record_on_failure(name, example):
    """Save `example` as pending if the body raises and SCW_SAVE_FAILURES=1."""
    try:
        yield
    except BaseException:
        if os.environ.get('SCW_SAVE_FAILURES') == '1':
            PENDING_DIR.mkdir(parents=True, exist_ok=True)
            (PENDING_DIR / f'{name}.json').write_text(_dump(example))
        raise


def promote(name):
    """Move the pending example for `name` into the committed regression set."""
    src = PENDING_DIR / f'{name}.json'
    text = src.read_text()
    digest = hashlib.sha256(text.encode()).hexdigest()[:10]
    dest = REGRESSION_DIR / f'{name}-{digest}.json'
    dest.write_text(text)
    src.unlink()
    return dest


def save_failing_example(name, example):
    """Directly save an example as a committed regression (for manual use)."""
    text = _dump(example)
    digest = hashlib.sha256(text.encode()).hexdigest()[:10]
    REGRESSION_DIR.mkdir(parents=True, exist_ok=True)
    dest = REGRESSION_DIR / f'{name}-{digest}.json'
    dest.write_text(text)
    return dest


def load_regressions(name):
    """Return every committed example saved for `name`, in a stable order."""
    return [json.loads(p.read_text()) for p in sorted(REGRESSION_DIR.glob(f'{name}-*.json'))]
