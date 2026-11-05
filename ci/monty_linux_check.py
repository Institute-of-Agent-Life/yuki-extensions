"""Build and exercise the independent native image on a disposable Linux runner."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

from units import load_catalog, validate_unit


def file_sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    p = argparse.ArgumentParser(); p.add_argument("--out", type=Path, required=True); args = p.parse_args()
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise SystemExit("native image validation requires Linux x86_64")
    root = Path(__file__).resolve().parents[1]
    unit = load_catalog(root)["monty-runtime"]; validate_unit(root, unit)
    source = root / unit["path"]; out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    commands = []
    def run(argv, name):
        with (out / (name + ".txt")).open("w", encoding="utf-8") as log:
            process = subprocess.run(argv, cwd=source, stdout=log, stderr=subprocess.STDOUT, text=True)
        commands.append({"argv": argv, "exit_code": process.returncode, "log": name + ".txt"})
        if process.returncode: raise RuntimeError("native step failed: " + name)
    image = None
    passed = False
    try:
        run([sys.executable, "scripts/prepare_inputs.py"], "inputs")
        # CI administrator installs the exact original profile in this disposable
        # runner. No daemon-wide defaults, capabilities or userns sysctls change.
        run(["sudo", "apparmor_parser", "-r", "deploy/security/yuki-bot-codemode.apparmor"], "apparmor")
        run(["docker", "build", "--platform", "linux/amd64", "--iidfile", str(out / "image-id.txt"), "."], "build")
        image = (out / "image-id.txt").read_text().strip()
        inspection = json.loads(subprocess.check_output(["docker", "image", "inspect", image]))[0]
        (out / "image-inspect.json").write_text(json.dumps(inspection, indent=2) + "\n")
        cid = subprocess.check_output(["docker", "create", image], text=True).strip()
        try:
            for name in ["artifacts.json", "runtime-contract.json", "THIRD_PARTY_NOTICES.json"]:
                run(["docker", "cp", cid + ":/opt/yuki-monty/" + name, str(out / name)], "copy-" + name)
        finally:
            subprocess.run(["docker", "rm", "-f", cid], check=True)
        notices = json.loads((out / "THIRD_PARTY_NOTICES.json").read_bytes())
        assert notices["license_text_audit_complete"] and not notices["license_text_gaps"]
        run([sys.executable, "scripts/verify_image.py", "--image", image, "--out", str(out / "native-isolation.json")], "isolation")
        run([sys.executable, "scripts/verify_bridge.py", "--image", image, "--out", str(out / "native-codec.json")], "codec")
        run([sys.executable, str(root / "ci/codemode_worker_check.py"),
             "--out", str(out / "rust-worker"), "--image", image,
             "--contract", str(out / "runtime-contract.json")], "rust-worker")
        passed = True
    finally:
        # Retain the exact built image even when a native assertion fails. A
        # later local rebuild cannot reproduce this binary's digest. Export
        # failure must not replace the original test traceback or produce PASS.
        original_failure = sys.exc_info()[0] is not None
        try:
            if image is not None:
                run(["docker", "save", "-o", str(out / "image.tar"), image], "export")
        except Exception:
            passed = False
            if not original_failure:
                raise
        finally:
            manifest = {"unit_id": "monty-runtime", "scope": "native image; CORE-034 consumer acceptance separate",
                "status": "PASS" if passed else "FAIL", "formal_card_acceptance": False,
                "image_id": image, "published": False, "commands": commands,
                "files": {f.name: file_sha256(f) for f in out.iterdir() if f.is_file()}}
            (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__": main()
