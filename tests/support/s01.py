"""Small S01 helpers shared by the property, fuzz and end-to-end tests.

Only uses the public S01 v0.1 modules. Hidden scenario data stays inside the
world; policies and tests read `view()` / `observation()` only.
"""
import json
from pathlib import Path

from supplychainworld.agent_runner import ObservableRunner
from supplychainworld.dynamic import OperationalWorld, SupplierDelayScenario

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = json.loads((ROOT / 'fixtures/dynamic/supplier-delay-inputs.json').read_text())['fixtures']
POLICIES = ('maintain', 'expedite', 'alternate')


def fixture(fixture_id):
    """Return (scenario dict, horizon_days) for a fixture id."""
    f = next(x for x in FIXTURES if x['fixture_id'] == fixture_id)
    return f['scenario'], f['horizon_days']


def world_factory(fixture_id='s01-five-day'):
    scenario, horizon = fixture(fixture_id)
    return lambda: OperationalWorld(horizon, scenario=SupplierDelayScenario(**scenario))


def new_runner(fixture_id='s01-five-day', **kw):
    return ObservableRunner(world_factory(fixture_id)(), **kw)


def finish(world):
    """Close days until the episode is complete (bounded, never loops forever)."""
    for _ in range(1000):
        if world.snapshot()['phase'] == 'complete':
            return
        world.close_day()
    raise AssertionError('episode did not complete')
