"""Independent checker for S01 v0.3 episodes (issue #36, round 2).

Like `dynamic_verifier.py` (v0.1) and `dynamic_verifier_v2.py` (v0.2), both untouched, this module imports NO simulator, baseline or runner
code (an AST test enforces it). It takes plain data: a scenario mapping, the recorded event history,
optionally a claimed scorecard, and re-derives the whole ledger from the *commands* in the history
with its own implementation of the written rules, then compares claims with that derivation.
It also checks conservation directly on the claimed states and that a possible-delay signal leaks
nothing about the eventual outcome.

Self-reported `passed`/`valid`/`verified` fields are never consulted; they are listed as ignored.
Feasibility and outcome quality are separate; the outcome is reported as separate metric blocks and
is never merged into one ranking number.

Every scenario number is PROVISIONAL, needs practitioner value. This is a synthetic-fixture checker
carrying the same unreviewed business assumptions as the fixtures.
"""
from dataclasses import dataclass, field

_SCENARIO_FIELDS = ('scenario_id', 'opening_components', 'daily_capacity', 'primary_quantity',
                    'primary_promised_day', 'signal_day', 'signal_level', 'notice_day', 'delay_outcome',
                    'delayed_arrival_day', 'base_unit_cost', 'expedite_card', 'alternate_card',
                    'alternate_max_units', 'recovery_budget', 'part_class', 'salvage_pct_by_class', 'tiers', 'orders')
_COMMANDS = ('recovery', 'release', 'day_close', 'close_day')
_COMPARED = ('receipt', 'signal', 'notice', 'recovery', 'release', 'day_close', 'close_day', 'episode_complete')
_SCALARS = ('day', 'phase', 'component_on_hand', 'finished_on_hand', 'produced_total', 'delivered_total',
            'cancelled_total', 'incremental_spend', 'penalties', 'salvage_credit', 'scheduled_production',
            'horizon_days', 'open_demand', 'scenario_id')
_ORDER_KEYS = ('order_id', 'tier', 'quantity', 'due_day', 'delivered', 'cancelled', 'status', 'penalty_total',
               'unit_days_late', 'days_short', 'on_time_units')
_SELF_REPORT_KEYS = ('passed', 'pass', 'valid', 'verified', 'ok', 'checked', 'status')
SIGNAL_TEXT = 'Possible delay on the primary PO (qualitative level, not a commitment)'
SIGNAL_LEVELS = ('low', 'medium', 'high')
LEAK_WORDS = ('delay_confirmed', 'on_time_confirmed', 'revised_day', 'will be delayed', 'will not be delayed',
              'eventual', 'eventual outcome', 'resolves', 'confirmed on time', 'delayed from')


class ScenarioError(ValueError):
    pass


@dataclass
class Report:
    feasible: bool
    complete: bool
    violations: list = field(default_factory=list)
    ledger: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    scorecard: dict = field(default_factory=dict)      # derived, separate blocks
    ignored_self_reports: list = field(default_factory=list)

    def codes(self):
        return sorted({v['code'] for v in self.violations})


def _isint(v, lo=0):
    return type(v) is int and v >= lo


def _config(raw):
    """Validate a scenario. Anything malformed surfaces as ScenarioError, never as a bare TypeError or KeyError."""
    try:
        return _config_unchecked(raw)
    except ScenarioError:
        raise
    except (TypeError, KeyError, AttributeError, IndexError) as exc:
        raise ScenarioError(f'malformed scenario: {type(exc).__name__}: {exc}') from exc


