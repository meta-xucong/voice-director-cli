"""Regression coverage for input-preserving artifact writes."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from voice_director.cli import main

class InputProtectionTests(unittest.TestCase):
    def invoke(self, args):
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = main(args)
        return code, err.getvalue()

    def fixture(self, root):
        script = root / 'narration.txt'
        script.write_bytes('A lesson.\r\n'.encode())
        director = root / 'director.json'
        director.write_text(json.dumps({'schema_version': 1, 'source_sha256': hashlib.sha256(script.read_bytes()).hexdigest(), 'voice_profile': {'description': 'Clear lesson narration'}, 'segments': [{'id': 's', 'start': 0, 'end': 11}]}), encoding='utf-8')
        alignment = root / 'alignment.json'
        alignment.write_text('{bad', encoding='utf-8')
        return script, director, alignment

    def test_all_command_inputs_and_manifests_are_protected_before_any_write(self):
        for command, input_index, name in [('compile', 0, 'compiled.json'), ('compile', 1, 'capability-report.json'), ('compile', 1, 'manifest.json'), ('chunk', 0, 'chunks.json'), ('chunk', 1, 'manifest.json'), ('alignment-audit', 0, 'alignment-audit.json'), ('alignment-audit', 2, 'alignment-audit.json'), ('alignment-audit', 2, 'manifest.json')]:
            with self.subTest(command=command, name=name, input_index=input_index), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                inputs = list(self.fixture(root))
                collision = root / name
                inputs[input_index].rename(collision)
                inputs[input_index] = collision
                before = {p.name: p.read_bytes() for p in root.iterdir()}
                args = [command, '--script', str(inputs[0]), '--out', str(root), '--overwrite']
                if command == 'alignment-audit':
                    args += ['--alignment', str(inputs[2])]
                else:
                    args += ['--director', str(inputs[1]), '--backend', 'f5']
                    if command == 'chunk':
                        args += ['--max-chars', '100']
                code, error = self.invoke(args)
                self.assertEqual(code, 2, error)
                self.assertIn('output aliases input', error)
                self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_hardlink_alias_is_rejected_without_writing_other_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script, director, _ = self.fixture(root)
            out = root / 'out'
            out.mkdir()
            try:
                os.link(script, out / 'manifest.json')
            except OSError as exc:
                self.skipTest(str(exc))
            before = script.read_bytes()
            code, error = self.invoke(['compile', '--script', str(script), '--director', str(director), '--backend', 'f5', '--out', str(out), '--overwrite'])
            self.assertEqual(code, 2, error)
            self.assertIn('output aliases input', error)
            self.assertEqual(script.read_bytes(), before)
            self.assertEqual([p.name for p in out.iterdir()], ['manifest.json'])

    def test_recovered_snapshot_matches_frozen_source_bytes(self):
        path = Path(__file__).resolve().parents[1] / 'references/source-snapshots/editing-playbook.original.md'
        raw = path.read_bytes()
        self.assertEqual(len(raw), 8940)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), 'a231b51fe04bb4548e5879ea6356b3cff7889b060bd0f5cf66448e7781ea7788')
