"""A verified source snapshot can finish acceptance on a runner without Git."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class AcceptanceSnapshot(unittest.TestCase):
    def test_public_entry_writes_manifest_without_git(self):
        root = Path(__file__).resolve().parents[2]
        snapshot = hashlib.sha256(b"isolated-acceptance-fixture").hexdigest()
        with tempfile.TemporaryDirectory(prefix="acceptance-without-git-") as temporary:
            isolated = Path(temporary)
            (isolated / "ci").mkdir()
            (isolated / "tests/cases").mkdir(parents=True)
            shutil.copyfile(root / "ci/check.py", isolated / "ci/check.py")
            (isolated / "tests/cases/fixture.py").write_text(
                "def run(root, output):\n"
                "    (output / '._sidecar').write_bytes(b'filesystem metadata')\n"
                "    return 'result.json', {'status': 'PASS'}\n",
                encoding="utf-8",
            )
            output = isolated / "result"
            result = subprocess.run(
                [sys.executable, str(isolated / "ci/check.py"), "fixture", "--out", str(output)],
                cwd=isolated,
                env={**os.environ, "PATH": temporary, "YUKI_SOURCE_SNAPSHOT_SHA256": snapshot},
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            manifest = json.loads((output / "manifest.json").read_bytes())
            self.assertEqual(manifest["status"], "PASS")
            self.assertIsNone(manifest["source_commit"])
            self.assertEqual(manifest["source_snapshot_sha256"], snapshot)
            self.assertTrue(manifest["files"])
            self.assertNotIn("._sidecar", manifest["files"])
            for name, digest in manifest["files"].items():
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), digest)
            # An extracted snapshot may be nested inside an unrelated checkout.
            # Its manifest must never inherit that ancestor's HEAD.
            command = (
                "import runpy,sys; from unittest.mock import patch; "
                "sys.argv=sys.argv[1:]; "
                "p=patch('shutil.which',side_effect=AssertionError('ancestor Git probed')); "
                "p.start(); runpy.run_path(sys.argv[0],run_name='__main__')"
            )
            result = subprocess.run(
                [sys.executable, "-c", command, str(isolated / "ci/check.py"),
                 "fixture", "--out", str(isolated / "nested-result")],
                cwd=isolated,
                env={**os.environ, "YUKI_SOURCE_SNAPSHOT_SHA256": snapshot},
                capture_output=True, text=True, encoding="utf-8", timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            nested = json.loads((isolated / "nested-result/manifest.json").read_bytes())
            self.assertIsNone(nested["source_commit"])
            self.assertEqual(nested["source_snapshot_sha256"], snapshot)


if __name__ == "__main__":
    unittest.main()
