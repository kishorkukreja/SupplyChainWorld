"""Independent checker for S01 v0.6 episodes (issue #19, audit follow-up).

Like the v0.1 to v0.5 checkers this module imports NO simulator, baseline or runner code (an AST test enforces it).
The only package imports allowed are the earlier independent checkers (v0.4 for the ledger and scoring rules,
v0.5 for the opaque-label and leak checks). It takes plain data and never trusts a self-reported pass flag.

The v0.4 and v0.5 checkers could not be edited (the first diagnostic run's manifest freezes `dynamic_verifier_v4.py`),
so five defects the S01 audit found (D2 to D6, evidence/s01-audit/results.md) stayed open there. This module fixes
them without touching those files:

* D2 opening records. The `opening_before_notice` and `day_open` records of every day are checked against the
  ledger the checker derives itself, in the right order; a forged, deleted, duplicated or moved opening record is a
  violation, and so is any pure reordering of the known record kinds.
* D3 the FULL recorded state is compared, key by key and type by type (`True` is not `1`), not a part of it. A state
  with a missing, extra or altered key, including the schema and runtime version fields, is a violation.
* D4 a record whose `details` or `state` is not a mapping is reported as malformed; it never crashes the checker.
* D5 a malformed scenario (orders, tiers, rate cards, version fields) raises the documented `ScenarioError`, never a
  bare TypeError or KeyError.
* D6 a malformed action log (entries that are not mappings, or whose arguments or result are not mappings) is
  reported as malformed, never a crash.

Exact-once (S01.4): a recovery recorded with the reserved `auto-` key must carry exactly the key derived from its day,
choice and quantity, and must not repeat an identical purchase made earlier the same day under any id; two accepted
records with the same id are a duplicate commitment; an explicit id may not use the reserved prefix.

If an unexpected error still escapes while reading a recorded history, the history is reported as malformed
(`malformed_event`, message `unreadable record`) and counted in `metrics['unreadable_guard']`: the checker never
returns feasible for something it could not read. All numbers PROVISIONAL, needs practitioner value.
"""
import hashlib

from . import dynamic_verifier_v4 as v4
from . import dynamic_verifier_v5 as v5

SCHEMA = '6.0'
SCORECARD_SCHEMA = 'dyn-scorecard-6'
AUTO_PREFIX = 'auto-'
ScenarioError = v4.ScenarioError
Report = v4.Report
OUTCOME_WORDS = v5.OUTCOME_WORDS
expected_label = v5.expected_label
_OPENING = ('opening_before_notice', 'day_open')
_COMPARED = v4._COMPARED
_KNOWN = tuple(_COMPARED) + _OPENING
_COMMANDS = v4._COMMANDS
_SELF_REPORT_KEYS = v4._SELF_REPORT_KEYS
_STATE_KEYS = ('schema_version', 'runtime_version', 'scenario_id', 'day', 'horizon_days', 'phase', 'component_on_hand',
               'finished_on_hand', 'produced_total', 'delivered_total', 'cancelled_total', 'lots', 'orders',
               'incremental_spend', 'penalties', 'salvage_credit', 'scheduled_production', 'commitments', 'signals',
               'notices', 'open_demand')
_ORDER_KEYS = ('order_id', 'tier', 'quantity', 'due_day', 'delivered', 'cancelled', 'status', 'penalty_total',
               'unit_days_late', 'days_short', 'on_time_units')
_TIER_FIELDS = {'tier', 'weight', 'on_shortfall', 'cancel_days_after_due'}
_ORDER_FIELDS = {'order_id', 'tier', 'quantity', 'due_day', 'unit_value', 'penalty_type', 'penalty_rate',
                 'penalty_cap_pct'}


def derived_key(day, choice, quantity):
    """The key an id-less commitment must carry (own implementation of the written rule)."""
    return AUTO_PREFIX + hashlib.sha256(f'{day}|{choice}|{quantity}'.encode()).hexdigest()[:8]


