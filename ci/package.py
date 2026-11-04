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

from units import inside, load_catalog, validate_unit


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(root: Path, ident: str, output: Path) -> dict:
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
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "VIRTUAL_ENV"}}
    with ExitStack() as stack:
        if unit["ecosystem"] == "python":
            commands = [
                ["uv", "lock", "--check", "--offline"],
                ["uv", "build", "--no-sources", "--out-dir", str(output)],
            ]
        else:
            target = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="yuki-rust-build-")))
            commands = [["rustc", "--version", "--verbose"],
                        ["cargo", "--version"],
                        ["cargo", "build", "--locked", "--release", "--target-dir", str(target)]]
        transcripts = []
        for command in commands:
            result = subprocess.run(command, cwd=path, env=env, text=True, capture_output=True)
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
            for notice in unit["notices"]:
                dest = output / notice
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(inside(path, notice), dest)
            shutil.copy2(path / "Cargo.lock", output / "Cargo.lock")
            shutil.copy2(path / "rust-toolchain.toml", output / "rust-toolchain.toml")
    artifacts = {p.relative_to(output).as_posix(): sha256(p) for p in sorted(output.rglob("*")) if p.is_file()}
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
