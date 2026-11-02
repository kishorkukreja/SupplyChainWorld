"""End-to-end smoke checks use external temporary private stores."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'scripts/run_smoke.py'
spec = importlib.util.spec_from_file_location('smoke', MODULE)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class SmokeTests(unittest.TestCase):
    def test_actual_pipeline_and_public_redaction(self):
        with tempfile.TemporaryDirectory(prefix='scw-smoke-') as directory:
            root = Path(directory)
            summary = smoke.run(12, root)
            self.assertEqual(summary['instances'], 12)
            self.assertEqual(summary['replayed'], 12)
            self.assertEqual(summary['checker_accepted'], 12)
            self.assertEqual(summary['critical_overlap_count'], 0)
            self.assertEqual(summary['admission_counts'], {'accepted': 12})
            self.assertTrue(all(not p['accepted'] for p in summary['negative_probe_results']))
            self.assertEqual(summary['usage']['provider_calls'], 0)
            manifest = json.loads((root / 'frozen-manifest.json').read_text())
            self.assertEqual(summary['frozen_manifest_sha256'], smoke.digest(manifest))
            self.assertNotIn('seed', summary)
            self.assertNotIn('cases', summary)
            self.assertNotIn('accepted', summary['training_export'])
            records = [json.loads(line) for line in (root / 'training.jsonl').read_text().splitlines()]
            self.assertEqual(len(records), summary['split_counts']['train'])
            self.assertTrue(all(r['provenance']['split'] == 'train' for r in records))
            rerun = smoke.run(12, root)
            self.assertEqual(summary, rerun)
            with self.assertRaisesRegex(ValueError, 'frozen manifest differs'):
                smoke.run(13, root)

    def test_private_output_cannot_be_in_repository(self):
        with self.assertRaises(ValueError):
            smoke.run(1, MODULE.parents[1] / 'unsafe-private')
