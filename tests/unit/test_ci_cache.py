"""Cache mechanics never substitute for package checks or checksum verification."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ci"))
import handshake_cargo
import rust_cache
from units import load_catalog


class RegistryCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = Path(self.tmp.name)
        self.data = b"checksum-locked registry test distribution"
        self.package = {"name": "fixture", "version": "1.0.0",
                        "checksum": hashlib.sha256(self.data).hexdigest()}
        self.environment = patch.dict(os.environ, {"YUKI_CRATE_CACHE": str(self.cache)})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_cold_download_then_warm_offline_hit(self):
        with patch.object(handshake_cargo, "urlopen", return_value=io.BytesIO(self.data)) as request:
            self.assertEqual(handshake_cargo.registry_crate(self.package), self.data)
            request.assert_called_once()
        with patch.object(handshake_cargo, "urlopen", side_effect=AssertionError("warm network")):
            self.assertEqual(handshake_cargo.registry_crate(self.package), self.data)

    def test_corrupt_flat_and_nested_candidates_do_not_bypass_hash(self):
        (self.cache / "fixture-1.0.0.crate").write_bytes(b"bad")
        nested = self.cache / self.package["checksum"]
        nested.mkdir()
        (nested / "fixture-1.0.0.crate").write_bytes(b"also bad")
        with patch.object(handshake_cargo, "urlopen", return_value=io.BytesIO(self.data)) as request:
            self.assertEqual(handshake_cargo.registry_crate(self.package), self.data)
            request.assert_called_once()

    def test_valid_flat_candidate_is_read_only(self):
        path = self.cache / "fixture-1.0.0.crate"
        path.write_bytes(self.data)
        with patch.object(handshake_cargo, "urlopen", side_effect=AssertionError("warm network")):
            self.assertEqual(handshake_cargo.registry_crate(self.package), self.data)
        self.assertEqual(list(self.cache.iterdir()), [path])

    def test_wrong_network_digest_is_never_persisted(self):
        with patch.object(handshake_cargo, "urlopen", return_value=io.BytesIO(b"bad")):
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                handshake_cargo.registry_crate(self.package)
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_same_version_different_distribution_remains_isolated(self):
        for data in (self.data, b"another distribution of the same version"):
            package = {**self.package, "checksum": hashlib.sha256(data).hexdigest()}
            with patch.object(handshake_cargo, "urlopen", return_value=io.BytesIO(data)):
                self.assertEqual(handshake_cargo.registry_crate(package), data)
        with patch.object(handshake_cargo, "urlopen", side_effect=AssertionError("wrong distribution")):
            self.assertEqual(handshake_cargo.registry_crate(self.package), self.data)
        self.assertEqual(len(list(self.cache.glob("*/fixture-1.0.0.crate"))), 2)

    def test_package_coordinates_are_rejected_before_io(self):
        for change in ({"name": "../escape"}, {"version": "1/2"}, {"checksum": "bad"}):
            with self.subTest(change=change), patch.object(handshake_cargo, "urlopen") as request:
                with self.assertRaisesRegex(ValueError, "invalid locked"):
                    handshake_cargo.registry_crate({**self.package, **change})
                request.assert_not_called()

    def test_default_cargo_cache_is_not_written(self):
        with patch.dict(os.environ, {"CARGO_HOME": str(self.cache)}):
            os.environ.pop("YUKI_CRATE_CACHE", None)
            with patch.object(handshake_cargo, "urlopen", return_value=io.BytesIO(self.data)):
                self.assertEqual(handshake_cargo.registry_crate(self.package), self.data)
        self.assertEqual(list(self.cache.iterdir()), [])


class BuildCache(unittest.TestCase):
    def test_compiler_arch_flags_lock_and_sdk_all_change_the_key(self):
        unit = load_catalog(ROOT)["local-agent"]
        with patch.object(rust_cache.subprocess, "check_output", return_value="compiler fixture"), \
                patch.object(rust_cache.platform, "machine", return_value="x86_64"), \
                patch.dict(os.environ, {"RUSTFLAGS": ""}):
            original = rust_cache.plan(ROOT, unit)
            self.assertTrue(original["enabled"])
            with patch.object(rust_cache.platform, "machine", return_value="arm64"):
                self.assertNotEqual(original["key"], rust_cache.plan(ROOT, unit)["key"])
            with patch.object(rust_cache.subprocess, "check_output", return_value="new compiler fixture"):
                self.assertNotEqual(original["key"], rust_cache.plan(ROOT, unit)["key"])
            with patch.dict(os.environ, {"RUSTFLAGS": "-C opt-level=1"}):
                self.assertNotEqual(original["key"], rust_cache.plan(ROOT, unit)["key"])
            real_hash = rust_cache.sha256
            def change_lock(path):
                return "1" * 64 if path.name == "Cargo.lock" else real_hash(path)
            with patch.object(rust_cache, "sha256", side_effect=change_lock):
                self.assertNotEqual(original["key"], rust_cache.plan(ROOT, unit)["key"])
            # Repacked same-version SDKs must miss; mismatch must fail before build.
            with patch.object(rust_cache, "sha256", side_effect=lambda path: "2" * 64 if path.suffix == ".crate" else real_hash(path)):
                with self.assertRaisesRegex(ValueError, "SDK crate digest mismatch"):
                    rust_cache.plan(ROOT, unit)
                sdk = json.loads((ROOT / unit["source"]["sdk_contract"]).read_bytes())
                with patch.object(rust_cache.json, "loads", return_value={**sdk, "rust_crate_sha256": "2" * 64}):
                    self.assertNotEqual(original["key"], rust_cache.plan(ROOT, unit)["key"])
            self.assertEqual(original["inputs"]["sdk"]["crate_sha256"],
                             json.loads((ROOT / unit["source"]["sdk_contract"]).read_bytes())["rust_crate_sha256"])

    def test_python_units_need_no_rust_compiler(self):
        with patch.object(rust_cache.subprocess, "check_output", side_effect=AssertionError("compiler")):
            self.assertEqual(rust_cache.plan(ROOT, load_catalog(ROOT)["connector"]), {"enabled": False})

    def test_project_reuses_only_a_path_and_preserves_preexisting_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with rust_cache.project_directory(root, "fixture", "digest") as project:
                (project / "owned").write_text("temporary source")
            self.assertFalse(project.exists())
            with rust_cache.project_directory(root, "fixture", "digest") as next_project:
                self.assertEqual(next_project, project)
                self.assertEqual(list(next_project.iterdir()), [])
            project.mkdir()
            original = project / "preexisting"
            original.write_text("preserve")
            with self.assertRaises(FileExistsError):
                with rust_cache.project_directory(root, "fixture", "digest"):
                    self.fail("must not enter")
            self.assertEqual(original.read_text(), "preserve")


if __name__ == "__main__":
    unittest.main()
