"""Independent checker for S01 supplier-delay episodes (issue #25, DYN04).

The verifier deliberately does NOT import `dynamic.py` or `baselines.py`. It takes
plain data: a scenario mapping (or any dataclass instance, read via `asdict`), the
recorded event history, and optionally a claimed scorecard. It re-derives the
ledger from the *commands* in that history using its own small implementation of
the written business rules (docs/acceptance/dynamic-supplier-delay-v0.1.md), then
compares the claimed record to that ledger. It also runs conservation invariants
directly on the claimed states, so a trace cannot pass merely because it is
internally consistent with a copied transition function.

Never consulted: any self-reported `passed`/`valid`/`verified` field. Such claims
are reported as ignored.

Feasibility and outcome quality are separate. A valid but costlier policy is
feasible; its cost is reported under `outcome`. Metrics that the configured
horizon never observed are `None`, not zero.

This is a synthetic-fixture checker, not a general ERP verifier, and it carries
the same unreviewed business assumptions as the fixture.
"""
from dataclasses import asdict, dataclass, field, is_dataclass

# Own copy of the documented fixture defaults (not read from the simulator).
DEFAULTS = {
    'scenario_id': 's01-five-day', 'schema_version': '1.0', 'runtime_version': '1.0',
    'disruption_enabled': True, 'opening_components': 4, 'order_quantity': 12,
    'daily_capacity': 4, 'order_due_day': 3, 'primary_quantity': 8,
    'initially_promised_day': 2, 'delay_notice_day': 1, 'delayed_arrival_day': 4,
    'recovery_deadline_day': 1, 'expedited_arrival_day': 2, 'alternate_arrival_day': 2,
    'alternate_quantity': 8, 'expedite_cost': 24, 'alternate_cost': 40,
    'recovery_budget': 40, 'daily_backlog_penalty': 10,
}
_INT_FIELDS = ('opening_components', 'order_quantity', 'daily_capacity', 'primary_quantity',
               'alternate_quantity', 'expedite_cost', 'alternate_cost', 'recovery_budget',
               'daily_backlog_penalty')
_DAY_FIELDS = ('order_due_day', 'initially_promised_day', 'delay_notice_day',
               'delayed_arrival_day', 'recovery_deadline_day', 'expedited_arrival_day',
               'alternate_arrival_day')
_COMMANDS = ('recovery', 'release', 'day_close', 'close_day')
_COMPARED = ('receipt', 'notice', 'recovery', 'release', 'day_close', 'close_day',
             'episode_complete')
_STATE_KEYS = ('schema_version', 'scenario_id', 'day', 'phase', 'component_on_hand',
               'finished_on_hand', 'produced_total', 'delivered_total',
               'primary_arrival_day', 'primary_received', 'alternate_arrival_day',
               'alternate_received', 'recovery', 'incremental_spend', 'penalties',
               'scheduled_production', 'horizon_days', 'notices')
_SELF_REPORT_KEYS = ('passed', 'pass', 'valid', 'verified', 'ok', 'checked', 'status')


class ScenarioError(ValueError):
    pass


@dataclass
class Report:
    feasible: bool
    complete: bool
    violations: list = field(default_factory=list)
    ledger: list = field(default_factory=list)       # one row per closed day, derived here
    metrics: dict = field(default_factory=dict)      # observed facts; None means unobserved
    outcome: dict = field(default_factory=dict)      # quality, reported separately
    ignored_self_reports: list = field(default_factory=list)

    def codes(self):
        return sorted({v['code'] for v in self.violations})


def _config(raw):
    """Validate a scenario. Anything malformed surfaces as ScenarioError, never as a bare TypeError or KeyError."""
    try:
        return _config_unchecked(raw)
    except ScenarioError:
        raise
    except (TypeError, KeyError, AttributeError, IndexError) as exc:
        raise ScenarioError(f'malformed scenario: {type(exc).__name__}: {exc}') from exc


