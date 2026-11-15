"""Pre-expansion split provenance, overlap review, and external private storage."""
from dataclasses import dataclass, asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Literal
from .schemas import Task, World

Split = Literal['train', 'development', 'evaluation']


def _hash(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


@dataclass(frozen=True)
class Assignment:
    lineage: str
    split: Split
    template: str
    source_case: str
    ancestry: tuple[str, ...]


class LineageRegistry:
    """Allocate the whole template/source ancestry before creating any variants.

    Shared source cases, template IDs, or ancestor IDs always share a split.
    Conflicting previously allocated ancestry fails instead of silently moving data.
    """
    def __init__(self, salt='supplychainworld-v1'):
        self.salt = salt
        self._members = {}
        self._assignments = {}
        self._provenance = []

    def assign(self, source_case: str, template: str, ancestry=(), *, split: Split | None = None):
        if not source_case or not template or any(not x for x in ancestry):
            raise ValueError('nonempty source, template and ancestry identifiers required')
        if split is not None and split not in ('train', 'development', 'evaluation'):
            raise ValueError('invalid split')
        # Provenance identifiers share a namespace: an ancestor may name a source
        # or template used by an earlier registration.
        members = tuple(sorted({source_case, template, *ancestry}))
        prior = {self._members[m] for m in members if m in self._members}
        if len(prior) > 1:
            raise ValueError('ancestry joins previously distinct lineages; rebuild manifest before expansion')
        lineage = next(iter(prior), 'lin-' + _hash([self.salt, sorted(members)])[:24])
        existing = self._assignments.get(lineage)
        assigned_split = existing.split if existing else ('train', 'development', 'evaluation')[int(_hash([self.salt, lineage])[:8], 16) % 3]
        if split is not None:
            if existing and existing.split != split:
                raise ValueError('lineage crosses splits')
            assigned_split = split
        result = Assignment(lineage, assigned_split, template, source_case, tuple(sorted(set(ancestry))))
        self._assignments[lineage] = result
        if result not in self._provenance:
            self._provenance.append(result)
        for member in members:
            self._members[member] = lineage
        return result

    def verify(self, task: Task, assignment: Assignment):
        if assignment not in self._provenance or (task.lineage, task.split) != (assignment.lineage, assignment.split):
            raise ValueError('task does not match pre-expansion assignment')
        return True

    def manifest(self):
        return [asdict(a) for a in sorted(self._provenance, key=lambda a: (a.lineage, a.template, a.source_case, a.ancestry))]


def business_fingerprint(world: World, *, structural=False):
    """Ignore IDs, seed, row order, and absolute calendar origin.

    Structural mode also removes magnitudes, retaining constraint presence,
    qualification, missing terms, order-rule activation and relative deadlines.
    Conservative collisions are review flags, not claims of equivalence.
    """
    data = world.model_dump(mode='json')
    origin = world.as_of
    def clean(value, key=''):
        if isinstance(value, dict):
            return {k: clean(v, k) for k, v in value.items()
                    if k not in ('world_id', 'seed', 'item_id', 'supplier_id', 'schema_version', 'visibility', 'as_of')}
        if isinstance(value, list):
            return sorted((clean(v, key) for v in value), key=lambda v: json.dumps(v, sort_keys=True))
        if key.endswith('date') or key in ('valid_from', 'valid_to'):
            from datetime import date
            delta = (date.fromisoformat(value) - origin).days
            return ('past' if delta < 0 else 'today' if delta == 0 else 'future') if structural else delta
        if structural and value is not None and key not in ('qualified', 'status', 'currency', 'calendar', 'unit'):
            try:
                number = float(value)
                return 'zero' if number == 0 else 'one' if number == 1 else 'positive'
            except (TypeError, ValueError):
                pass
        return value
    return _hash(clean(data))


@dataclass(frozen=True)
class OverlapFlag:
    left: str
    right: str
    kind: str
    critical: bool


def overlap_report(records):
    """records: iterable of (Task, World). Semantic flags use request token overlap."""
    records = list(records)
    flags = []
    for i, (left, lw) in enumerate(records):
        for right, rw in records[i + 1:]:
            if left.split == right.split:
                continue
            kind = None
            if left.lineage == right.lineage:
                kind = 'lineage'
            elif business_fingerprint(lw) == business_fingerprint(rw):
                kind = 'exact'
            elif business_fingerprint(lw, structural=True) == business_fingerprint(rw, structural=True):
                kind = 'structural'
            if kind:
                flags.append(OverlapFlag(left.task_id, right.task_id, kind, True))
            else:
                a, b = (set(re.findall(r'[a-z]+', t.request.lower())) for t in (left, right))
                if a and b and len(a & b) / len(a | b) >= .8:
                    flags.append(OverlapFlag(left.task_id, right.task_id, 'semantic', False))
    return flags


@dataclass(frozen=True)
class Adjudication:
    left: str
    right: str
    kind: str
    decision: Literal['allow', 'reject']
    reviewer: str
    reason: str


def require_resolved(flags, adjudications=()):
    for flag in flags:
        matches = [a for a in adjudications if (a.left, a.right, a.kind) == (flag.left, flag.right, flag.kind)]
        if not matches or any(not a.reviewer.strip() or not a.reason.strip() or a.decision != 'allow' for a in matches):
            raise ValueError('unresolved or rejected overlap')
        if flag.critical:
            raise ValueError('critical overlap requires regrouping/reassignment, not an allow override')
    return True


def agent_task_view(task: Task):
    return task.model_dump(mode='json', include={'schema_version', 'task_id', 'family', 'family_version', 'request', 'visible_artifacts', 'permitted_tools', 'restrictions', 'runtime_version', 'policy_version'})


def training_export_allowed(task: Task):
    if task.split != 'train':
        raise ValueError('only training split may enter training export')
    return True


class PrivateStore:
    """Local files outside repository; no private bytes are accepted by public views.

    An OS/process boundary is still needed for adversarial executable adapters.
    """
    def __init__(self, root, repository_root):
        self.root = Path(root).resolve()
        self.repository_root = Path(repository_root).resolve()
        if self.root == self.repository_root or self.repository_root in self.root.parents:
            raise ValueError('private store must be outside public repository')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)

    def _path(self, key):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', key):
            raise ValueError('invalid private record key')
        path = self.root / (key + '.json')
        if path.is_symlink() or path.resolve().parent != self.root or self.repository_root in path.resolve().parents:
            raise ValueError('private record escapes store')
        return path

    def write(self, key, value):
        path = self._path(key)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(value, stream, sort_keys=True)

    def read(self, key):
        descriptor = os.open(self._path(key), os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor) as stream:
            return json.load(stream)
