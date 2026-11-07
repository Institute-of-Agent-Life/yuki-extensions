"""Independent real wheel builds, installed smoke runs and boundary faults."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from package import build, sha256
from units import BoundaryError, load_catalog, select_units, validate_unit


def run(root: Path, output: Path):
    transcript = []

    def execute(argv, cwd):
        result = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, timeout=180)
        transcript.append({"command": argv, "exit_code": result.returncode,
                           "stdout": result.stdout, "stderr": result.stderr})
        assert result.returncode == 0, transcript[-1]
        return result

    with tempfile.TemporaryDirectory(prefix="yuki-independent-") as tmp:
        isolated = Path(tmp)
        (isolated / "catalog").mkdir()
        for name in ["alpha", "beta"]:
            path = isolated / "plugins" / name
            module = "fixture_" + name
            (path / "src" / module).mkdir(parents=True)
            (path / "src" / module / "__init__.py").write_text("VALUE = 'independent'\n", encoding="utf-8")
            (path / "LICENSE").write_text("SPDX-License-Identifier: MIT\nTest-only original fixture.\n", encoding="utf-8")
            (path / "pyproject.toml").write_text(
                f'[project]\nname = "fixture-{name}"\nversion = "0.0.1"\nrequires-python = ">=3.12"\n'
                '[build-system]\nrequires = ["hatchling==1.27.0"]\nbuild-backend = "hatchling.build"\n', encoding="utf-8")
            execute(["uv", "lock", "--offline"], path)
            record = {"unit_id": name, "kind": "plugin", "path": f"plugins/{name}", "ecosystem": "python",
                      "version": "0.0.1", "tag_prefix": name + "/v", "license": "MIT", "notices": ["LICENSE"],
                      "source": {"kind": "test-only-original"}}
            (isolated / "catalog" / (name + ".json")).write_text(json.dumps(record), encoding="utf-8")
        sidecar = isolated / "catalog/._alpha.json"
        sidecar.write_bytes(bytes.fromhex("0005160700020000") + b"\xff")
        assert set(load_catalog(isolated)) == {"alpha", "beta"}
        sidecar_selection = select_units(isolated, ["catalog/._alpha.json"])
        assert sidecar_selection == []
        malformed = isolated / "catalog/broken.json"
        malformed.write_text("{", encoding="utf-8")
        try:
            load_catalog(isolated)
        except json.JSONDecodeError:
            malformed.unlink()
        else:
            raise AssertionError("malformed release manifest was ignored")
        assert not (isolated / "yuki-core").exists()
        packages = {}
        for name in ["alpha", "beta"]:
            destination = isolated / "built" / name
            packages[name] = build(isolated, name, destination)
            wheel = next(destination.glob("*.whl"))
            env = isolated / (name + "-env")
            execute(["uv", "venv", "--python", sys.executable, str(env)], isolated)
            python = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            execute(["uv", "pip", "install", "--python", str(python), "--no-deps", "--no-index", str(wheel)], isolated)
            execute([str(python), "-I", "-c", "import importlib.util; "
                     "assert importlib.util.find_spec('yuki') is None; "
                     f"import fixture_{name}; assert fixture_{name}.VALUE == 'independent'"], isolated)
        # Compile and execute an actual independent Rust binary. This is a fixture,
        # not a substitute for an SDK-consuming product plugin.
        gamma = isolated / "plugins" / "gamma"
        (gamma / "src").mkdir(parents=True)
        (gamma / "src/main.rs").write_text('fn main() { println!("fixture-gamma 0.0.1"); }\n', encoding="utf-8")
        (gamma / "Cargo.toml").write_text('[package]\nname="fixture-gamma"\nversion="0.0.1"\nedition="2024"\n', encoding="utf-8")
        (gamma / "rust-toolchain.toml").write_text('[toolchain]\nchannel="1.90.0"\nprofile="minimal"\n', encoding="utf-8")
        (gamma / "LICENSE").write_text("SPDX-License-Identifier: MIT\nTest-only original fixture.\n", encoding="utf-8")
        execute(["cargo", "generate-lockfile", "--offline"], gamma)
        gamma_record = {"unit_id": "gamma", "kind": "plugin", "path": "plugins/gamma", "ecosystem": "rust",
                        "version": "0.0.1", "tag_prefix": "gamma/v", "license": "MIT", "notices": ["LICENSE"],
                        "source": {"kind": "test-only-original"}}
        (isolated / "catalog/gamma.json").write_text(json.dumps(gamma_record), encoding="utf-8")
        packages["gamma"] = build(isolated, "gamma", isolated / "built/gamma")
        executable = isolated / "built/gamma" / ("fixture-gamma.exe" if os.name == "nt" else "fixture-gamma")
        observed = execute([str(executable)], isolated).stdout.strip()
        assert observed == "fixture-gamma 0.0.1", observed
        gamma_hashes = {p.name: sha256(p) for p in (isolated / "built/gamma").iterdir()}
        assert all(not any(part.startswith("._") for part in Path(name).parts)
                   for package in packages.values() for name in package["artifacts"])
        beta_hashes = {p.name: sha256(p) for p in (isolated / "built" / "beta").iterdir()}
        # A manifest change selects and builds only alpha. Beta's emitted bytes stay identical.
        alpha_manifest = isolated / "catalog" / "alpha.json"
        record = json.loads(alpha_manifest.read_text(encoding="utf-8"))
        record["version"] = "0.0.2"
        alpha_manifest.write_text(json.dumps(record), encoding="utf-8")
        pyproject = isolated / "plugins" / "alpha" / "pyproject.toml"
        pyproject.write_text(pyproject.read_text(encoding="utf-8").replace('"0.0.1"', '"0.0.2"'), encoding="utf-8")
        execute(["uv", "lock", "--offline"], pyproject.parent)
        selected = select_units(isolated, ["catalog/alpha.json", "plugins/alpha/pyproject.toml"])
        assert selected == ["alpha"], selected
        build(isolated, selected[0], isolated / "built" / "alpha-next")
        assert beta_hashes == {p.name: sha256(p) for p in (isolated / "built" / "beta").iterdir()}
        assert gamma_hashes == {p.name: sha256(p) for p in (isolated / "built/gamma").iterdir()}
        unit = load_catalog(isolated)["alpha"]
        original = pyproject.read_text(encoding="utf-8")
        faults = {}

        def rejects(name, mutate, restore):
            mutate()
            try:
                validate_unit(isolated, unit)
            except BoundaryError as exc:
                faults[name] = {"rejected": True, "reason": str(exc)}
            else:
                raise AssertionError(f"boundary fault was accepted: {name}")
            finally:
                restore()

        for name, suffix in {
            "core_checkout_path": '\n[tool.uv.sources]\nyuki-core = {path = "../yuki-core"}\n',
            "outside_unit_path": '\n[tool.uv.sources]\nother = {path = "../../other"}\n',
            "mutable_git_main": '\n[tool.uv.sources]\nother = {git = "https://example.invalid/repo.git", rev = "main"}\n',
            "unpinned_git": '\n[tool.uv.sources]\nother = {git = "https://example.invalid/repo.git"}\n',
        }.items():
            rejects(name, lambda s=suffix: pyproject.write_text(original + s, encoding="utf-8"),
                    lambda: pyproject.write_text(original, encoding="utf-8"))
        source = pyproject.parent / "src" / "fixture_alpha" / "__init__.py"
        rejects("private_python_import", lambda: source.write_text("from yuki import store\n", encoding="utf-8"),
                lambda: source.write_text("VALUE = 'independent'\n", encoding="utf-8"))
        lock = pyproject.parent / "uv.lock"
        lock_content = lock.read_bytes()
        rejects("missing_independent_lock", lock.unlink, lambda: lock.write_bytes(lock_content))
        # One pinned Cargo dependency must not mask another unpinned dependency.
        rust = isolated / "rust-unit"
        rust.mkdir()
        cargo = rust / "Cargo.toml"
        valid_cargo = ('[package]\nname="test-rust"\nversion="0.0.1"\n'
                       '[dependencies]\na={git="https://example.invalid/a",rev="' + 'a' * 40 + '"}\n')
        cargo.write_text(valid_cargo, encoding="utf-8")
        (rust / "Cargo.lock").write_text("version = 4\n", encoding="utf-8")
        (rust / "rust-toolchain.toml").write_text('[toolchain]\nchannel="1.90.0"\n', encoding="utf-8")
        rust_unit = {"unit_id": "rust-check", "path": "rust-unit", "ecosystem": "rust", "version": "0.0.1"}
        validate_unit(isolated, rust_unit)
        cargo.write_text(valid_cargo + 'b={git="https://example.invalid/b"}\n', encoding="utf-8")
        try:
            validate_unit(isolated, rust_unit)
        except BoundaryError as exc:
            faults["cargo_pin_not_shared_between_dependencies"] = {"rejected": True, "reason": str(exc)}
        else:
            raise AssertionError("an unrelated Cargo rev masked an unpinned dependency")
        assert select_units(isolated, ["plugins\\alpha\\pyproject.toml"]) == ["alpha"]
        # These are test packages; no product plugin or host was substituted for one.
        report = {"status": "PASS", "scope": "two test-only Python distributions and one real Rust binary; independent builds + execution",
                  "selected_after_catalog_sidecar_change": sidecar_selection, "no_core_checkout": True, "selected_after_alpha_change": selected,
                  "beta_bytes_unchanged": True, "packages": packages, "faults": faults,
                  "rust_scope": "Rust 1.90.0 compile, package and executable stdout; no product plugin/host",
                  "rust_stdout": observed, "gamma_bytes_unchanged": True,
                  "not_run": ["public SDK handshake", "real plugin/host acceptance"],
                  "commands": transcript}
    return "extension-build-isolation.json", report