def _config_unchecked(raw):
    if is_dataclass(raw) and not isinstance(raw, type):
        raw = asdict(raw)
    if not isinstance(raw, dict):
        raise ScenarioError('scenario must be a mapping')
    unknown = set(raw) - set(DEFAULTS)
    if unknown:
        raise ScenarioError('unknown scenario fields: ' + ', '.join(sorted(unknown)))
    cfg = {**DEFAULTS, **raw}
    if type(cfg['disruption_enabled']) is not bool:
        raise ScenarioError('disruption_enabled must be boolean')
    for key in _INT_FIELDS:
        if type(cfg[key]) is not int or cfg[key] < 0:
            raise ScenarioError(f'{key} must be a nonnegative integer')
    for key in _DAY_FIELDS:
        if type(cfg[key]) is not int or cfg[key] < 1:
            raise ScenarioError(f'{key} must be a positive integer')
    if not cfg['delay_notice_day'] < cfg['initially_promised_day'] < cfg['delayed_arrival_day']:
        raise ScenarioError('notice < promised arrival < delayed arrival required')
    if not cfg['delay_notice_day'] <= cfg['recovery_deadline_day'] < cfg['initially_promised_day']:
        raise ScenarioError('recovery deadline must be in [notice, promised arrival)')
    if not cfg['recovery_deadline_day'] < cfg['expedited_arrival_day'] < cfg['delayed_arrival_day']:
        raise ScenarioError('expedited arrival must follow deadline and precede delayed arrival')
    if not cfg['recovery_deadline_day'] < cfg['alternate_arrival_day']:
        raise ScenarioError('alternate arrival must follow the recovery deadline')
    return cfg


class _Ledger:
    """Own implementation of the written rules, driven only by commands."""

    def __init__(self, cfg, horizon):
        self.c, self.h = cfg, horizon
        self.day = 1
        self.phase = 'action'
        self.comp = cfg['opening_components']
        self.fin = self.produced = self.delivered = 0
        self.primary_day = cfg['initially_promised_day']
        self.primary_in = False
        self.alt_day = None
        self.alt_in = False
        self.recovery = None
        self.spend = self.pen = 0
        self.sched = None
        self.noticed = False
        self.events = []     # expected comparable events
        self.rows = []       # daily ledger rows
        self.receipts = []   # (day, order, qty)
        self.notice_day = None
        self.reset_row()
        self.open_day()

    def reset_row(self):
        self.row_receipts = 0

    def state(self):
        return {'schema_version': self.c['schema_version'], 'scenario_id': self.c['scenario_id'],
                'day': self.day, 'phase': self.phase, 'component_on_hand': self.comp,
                'finished_on_hand': self.fin, 'produced_total': self.produced,
                'delivered_total': self.delivered, 'primary_arrival_day': self.primary_day,
                'primary_received': self.primary_in, 'alternate_arrival_day': self.alt_day,
                'alternate_received': self.alt_in, 'recovery': self.recovery,
                'incremental_spend': self.spend, 'penalties': self.pen,
                'scheduled_production': self.sched, 'horizon_days': self.h,
                'notices': ([f"Primary PO delayed from day {self.c['initially_promised_day']} to day {self.c['delayed_arrival_day']}"]
                            if self.noticed else [])}

    def emit(self, kind, details, accepted=True):
        self.events.append({'day': self.day, 'kind': kind, 'details': details,
                            'accepted': accepted, 'state': self.state()})

    def open_day(self):
        c = self.c
        self.reset_row()
        if not self.primary_in and self.primary_day == self.day:
            self.primary_in = True
            self.comp += c['primary_quantity']
            self.row_receipts += c['primary_quantity']
            self.receipts.append((self.day, 'primary', c['primary_quantity']))
            self.emit('receipt', {'order': 'primary', 'quantity': c['primary_quantity']})
        if self.alt_day is not None and not self.alt_in and self.alt_day == self.day:
            self.alt_in = True
            self.comp += c['alternate_quantity']
            self.row_receipts += c['alternate_quantity']
            self.receipts.append((self.day, 'alternate', c['alternate_quantity']))
            self.emit('receipt', {'order': 'alternate', 'quantity': c['alternate_quantity']})
        self.emit('opening_before_notice', {})
        if c['disruption_enabled'] and self.day == c['delay_notice_day']:
            self.noticed = True
            self.notice_day = self.day
            self.primary_day = c['delayed_arrival_day']
            self.emit('notice', {'original_day': c['initially_promised_day'],
                                 'revised_day': c['delayed_arrival_day']})
        self.emit('day_open', {})

    # Each legality check returns a violation code or None. Order is not significant.
    def check_recovery(self, choice):
        c = self.c
        if self.phase != 'action':
            return 'command_after_complete'
        if not self.noticed:
            return 'premature_recovery'
        if self.day > c['recovery_deadline_day']:
            return 'late_recovery'
        if self.recovery is not None:
            return 'duplicate_commitment'
        cost = {'maintain': 0, 'expedite': c['expedite_cost'], 'alternate': c['alternate_cost']}.get(choice)
        if cost is None:
            return 'unknown_recovery_option'
        if self.spend + cost > c['recovery_budget']:
            return 'budget_exceeded'
        return None

    def check_release(self, qty):
        c = self.c
        if self.phase != 'action':
            return 'command_after_complete'
        if self.sched is not None:
            return 'duplicate_release'
        if type(qty) is not int or qty < 0:
            return 'invalid_quantity'
        if qty > c['daily_capacity']:
            return 'over_capacity'
        if qty > self.comp:
            return 'insufficient_material'
        if self.produced + qty > c['order_quantity']:
            return 'excess_production'
        return None

    def recover(self, choice):
        c = self.c
        self.recovery = choice
        self.spend += {'maintain': 0, 'expedite': c['expedite_cost'], 'alternate': c['alternate_cost']}[choice]
        if choice == 'expedite':
            self.primary_day = c['expedited_arrival_day']
        elif choice == 'alternate':
            self.alt_day = c['alternate_arrival_day']

    def close(self):
        c = self.c
        q = self.sched or 0
        self.comp -= q
        self.fin += q
        self.produced += q
        self.sched = None
        shipped = 0
        assessed = None
        if self.day >= c['order_due_day']:
            shipped = min(self.fin, c['order_quantity'] - self.delivered)
            self.fin -= shipped
            self.delivered += shipped
            assessed = c['order_quantity'] - self.delivered
            self.pen += c['daily_backlog_penalty'] * assessed
        self.rows.append({'day': self.day, 'received': self.row_receipts, 'produced': q,
                          'shipped': shipped, 'components_close': self.comp,
                          'finished_close': self.fin, 'delivered_total': self.delivered,
                          'undelivered_assessed': assessed, 'penalty_total': self.pen,
                          'spend_total': self.spend})
        self.emit('day_close', {'produced': q, 'shipped': shipped})
        if self.day == self.h:
            self.phase = 'complete'
            self.emit('episode_complete', {'comparison_cost': self.spend + self.pen})
        else:
            self.day += 1
            self.open_day()


