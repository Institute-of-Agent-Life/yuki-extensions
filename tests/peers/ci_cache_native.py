"""Cold/warm real Rust package builds; cache behavior is not Host acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import traceback
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ci"))
import handshake_cargo
from package import build
from rust_cache import build_root, plan
from units import load_catalog, validate_unit


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--baseline-workflow", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir()  # A named run may never overwrite old evidence.
    report = {"status": "FAIL", "scope": "CI cache mechanics and two real local-agent builds; no Host/provider call",
              "platform": platform.platform(), "python": platform.python_version()}
    try:
        import yaml
        old = yaml.safe_load(args.baseline_workflow.read_bytes())
        new = yaml.safe_load((ROOT / ".github/workflows/plugin.yml").read_bytes())
        # YAML 1.1 parsers treat the GitHub 'on' key as True.
        events = new.get("on", new.get(True))
        assert events["push"]["branches"] == ["main"]
        assert events["pull_request"]["branches"] == ["main"]
        assert "workflow_dispatch" in events
        assert set(old["jobs"]) == set(new["jobs"])
        for name, job in old["jobs"].items():
            current = new["jobs"][name]
            assert {k: v for k, v in job.items() if k != "steps"} == {
                k: v for k, v in current.items() if k != "steps"}
            previous = iter(current["steps"])
            for step in job["steps"]:
                expected = json.loads(json.dumps(step))
                # Only add the optional build cache env to these two steps.
                if step.get("name") in ("Build only the selected release unit",
                                        "Exercise the Linux Rust env consumer against the original Manager socket"):
                    expected["env"] = {**step.get("env", {}), "YUKI_RUST_CACHE_ROOT":
                                       "${{ github.workspace }}/.ci-transfer/rust-cache"}
                assert any(candidate == expected for candidate in previous), step
        report["workflow"] = {"previous_sha256": sha256(args.baseline_workflow),
                              "current_sha256": sha256(ROOT / ".github/workflows/plugin.yml"),
                              "all_original_jobs_steps_matrices_and_evidence_retained": True,
                              "same_pr_only_concurrency": new["concurrency"]}
        unit = load_catalog(ROOT)["local-agent"]
        source = ROOT / unit["path"]
        bindings = {str(p.relative_to(ROOT)): sha256(p) for p in [
            ROOT / ".github/workflows/plugin.yml", ROOT / "ci/package.py", ROOT / "ci/rust_cache.py",
            ROOT / "ci/handshake_cargo.py", ROOT / "ci/units.py", Path(__file__),
            ROOT / "tests/unit/test_ci_cache.py", ROOT / unit["source"]["sdk_contract"],
            *[source / name for name in validate_unit(ROOT, unit)]]}
        test = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests/unit",
                               "-p", "test_ci_cache.py", "-v"], cwd=ROOT, capture_output=True, text=True)
        (out / "unit-tests.txt").write_text(test.stdout + test.stderr, encoding="utf-8")
        assert test.returncode == 0, "cache unit tests failed"
        cache = out / "cache"
        os.environ["YUKI_CRATE_CACHE"] = str(cache / "registry")
        os.environ["YUKI_RUST_CACHE_ROOT"] = str(cache / "rust")
        os.environ["YUKI_RUST_BUILD_ROOT"] = str(Path(tempfile.gettempdir()).resolve() / "yuki-rust-src")
        report["cache_inputs"] = plan(ROOT, unit)
        requests = []
        original = handshake_cargo.urlopen
        def download(url, **kwargs):
            requests.append(url)
            return original(url, **kwargs)
        builds = []
        for label in ("cold", "warm"):
            before = len(requests)
            start = time.monotonic()
            with patch.object(handshake_cargo, "urlopen", side_effect=download if label == "cold" else
                              AssertionError("warm build attempted a registry request")):
                package = build(ROOT, "local-agent", out / "packages" / label)
            elapsed = time.monotonic() - start
            commands = package["commands"]
            assert all(command["exit_code"] == 0 for command in commands)
            assert len([c for c in commands if c["command"][:2] == ["cargo", "test"]]) == 1
            assert len([c for c in commands if c["command"][:2] == ["cargo", "build"]]) == 1
            assert package["lock_sha256"] == sha256(source / "Cargo.lock")
            assert not (build_root() / "local-agent" / report["cache_inputs"]["digest"][:16]).exists(), "temporary source tree leaked"
            builds.append({"label": label, "seconds": elapsed,
                           "registry_requests": len(requests) - before,
                           "compile_lines": [line.strip() for c in commands for line in c["stderr"].splitlines()
                                             if line.strip().startswith("Compiling ")],
                           "artifacts": package["artifacts"],
                           "manifest_sha256": sha256(out / "packages" / label / "package-manifest.json"),
                           "tests_and_build_executed": True})
        assert bindings == {name: sha256(ROOT / name) for name in bindings}, "source was modified"
        report.update(status="PASS", builds=builds, registry_requests=requests,
                      source_sha256=bindings, source_unchanged=True,
                      queue_time_measured=False, hosted_cache_hit_measured=False)
    except BaseException:
        report["error"] = traceback.format_exc()
        raise
    finally:
        (out / "cache-native.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "builds": report["builds"]}, indent=2))


if __name__ == "__main__":
    main()
