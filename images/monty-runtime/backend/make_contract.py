"""Bind the actual built worker, launcher and CPython codec inputs."""
import hashlib
import json
from pathlib import Path
import platform
import sys

def build_contract():
    root = Path("/opt/yuki-monty")
    assert sys.version_info[:2] == (3, 12)
    artifacts = json.loads((root / "artifacts.json").read_text())
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    assert sha(root / "monty") == artifacts["worker"]["sha256"]
    assert sha(root / "monty-isolated") == artifacts["launcher"]["sha256"]
    wheel = root / "wheels" / artifacts["binding"]["filename"]
    assert sha(wheel) == artifacts["binding"]["sha256"]
    codec = {"binding_wheel": sha(wheel), "cpython_binary": sha(Path(sys.executable).resolve())}
    for path in sorted((root / "backend").rglob("*.py")):
        codec[path.relative_to(root).as_posix()] = sha(path)
    return {
        "abi": "monty-3f9d6ef-cpython312-linux-" + platform.machine() + "-codec1",
        "engine_sha256": artifacts["worker"]["sha256"],
        "launcher_sha256": artifacts["launcher"]["sha256"],
        "codec_sha256": hashlib.sha256(json.dumps(codec, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "codec_members": codec,
        "monty_source": "3f9d6ef413fb951e5b80113b7088d535bd028fcb",
    }


if __name__ == "__main__":
    Path("/opt/yuki-monty/runtime-contract.json").write_text(json.dumps(build_contract(), indent=2) + "\n")