def _config_unchecked(raw):
    if not isinstance(raw, dict):
        if hasattr(raw, 'to_dict'):
            raw = raw.to_dict()
        else:
            raise ScenarioError('scenario must be a mapping')
    raw = {k: v for k, v in raw.items() if k not in ('schema_version', 'runtime_version')}
    unknown = set(raw) - set(_SCENARIO_FIELDS)
    if unknown:
        raise ScenarioError('unknown scenario fields: ' + ', '.join(sorted(unknown)))
    missing = [f for f in _SCENARIO_FIELDS if f not in raw]
    if missing:
        raise ScenarioError('missing scenario fields: ' + ', '.join(missing))
    c = dict(raw)
    for k in ('opening_components', 'daily_capacity', 'primary_quantity', 'alternate_max_units', 'recovery_budget'):
        if not _isint(c[k]):
            raise ScenarioError(f'{k} must be a nonnegative integer')
    if not _isint(c['base_unit_cost'], 1):
        raise ScenarioError('base_unit_cost must be a positive integer')
    sal = c['salvage_pct_by_class']
    if not isinstance(sal, dict) or set(sal) != {'standard', 'custom'} or not all(_isint(v) and v <= 100 for v in sal.values()):
        raise ScenarioError('salvage_pct_by_class needs integer percents for standard and custom')
    if c['part_class'] not in sal:
        raise ScenarioError('part_class must be standard or custom')
    for k in ('primary_promised_day', 'notice_day'):
        if not _isint(c[k], 1):
            raise ScenarioError(f'{k} must be a positive integer')
    if c['signal_day'] is not None and not (_isint(c['signal_day'], 1) and c['signal_day'] < c['notice_day']
                                            and c['signal_level'] in SIGNAL_LEVELS):
        raise ScenarioError('signal must precede the notice and carry a level of low, medium or high')
    if c['signal_day'] is None and c['signal_level'] is not None:
        raise ScenarioError('signal_level requires signal_day')
    if not c['notice_day'] < c['primary_promised_day']:
        raise ScenarioError('notice must precede the promised arrival')
    if c['delay_outcome'] not in ('delay', 'none'):
        raise ScenarioError('delay_outcome must be delay or none')
    if c['delay_outcome'] == 'delay' and not (_isint(c['delayed_arrival_day'], 1)
                                              and c['delayed_arrival_day'] > c['primary_promised_day']):
        raise ScenarioError('delayed arrival must follow the promised arrival')
    for k in ('expedite_card', 'alternate_card'):
        if not isinstance(c[k], list) or not c[k] or any(
                not (isinstance(r, list) and len(r) == 3 and all(_isint(x, 1) for x in r) and r[2] > r[0]) for r in c[k]):
            raise ScenarioError(f'{k} must be rows of [day, premium_pct, arrival_day] with arrival after the day')
        if any(c['base_unit_cost'] * r[1] % 100 for r in c[k]):
            raise ScenarioError(f'{k}: base_unit_cost x premium_pct must be a whole dollar')
    if not isinstance(c['tiers'], list) or not isinstance(c['orders'], list) or not c['orders']:
        raise ScenarioError('tiers and orders must be lists')
    tiers = {}
    for t in c['tiers']:
        if t.get('on_shortfall') not in ('backlog', 'cancel_after') or not _isint(t.get('weight'), 1):
            raise ScenarioError('bad tier')
        if (t['on_shortfall'] == 'cancel_after') != _isint(t.get('cancel_days_after_due')):
            raise ScenarioError('cancel_days_after_due applies to, and is required by, cancel_after tiers only')
        tiers[t['tier']] = t
    for o in c['orders']:
        if o['tier'] not in tiers or o['penalty_type'] not in ('percent_of_value', 'fixed_per_unit', 'per_unit_per_day'):
            raise ScenarioError('bad order')
        if not all(_isint(o[k]) for k in ('quantity', 'due_day', 'unit_value', 'penalty_rate')):
            raise ScenarioError('order numbers must be nonnegative integers')
        if o['penalty_cap_pct'] is not None and not (_isint(o['penalty_cap_pct']) and o['penalty_cap_pct'] <= 100):
            raise ScenarioError('penalty_cap_pct must be None or an integer 0..100')
    c['_tiers'] = tiers
    return c