def _diff(expected, claimed):
    out = []
    claimed = claimed if isinstance(claimed, dict) else {}     # a non-mapping state is a mismatch, not a crash
    for key in _STATE_KEYS:
        if expected.get(key) != (claimed or {}).get(key, '<missing>'):
            out.append(f"state.{key}: expected {expected.get(key)!r}, claimed {(claimed or {}).get(key, '<missing>')!r}")
    return out


def _add(violations, code, day, message):
    violations.append({'code': code, 'day': day, 'message': message})


def _conservation(cfg, claimed, violations):
    """Invariants applied directly to the claimed states, independent of the replay."""
    received = 0
    for ev in claimed:
        st = ev.get('state') if isinstance(ev.get('state'), dict) else None
        if ev.get('kind') == 'receipt' and ev.get('accepted') is True:
            received += (ev.get('details') or {}).get('quantity', 0)
        if st is None or ev.get('kind') not in ('receipt', 'day_close', 'episode_complete'):
            continue
        day = ev.get('day')
        try:
            if st['component_on_hand'] != cfg['opening_components'] + received - st['produced_total']:
                _add(violations, 'component_conservation', day,
                     'components on hand differ from opening + receipts - produced')
            if st['finished_on_hand'] != st['produced_total'] - st['delivered_total']:
                _add(violations, 'finished_goods_conservation', day,
                     'finished goods on hand differ from produced - delivered')
            if st['component_on_hand'] < 0 or st['finished_on_hand'] < 0:
                _add(violations, 'negative_inventory', day, 'negative inventory in claimed state')
            if st['delivered_total'] > cfg['order_quantity'] or st['produced_total'] > cfg['order_quantity']:
                _add(violations, 'order_quantity_exceeded', day, 'production or delivery above customer order')
        except (KeyError, TypeError):
            _add(violations, 'malformed_event', day, 'claimed state lacks required numeric fields')


_OPENING = ('opening_before_notice', 'day_open')


def _check_opening(led, claimed, violations):
    """Opening records must match the ledger's opening states (they were previously not looked at at all)."""
    exp = [e for e in led.events if e['kind'] in _OPENING]
    got = [e for e in claimed if e.get('kind') in _OPENING]
    for i in range(max(len(exp), len(got))):
        if i >= len(got):
            _add(violations, 'missing_event', exp[i]['day'], f"expected {exp[i]['kind']} on day {exp[i]['day']} is absent")
            continue
        if i >= len(exp):
            _add(violations, 'unexpected_event', got[i].get('day'), f"recorded {got[i].get('kind')} has no basis in the ledger")
            continue
        x, y = exp[i], got[i]
        if x['kind'] != y.get('kind') or x['day'] != y.get('day') or y.get('accepted') is not True:
            _add(violations, 'ledger_mismatch', x['day'],
                 f"opening record {i} ({x['kind']}): expected {x['kind']} on day {x['day']}, claimed {y.get('kind')} on day {y.get('day')}")
            continue
        for problem in _diff(x['state'], y.get('state')):
            _add(violations, 'ledger_mismatch', x['day'], f"opening record {i} ({x['kind']}): {problem}")


