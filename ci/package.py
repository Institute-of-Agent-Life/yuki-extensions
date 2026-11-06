"""Build one release unit from its own locked manifest, never a sibling."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from contextlib import ExitStack

from handshake_cargo import vendor_sdk
from units import inside, load_catalog, validate_unit


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(root: Path, ident: str, output: Path, *, test_evidence: Path | None = None) -> dict:
    units = load_catalog(root)
    if ident not in units:
        raise ValueError(f"unknown release unit: {ident}")
    unit = units[ident]
    validate_unit(root, unit)
    path = inside(root, unit["path"])
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("use an empty output directory; published artifacts are immutable")
    output.mkdir(parents=True, exist_ok=True)
    build_path = path
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "VIRTUAL_ENV"}}
    with ExitStack() as stack:
        if unit["ecosystem"] == "python":
            commands = [
                ["uv", "lock", "--check", "--offline"],
                ["uv", "build", "--no-sources", "--out-dir", str(output)],
            ]
        else:
            target = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="yuki-rust-build-")))
            if contract := unit["source"].get("sdk_contract"):
                contract_path = inside(root, contract)
                sdk = json.loads(contract_path.read_bytes())
                crate = contract_path.parent / f"yuki-plugin-sdk-{sdk['sdk']['rust']}.crate"
                if sha256(crate) != sdk["rust_crate_sha256"]:
                    raise ValueError("plugin SDK crate digest mismatch")
                build_path = target / "unit"
                shutil.copytree(path, build_path, ignore=shutil.ignore_patterns("target","._*"))
                vendor_sdk(crate, build_path, build_path / "Cargo.lock")
            commands = [["rustc", "--version", "--verbose"],
                        ["cargo", "--version"],
                        ["cargo", "build", "--locked", "--release", "--target-dir", str(target)]]
            if build_path != path or unit["kind"] == "tool":
                commands.insert(-1, ["cargo", "test", "--locked", "--offline", "--target-dir", str(target)])
        transcripts = []
        for command in commands:
            command_env = env
            if test_evidence is not None and command[:2] == ["cargo", "test"]:
                command_env = {**env, "YUKI_UNIT_TEST_EVIDENCE": str(test_evidence)}
            result = subprocess.run(command, cwd=build_path, env=command_env, text=True, capture_output=True)
            transcripts.append({"command": command, "exit_code": result.returncode,
                                "stdout": result.stdout, "stderr": result.stderr})
            if result.returncode:
                (output / "build-failure.json").write_text(json.dumps(transcripts, indent=2), encoding="utf-8")
                raise RuntimeError(f"build failed: {command}; see {output / 'build-failure.json'}")
        if unit["ecosystem"] == "rust":
            metadata = __import__("tomllib").loads((path / "Cargo.toml").read_text(encoding="utf-8"))
            binaries = metadata.get("bin", [{"name": metadata["package"]["name"]}])
            for binary in binaries:
                name = binary["name"] + (".exe" if os.name == "nt" else "")
                shutil.copy2(target / "release" / name, output / name)
            for notice in [*unit["notices"], *unit.get("runtime_files", [])]:
                dest = output / notice
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(inside(path, notice), dest)
            shutil.copy2(path / "Cargo.lock", output / "Cargo.lock")
            shutil.copy2(path / "rust-toolchain.toml", output / "rust-toolchain.toml")
    artifacts = {p.relative_to(output).as_posix(): sha256(p) for p in sorted(output.rglob("*"))
                 if p.is_file() and p.name != ".gitignore"}
    result = {"unit_id": ident, "version": unit["version"], "release_tag": unit["tag_prefix"] + unit["version"],
              "published": False, "manifest_sha256": sha256(path / ("pyproject.toml" if unit["ecosystem"] == "python" else "Cargo.toml")),
              "lock_sha256": sha256(path / ("uv.lock" if unit["ecosystem"] == "python" else "Cargo.lock")),
              "source": unit["source"], "license": unit["license"], "artifacts": artifacts, "commands": transcripts}
    (output / "package-manifest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--unit", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.root, args.unit, args.out), indent=2))


if __name__ == "__main__":
    main()