class _Ledger:
    """Own implementation of the written rules, driven only by commands."""

    def __init__(self, cfg, horizon):
        self.c, self.h = cfg, horizon
        for o in cfg['orders']:
            if o['due_day'] > horizon:
                raise ScenarioError('every order must fall due within the horizon')
        self.day, self.phase = 1, 'action'
        self.comp, self.fin, self.produced, self.delivered, self.cancelled = cfg['opening_components'], 0, 0, 0, 0
        self.lots = [dict(lot_id='primary', source='primary', quantity=cfg['primary_quantity'],
                          arrival_day=cfg['primary_promised_day'], received=False, expedited=False)]
        self.ord = [dict(order_id=o['order_id'], tier=o['tier'], quantity=o['quantity'], due_day=o['due_day'],
                         delivered=0, cancelled=0, status='open', penalty_total=0, unit_days_late=0, days_short=0,
                         on_time_units=None) for o in cfg['orders']]
        self.spend = self.pen = 0
        self.salvage = None
        self.sched = None
        self.commits, self.signals, self.notices = [], [], []
        self.events, self.rows = [], []
        self.row_receipts = 0
        self.open_day()

    # ---- derived views
    def demand(self):
        return sum(o['quantity'] - o['delivered'] - o['cancelled'] for o in self.ord if o['status'] == 'open')

    def alert(self):
        return bool(self.signals or self.notices)

    def state(self):
        return {'day': self.day, 'phase': self.phase, 'component_on_hand': self.comp, 'finished_on_hand': self.fin,
                'produced_total': self.produced, 'delivered_total': self.delivered, 'cancelled_total': self.cancelled,
                'incremental_spend': self.spend, 'penalties': self.pen, 'salvage_credit': self.salvage,
                'scheduled_production': self.sched, 'horizon_days': self.h, 'open_demand': self.demand(),
                'scenario_id': self.c['scenario_id'],
                'lots': [dict(x) for x in self.lots],
                'orders': [{k: o[k] for k in _ORDER_KEYS} for o in self.ord],
                'commitments': [dict(x) for x in self.commits],
                'signals': [dict(x) for x in self.signals], 'notices': [dict(x) for x in self.notices]}

    def emit(self, kind, details, accepted=True):
        self.events.append({'day': self.day, 'kind': kind, 'details': details, 'accepted': accepted,
                            'state': self.state()})

    def open_day(self):
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
            self.signals.append({'day': self.day, 'level': c['signal_level'], 'text': SIGNAL_TEXT})
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

    # ---- offers (price and arrival are read from the rate card for the commit day)
    def offer(self, choice):
        c = self.c
        card = c['expedite_card'] if choice == 'expedite' else c['alternate_card']
        row = next((r for r in card if r[0] == self.day), None)
        if row is None:
            return None
        base = c['base_unit_cost']
        if choice == 'expedite':
            p = self.lots[0]
            if p['received'] or p['expedited'] or p['arrival_day'] <= row[2]:
                return None
            return {'unit': base * row[1] // 100, 'arrival': row[2], 'max': p['quantity']}
        left = c['alternate_max_units'] - sum(x['quantity'] for x in self.commits if x['choice'] == 'alternate')
        return None if left <= 0 else {'unit': base + base * row[1] // 100, 'arrival': row[2], 'max': left}

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
        if cid is not None and (not isinstance(cid, str) or not cid or cid in {x['commit_id'] for x in self.commits}):
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
        choice, qty, cid = d['choice'], d['quantity'], d.get('commit_id')
        o = self.offer(choice)
        ids = {x['commit_id'] for x in self.commits}
        if cid is None:
            n = len(self.commits) + 1
            while f'c{n}' in ids:
                n += 1
            cid = f'c{n}'
        cost = qty * o['unit']
        self.spend += cost
        if choice == 'expedite':
            p = self.lots[0]
            if qty == p['quantity']:
                p['arrival_day'], p['expedited'] = o['arrival'], True
                lot_id = 'primary'
            else:
                p['quantity'] -= qty
                lot_id = 'exp%d' % (sum(1 for x in self.commits if x['choice'] == 'expedite') + 1)
                self.lots.append(dict(lot_id=lot_id, source='primary', quantity=qty, arrival_day=o['arrival'],
                                      received=False, expedited=True))
        else:
            lot_id = 'alt%d' % (sum(1 for x in self.commits if x['choice'] == 'alternate') + 1)
            self.lots.append(dict(lot_id=lot_id, source='alternate', quantity=qty, arrival_day=o['arrival'],
                                  received=False, expedited=False))
        self.commits.append(dict(commit_id=cid, day=self.day, choice=choice, quantity=qty, unit_cost=o['unit'],
                                 cost=cost, arrival_day=o['arrival'], lot_id=lot_id))
        return {'choice': choice, 'quantity': qty, 'commit_id': cid}

    def check_release(self, qty):
        if self.phase != 'action':
            return 'command_after_complete'
        if self.sched is not None:
            return 'duplicate_release'
        if type(qty) is not int or qty < 0:
            return 'invalid_quantity'
        if qty > self.c['daily_capacity']:
            return 'over_capacity'
        if qty > self.comp:
            return 'insufficient_material'
        if qty + self.fin > self.demand():
            return 'excess_production'
        return None

    def close(self):
        c = self.c
        q = self.sched or 0
        self.comp -= q
        self.fin += q
        self.produced += q
        self.sched = None
        ships, pens, cans = {}, {}, {}
        rank = {t: v['weight'] for t, v in c['_tiers'].items()}
        due = [o for o in self.ord if o['status'] == 'open' and self.day >= o['due_day']]
        for o in sorted(due, key=lambda x: (-rank[x['tier']], x['order_id'])):
            s = min(self.fin, o['quantity'] - o['delivered'])
            if s:
                o['delivered'] += s
                self.fin -= s
                self.delivered += s
                ships[o['order_id']] = s
        terms = {o['order_id']: o for o in c['orders']}
        for o in self.ord:
            if o['status'] != 'open' or self.day < o['due_day']:
                continue
            if self.day == o['due_day']:
                o['on_time_units'] = o['delivered']
            short = o['quantity'] - o['delivered']
            if short == 0:
                o['status'] = 'complete'
                continue
            t = terms[o['order_id']]
            if t['penalty_type'] == 'percent_of_value':
                amt = short * t['unit_value'] * t['penalty_rate'] // 10000
            elif t['penalty_type'] == 'fixed_per_unit':
                amt = short * t['penalty_rate'] if self.day == o['due_day'] else 0
            else:
                amt = short * t['penalty_rate']
            if t['penalty_cap_pct'] is not None:
                amt = max(0, min(amt, o['quantity'] * t['unit_value'] * t['penalty_cap_pct'] // 100 - o['penalty_total']))
            o['penalty_total'] += amt
            self.pen += amt
            o['unit_days_late'] += short
            o['days_short'] += 1
            if amt:
                pens[o['order_id']] = amt
            tier = c['_tiers'][o['tier']]
            if tier['on_shortfall'] == 'cancel_after' and self.day == o['due_day'] + tier['cancel_days_after_due']:
                o['cancelled'] += short
                o['status'] = 'cancelled'
                self.cancelled += short
                cans[o['order_id']] = short
        self.rows.append({'day': self.day, 'received': self.row_receipts, 'produced': q, 'shipped': sum(ships.values()),
                          'components_close': self.comp, 'finished_close': self.fin, 'delivered_total': self.delivered,
                          'penalty_total': self.pen, 'spend_total': self.spend, 'cancelled_total': self.cancelled})
        self.emit('day_close', {'produced': q, 'shipped': sum(ships.values()), 'shipments': ships,
                                'penalties': pens, 'cancelled': cans})
        if self.day == self.h:
            self.phase = 'complete'
            self.salvage = self.comp * (c['base_unit_cost'] * c['salvage_pct_by_class'][c['part_class']] // 100)
            self.emit('episode_complete', {'salvage_credit': self.salvage,
                                           'net_cost': self.spend + self.pen - self.salvage})
        else:
            self.day += 1
            self.open_day()

    def derived_scorecard(self):
        c = self.c
        val = {o['order_id']: o['unit_value'] for o in c['orders']}
        wt = {t: v['weight'] for t, v in c['_tiers'].items()}
        orders, tiers = [], {}
        for o in self.ord:
            row = {'order_id': o['order_id'], 'tier': o['tier'], 'ordered': o['quantity'],
                   'otif': o['on_time_units'] == o['quantity'], 'on_time_units': o['on_time_units'],
                   'delivered': o['delivered'], 'cancelled': o['cancelled'], 'unit_days_late': o['unit_days_late'],
                   'days_short': o['days_short'], 'penalty': o['penalty_total']}
            orders.append(row)
            t = tiers.setdefault(o['tier'], dict(orders=0, otif_orders_met=0, ordered=0, on_time_units=0, delivered=0,
                                                 cancelled=0, unit_days_late=0, penalties=0))
            t['orders'] += 1
            t['otif_orders_met'] += 1 if row['otif'] else 0
            t['ordered'] += o['quantity']
            t['on_time_units'] += o['on_time_units']
            t['delivered'] += o['delivered']
            t['cancelled'] += o['cancelled']
            t['unit_days_late'] += o['unit_days_late']
            t['penalties'] += o['penalty_total']
        total = sum(x['quantity'] for x in self.lots)
        prim = sum(x['quantity'] for x in self.lots if x['source'] == 'primary')
        return {
            'schema': 'dyn-scorecard-3',
            'cost': {'recovery_spend': self.spend,
                     'expedite_spend': sum(x['cost'] for x in self.commits if x['choice'] == 'expedite'),
                     'alternate_spend': sum(x['cost'] for x in self.commits if x['choice'] == 'alternate'),
                     'service_penalties': self.pen, 'salvage_credit': self.salvage,
                     'net_cost': self.spend + self.pen - self.salvage},
            'service': {'otif_orders_met': sum(1 for r in orders if r['otif']), 'orders_total': len(orders),
                        'on_time_units': sum(r['on_time_units'] for r in orders),
                        'ordered_units': sum(r['ordered'] for r in orders), 'delivered_total': self.delivered,
                        'cancelled_units': self.cancelled, 'unit_days_late': sum(r['unit_days_late'] for r in orders),
                        'orders': orders},
            'tier_impact': {'by_tier': tiers,
                            'priority_weighted_unit_days_late': sum(wt[r['tier']] * r['unit_days_late'] for r in orders)},
            'downstream': {'cancelled_units': self.cancelled,
                           'cancelled_order_value': sum(r['cancelled'] * val[r['order_id']] for r in orders),
                           'undelivered_at_end': sum(o['quantity'] - o['delivered'] - o['cancelled'] for o in self.ord)},
            'supply_risk': {'ending_components': self.comp,
                            'pending_inbound_units': sum(x['quantity'] for x in self.lots if not x['received']),
                            'ending_cover_days_floor': self.comp // c['daily_capacity'] if c['daily_capacity'] else None,
                            'primary_reliance_pct': 100 * prim // total if total else None,
                            'recovery_commitments': len(self.commits),
                            'unused_recovery_budget': c['recovery_budget'] - self.spend},
            'values_status': 'PROVISIONAL, needs practitioner value; not reviewed by a practitioner'}


def _add(violations, code, day, message):
    violations.append({'code': code, 'day': day, 'message': message})


def _signal_leaks(sig):
    """True when a claimed signal carries anything beyond day, hint and the fixed text."""
    if not isinstance(sig, dict):
        return True
    if set(sig) - {'day', 'level', 'text'}:
        return True
    text = str(sig.get('text', '')).lower()
    return sig.get('text') != SIGNAL_TEXT or any(w in text for w in LEAK_WORDS)


def _diff(expected, claimed, violations, day, label):
    claimed = claimed if isinstance(claimed, dict) else {}
    for key in _SCALARS:
        if expected[key] != claimed.get(key, '<missing>'):
            code = {'penalties': 'penalty_mismatch', 'incremental_spend': 'spend_mismatch'}.get(key, 'ledger_mismatch')
            _add(violations, code, day, f"{label} state.{key}: expected {expected[key]!r}, claimed {claimed.get(key, '<missing>')!r}")
    for key in ('lots', 'commitments', 'notices'):
        if expected[key] != claimed.get(key, '<missing>'):
            _add(violations, 'ledger_mismatch', day, f'{label} state.{key} differs from the ledger')
    if expected['orders'] != [{k: o.get(k) for k in _ORDER_KEYS} for o in claimed.get('orders', []) if isinstance(o, dict)]:
        _add(violations, 'ledger_mismatch', day, f'{label} state.orders differs from the ledger')
    cs = claimed.get('signals', '<missing>')
    if expected['signals'] != cs:
        leak = isinstance(cs, list) and any(_signal_leaks(s) for s in cs)
        _add(violations, 'signal_leak' if leak else 'ledger_mismatch', day, f'{label} state.signals differs from the ledger')


def _conservation(cfg, claimed, violations):
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
                _add(violations, 'component_conservation', day, 'components differ from opening + receipts - produced')
            if st['finished_on_hand'] != st['produced_total'] - st['delivered_total']:
                _add(violations, 'finished_goods_conservation', day, 'finished goods differ from produced - delivered')
            if st['component_on_hand'] < 0 or st['finished_on_hand'] < 0:
                _add(violations, 'negative_inventory', day, 'negative inventory in claimed state')
            if st['delivered_total'] + st['cancelled_total'] > sum(o['quantity'] for o in cfg['orders']):
                _add(violations, 'order_quantity_exceeded', day, 'deliveries and cancellations above customer orders')
        except (KeyError, TypeError):
            _add(violations, 'malformed_event', day, 'claimed state lacks required numeric fields')


def _flat(prefix, node, out):
    if isinstance(node, dict):
        for k, v in node.items():
            _flat(f'{prefix}.{k}', v, out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _flat(f'{prefix}[{i}]', v, out)
    else:
        out[prefix] = node


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
        label = f"opening record {i} ({x['kind']})"
        if x['kind'] != y.get('kind') or x['day'] != y.get('day') or y.get('accepted') is not True:
            _add(violations, 'ledger_mismatch', x['day'],
                 f"{label}: expected {x['kind']} on day {x['day']}, claimed {y.get('kind')} on day {y.get('day')}")
            continue
        before = len(violations)
        _diff(x['state'], y.get('state'), violations, x['day'], label)
        for v in violations[before:]:       # a cascade from an earlier tamper must not add the specific money codes
            if v['code'] in ('penalty_mismatch', 'spend_mismatch'):
                v['code'] = 'ledger_mismatch'


def _check_order(led, claimed, violations):
    """Records of the compared kinds must appear in the order the ledger produces them (a pure reordering was silent)."""
    known = set(_COMPARED) | set(_OPENING)
    exp = [e['kind'] for e in led.events if e['kind'] in known]
    got = [e.get('kind') for e in claimed if isinstance(e.get('kind'), str) and e.get('kind') in known]
    if exp != got:
        _add(violations, 'ledger_mismatch', None, 'records are out of order compared with the ledger')


def _clean_actions(actions, violations):
    """Keep dict entries (a non-mapping `arguments` or `result` counts as empty, so it is not an accepted command);
    report entries that are not mappings at all instead of crashing on them."""
    clean = []
    for a in actions:
        if isinstance(a, dict):
            clean.append({**a, **{k: {} for k in ('arguments', 'result') if a.get(k) is not None and not isinstance(a.get(k), dict)}})
        else:
            _add(violations, 'malformed_event', None, 'action log entries must be mappings')
    return clean


def verify_episode(scenario, history, *, horizon_days, scorecard=None, actions=None):
    """Check a recorded episode against the written rules (see module docstring)."""
    cfg = _config(scenario)
    if type(horizon_days) is not int or horizon_days < 1:
        raise ScenarioError('horizon_days must be a positive integer')
    violations, ignored = [], []
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
            code = led.check_recovery(details)
            if code is None and claim_ok:
                led.emit('recovery', led.recover(details), True)
            else:
                if code is not None and claim_ok:
                    _add(violations, code, day, f'accepted recovery {details!r} violates rule {code}')
                elif code is None and not claim_ok:
                    _add(violations, 'valid_command_rejected', day, 'legal recovery recorded as rejected')
                led.emit('recovery', {k: details.get(k) for k in ('choice', 'quantity', 'commit_id')}, False)
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
        else:
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
    exp = [e for e in led.events if e['kind'] in _COMPARED]
    got = [e for e in claimed if e.get('kind') in _COMPARED]
    for e in got:
        if e.get('kind') == 'signal' and set((e.get('details') or {})) - {'level'}:
            _add(violations, 'signal_leak', e.get('day'), 'signal event carries more than the level')
    for i in range(max(len(exp), len(got))):
        if i >= len(got):
            _add(violations, 'missing_event', exp[i]['day'], f"expected {exp[i]['kind']} on day {exp[i]['day']} is absent")
            continue
        if i >= len(exp):
            _add(violations, 'unexpected_event', got[i].get('day'), f"recorded {got[i].get('kind')} has no basis in the ledger")
            continue
        x, y = exp[i], got[i]
        label = f"event {i} ({x['kind']})"
        if x['kind'] != y.get('kind'):
            _add(violations, 'ledger_mismatch', x['day'], f"{label}: claimed kind {y.get('kind')}")
            continue
        if x['day'] != y.get('day'):
            _add(violations, 'receipt_timing_or_quantity' if x['kind'] == 'receipt' else 'ledger_mismatch', x['day'],
                 f"{label}: expected day {x['day']}, claimed {y.get('day')}")
        if x['kind'] != 'recovery' or x['accepted']:
            if x['kind'] in ('receipt', 'signal', 'notice', 'day_close', 'episode_complete', 'recovery') \
                    and x['details'] != y.get('details'):
                if x['kind'] == 'receipt':
                    code = 'receipt_timing_or_quantity'
                elif x['kind'] == 'day_close' and x['details'].get('penalties') != (y.get('details') or {}).get('penalties'):
                    code = 'penalty_mismatch'
                elif x['kind'] == 'signal':
                    code = 'signal_leak'
                else:
                    code = 'ledger_mismatch'
                _add(violations, code, x['day'], f"{label}: details expected {x['details']}, claimed {y.get('details')}")
        if x['accepted'] != y.get('accepted'):
            _add(violations, 'ledger_mismatch', x['day'], f"{label}: accepted expected {x['accepted']}, claimed {y.get('accepted')}")
        _diff(x['state'], y.get('state'), violations, x['day'], label)
    _conservation(cfg, claimed, violations)
    _check_opening(led, claimed, violations)
    if not violations:
        _check_order(led, claimed, violations)

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
            _add(violations, 'scorecard_for_incomplete_episode', None, 'scorecard claimed before episode completed')
        else:
            a, b = {}, {}
            _flat('scorecard', card, a)
            _flat('scorecard', {k: v for k, v in scorecard.items() if k not in _SELF_REPORT_KEYS}, b)
            for key in sorted(set(a) | set(b)):
                if a.get(key, '<absent>') != b.get(key, '<missing>'):
                    _add(violations, 'scorecard_mismatch', None,
                         f"{key}: derived {a.get(key, '<absent>')!r}, claimed {b.get(key, '<missing>')!r}")
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
        if mine != theirs:
            _add(violations, 'action_log_mismatch', None, 'action log and event history disagree on accepted commands')
    return Report(feasible=not violations, complete=complete, violations=violations, ledger=led.rows,
                  metrics=metrics, scorecard=card, ignored_self_reports=ignored)


def check_observations_for_leaks(scenario, observations):
    """Scan agent-visible observations ({'state','rules'} dicts) for outcome leaks and private keys.

    Returns a list of leak descriptions (empty means none found). Before the firm notice is visible
    an observation must show nothing but the fixed signal template and level and the originally promised
    primary arrival (unless the agent itself expedited), and must contain no hidden-plan fields.
    """
    cfg = _config(scenario)
    hidden = ('delay_outcome', 'delayed_arrival_day', 'signal_day', 'notice_day', 'oracle', 'answer', 'expected',
              'hidden', 'private', 'verifier', 'hand_ledger', 'opening_components')
    leaks = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                if any(h in str(k).lower() for h in hidden):
                    leaks.append(f'forbidden key {k!r} at {path}')
                walk(v, f'{path}.{k}')
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f'{path}[{i}]')

    for n, obs in enumerate(observations):
        walk(obs, f'$[{n}]')
        st = obs.get('state', {})
        if st.get('notices'):
            continue
        for s in st.get('signals', []):
            if _signal_leaks(s) or s.get('level') != cfg['signal_level']:
                leaks.append(f'observation {n}: signal carries more than the fixed level')
        for lot in st.get('lots', []):
            if lot['lot_id'] == 'primary' and not lot['expedited'] and lot['arrival_day'] != cfg['primary_promised_day']:
                leaks.append(f'observation {n}: primary arrival differs from the promised day before the firm notice')
        blob = str({k: v for k, v in obs.items()}).lower()
        for w in LEAK_WORDS:
            if w in blob:
                leaks.append(f'observation {n}: outcome wording {w!r} before the firm notice')
    return leaks
