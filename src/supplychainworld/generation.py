"""Seeded structured procurement worlds; private construction truth stays separate."""
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from hashlib import sha256
import random

from .environment import TOOLS, render_artifacts
from .lineage import LineageRegistry, agent_task_view
from .schemas import World, Task
from .solvers import SolverResult, solve_reference
from .verification import VerificationResult, verify

VARIANTS = ('multi_item', 'inventory', 'timing', 'moq', 'fixed_freight', 'budget', 'concentration', 'excess')
OUTCOMES = ('award', 'clarification', 'infeasible')

class GenerationRejected(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)

@dataclass(frozen=True)
class GenerationTruth:
    reference: SolverResult
    verification: VerificationResult
    provenance: dict
    variation_tags: tuple[str, ...]

@dataclass(frozen=True)
class Candidate:
    world: World
    task: Task
    private: GenerationTruth

    def public_bundle(self):
        if self.task.split != 'train':
            raise ValueError('only training candidates may be publicly bundled')
        return {'world': self.world.model_dump(mode='json'),
                'task': agent_task_view(self.task), 'artifacts': render_artifacts(self.world)}

@dataclass(frozen=True)
class GenerationBatch:
    candidates: tuple[Candidate, ...]
    rejection_counts: dict[str, int]
    attempted: int
    lineage_manifest: tuple[dict, ...] = ()


def generate_candidate(seed, lineage, split, *, variant=None, outcome=None):
    """Generate from a caller's preassigned ancestry; independently verify truth.

    Caller must register the lineage before expansion. Use generate_population for
    managed assignments. No fixture answers or environment-private files are read.
    """
    if type(seed) is not int:
        raise ValueError('seed must be integral')
    if split not in ('train', 'development', 'evaluation'):
        raise ValueError('invalid split')
    rng = random.Random(seed)
    variant = variant or VARIANTS[seed % len(VARIANTS)]
    outcome = outcome or OUTCOMES[seed % len(OUTCOMES)]
    if variant not in VARIANTS or outcome not in OUTCOMES:
        raise ValueError('unsupported variant or outcome')
    identity = sha256(f'{seed}:{lineage}:{split}:{variant}:{outcome}'.encode()).hexdigest()[:20]
    origin = date(2026, 11, 2) + timedelta(days=rng.randrange(20))
    due = origin + timedelta(days=10)
    # Distinct business structures prevent cross-split template copies.
    nitems = {'train': 2, 'development': 3, 'evaluation': 4}[split]
    items, stock, inbound, quotes = [], [], [], []
    for index in range(nitems):
        iid = f'part-{index}'
        need = 2 * rng.randint(1, 2)
        usable = rng.randint(1, 3) if variant == 'inventory' else 0
        committed = 2 if variant == 'timing' else 0
        items.append(dict(item_id=iid, demand=need + usable + committed - (1 if variant == 'excess' else 0),
                          due_date=due, excess_allowance=1 if variant == 'excess' else 0))
        if usable:
            stock.extend([dict(item_id=iid, quantity=usable, status='usable'),
                          dict(item_id=iid, quantity=7, status='held')])
        if committed:
            inbound.extend([dict(item_id=iid, quantity=committed, arrival_date=due),
                            dict(item_id=iid, quantity=9, arrival_date=due + timedelta(days=1))])
        for sid in ('A', 'B', 'C'):
            capacity = need if sid != 'C' else need * 3
            if outcome == 'infeasible' and index == 0:
                capacity = 0 if sid != 'C' else need * 3
            price = rng.randint(2, 7) + (0 if sid == ('A' if index % 2 == 0 else 'B') else 3)
            quotes.append(dict(supplier_id=sid, item_id=iid, unit_price=str(price),
                               variable_freight=str(rng.randint(0, 2)), capacity=capacity,
                               moq=2 if variant in ('moq', 'excess') else 1,
                               multiple=2 if variant in ('moq', 'excess') else 1,
                               qualified=sid != 'C', valid_from=origin - timedelta(days=1),
                               valid_to=due, arrival_date=due if sid != 'C' else due + timedelta(days=1)))
    if outcome == 'clarification':
        quotes[0]['variable_freight'] = None
    world = World(world_id=f'generated-{identity}', seed=seed, currency='USD', as_of=origin,
                  items=items, stock=stock, inbound=inbound,
                  suppliers=[dict(supplier_id=s, fixed_charge=str(rng.randint(1, 8) if variant == 'fixed_freight' else 0)) for s in ('A', 'B', 'C')],
                  quotes=quotes, constraints=dict(budget='10000', concentration_limit='0.75' if variant == 'concentration' else None),
                  visibility={})
    reference = solve_reference(world)
    if variant == 'budget' and reference.status == 'optimal':
        world.constraints.budget = reference.total_cost
        reference = solve_reference(world)
    expected_status = {'award': 'optimal', 'clarification': 'clarification_required', 'infeasible': 'infeasible'}[outcome]
    if reference.status != expected_status:
        raise GenerationRejected('reference_' + reference.status)
    checked = verify(world, reference.submission(), expected_outcome=outcome, reference_cost=reference.total_cost)
    if not checked.accepted:
        raise GenerationRejected('checker_' + '_'.join(checked.critical_failures))
    requests = {
        'train': 'Allocate the factory component basket using quoted costs, stock records and purchasing rules. Recommend the least landed expense or document the supported exception.',
        'development': 'Prepare a sourcing recommendation for assembly requirements. Respect supplier eligibility, delivery deadlines and commercial constraints; minimize total expenditure or escalate with evidence.',
        'evaluation': 'Review this distribution procurement portfolio. Cover dated material needs at minimum delivered cost while satisfying every stated policy, or identify the justified information or capacity exception.'}
    task = Task(task_id=f'task-{identity}', world_id=world.world_id, lineage=lineage, split=split,
                request=requests[split], visible_artifacts=list(render_artifacts(world)), permitted_tools=TOOLS,
                expected_outcome=outcome,
                clarification_policy={reference.clarification_field: 'record_and_escalate'} if reference.clarification_field else {})
    return Candidate(world, task, GenerationTruth(reference, checked,
        {'generator_version': '1.0', 'seed': seed, 'lineage': lineage, 'split': split,
         'template': f'procurement-{nitems}-item', 'source': 'synthetic_structured',
         'intended_outcome': outcome}, (variant, outcome, 'multi_item', 'eligibility', 'capacity')))


