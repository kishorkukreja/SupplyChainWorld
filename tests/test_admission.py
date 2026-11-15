import json
from pathlib import Path
import tempfile
import unittest
from supplychainworld.schemas import World, Task
from supplychainworld.environment import ProcurementEnvironment, TOOLS, render_artifacts
from supplychainworld.runner import run_episode, OfflineVisibleAgent
from supplychainworld.admission import admit, export_jsonl, bounded_repair, diagnose_failure

ROOT = Path(__file__).resolve().parents[1]


def sample(split='train'):
    fixture = json.loads((ROOT/'fixtures/reference_cases/ref-01.json').read_text())
    world = World.model_validate(fixture['world'])
    task = Task(task_id='demo', world_id=world.world_id, lineage='demo-lineage', split=split,
                request=fixture['request'], visible_artifacts=list(render_artifacts(world)),
                permitted_tools=TOOLS, expected_outcome='award')
    run = run_episode(ProcurementEnvironment(world, task), OfflineVisibleAgent())
    return world, task, run.trajectory


class AdmissionTests(unittest.TestCase):
    def test_clean_export_and_loss(self):
        world, task, trajectory = sample()
        result = admit(world, task, trajectory, split_assignments={task.lineage:'train'})
        self.assertTrue(result.accepted, result.reasons)
        with tempfile.TemporaryDirectory() as tmp:
            manifest = export_jsonl([result], Path(tmp)/'train.jsonl')
            self.assertEqual(manifest['accepted_count'], 1)
            record = json.loads((Path(tmp)/'train.jsonl').read_text())
        messages = record['messages']
        self.assertTrue(all(m['loss'] == (m['role']=='assistant') for m in messages))
        self.assertNotIn('expected_outcome', json.dumps(messages))
        self.assertNotIn('reference', json.dumps(messages))

    def test_injected_observation_and_replay_rejected(self):
        for field in ('observation', 'replay', 'hash'):
            world, task, trajectory = sample()
            if field == 'observation':
                trajectory.observations[0]['expected_outcome'] = 'award'
            elif field == 'replay':
                trajectory.results[0].observation['secret'] = 'answer'
            else:
                trajectory.artifact_hashes = {}
            result = admit(world, task, trajectory, split_assignments={task.lineage:'train'})
            self.assertFalse(result.accepted)
            self.assertIsNone(result.record)

    def test_wrong_solution_and_split(self):
        world, task, trajectory = sample()
        trajectory.final_submission.claimed_total_cost = '99999'
        result = admit(world, task, trajectory, split_assignments={task.lineage:'evaluation'})
        self.assertFalse(result.accepted)
        self.assertIn('split_assignment', result.reasons)
        self.assertTrue(any(r.startswith('agent_error:') for r in result.reasons))

    def test_protected_duplicate_and_record_tamper(self):
        world, task, trajectory = sample('evaluation')
        result = admit(world, task, trajectory, split_assignments={task.lineage:'evaluation'})
        self.assertTrue(result.accepted, result.reasons)
        self.assertIsNone(result.record)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'train.jsonl'
            self.assertEqual(export_jsonl([result],path)['accepted_count'], 0)
            self.assertEqual(path.read_text(), '')
            with self.assertRaises(ValueError):
                export_jsonl([result,result],path)
            w,t,tr=sample()
            train=admit(w,t,tr,split_assignments={t.lineage:'train'})
            train.record['messages'][0]['content']='private answer'
            with self.assertRaises(ValueError):
                export_jsonl([train],path)

    def test_diagnosis_and_no_agent_repair(self):
        self.assertEqual(diagnose_failure(grader_defect=True), 'grader_defect')
        self.assertEqual(diagnose_failure(legitimate_uncertainty=True), 'legitimate_uncertainty')
        calls=[]
        candidate=object()
        returned=bounded_repair(candidate,'agent_error',lambda c,d:calls.append(c),lambda c:'clean')
        self.assertEqual(calls,[])
        self.assertEqual(returned,(candidate,'clean',[]))

    def test_mixed_split_same_lineage_rejected(self):
        w,t,tr=sample()
        a=admit(w,t,tr,split_assignments={t.lineage:'train'})
        w2,t2,tr2=sample('evaluation')
        t2.task_id='other'
        tr2.task_id='other'
        b=admit(w2,t2,tr2,split_assignments={t2.lineage:'evaluation'})
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                export_jsonl([a,b],Path(tmp)/'out')

    def test_repair_cannot_drop_demand(self):
        from types import SimpleNamespace
        w,t,tr=sample()
        candidate=SimpleNamespace(world=w,task=t)
        def repair(c,d):
            changed=c.world.model_copy(deep=True)
            changed.items[0].demand=0
            return SimpleNamespace(world=changed,task=t)
        with self.assertRaises(ValueError):
            bounded_repair(candidate,'environment_defect',repair,lambda c:SimpleNamespace(accepted=False))
