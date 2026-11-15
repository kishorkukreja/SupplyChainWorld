#!/usr/bin/env python3
"""Run offline integration experiment; all case-level artifacts stay external."""
from __future__ import annotations
import argparse
from collections import Counter
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sys
import secrets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def serial(value):
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def encoded(value):
    return json.dumps(value, default=serial, sort_keys=True, indent=2) + '\n'


def digest(value):
    return sha256(encoded(value).encode()).hexdigest()


def run(count=100, private_root=Path('/workspace/SupplyChainWorld-private'), public_report=None):
    from supplychainworld.generation import generate_population
    from supplychainworld.lineage import PrivateStore, overlap_report, require_resolved
    from supplychainworld.environment import ProcurementEnvironment
    from supplychainworld.runner import run_episode, replay_run, OfflineVisibleAgent, RunnerConfig
    from supplychainworld.solvers import solve_reference, solve_heuristic
    from supplychainworld.verification import verify
    from supplychainworld.admission import admit, export_jsonl

    store = PrivateStore(private_root, ROOT)
    def save(key, value):
        store.write(key, json.loads(encoded(value)))
    seed_path = Path(private_root) / 'experiment-seed.json'
    if seed_path.exists():
        seed = json.loads(seed_path.read_text())['seed']
    else:
        seed = secrets.randbits(63)
        save('experiment-seed', {'seed': seed})
    batch = generate_population(count=count, seed=seed)
    candidates = batch.candidates
    assignments = {c.task.lineage: c.task.split for c in candidates}
    frozen = {'experiment_version': 'offline-smoke-v1', 'seed': seed, 'lineage_manifest': batch.lineage_manifest,
              'cases': [{'task': c.task.model_dump(mode='json'), 'world_hash': digest(c.world)} for c in candidates],
              'assignments': assignments}
    # Persist immutable inputs before the first baseline or agent run.
    manifest_path = Path(private_root) / 'frozen-manifest.json'
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != json.loads(encoded(frozen)):
        raise ValueError('frozen manifest differs; use a new private root')
    if not manifest_path.exists():
        save('frozen-manifest', frozen)
    flags = overlap_report([(c.task, c.world) for c in candidates])
    adjudications = []
    require_resolved(flags, adjudications)
    save('overlap-review', {'flags': flags, 'adjudications': adjudications})
    splits, outcomes, variations = Counter(), Counter(), Counter()
    reference, heuristic, termination, decisions, rejects = Counter(), Counter(), Counter(), Counter(), Counter()
    admissions = []
    actions = replayed = checker_accepted = 0
    negative_probes = []
    for index, candidate in enumerate(candidates):
        world, task = candidate.world, candidate.task
        splits[task.split] += 1
        outcomes[task.expected_outcome] += 1
        variations.update(set(candidate.private.variation_tags))
        ref, greedy = solve_reference(world), solve_heuristic(world)
        reference[ref.status] += 1
        heuristic[greedy.status] += 1
        greedy_check = None
        if greedy.status in ('feasible', 'optimal', 'clarification_required', 'infeasible'):
            greedy_check = verify(world, greedy.submission(), expected_outcome=task.expected_outcome,
                                  reference_cost=ref.total_cost)
        env = ProcurementEnvironment(world, task)
        result = run_episode(env, OfflineVisibleAgent(), RunnerConfig(), run_id=f'smoke-{index}', seed=world.seed)
        termination[result.termination_reason] += 1
        actions += len(result.actions)
        replayed += int(replay_run(ProcurementEnvironment(world, task), result))
        checked = None
        admission = None
        if result.trajectory is not None:
            checked = verify(world, result.trajectory.final_submission,
                             expected_outcome=task.expected_outcome, reference_cost=ref.total_cost)
            checker_accepted += int(checked.accepted)
            admission = admit(world, task, result.trajectory, split_assignments=assignments)
            admissions.append(admission)
            if len(negative_probes) < 3:
                tampered = result.trajectory.model_copy(deep=True)
                tampered.artifact_hashes = {}
                rejected = admit(world, task, tampered, split_assignments=assignments)
                negative_probes.append({'accepted': rejected.accepted, 'reasons': rejected.reasons})
            decisions['accepted' if admission.accepted else 'rejected'] += 1
            if not admission.accepted:
                rejects.update(admission.reasons)
        else:
            decisions['unsubmitted'] += 1
        save(f'case-{index:04d}', {'world': world, 'task': task, 'truth': candidate.private,
                    'reference': ref, 'heuristic': greedy, 'heuristic_check': greedy_check,
                    'run': result, 'checker': checked, 'admission': admission})
    export = export_jsonl(admissions, Path(private_root) / 'training.jsonl', dataset_version='smoke-v1', adjudications=adjudications)
    summary = {'experiment': 'offline-smoke-v1', 'instances': len(candidates),
        'split_counts': dict(splits), 'expected_outcome_counts': dict(outcomes),
        'variation_counts': dict(variations), 'generation_attempted': batch.attempted,
        'generation_rejections': batch.rejection_counts, 'reference_status_counts': dict(reference),
        'heuristic_status_counts': dict(heuristic), 'termination_counts': dict(termination),
        'checker_accepted': checker_accepted, 'replayed': replayed, 'actions': actions,
        'admission_counts': dict(decisions), 'negative_probe_results': negative_probes, 'admission_rejections': dict(rejects),
        'overlap_flags': dict(Counter(f.kind for f in flags)),
        'overlap_reviewed': len(adjudications), 'critical_overlap_count': sum(f.critical for f in flags),
        'frozen_manifest_sha256': digest(frozen), 'training_export': export,
        'usage': {'provider_calls': 0, 'input_tokens': 0, 'output_tokens': 0, 'cost_usd': '0.00'},
        'interpretation': 'Deterministic offline software integration and baselines; no model quality claim.'}
    # Export manifests can contain train task IDs; expose only aggregate export metadata.
    summary['training_export'] = {k: v for k, v in export.items() if k in
        ('accepted_count', 'rejected_count', 'filtering_reasons', 'dataset_version')}
    save('summary', summary)
    if public_report:
        Path(public_report).write_text(encoded(summary))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=100)
    parser.add_argument('--private-root', type=Path, default=Path('/workspace/SupplyChainWorld-private'))
    parser.add_argument('--public-report', type=Path, default=ROOT / 'evidence/issue-11-summary.json')
    args = parser.parse_args()
    print(encoded(run(args.count, args.private_root, args.public_report)))