def generate_population(count=100, seed=20261102, *, lineage_assignments=None, max_attempts_per_candidate=3):
    """Preassign three disjoint structural families, then expand bounded variants.

    Optional assignments must map all three split names to lineage.Assignment.
    Repairs never alter intended outcome/variant; retries use fresh seeds.
    """
    if type(count) is not int or count < 0 or type(max_attempts_per_candidate) is not int or max_attempts_per_candidate < 1:
        raise ValueError('nonnegative count and positive retry cap required')
    registry = LineageRegistry()
    splits = ('train', 'development', 'evaluation')
    assignments = lineage_assignments or {s: registry.assign(f'synthetic-{s}', f'procurement-{i + 2}-item', split=s) for i, s in enumerate(splits)}
    if set(assignments) != set(splits) or any(assignments[s].split != s for s in splits):
        raise ValueError('assignments must cover matching splits')
    ancestry_registry = LineageRegistry()
    for split in splits:
        assignment = assignments[split]
        ancestry_registry.assign(assignment.source_case, assignment.template, assignment.ancestry, split=split)
    if len({a.lineage for a in assignments.values()}) != 3:
        raise ValueError('lineage crosses splits')
    accepted, rejected, attempted = [], Counter(), 0
    for index in range(count):
        split = 'train' if index % 10 < 6 else 'development' if index % 10 < 8 else 'evaluation'
        assignment = assignments[split]
        for retry in range(max_attempts_per_candidate):
            attempted += 1
            try:
                candidate = generate_candidate(seed + index + retry * max(1, count), assignment.lineage, split,
                    variant=VARIANTS[index % len(VARIANTS)], outcome=OUTCOMES[(index // 2) % len(OUTCOMES)])
                accepted.append(candidate)
                break
            except GenerationRejected as exc:
                rejected[exc.reason] += 1
    manifest = tuple(vars(assignments[s]).copy() for s in splits)
    return GenerationBatch(tuple(accepted), dict(rejected), attempted, manifest)