def same(a, b):
    """Strict deep equality: same types all the way down (`True` is not `1`, `1.0` is not `1`)."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


# ------------------------------------------------------------------ scenario (D5)

def _config(raw):
    """Validate a scenario; every kind of malformed input surfaces as ScenarioError."""
    if not isinstance(raw, dict):
        raw = raw.to_dict() if hasattr(raw, 'to_dict') else raw
    if not isinstance(raw, dict):
        raise ScenarioError('scenario must be a mapping')
    for k in ('schema_version', 'runtime_version'):
        if k in raw and raw[k] != SCHEMA:
            raise ScenarioError(f'{k} must be {SCHEMA} for a v0.6 scenario')
    try:
        cfg = v4._config(raw)
        _structure(cfg)
        return cfg
    except ScenarioError:
        raise
    except (TypeError, KeyError, AttributeError, IndexError, ValueError, OverflowError, RecursionError) as exc:
        raise ScenarioError(f'malformed scenario: {type(exc).__name__}: {exc}') from exc


def _structure(cfg):
    """Structural rules the v0.4 validator leaves to the ledger (exact fields, unique ids and tier names)."""
    if not isinstance(cfg['scenario_id'], str) or not cfg['scenario_id']:
        raise ScenarioError('scenario_id must be a nonempty string')
    names = set()
    for t in cfg['tiers']:
        if set(t) != _TIER_FIELDS or not isinstance(t['tier'], str) or t['tier'] in names:
            raise ScenarioError('tiers need exactly tier, weight, on_shortfall, cancel_days_after_due and unique names')
        names.add(t['tier'])
    ids = set()
    for o in cfg['orders']:
        if set(o) != _ORDER_FIELDS or not isinstance(o['order_id'], str) or o['order_id'] in ids:
            raise ScenarioError('orders need exactly their fields and unique string order ids')
        ids.add(o['order_id'])
        if o['quantity'] < 1 or o['due_day'] < 1:
            raise ScenarioError('order quantity and due_day must be at least 1')
        if o['penalty_type'] == 'percent_of_value' and o['penalty_rate'] > 10000:
            raise ScenarioError('percent_of_value penalty_rate is in basis points and must be at most 10000')
    for k in ('expedite_card', 'alternate_card'):
        days = [r[0] for r in cfg[k]]
        if len(days) != len(set(days)):
            raise ScenarioError(f'{k}: commit days must be unique')
    if cfg['delay_outcome'] == 'none' and cfg['delayed_arrival_day'] is not None:
        raise ScenarioError('delayed_arrival_day must be None when there is no delay')


# ------------------------------------------------------------------ ledger

class _LedgerV6(v4._Ledger):
    """The v0.4 ledger with the full state, the opening records and the v0.6 exact-once rule."""

    def state(self):
        c = self.c
        return {'schema_version': SCHEMA, 'runtime_version': SCHEMA, 'scenario_id': c['scenario_id'], 'day': self.day,
                'horizon_days': self.h, 'phase': self.phase, 'component_on_hand': self.comp,
                'finished_on_hand': self.fin, 'produced_total': self.produced, 'delivered_total': self.delivered,
                'cancelled_total': self.cancelled, 'lots': [dict(x) for x in self.lots],
                'orders': [{k: o[k] for k in _ORDER_KEYS} for o in self.ord],
                'incremental_spend': self.spend, 'penalties': self.pen, 'salvage_credit': self.salvage,
                'scheduled_production': self.sched, 'commitments': [dict(x) for x in self.commits],
                'signals': [dict(x) for x in self.signals], 'notices': [dict(x) for x in self.notices],
                'open_demand': self.demand()}

    def open_day(self):
        """v0.4 opening plus the two opening records the simulator writes (before the signal and notice, and after)."""
        c = self.c
        self.row_receipts = 0
        for lot in self.lots:
            if not lot['received'] and lot['arrival_day'] == self.day:
                lot['received'] = True
                self.comp += lot['quantity']
                self.row_receipts += lot['quantity']
                self.emit('receipt', {'lot': lot['lot_id'], 'source': lot['source'], 'quantity': lot['quantity']})
        self.emit('opening_before_notice', {})
        if c['signal_day'] == self.day:
            self.signals.append({'day': self.day, 'level': c['signal_level'], 'text': v4.SIGNAL_TEXT})
            self.emit('signal', {'level': c['signal_level']})
        if c['notice_day'] == self.day:
            if c['delay_outcome'] == 'delay':
                p = self.lots[0]
                if p['lot_id'] == 'primary' and not p['received'] and not p['expedited']:
                    p['arrival_day'] = c['delayed_arrival_day']
                d = {'kind': 'delay_confirmed', 'original_day': c['primary_promised_day'],
                     'revised_day': c['delayed_arrival_day']}
                text = f"Primary PO delayed from day {d['original_day']} to day {d['revised_day']}"
            else:
                d = {'kind': 'on_time_confirmed', 'promised_day': c['primary_promised_day']}
                text = f"Primary PO confirmed on time for day {d['promised_day']}"
            self.notices.append({'day': self.day, **d, 'text': text})
            self.emit('notice', d)
        self.emit('day_open', {})

    def check_recovery(self, d):
        choice, qty, cid = d.get('choice'), d.get('quantity'), d.get('commit_id')
        if self.phase != 'action':
            return 'command_after_complete'
        if not self.alert():
            return 'premature_recovery'
        if choice not in ('expedite', 'alternate'):
            return 'unknown_recovery_option'
        if type(qty) is not int or qty < 1:
            return 'invalid_quantity'
        ids = {x['commit_id'] for x in self.commits}
        if cid is not None and (not isinstance(cid, str) or not cid or cid in ids):
            return 'duplicate_commitment'
        key = derived_key(self.day, choice, qty)
        repeats_today = any(x['day'] == self.day and x['choice'] == choice and x['quantity'] == qty
                            for x in self.commits)
        if cid is None:
            if repeats_today or key in ids:
                return 'duplicate_commitment'
        elif cid.startswith(AUTO_PREFIX):
            # The reserved prefix: only the key derived from this very purchase may carry it, and only once.
            if cid != key or repeats_today:
                return 'duplicate_commitment'
        o = self.offer(choice)
        if o is None:
            return 'recovery_window_closed'
        if qty > o['max']:
            return 'expedite_exceeds_units' if choice == 'expedite' else 'alternate_exceeds_availability'
        if self.spend + qty * o['unit'] > self.c['recovery_budget']:
            return 'budget_exceeded'
        return None

    def recover(self, d):
        d = dict(d)
        if d.get('commit_id') is None:
            d['commit_id'] = derived_key(self.day, d['choice'], d['quantity'])
        return super().recover(d)

    def derived_scorecard(self):
        card = super().derived_scorecard()
        card['schema'] = SCORECARD_SCHEMA
        return card


# ------------------------------------------------------------------ comparison helpers

_CODE = {'penalties': 'penalty_mismatch', 'incremental_spend': 'spend_mismatch'}


def _signal_leak(sig):
    return v4._signal_leaks(sig)


def _diff_state(expected, claimed, violations, day, label, plain=False):
    """Compare the FULL claimed state with the ledger's. `plain` keeps money mismatches under the generic code
    (an opening record that disagrees is a cascade, not a separate money error)."""
    if not isinstance(claimed, dict):
        v4._add(violations, 'malformed_event', day, f'{label}: state is not a mapping')
        return
    for key in _STATE_KEYS:
        if key not in claimed:
            v4._add(violations, 'ledger_mismatch', day, f'{label} state.{key} is missing')
        elif not same(expected[key], claimed[key]):
            if key == 'signals':
                leak = isinstance(claimed[key], list) and any(_signal_leak(s) for s in claimed[key])
                code = 'signal_leak' if leak else 'ledger_mismatch'
            else:
                code = 'ledger_mismatch' if plain else _CODE.get(key, 'ledger_mismatch')
            v4._add(violations, code, day, f'{label} state.{key}: expected {expected[key]!r}, claimed {claimed[key]!r}')
    extra = sorted(str(k) for k in claimed if k not in _STATE_KEYS)
    if extra:
        v4._add(violations, 'ledger_mismatch', day, f'{label} state has unknown keys: ' + ', '.join(extra))


def _clean_history(history, violations):
    """A list of mapping records; details and state that are not mappings are reported, not crashed on (D4)."""
    if not isinstance(history, list):
        v4._add(violations, 'malformed_event', None, 'history must be a list of records')
        return []
    claimed = [e for e in history if isinstance(e, dict)]
    if len(claimed) != len(history):
        v4._add(violations, 'malformed_event', None, 'non-mapping entries in history')
    out = []
    for e in claimed:
        e = dict(e)
        if e.get('details') is not None and not isinstance(e.get('details'), dict):
            v4._add(violations, 'malformed_event', e.get('day'), 'event details must be a mapping')
            e['details'] = {}
        if 'state' in e and not isinstance(e['state'], dict):
            v4._add(violations, 'malformed_event', e.get('day'), 'event state must be a mapping')
            e['state'] = {}
        out.append(e)
    return out


def _clean_actions(actions, violations):
    """Keep well-formed action-log entries; report the others (D6)."""
    if not isinstance(actions, list):
        v4._add(violations, 'malformed_event', None, 'action log must be a list')
        return []
    clean = []
    for a in actions:
        if isinstance(a, dict) and all(a.get(k) is None or isinstance(a.get(k), dict) for k in ('arguments', 'result')):
            clean.append(a)
        else:
            v4._add(violations, 'malformed_event', None,
                    'action log entries must be mappings with mapping arguments and result')
    return clean


def _conservation(cfg, claimed, violations):
    """v0.4 conservation checks, tolerant of non-numeric fields."""
    received = 0
    for ev in claimed:
        st = ev.get('state') if isinstance(ev.get('state'), dict) else None
        if ev.get('kind') == 'receipt' and ev.get('accepted') is True:
            q = (ev.get('details') or {}).get('quantity', 0)
            received += q if type(q) is int else 0
        if st is None or ev.get('kind') not in ('receipt', 'day_close', 'episode_complete'):
            continue
        day = ev.get('day')
        try:
            if st['component_on_hand'] != cfg['opening_components'] + received - st['produced_total']:
                v4._add(violations, 'component_conservation', day, 'components differ from opening + receipts - produced')
            if st['finished_on_hand'] != st['produced_total'] - st['delivered_total']:
                v4._add(violations, 'finished_goods_conservation', day, 'finished goods differ from produced - delivered')
            if st['component_on_hand'] < 0 or st['finished_on_hand'] < 0:
                v4._add(violations, 'negative_inventory', day, 'negative inventory in claimed state')
            if st['delivered_total'] + st['cancelled_total'] > sum(o['quantity'] for o in cfg['orders']):
                v4._add(violations, 'order_quantity_exceeded', day, 'deliveries and cancellations above customer orders')
        except (KeyError, TypeError):
            v4._add(violations, 'malformed_event', day, 'claimed state lacks required numeric fields')


# ------------------------------------------------------------------ the check

def verify_episode(scenario, history, *, horizon_days, scorecard=None, actions=None):
    """Check a recorded episode against the written rules (see module docstring). Returns the v0.4 `Report`."""
    cfg = _config(scenario)
    if type(horizon_days) is not int or horizon_days < 1:
        raise ScenarioError('horizon_days must be a positive integer')
    if any(o['due_day'] > horizon_days for o in cfg['orders']):
        raise ScenarioError('every order must fall due within the horizon')
    violations = []
    raw = scenario if isinstance(scenario, dict) else scenario.to_dict()
    label, want = raw.get('scenario_id'), expected_label(raw)
    if not v5._is_opaque(label):
        violations.append({'code': 'scenario_id_not_opaque', 'day': None,
                           'message': 'scenario_id is not an opaque scn-xxxxxxxx label'})
    elif label != want:
        violations.append({'code': 'scenario_id_mismatch', 'day': None,
                           'message': 'scenario_id is not the label derived from the visible parameters'})
    try:
        return _check(cfg, history, horizon_days, scorecard, actions, violations)
    except ScenarioError:
        raise
    except Exception as exc:  # noqa: BLE001 - anything unreadable is a rejection, never a crash and never feasible
        violations.append({'code': 'malformed_event', 'day': None,
                           'message': f'unreadable record: {type(exc).__name__}'})
        return Report(feasible=False, complete=False, violations=violations, ledger=[],
                      metrics={'unreadable_guard': True}, scorecard={}, ignored_self_reports=[])


def _check(cfg, history, horizon_days, scorecard, actions, violations):
    ignored = []
    claimed = _clean_history(history, violations)
    for e in claimed:
        for key in _SELF_REPORT_KEYS:
            if key in e and key not in ignored:
                ignored.append(key)
    if isinstance(scorecard, dict):
        ignored += [k for k in _SELF_REPORT_KEYS if k in scorecard and k not in ignored]

    led = _LedgerV6(cfg, horizon_days)
    for e in claimed:
        kind = e.get('kind')
        if kind not in _COMMANDS:
            continue
        day, claim_ok = e.get('day'), e.get('accepted')
        if type(claim_ok) is not bool:
            v4._add(violations, 'malformed_event', day, f'{kind} lacks boolean accepted flag')
            continue
        if day != led.day and led.phase == 'action':
            v4._add(violations, 'event_day_mismatch', day, f'{kind} recorded on day {day}, ledger is on day {led.day}')
        details = e.get('details') or {}
        if kind == 'recovery':
            code = led.check_recovery(details)
            if code is None and claim_ok:
                led.emit('recovery', led.recover(details), True)
            else:
                if code is not None and claim_ok:
                    v4._add(violations, code, day, f'accepted recovery {details!r} violates rule {code}')
                elif code is None and not claim_ok:
                    v4._add(violations, 'valid_command_rejected', day, 'legal recovery recorded as rejected')
                led.emit('recovery', {k: details.get(k) for k in ('choice', 'quantity', 'commit_id')}, False)
        elif kind == 'release':
            code = led.check_release(details.get('quantity'))
            if code is None and claim_ok:
                led.sched = details['quantity']
                led.emit('release', {'quantity': details['quantity']}, True)
            else:
                if code is not None and claim_ok:
                    v4._add(violations, code, day, f'accepted release of {details.get("quantity")!r} violates rule {code}')
                elif code is None and not claim_ok:
                    v4._add(violations, 'valid_command_rejected', day, 'legal release recorded as rejected')
                led.emit('release', {'quantity': details.get('quantity')}, False)
        else:
            if led.phase != 'action':
                if claim_ok:
                    v4._add(violations, 'command_after_complete', day, 'day closed after the episode ended')
                led.emit('close_day', {}, False)
            elif kind == 'close_day' and not claim_ok:
                v4._add(violations, 'valid_command_rejected', day, 'legal day close recorded as rejected')
                led.close()
            else:
                led.close()

    complete = led.phase == 'complete'
    exp = [e for e in led.events if e['kind'] in _KNOWN]
    got = [e for e in claimed if isinstance(e.get('kind'), str) and e['kind'] in _KNOWN]
    for e in got:
        if e.get('kind') == 'signal' and set(e.get('details') or {}) - {'level'}:
            v4._add(violations, 'signal_leak', e.get('day'), 'signal event carries more than the level')
    for i in range(max(len(exp), len(got))):
        if i >= len(got):
            v4._add(violations, 'missing_event', exp[i]['day'], f"expected {exp[i]['kind']} on day {exp[i]['day']} is absent")
            continue
        if i >= len(exp):
            v4._add(violations, 'unexpected_event', got[i].get('day'), f"recorded {got[i].get('kind')} has no basis in the ledger")
            continue
        x, y = exp[i], got[i]
        label = f"event {i} ({x['kind']})"
        opening = x['kind'] in _OPENING
        if x['kind'] != y.get('kind'):
            v4._add(violations, 'ledger_mismatch', x['day'], f"{label}: claimed kind {y.get('kind')}")
            continue
        if not same(x['day'], y.get('day')):
            v4._add(violations, 'receipt_timing_or_quantity' if x['kind'] == 'receipt' else 'ledger_mismatch', x['day'],
                    f"{label}: expected day {x['day']}, claimed {y.get('day')}")
        if x['kind'] != 'recovery' or x['accepted']:
            if not same(x['details'], y.get('details') if y.get('details') is not None else {}):
                if x['kind'] == 'receipt':
                    code = 'receipt_timing_or_quantity'
                elif x['kind'] == 'day_close' and not same(x['details'].get('penalties'),
                                                           (y.get('details') or {}).get('penalties')):
                    code = 'penalty_mismatch'
                elif x['kind'] == 'signal':
                    code = 'signal_leak'
                else:
                    code = 'ledger_mismatch'
                v4._add(violations, code, x['day'], f"{label}: details expected {x['details']}, claimed {y.get('details')}")
        if not same(x['accepted'], y.get('accepted')):
            v4._add(violations, 'ledger_mismatch', x['day'], f"{label}: accepted expected {x['accepted']}, claimed {y.get('accepted')}")
        if x['accepted'] and y.get('reason') is not None:
            v4._add(violations, 'ledger_mismatch', x['day'], f"{label}: an accepted record carries a reason")
        _diff_state(x['state'], y.get('state'), violations, x['day'], label, plain=opening)
    _conservation(cfg, claimed, violations)

    closed = len(led.rows)
    due_days = {o['order_id']: o['due_day'] for o in cfg['orders']}
    metrics = {'days_closed': closed, 'horizon_days': horizon_days,
               'signal_day': next((s['day'] for s in led.signals), None),
               'firm_notice_day': next((n['day'] for n in led.notices), None),
               'receipt_days': {x['lot_id']: x['arrival_day'] for x in led.lots if x['received']},
               'commitments': [dict(x) for x in led.commits], 'due_days': due_days}
    card = led.derived_scorecard() if complete else {}
    if isinstance(scorecard, dict):
        if not complete:
            v4._add(violations, 'scorecard_for_incomplete_episode', None, 'scorecard claimed before episode completed')
        else:
            a, b = {}, {}
            v4._flat('scorecard', card, a)
            v4._flat('scorecard', {k: v for k, v in scorecard.items() if k not in _SELF_REPORT_KEYS}, b)
            for key in sorted(set(a) | set(b)):
                if not same(a.get(key, '<absent>'), b.get(key, '<missing>')):
                    v4._add(violations, 'scorecard_mismatch', None,
                            f"{key}: derived {a.get(key, '<absent>')!r}, claimed {b.get(key, '<missing>')!r}")
    elif scorecard is not None:
        v4._add(violations, 'malformed_event', None, 'scorecard must be a mapping')
    if actions is not None:
        actions = _clean_actions(actions, violations)
        pick = lambda d: (d.get('choice'), d.get('quantity'), d.get('commit_id')) if 'choice' in d else d.get('quantity')  # noqa: E731
        mine = [(e.get('day'), e['kind'], pick(e.get('details') or {})) for e in claimed
                if e.get('kind') in ('recovery', 'release') and e.get('accepted') is True]
        theirs = []
        for a in actions:
            if a.get('kind') in ('recovery', 'release') and (a.get('result') or {}).get('accepted') is True:
                arg = a.get('arguments') or {}
                if a['kind'] == 'recovery':
                    theirs.append((a.get('day'), 'recovery', (arg.get('choice'), arg.get('quantity'),
                                                              (a.get('result') or {}).get('commit_id'))))
                else:
                    theirs.append((a.get('day'), 'release', arg.get('quantity')))
        if not same(mine, theirs):
            v4._add(violations, 'action_log_mismatch', None, 'action log and event history disagree on accepted commands')
    return Report(feasible=not violations, complete=complete, violations=violations, ledger=led.rows,
                  metrics=metrics, scorecard=card, ignored_self_reports=ignored)


def check_observations_for_leaks(scenario, observations):
    """The v0.5 scan (opaque id, private keys, outcome wording before the firm notice) over every observation; an
    observation that cannot be read is reported, never passed. Scenario malformations raise ScenarioError."""
    try:
        return v5.check_observations_for_leaks(scenario, observations)
    except ScenarioError:
        raise
    except Exception:  # noqa: BLE001
        return ['observations are malformed: the leak scan could not read them']
