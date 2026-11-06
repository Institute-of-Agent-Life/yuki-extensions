"""Keep a failed native gate's original error and exact image export separate."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ci"))
import monty_linux_check


class NativeFailureEvidence(unittest.TestCase):
    def exercise(self, failures):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "evidence"
            image = "sha256:" + "a" * 64
            actions = []

            def run(argv, **kwargs):
                actions.append(argv)
                if argv[:2] == ["docker", "build"]:
                    step = "build"
                    if step not in failures:
                        Path(argv[argv.index("--iidfile") + 1]).write_text(image)
                elif argv[:2] == ["docker", "cp"]:
                    step = "copy"
                    name = Path(argv[-1]).name
                    data = {"license_text_audit_complete": True, "license_text_gaps": []} if name == "THIRD_PARTY_NOTICES.json" else {"fixture": name}
                    Path(argv[-1]).write_text(json.dumps(data))
                elif argv[:2] == ["docker", "save"]:
                    step = "export"
                    if step not in failures:
                        Path(argv[argv.index("-o") + 1]).write_bytes(b"unit-test image export")
                elif "scripts/verify_bridge.py" in argv:
                    step = "codec"
                elif "scripts/verify_image.py" in argv:
                    step = "isolation"
                elif any(str(a).endswith("codemode_worker_check.py") for a in argv):
                    step = "worker"
                else:
                    step = "setup"
                code = 1 if step in failures else 0
                if kwargs.get("stdout"):
                    kwargs["stdout"].write("fixture " + step + " exit=" + str(code) + "\n")
                return subprocess.CompletedProcess(argv, code)

            def output(argv, **kwargs):
                if argv[:3] == ["docker", "image", "inspect"]:
                    return json.dumps([{"Id": image}]).encode()
                self.assertEqual(argv, ["docker", "create", image])
                return "test-container\n"

            error = None
            with patch.object(sys, "argv", ["monty_linux_check", "--out", str(out)]), \
                    patch.object(monty_linux_check.platform, "system", return_value="Linux"), \
                    patch.object(monty_linux_check.platform, "machine", return_value="x86_64"), \
                    patch.object(monty_linux_check.subprocess, "run", side_effect=run), \
                    patch.object(monty_linux_check.subprocess, "check_output", side_effect=output):
                try:
                    monty_linux_check.main()
                except RuntimeError as exc:
                    error = str(exc)
            report = json.loads((out / "manifest.json").read_bytes())
            for name, digest in report["files"].items():
                self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), digest)
            self.assertFalse(report["formal_card_acceptance"])
            self.assertFalse(report["published"])
            self.assertEqual(report["status"], "FAIL" if failures else "PASS")
            return error, report, actions

    def test_codec_failure_keeps_exact_image_and_contract(self):
        error, report, actions = self.exercise({"codec"})
        self.assertEqual(error, "native step failed: codec")
        self.assertIn("image.tar", report["files"])
        self.assertIn("runtime-contract.json", report["files"])
        self.assertEqual(sum(a[:2] == ["docker", "save"] for a in actions), 1)

    def test_export_failure_does_not_mask_codec_failure(self):
        error, report, _ = self.exercise({"codec", "export"})
        self.assertEqual(error, "native step failed: codec")
        self.assertEqual(report["commands"][-1]["exit_code"], 1)
        self.assertNotIn("image.tar", report["files"])

    def test_successful_checks_cannot_hide_export_failure(self):
        error, report, _ = self.exercise({"export"})
        self.assertEqual(error, "native step failed: export")
        self.assertEqual(report["status"], "FAIL")

    def test_failed_build_does_not_export_an_unknown_image(self):
        error, report, actions = self.exercise({"build"})
        self.assertEqual(error, "native step failed: build")
        self.assertIsNone(report["image_id"])
        self.assertFalse(any(a[:2] == ["docker", "save"] for a in actions))

    def test_passing_checks_and_export_keep_pass(self):
        error, report, _ = self.exercise(set())
        self.assertIsNone(error)
        self.assertIn("image.tar", report["files"])


if __name__ == "__main__":
    unittest.main()
