"""Deterministic operational kernel for the S01 v0.5 scenario family (issue #19 fixes, finding 1: task defect).

Built beside `dynamic_v4.py` (and v0.1 to v0.4), all untouched; v0.4 is reused by subclassing. Every
business rule and every number is the v0.4 rule and number (all PROVISIONAL, needs practitioner value;
not reviewed by a practitioner). The ONLY change is what a scenario is called inside the world.

THE DEFECT (found by the #19 diagnostic): the v0.4 world state carried `scenario_id`, whose text named the
outcome class, for example `s04-warned-delayed-10d` against `s04-warned-no-delay-10d`. Anything that read the
state, including a model, could read the answer to the paired scenarios.

THE FIX, in the world and not only in a harness view: a v0.5 scenario id must be an opaque label,
`scn-` plus 8 hex characters, and it must equal a hash of the scenario's VISIBLE-side parameters only (every
field except the scenario id and the two hidden outcome fields `delay_outcome` and `delayed_arrival_day`).
So two scenarios that differ only in the hidden outcome (warned and delayed against warned and not
delayed) carry the SAME label, and the label says nothing about the outcome. A hand-picked name such as
`scn-warned-delayed` is refused. The label is stable (same parameters, same label) so records can still be
matched, and the human-readable fixture name stays outside the world, in the fixture file.
"""
import hashlib
import json
import re

from .dynamic_v3 import SIGNAL_TEXT, _tier  # noqa: F401
from .dynamic_v4 import OperationalWorldV4, ScenarioV4

SCHEMA = '5.0'
VALUES_STATUS = 'PROVISIONAL, needs practitioner value; not reviewed by a practitioner'
LABEL_PATTERN = re.compile(r'^scn-[0-9a-f]{8}$')
# Fields that never enter the label: the id itself and the hidden outcome.
LABEL_EXCLUDES = ('scenario_id', 'delay_outcome', 'delayed_arrival_day', 'schema_version', 'runtime_version')


def opaque_label(scenario):
    """The stable opaque id for a scenario mapping: a hash of its visible-side parameters, outcome excluded."""
    visible = {k: v for k, v in scenario.items() if k not in LABEL_EXCLUDES}
    blob = json.dumps(visible, sort_keys=True, separators=(',', ':'))
    return 'scn-' + hashlib.sha256(blob.encode()).hexdigest()[:8]


class ScenarioV5(ScenarioV4):
    """v0.4 scenario fields and validation; the scenario id must be the opaque label for its visible parameters."""

    def __init__(self, **kw):
        if kw.get('schema_version', SCHEMA) != SCHEMA or kw.get('runtime_version', SCHEMA) != SCHEMA:
            raise ValueError('unsupported scenario or runtime version')
        kw = {k: v for k, v in kw.items() if k not in ('schema_version', 'runtime_version')}
        super().__init__(**kw)
        self.schema_version = self.runtime_version = SCHEMA
        if not LABEL_PATTERN.match(self.scenario_id):
            raise ValueError('scenario_id must be an opaque label like scn-0a1b2c3d, not a descriptive name')
        if self.scenario_id != opaque_label(self.to_dict()):
            raise ValueError('scenario_id must equal the label derived from the scenario visible parameters')


class OperationalWorldV5(OperationalWorldV4):
    """v0.4 world, same rules and numbers; requires a v0.5 scenario so the visible id is opaque."""

    def __init__(self, horizon_days: int = 5, *, scenario: ScenarioV5):
        if not isinstance(scenario, ScenarioV5):
            raise TypeError('scenario must be a ScenarioV5')
        super().__init__(horizon_days, scenario=scenario)

    def snapshot(self):
        s = super().snapshot()
        s['schema_version'] = s['runtime_version'] = SCHEMA
        return s
