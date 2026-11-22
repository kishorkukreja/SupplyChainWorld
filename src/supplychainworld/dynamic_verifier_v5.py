"""Independent checker for S01 v0.5 episodes (issue #19 fixes, finding 1).

Like the v0.1 to v0.4 verifiers it imports NO simulator, baseline or runner code (an AST test enforces it): the only
package import allowed is the independent v0.4 verifier, whose ledger and rules are unchanged in v0.5 (same
numbers, same rules). It takes plain data and adds the v0.5 checks, none of which trust the simulator:

* the scenario id must be an opaque label (`scn-` and 8 hex characters) and must equal the label this module
  derives ITSELF (own hash code, not the simulator's) from the visible-side scenario parameters, outcome fields
  excluded; a descriptive name such as `s04-warned-delayed-10d` is a violation;
* every recorded state must carry that same label;
* observations shown to an agent are scanned for outcome wording in ANY string before the firm notice, which
  includes the scenario id, tool or notice text, and error reasons, not only the signal text.

Self-reported pass flags are never consulted. All numbers PROVISIONAL, needs practitioner value.
"""
import hashlib
import json

from . import dynamic_verifier_v4 as v4

ScenarioError = v4.ScenarioError
Report = v4.Report
_LABEL_EXCLUDES = ('scenario_id', 'delay_outcome', 'delayed_arrival_day', 'schema_version', 'runtime_version')
# Outcome-class words that must not appear in any agent-visible string before the firm notice.
OUTCOME_WORDS = ('delayed', 'no-delay', 'no delay', 'nodelay', 'not be delayed', 'on-time-confirmed', 'sudden', 'warned',
                 'unwarned', 'multitier', 'alt-cheaper', 'delay_confirmed', 'on_time_confirmed')


def expected_label(scenario):
    """The label this checker derives on its own from the visible-side parameters (outcome fields excluded)."""
    raw = scenario.to_dict() if hasattr(scenario, 'to_dict') else scenario
    visible = {k: v for k, v in raw.items() if k not in _LABEL_EXCLUDES}
    blob = json.dumps(visible, sort_keys=True, separators=(',', ':'))
    return 'scn-' + hashlib.sha256(blob.encode()).hexdigest()[:8]


def _is_opaque(label):
    if not isinstance(label, str) or len(label) != 12 or not label.startswith('scn-'):
        return False
    return all(c in '0123456789abcdef' for c in label[4:])


def verify_episode(scenario, history, *, horizon_days, scorecard=None, actions=None):
    """The v0.4 independent check plus the v0.5 opaque-label checks. Returns the same `Report`."""
    report = v4.verify_episode(scenario, history, horizon_days=horizon_days, scorecard=scorecard, actions=actions)
    raw = scenario.to_dict() if hasattr(scenario, 'to_dict') else scenario
    label, want = raw.get('scenario_id'), expected_label(raw)
    if not _is_opaque(label):
        report.violations.append({'code': 'scenario_id_not_opaque', 'day': None,
                                  'message': 'scenario_id is not an opaque scn-xxxxxxxx label'})
    elif label != want:
        report.violations.append({'code': 'scenario_id_mismatch', 'day': None,
                                  'message': 'scenario_id is not the label derived from the visible parameters'})
    for e in history:
        st = e.get('state') if isinstance(e, dict) else None
        if isinstance(st, dict) and st.get('scenario_id') != label:
            report.violations.append({'code': 'scenario_id_mismatch', 'day': e.get('day'),
                                      'message': 'recorded state carries a different scenario_id'})
            break
    report.feasible = not report.violations
    return report


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def check_observations_for_leaks(scenario, observations):
    """v0.4 scan plus: opaque scenario id on every observation, and no outcome-class wording in any string
    (state, rules, last outcome and error reasons) before the firm notice is visible."""
    raw = scenario.to_dict() if hasattr(scenario, 'to_dict') else scenario
    want = expected_label(raw)
    leaks = []
    try:
        leaks += v4.check_observations_for_leaks(scenario, observations)
    except (KeyError, TypeError, AttributeError, ValueError):
        # An observation the scanner cannot read is never reported as clean.
        leaks.append('observations are malformed: the leak scan could not read them')
    for n, obs in enumerate(observations):
        st = obs.get('state') if isinstance(obs, dict) else None
        if not isinstance(st, dict):
            leaks.append(f'observation {n}: malformed (no state object)')
            continue
        sid = st.get('scenario_id')
        if sid != want or not _is_opaque(sid):
            leaks.append(f'observation {n}: scenario_id is not the opaque label')
        if st.get('notices'):
            continue
        for text in _strings(obs):
            low = text.lower()
            hit = next((w for w in OUTCOME_WORDS if w in low), None)
            if hit:
                leaks.append(f'observation {n}: outcome wording {hit!r} before the firm notice')
                break
    return leaks
