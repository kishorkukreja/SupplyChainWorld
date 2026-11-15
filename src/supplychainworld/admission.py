"""Fail-closed replay admission and train-only observable-message export."""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Callable
from .schemas import World, Task, Trajectory
from .environment import ProcurementEnvironment
from .verification import verify
from .lineage import overlap_report, require_resolved


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


@dataclass
class AdmissionResult:
    accepted: bool
    reasons: list[str]
    diagnosis: str
    record: dict | None
    task: Task
    world: World
    trajectory_hash: str
    record_hash: str | None = None
    trajectory: Trajectory | None = None
    split_assignments: dict | None = None


def admit(world: World, task: Task, trajectory: Trajectory, *, split_assignments: dict[str, str]) -> AdmissionResult:
    """Never trust a caller-supplied verification verdict or logged observation."""
    world = World.model_validate(world)
    task = Task.model_validate(task)
    trajectory = Trajectory.model_validate(trajectory)
    thash = digest(trajectory.model_dump(mode='json'))
    reasons = []
    if split_assignments.get(task.lineage) != task.split:
        reasons.append('split_assignment')
    if trajectory.task_id != task.task_id:
        reasons.append('task_identity')
    env = ProcurementEnvironment(world, task)
    initial = env.observe()
    observations = [initial]
    if trajectory.artifact_hashes != initial['artifacts']:
        reasons.append('artifact_hashes')
    for action, expected in zip(trajectory.actions, trajectory.results):
        actual = env.step(action)
        observations.append(env.observe())
        if actual.model_dump(mode='json') != expected.model_dump(mode='json'):
            reasons.append('replay_divergence')
            break
    if trajectory.observations != observations:
        reasons.append('observations_mismatch')
    submitted = trajectory.final_submission.model_dump(mode='json')
    if trajectory.termination_reason != 'submitted' or env.submission != submitted:
        reasons.append('terminal_submission')
    checked = verify(world, submitted, expected_outcome=task.expected_outcome)
    if not checked.accepted:
        reasons.append('agent_error:' + ','.join(checked.critical_failures))
    # Messages are rebuilt from trusted environment data after exact replay.
    messages = [{'role': 'user', 'content': canonical(initial), 'loss': False}]
    for action, result in zip(trajectory.actions, trajectory.results):
        messages.append({'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': action.request_id, 'type': 'function', 'function': {
                'name': action.tool_name, 'arguments': canonical(action.arguments)}}], 'loss': True})
        messages.append({'role': 'tool', 'tool_call_id': action.request_id,
                         'content': canonical(result.model_dump(mode='json')), 'loss': False})
    record = None
    if not reasons and task.split == 'train':
        record = {'messages': messages, 'provenance': {
            'task_id': task.task_id, 'lineage': task.lineage, 'split': task.split,
            'trajectory_hash': thash, 'world_hash': digest(world.model_dump(mode='json')),
            'task_hash': digest(task.model_dump(mode='json')), 'artifact_hashes': initial['artifacts'],
            'schema_version': '1.0', 'runtime_version': task.runtime_version,
            'checker_version': checked.checker_version, 'source_use_status': 'synthetic_public'}}
    diagnosis = 'accepted' if not reasons else ('agent_error' if all(r.startswith('agent_error:') for r in reasons) else 'task_or_trajectory_defect')
    return AdmissionResult(not reasons, reasons, diagnosis, record, task, world, thash, digest(record) if record else None, trajectory.model_copy(deep=True), dict(split_assignments))


def export_jsonl(results: list[AdmissionResult], path, *, dataset_version='1.0', adjudications=()):
    """Validate entire batch before writing; protected-split records never enter JSONL."""
    ids = [r.task.task_id for r in results]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate task IDs')
    require_resolved(overlap_report([(r.task, r.world) for r in results]), adjudications)
    accepted = [r for r in results if r.accepted and r.task.split == 'train']
    if any(r.record is None for r in accepted):
        raise ValueError('missing admitted record')
    # Rebuild and compare records, so mutating a previously accepted record fails closed.
    for result in accepted:
        if result.trajectory is None or result.split_assignments is None:
            raise ValueError('missing replay provenance')
        fresh = admit(result.world, result.task, result.trajectory, split_assignments=result.split_assignments)
        if not fresh.accepted or fresh.record != result.record:
            raise ValueError('admission no longer verifies')
        if digest(result.record) != result.record_hash or result.record['provenance']['trajectory_hash'] != result.trajectory_hash:
            raise ValueError('provenance tampered')
    filtering = {}
    for r in results:
        for reason in (r.reasons if not r.accepted else ([] if r.task.split == 'train' else ['protected_split'])):
            filtering[reason] = filtering.get(reason, 0) + 1
    payload = ''.join(canonical(r.record) + '\n' for r in accepted)
    Path(path).write_text(payload)
    return {'dataset_version': dataset_version, 'accepted_count': len(accepted),
            'rejected_count': len(results) - len(accepted), 'filtering_reasons': filtering,
            'accepted': [r.record['provenance'] for r in accepted], 'jsonl_sha256': sha256(payload.encode()).hexdigest()}


def diagnose_failure(*, environment_defect=False, grader_defect=False, legitimate_uncertainty=False):
    if environment_defect:
        return 'environment_defect'
    if grader_defect:
        return 'grader_defect'
    return 'legitimate_uncertainty' if legitimate_uncertainty else 'agent_error'


def bounded_repair(candidate, diagnosis: str, repair: Callable, probe: Callable, *, max_repairs=1, allowed_changes=()):
    """Only diagnosed premise defects authorize repair; each attempt uses a fresh probe."""
    if type(max_repairs) is not int or not 0 <= max_repairs <= 3:
        raise ValueError('max_repairs must be between zero and three')
    if diagnosis not in ('environment_defect', 'grader_defect'):
        return candidate, probe(candidate), []
    identity = (candidate.task.task_id, candidate.task.family, candidate.task.family_version, candidate.task.expected_outcome, candidate.task.lineage, candidate.task.split)
    def changes(left, right, prefix=''):
        if isinstance(left, dict) and isinstance(right, dict):
            return {p for key in left.keys() | right.keys() for p in changes(left.get(key), right.get(key), prefix + '.' + key if prefix else key)}
        return set() if left == right else {prefix}
    history = []
    result = probe(candidate)
    for attempt in range(max_repairs):
        if result.accepted:
            break
        updated = repair(candidate, diagnosis)
        if (updated.task.task_id, updated.task.family, updated.task.family_version, updated.task.expected_outcome, updated.task.lineage, updated.task.split) != identity:
            raise ValueError('repair changed task type or split lineage')
        altered = changes({'task': candidate.task.model_dump(mode='json'), 'world': candidate.world.model_dump(mode='json')}, {'task': updated.task.model_dump(mode='json'), 'world': updated.world.model_dump(mode='json')})
        # Business demands/constraints may never be weakened by automated repairs.
        permitted = {'task.visible_artifacts', 'task.permitted_tools'} & set(allowed_changes)
        if altered - permitted:
            raise ValueError('repair changed protected business premises or unapproved fields')
        World.model_validate(updated.world)
        Task.model_validate(updated.task)
        candidate = updated
        history.append({'attempt': attempt + 1, 'diagnosis': diagnosis, 'probe_requested': True})
        result = probe(candidate)
    return candidate, result, history