def _check_order(led, claimed, violations):
    """Records of the compared kinds must appear in the order the ledger produces them (a pure reordering was silent)."""
    known = set(_COMPARED) | set(_OPENING)
    exp = [e['kind'] for e in led.events if e['kind'] in known]
    got = [e.get('kind') for e in claimed if isinstance(e.get('kind'), str) and e.get('kind') in known]
    if exp != got:
        _add(violations, 'ledger_mismatch', None, 'records are out of order compared with the ledger')


def _clean_actions(actions, violations):
    """Keep well-formed action-log entries; report the others instead of crashing on them."""
    clean = []
    for a in actions:
        if isinstance(a, dict) and all(a.get(k) is None or isinstance(a.get(k), dict) for k in ('arguments', 'result')):
            clean.append(a)
        else:
            _add(violations, 'malformed_event', None, 'action log entries must be mappings with mapping arguments and result')
    return clean


def verify_episode(scenario, history, *, horizon_days, scorecard=None, actions=None):
    """Check a recorded episode against the written rules.

    scenario: mapping (or dataclass) of scenario fields; horizon_days: configured horizon.
    history: list of recorded events (dicts with day/kind/details/accepted/state).
    scorecard: optional claimed scorecard to compare with the derived one.
    actions: optional claimed action log; its accepted commands must match history.
    """
    cfg = _config(scenario)
    if type(horizon_days) is not int or horizon_days < 1:
        raise ScenarioError('horizon_days must be a positive integer')
    violations = []
    ignored = []
    claimed = [e for e in history if isinstance(e, dict)]
    if len(claimed) != len(history):
        _add(violations, 'malformed_event', None, 'non-mapping entries in history')
    for i, e in enumerate(claimed):
        if e.get('details') is not None and not isinstance(e.get('details'), dict):
            _add(violations, 'malformed_event', e.get('day'), 'event details must be a mapping')
            claimed[i] = {**e, 'details': {}}
    for e in claimed:
        for key in _SELF_REPORT_KEYS:
            if key in e and key not in ignored:
                ignored.append(key)
    if isinstance(scorecard, dict):
        ignored += [k for k in _SELF_REPORT_KEYS if k in scorecard and k not in ignored]

    led = _Ledger(cfg, horizon_days)
    for e in claimed:
        kind = e.get('kind')
        if kind not in _COMMANDS:
            continue
        day, claim_ok = e.get('day'), e.get('accepted')
        if type(claim_ok) is not bool:
            _add(violations, 'malformed_event', day, f'{kind} lacks boolean accepted flag')
            continue
        if day != led.day and led.phase == 'action':
            _add(violations, 'event_day_mismatch', day, f'{kind} recorded on day {day}, ledger is on day {led.day}')
        details = e.get('details') or {}
        if kind == 'recovery':
            code = led.check_recovery(details.get('choice'))
            if code is None and claim_ok:
                led.recover(details['choice'])
                led.emit('recovery', {'choice': details['choice']}, True)
            else:
                if code is not None and claim_ok:
                    _add(violations, code, day, f'accepted recovery {details.get("choice")!r} violates rule {code}')
                elif code is None and not claim_ok:
                    _add(violations, 'valid_command_rejected', day, 'legal recovery recorded as rejected')
                led.emit('recovery', {'choice': details.get('choice')}, False)
        elif kind == 'release':
            code = led.check_release(details.get('quantity'))
            if code is None and claim_ok:
                led.sched = details['quantity']
                led.emit('release', {'quantity': details['quantity']}, True)
            else:
                if code is not None and claim_ok:
                    _add(violations, code, day, f'accepted release of {details.get("quantity")!r} violates rule {code}')
                elif code is None and not claim_ok:
                    _add(violations, 'valid_command_rejected', day, 'legal release recorded as rejected')
                led.emit('release', {'quantity': details.get('quantity')}, False)
        else:  # a close command, accepted ('day_close') or rejected ('close_day')
            if led.phase != 'action':
                if claim_ok:
                    _add(violations, 'command_after_complete', day, 'day closed after the episode ended')
                led.emit('close_day', {}, False)
            elif kind == 'close_day' and not claim_ok:
                _add(violations, 'valid_command_rejected', day, 'legal day close recorded as rejected')
                led.close()
            else:
                led.close()

    complete = led.phase == 'complete'
    # Compare claimed business events with the ledger's expected ones, in order.
    exp = [e for e in led.events if e['kind'] in _COMPARED]
    got = [e for e in claimed if e.get('kind') in _COMPARED]
    for i in range(max(len(exp), len(got))):
        if i >= len(got):
            x = exp[i]
            _add(violations, 'missing_event', x['day'], f"expected {x['kind']} on day {x['day']} is absent from the record")
            continue
        if i >= len(exp):
            y = got[i]
            _add(violations, 'unexpected_event', y.get('day'), f"recorded {y.get('kind')} has no basis in the ledger")
            continue
        x, y = exp[i], got[i]
        problems = []
        if x['kind'] != y.get('kind'):
            problems.append(f"kind: expected {x['kind']}, claimed {y.get('kind')}")
        else:
            if x['day'] != y.get('day'):
                problems.append(f"day: expected {x['day']}, claimed {y.get('day')}")
            if x['kind'] in ('receipt', 'notice', 'day_close', 'episode_complete') and x['details'] != y.get('details'):
                problems.append(f"details: expected {x['details']}, claimed {y.get('details')}")
            if x['accepted'] != y.get('accepted'):
                problems.append(f"accepted: expected {x['accepted']}, claimed {y.get('accepted')}")
            problems += _diff(x['state'], y.get('state'))
        for p in problems:
            code = 'receipt_timing_or_quantity' if x['kind'] == 'receipt' else 'ledger_mismatch'
            _add(violations, code, x['day'], f"event {i} ({x['kind']}): {p}")
    _conservation(cfg, claimed, violations)
    _check_opening(led, claimed, violations)
    if not violations:
        _check_order(led, claimed, violations)

    # Derived metrics. None means the configured horizon never observed the quantity.
    closed = len(led.rows)
    due = cfg['order_due_day']
    due_row = next((r for r in led.rows if r['day'] == due), None)
    rec = {order: day for day, order, _ in led.receipts}
    metrics = {
        'days_closed': closed, 'horizon_days': horizon_days,
        'notice_day': led.notice_day,                       # None: no notice observed
        'primary_receipt_day': rec.get('primary'),          # None: not received within horizon
        'alternate_receipt_day': rec.get('alternate'),
        'delivered_on_time': due_row['delivered_total'] if due_row else None,
        'due_day_observed': due_row is not None,
        'delivered_total': led.delivered if closed else None,
        'undelivered_at_end': (cfg['order_quantity'] - led.delivered) if closed else None,
        'ending_components': led.comp if closed else None,
        'penalty_assessments': [r['undelivered_assessed'] for r in led.rows if r['undelivered_assessed'] is not None],
    }
    outcome = {
        'incremental_spend': led.spend if closed else None,
        'service_penalties': led.pen if closed else None,
        'comparison_cost': (led.spend + led.pen) if complete else None,
        'recovery': led.recovery,
        'note': 'Quality is reported separately; a feasible episode may still be costly.',
    }
    if isinstance(scorecard, dict):
        if not complete:
            _add(violations, 'scorecard_for_incomplete_episode', None, 'scorecard claimed before episode completed')
        else:
            derived = {'delivered_on_time': metrics['delivered_on_time'],
                       'delivered_total': metrics['delivered_total'],
                       'ending_components': metrics['ending_components'],
                       'incremental_spend': outcome['incremental_spend'],
                       'service_penalties': outcome['service_penalties'],
                       'comparison_cost': outcome['comparison_cost']}
            for key in sorted(set(derived) | (set(scorecard) - set(_SELF_REPORT_KEYS))):
                if derived.get(key, '<absent>') != scorecard.get(key, '<missing>'):
                    _add(violations, 'scorecard_mismatch', None,
                         f"{key}: derived {derived.get(key, '<absent>')!r}, claimed {scorecard.get(key, '<missing>')!r}")
    if actions is not None:
        actions = _clean_actions(actions, violations)
        mine = [(e.get('day'), e['kind'], (e.get('details') or {}).get('choice', (e.get('details') or {}).get('quantity')))
                for e in claimed if e.get('kind') in ('recovery', 'release') and e.get('accepted') is True]
        theirs = [(a.get('day'), a.get('kind'), (a.get('arguments') or {}).get('choice', (a.get('arguments') or {}).get('quantity')))
                  for a in actions if a.get('kind') in ('recovery', 'release') and (a.get('result') or {}).get('accepted') is True]
        if mine != theirs:
            _add(violations, 'action_log_mismatch', None, 'action log and event history disagree on accepted commands')
    return Report(feasible=not violations, complete=complete, violations=violations,
                  ledger=led.rows, metrics=metrics, outcome=outcome, ignored_self_reports=ignored)
