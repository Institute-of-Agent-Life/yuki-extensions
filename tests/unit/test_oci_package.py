"""Integrity regressions for the independent OCI source package and crate archives."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ci"))
from handshake_cargo import unpack_crate
from package import build
from units import BoundaryError, load_catalog, validate_unit


class ImageInputs(unittest.TestCase):
    def test_package_and_reject_changed_or_unlocked_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "catalog").mkdir()
            shutil.copyfile(ROOT / "catalog/monty-runtime.json", root / "catalog/monty-runtime.json")
            shutil.copytree(ROOT / "images/monty-runtime", root / "images/monty-runtime",
                            ignore=shutil.ignore_patterns("inputs", "._*", "__pycache__"))
            unit = load_catalog(root)["monty-runtime"]
            package = build(root, "monty-runtime", root / "out")
            archive = next((root / "out").glob("*.tar.gz"))
            with tarfile.open(archive) as tar:
                received = {m.name: hashlib.sha256(tar.extractfile(m).read()).hexdigest() for m in tar if m.isfile()}
            self.assertEqual(received, package["members"])
            source = root / "images/monty-runtime"
            bridge = source / "backend/bridge.py"
            original = bridge.read_bytes()
            bridge.write_bytes(original + b"\n# altered after pinning\n")
            with self.assertRaisesRegex(BoundaryError, "OCI input digest mismatch"):
                validate_unit(root, unit)
            bridge.write_bytes(original)
            (source / "backend/unlocked.py").write_text("VALUE = 1\n")
            with self.assertRaisesRegex(BoundaryError, "OCI source member set differs"):
                validate_unit(root, unit)

    def test_crate_checksums_only_cover_actual_archive_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "fixture-1/src").mkdir(parents=True)
            # Simulates a filesystem-created metadata file, not archive content.
            (directory / "fixture-1/src/._lib.rs").write_bytes(b"filesystem metadata")
            data = io.BytesIO()
            with tarfile.open(fileobj=data, mode="w:gz") as tar:
                member = tarfile.TarInfo("fixture-1/src/lib.rs"); source = b"pub const VALUE: u8 = 1;\n"
                member.size = len(source); tar.addfile(member, io.BytesIO(source))
            target = unpack_crate(data.getvalue(), directory, "fixture-1")
            checks = json.loads((target / ".cargo-checksum.json").read_bytes())
            self.assertEqual(checks["files"], {"src/lib.rs": hashlib.sha256(source).hexdigest()})
            self.assertEqual(checks["package"], hashlib.sha256(data.getvalue()).hexdigest())

    def test_crate_relative_base_preserves_traversal_guard(self):
        # A noncanonical base exercises the same mismatch as Windows 8.3 TEMP.
        with tempfile.TemporaryDirectory(dir=".") as tmp:
            directory = Path(tmp).relative_to(Path.cwd()) if Path(tmp).is_absolute() else Path(tmp)
            for name, accepted in (("fixture-1/src/lib.rs", True),
                                   ("fixture-1/../../escaped.rs", False)):
                data = io.BytesIO()
                with tarfile.open(fileobj=data, mode="w:gz") as tar:
                    member = tarfile.TarInfo(name)
                    member.size = 1
                    tar.addfile(member, io.BytesIO(b"x"))
                if accepted:
                    target = unpack_crate(data.getvalue(), directory, "fixture-1")
                    self.assertEqual((target / "src/lib.rs").read_bytes(), b"x")
                else:
                    with self.assertRaisesRegex(ValueError, "invalid crate member"):
                        unpack_crate(data.getvalue(), directory, "fixture-1")


if __name__ == "__main__": unittest.main()
