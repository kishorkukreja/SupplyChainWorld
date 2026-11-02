import json
from pathlib import Path
import tempfile
import unittest
from supplychainworld.lineage import (Assignment, LineageRegistry, PrivateStore, agent_task_view,
    training_export_allowed, business_fingerprint, overlap_report, require_resolved, Adjudication, OverlapFlag)
from supplychainworld.schemas import Task, World

ROOT = Path(__file__).resolve().parents[1]


def record(split='train', task_id='one'):
    fixture = json.loads((ROOT / 'fixtures/reference_cases/ref-01.json').read_text())
    world = World.model_validate(fixture['world'])
    task = Task(task_id=task_id, world_id=world.world_id, lineage=task_id, split=split,
                request=fixture['request'], visible_artifacts=[], permitted_tools=[], expected_outcome='award')
    return task, world


class LineageTests(unittest.TestCase):
    def test_determinism_ancestry_and_conflicting_assignments(self):
        registry = LineageRegistry()
        first = registry.assign('source-a', 'template-a', ('root-a',), split='train')
        self.assertEqual(first, LineageRegistry().assign('source-a', 'template-a', ('root-a',), split='train'))
        child = registry.assign('source-b', 'template-b', ('root-a',))
        self.assertEqual((child.lineage, child.split), (first.lineage, first.split))
        with self.assertRaises(ValueError):
            registry.assign('source-a', 'new', split='evaluation')
        registry.assign('source-c', 'template-c', split='evaluation')
        with self.assertRaises(ValueError):
            registry.assign('source-c', 'template-a')
        task, _ = record()
        task.lineage = first.lineage
        self.assertTrue(registry.verify(task, first))
        task.split = 'evaluation'
        with self.assertRaises(ValueError):
            registry.verify(task, first)
        forged = Assignment(first.lineage, 'evaluation', first.template, first.source_case, first.ancestry)
        with self.assertRaises(ValueError):
            registry.verify(task, forged)
        linked = registry.assign('new-source', 'new-template', ('source-a',))
        self.assertEqual(linked.lineage, first.lineage)

    def test_overlap_survives_renaming_and_numeric_variants(self):
        task, world = record()
        other, variant = record('evaluation', 'two')
        variant.world_id = 'renamed'
        variant.seed += 100
        variant.items[0].item_id = 'renamed-item'
        for row in [*variant.quotes, *variant.stock, *variant.inbound]:
            row.item_id = 'renamed-item'
        self.assertEqual(business_fingerprint(world), business_fingerprint(variant))
        flags = overlap_report([(task, world), (other, variant)])
        self.assertEqual(flags[0].kind, 'exact')
        with self.assertRaises(ValueError):
            require_resolved(flags, [Adjudication('one', 'two', 'exact', 'allow', 'reviewer', 'reviewed')])
        variant.items[0].demand += 5
        self.assertNotEqual(business_fingerprint(world), business_fingerprint(variant))
        self.assertEqual(overlap_report([(task, world), (other, variant)])[0].kind, 'structural')

    def test_semantic_review_requires_named_reason_and_explicit_allow(self):
        flags = [OverlapFlag('a', 'b', 'semantic', False)]
        with self.assertRaises(ValueError):
            require_resolved(flags)
        with self.assertRaises(ValueError):
            require_resolved(flags, [Adjudication('a', 'b', 'semantic', 'allow', '', '')])
        self.assertTrue(require_resolved(flags, [Adjudication('a', 'b', 'semantic', 'allow', 'domain-review', 'Different constraint regimes; shared request boilerplate only.')]))

    def test_private_store_denies_repository_paths_traversal_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / 'repo'
            repo.mkdir()
            with self.assertRaises(ValueError):
                PrivateStore(repo / 'ignored-private', repo)
            store = PrivateStore(root / 'private', repo)
            store.write('sealed', {'answer': 'private'})
            self.assertEqual(store.read('sealed'), {'answer': 'private'})
            self.assertEqual((store.root / 'sealed.json').stat().st_mode & 0o777, 0o600)
            for key in ('../escape', '/absolute', 'a/b'):
                with self.assertRaises(ValueError):
                    store.read(key)
            (store.root / 'link.json').symlink_to(repo / 'public.json')
            with self.assertRaises(ValueError):
                store.write('link', {'answer': 'private'})
            self.assertFalse((repo / 'public.json').exists())

    def test_agent_view_and_training_boundary(self):
        task, _ = record()
        view = agent_task_view(task)
        self.assertNotIn('expected_outcome', view)
        self.assertNotIn('split', view)
        self.assertNotIn('lineage', view)
        self.assertTrue(training_export_allowed(task))
        for split in ('development', 'evaluation'):
            task.split = split
            with self.assertRaises(ValueError):
                training_export_allowed(task)
