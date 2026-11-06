"""Verify packaged baseline bytes and fetch the one pinned native source revision."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


def prepare(root: Path) -> dict:
    baseline = json.loads((root / "baseline.lock.json").read_bytes())
    adaptations = json.loads((root / "backend-adaptation.lock.json").read_bytes())
    by_source = {item["source"]: item for item in adaptations["changes"]}
    checked = {}
    for item in baseline["files"]:
        path = item["path"]
        expected = by_source.get(path, {}).get("packaged_sha256", item["sha256"])
        actual = hashlib.sha256((root / path).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("baseline input changed: " + path)
        checked[path] = actual
    for item in adaptations["changes"]:
        path = item.get("packaged", item["source"])
        actual = hashlib.sha256((root / path).read_bytes()).hexdigest()
        if actual != item["packaged_sha256"]:
            raise ValueError("backend adaptation changed: " + path)
        checked[path] = actual
    source = json.loads((root / "upstream-mirror.lock.json").read_bytes())
    target = root / "inputs" / "monty.git"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "--bare", str(target)], check=True)
    def git(*args):
        return subprocess.check_output(["git", "--git-dir", str(target), *args], text=True).strip()
    if git("rev-parse", "--is-bare-repository") != "true":
        raise ValueError("the source input must be a bare Git object repository")
    present = subprocess.run(["git", "--git-dir", str(target), "cat-file", "-e", source["commit"]], capture_output=True)
    if present.returncode:
        git("fetch", "--depth=1", source["repository"], source["commit"])
    if git("rev-parse", source["commit"] + "^{commit}") != source["commit"]:
        raise ValueError("native source revision mismatch")
    # Keep the fetched object reachable for the unchanged upstream builder's fetch.
    ref = subprocess.run(["git", "--git-dir", str(target), "rev-parse", "--verify", "refs/heads/pinned"], capture_output=True, text=True)
    if ref.returncode == 0 and ref.stdout.strip() != source["commit"]:
        raise ValueError("existing pinned ref belongs to another source; leave it unchanged")
    git("update-ref", "refs/heads/pinned", source["commit"], "0" * 40 if ref.returncode else source["commit"])
    return {"source_commit": source["commit"], "packaged_inputs": checked}


if __name__ == "__main__":
    print(json.dumps(prepare(Path(__file__).resolve().parents[1]), indent=2))
