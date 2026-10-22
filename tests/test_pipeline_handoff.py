"""Integration tests for the source-script to voice-director byte contract."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PipelineHandoffTests(unittest.TestCase):
    def _write_handoff(self, directory, source):
        script_path = directory / "narration.txt"
        director_path = directory / "director.json"
        script_bytes = source.encode("utf-8")
        script_path.write_bytes(script_bytes)
        director = {
            "schema_version": 1,
            "source_sha256": hashlib.sha256(script_bytes).hexdigest(),
            "voice_profile": {"description": "Clear, measured lesson narration"},
            "segments": ([{"id": "S001", "start": 0, "end": len(source)}] if source else []),
        }
        director_path.write_text(json.dumps(director, ensure_ascii=False), encoding="utf-8")
        return script_path, director_path

    def _validate(self, script_path, director_path):
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "voice_director",
                "validate",
                "--script",
                str(script_path),
                "--director",
                str(director_path),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_exact_utf8_script_handoff_passes_and_reports_matching_hash(self):
        source = "第一部分：历史背景。\r\n第二部分：关键概念🙂。\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            script_path, director_path = self._write_handoff(Path(temp_dir), source)
            result = self._validate(script_path, director_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["source_sha256"], hashlib.sha256(source.encode("utf-8")).hexdigest())
        self.assertEqual(payload["source_characters"], len(source))

    def test_stale_director_hash_rejects_changed_narration(self):
        source = "原始净稿。\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            script_path, director_path = self._write_handoff(Path(temp_dir), source)
            script_path.write_bytes("改过的净稿。\n".encode("utf-8"))
            result = self._validate(script_path, director_path)

        self.assertEqual(result.returncode, 2)
        self.assertIn("source hash mismatch", result.stderr)


if __name__ == "__main__":
    unittest.main()
