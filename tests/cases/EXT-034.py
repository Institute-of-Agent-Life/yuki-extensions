"""Run the installed Rust rebuild worker against the exact CORE-035/050 pair."""

import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import zipfile

from package import build
from rebuild_intake import ACTOR, Owner, provider, sha, wait_for, write


PLUGIN = "memory-maintenance"
METHODS = [
    "maintenance.history.page", "maintenance.evidence", "maintenance.content",
    "maintenance.extract.preview", "maintenance.extract.apply",
]


def target():
    system = platform.system().lower()
    arch = {"amd64": "x86_64", "aarch64": "arm64"}.get(platform.machine().lower(), platform.machine().lower())
    return system, arch


def candidate(root, output):
    system, arch = target()
    lock = json.loads((root / f"tests/fixtures/EXT-034/{system}-{arch}.lock.json").read_bytes())
    binary = "yuki-core.exe" if system == "windows" else "yuki-core"
    bound = {}
    for card, info in lock["cards"].items():
        env = "YUKI_" + card.replace("-", "") + "_CANDIDATE"
        path = Path(os.environ[env])
        assert sha(path) == info["archive_sha256"], card
        with zipfile.ZipFile(path) as archive:
            meta = json.loads(archive.read("candidate.json"))
            inventory = meta["members"]
            assert sorted(archive.namelist()) == sorted([*inventory, "candidate.json"]), card
            for name, member in inventory.items():
                assert archive.getinfo(name).file_size == member["bytes"]
                with archive.open(name) as stream:
                    assert hashlib.file_digest(stream, "sha256").hexdigest() == member["sha256"], (card, name)
            assert (meta["os"], meta["arch"]) == (system, arch)
            assert meta["source_commit"] == lock["source_commit"] and not meta["dirty"]
            assert meta["source_tree_sha256"] == lock["source_tree_sha256"]
            assert meta["validation"]["card"] == card and meta["status"] == lock["status"]
            assert meta["host_schema_sha256"] == lock["host_schema_sha256"]
            assert inventory["protocol/host-preview.json"]["sha256"] == lock["host_schema_sha256"]
            assert inventory[info["method_module"]]["sha256"] == info["method_module_sha256"]
            assert inventory[f"bin/{binary}"]["sha256"] == lock["binary_sha256"]
            sdk = lock["rust_sdk"]
            assert meta["sdk_versions"]["rust"] == sdk["version"]
            assert inventory[f"sdk/yuki-plugin-sdk-{sdk['version']}.crate"]["sha256"] == sdk["sha256"]
            if card == "CORE-035":
                assert set(METHODS) <= set(meta["validated_maintenance_methods"])
                executable = output / binary
                with archive.open(f"bin/{binary}") as stream, executable.open("xb") as destination:
                    shutil.copyfileobj(stream, destination)
                executable.chmod(0o700)
            else:
                assert {"llm.complete", "llm.result"} <= set(meta["validated_aux_methods"])
            bound[card] = meta["validation"]
    return executable, lock, bound


class Worker(Owner):
    def __init__(self, root, output, executable, plugin, source, declaration):
        super().__init__(root, executable, output)
        self.plugin = plugin
        self.jobs = self.probe_root
        self.control = root / "control"
        self.control.mkdir()
        self.source = source
        self.declaration = declaration
        self.env["YUKI_MEMORY_MAINTENANCE_JOBS"] = str(self.jobs)

    @contextmanager
    def running(self):
        relay = self.control / "relay-process.json"
        relay.unlink(missing_ok=True)
        with super().running():
            yield
        if relay.exists():
            pid = int(wait_for(relay)["child"])
            until = time.monotonic() + 8
            while time.monotonic() < until:
                if os.name == "nt":
                    command = ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"]
                    listing = subprocess.check_output(command, timeout=5)
                    alive = f'"{pid}"'.encode() in listing
                elif sys.platform == "linux":
                    try:
                        state = (Path("/proc") / str(pid) / "stat").read_bytes().rsplit(b") ", 1)[1]
                        alive = state[:1] != b"Z"
                    except FileNotFoundError:
                        alive = False
                else:
                    command = ["ps", "-p", str(pid), "-o", "stat="]
                    result = subprocess.run(command, capture_output=True, timeout=5)
                    alive = result.returncode == 0 and not result.stdout.strip().startswith(b"Z")
                if not alive:
                    return
                time.sleep(0.05)
            raise TimeoutError("maintenance test relay still holds its child")

    def install_worker(self, entry, port, *, evidence):
        methods = [m for m in METHODS if evidence or m != "maintenance.evidence"]
        fields = {
            "id": self.declaration["id"],
            "namespace": PLUGIN,
            "program": sys.executable,
            "args": [str(self.source / "tests/peers/rebuild_stdio.py"),
                     str(self.plugin), str(self.output / "wire.jsonl"), str(self.control)],
            "env": self.declaration["env"],
            "grants": [m for m in self.declaration["grants"] if evidence or m != "maintenance.evidence"],
        }
        fields["erasure_args"] = fields["args"]
        policy = "\n[[plugins]]\n" + "\n".join(k + "=" + json.dumps(v) for k, v in fields.items()) + "\n"
        policy += "\n[plugins.maintenance.scopes.own]\n"
        policy += f'actor="{ACTOR}"\nentry="{entry}"\nmethods={json.dumps(methods)}\n'
        policy += 'purposes=["rebuild"]\nroutes=["extract"]\n'
        policy += f'write_subject={{kind="person",person="{ACTOR}"}}\n'
        policy += '\n[plugins.aux_routes.extract]\npurposes=["rebuild"]\norigins=["maintenance"]\n'
        policy += f'entries={json.dumps([entry])}\n[plugins.aux_routes.extract.profile]\n'
        policy += f'endpoint="http://127.0.0.1:{port}/v1/chat/completions"\n'
        policy += 'model="fixture-extraction"\nname="EXT-034 worker"\nmerge_ms=0\nroot_slots=1\n'
        policy += 'max_input_units=1000000\nmax_output=1024\n'
        with (self.data / "yuki.toml").open("a", encoding="utf-8") as f:
            f.write(policy)
        (self.output / "policy.toml").write_text(policy, encoding="utf-8")

    def submit(self, name, action, batch="first-batch", **args):
        tmp = self.jobs / (name + ".tmp")
        write(tmp, {"action": "rebuild." + action, "batch": batch, **args})
        tmp.rename(self.jobs / (name + ".job"))

    def result(self, name):
        return wait_for(self.jobs / (name + ".result"))

    def job(self, name, action, **args):
        self.submit(name, action, **args)
        return self.result(name)

    def online(self):
        until = time.monotonic() + 8
        while time.monotonic() < until:
            if any(p["online"] for p in self.op("host", "status")["plugins"]):
                return
            time.sleep(.05)
        raise TimeoutError("memory maintenance worker did not come online")


def completed(report):
    assert report["state"] == "completed", report
    return report["result"]


def check(root, output, working, executable, plugin, declaration, evidence):
    working.mkdir()
    output.mkdir()
    owner = Worker(working, output, executable, plugin, root, declaration)
    with owner.running():
        entry, (source, context, foreign) = owner.admit()
    plan = {"scope": "own", "route": "extract", "mode": "text_json",
            "sources": [{"event": source, "role": "primary"}, {"event": context, "role": "context"}]}
    with provider(source) as (server, calls):
        owner.install_worker(entry, server.server_port, evidence=evidence)
        with owner.running():
            owner.online()
            if not evidence:
                refused = owner.job("no-evidence", "preview", plan=plan)
                assert refused["state"] == "not_completed" and "-32003" in refused["error"]
                assert not calls and owner.facts() == []
                write(output / "provider.json", calls)
                return {"missing_evidence": refused, "loopback_requests": 0}
            assert not calls and owner.facts() == []
            wrong = {**plan, "sources": [{"event": foreign, "role": "primary"}]}
            refused = owner.job("outside-scope", "preview", batch="foreign", plan=wrong)
            assert refused["state"] == "not_completed" and "-32003" in refused["error"] and not calls
            assert completed(owner.job("cancel-foreign", "cancel", batch="foreign"))["execution"] == "cancelled"
            review = completed(owner.job("preview", "preview", plan=plan))
            assert review["phase"] == "review" and review["action_count"] == 2
            assert review["applied_ordinals"] == [] and review["pending"] is None
            assert len(calls) == 1 and owner.facts() == []
            page = completed(owner.job("read-preview", "read", offset=0))
            assert page["sha256"] == review["content"]["sha256"] and page["next_offset"] is None
            raw = base64.b64decode(page["bytes"], validate=True)
            assert hashlib.sha256(raw).hexdigest() == page["sha256"]
            assert [a["fact_key"] for a in json.loads(raw)["actions"]] == ["tea", "walk"]
            original = {"preview": review["preview"], "operation": "approved-tea", "approved": [0]}
            assert completed(owner.job("pause", "pause"))["execution"] == "paused"
            paused = owner.job("apply-while-paused", "apply", **original)
            assert paused["state"] == "not_completed" and not owner.facts()
            assert completed(owner.job("resume", "resume")) == review
            cut = owner.control / "kill-operation"
            cut.write_text(review["preview"] + "/approved-tea")
            owner.submit("apply-killed", "apply", **original)
            saved = wait_for(owner.control / "committed-before-kill.json")["result"]
            assert owner.facts() == [("tea", 1)]
            assert not (owner.jobs / "apply-killed.result").exists()
            state = json.loads((owner.jobs / "batch-first-batch/state.json").read_bytes())["phase"]
            assert state["pending"] == "approved-tea" and state["approvals"]["approved-tea"] == [0]
        with owner.running():
            owner.online()
            assert not (owner.jobs / "apply-killed.result").exists()
            pending = {"operation": "approved-tea", "ordinals": [0]}
            assert completed(owner.job("status-cold", "status")) == {**review, "pending": pending}
            assert completed(owner.job("preview-cold", "preview", plan=plan)) == {**review, "pending": pending}
            changed = owner.job("changed-subset", "apply", **{**original, "approved": [1]})
            assert changed["state"] == "not_completed" and "original approved subset changed" in changed["error"]
            diverted = owner.job("changed-operation", "apply", **{**original, "operation": "other"})
            assert diverted["state"] == "not_completed" and "original pending apply" in diverted["error"]
            (owner.control / "mismatch-operation").write_text(review["preview"] + "/approved-tea")
            mismatch = owner.job("mismatched-receipt", "apply", **original)
            assert mismatch["state"] == "not_completed" and "original apply receipt mismatch" in mismatch["error"]
            assert completed(owner.job("status-mismatch", "status")) == {**review, "pending": pending}
            assert completed(owner.job("apply-explicit-resume", "apply", **original)) == saved
            assert completed(owner.job("status-recovered", "status")) == {**review, "applied_ordinals": [0]}
            assert owner.facts() == [("tea", 1)] and len(calls) == 1
            assert completed(owner.job("cancel", "cancel"))["execution"] == "cancelled"
            assert completed(owner.job("resume-after-cancel", "resume"))["execution"] == "cancelled"
            assert owner.job("apply-after-cancel", "apply", **original)["state"] == "not_completed"
            broken = owner.jobs / "unresolved.job"
            broken.write_bytes(b'{"action": "rebuild.preview"')
            assert owner.result("unresolved")["state"] == "not_completed"
            owner.submit("queued-copy", "preview", plan=plan)
            journal = owner.jobs / "batch-first-batch/state.json"
            transient = journal.with_name("state.json.tmp")
            transient.write_bytes(journal.read_bytes())
            retained_marker = owner.jobs / "apply-killed.started"
            marker_before = retained_marker.read_bytes()
            erasure = owner.op("privacy", "erase", "rebuild-erasure", ACTOR, json.dumps([source]))
            until = time.monotonic() + 8
            while time.monotonic() < until:
                state = json.loads(journal.read_bytes())
                if state["phase"]["phase"] == "forgotten" and not any(
                    (owner.jobs / name).exists() for name in
                    ("read-preview.result", "apply-explicit-resume.result", "queued-copy.job")
                ):
                    break
                time.sleep(.05)
            else:
                raise TimeoutError("real forget callback did not clear rebuild files")
            assert state["plan"]["sources"] == []
            assert not (owner.jobs / "apply-explicit-resume.result").exists()
            assert not (owner.jobs / "queued-copy.job").exists()
            assert not transient.exists()
            assert retained_marker.read_bytes() == marker_before
            assert "approvals" not in state["phase"]
            assert (owner.jobs / "batch-foreign/state.json").is_file()
            assert (owner.jobs / "cancel-foreign.result").is_file()
            [obligation] = owner.op("privacy", "pending", PLUGIN)["obligations"]
            assert obligation["watermark"] == erasure["watermark"] and broken.is_file()
        write(broken, {"action": "rebuild.status", "batch": "foreign"})
        with owner.running():
            until = time.monotonic() + 8
            while owner.op("privacy", "pending", PLUGIN)["obligations"]:
                if time.monotonic() >= until:
                    raise TimeoutError("real Host did not record source erasure acknowledgement")
                time.sleep(.05)
            assert json.loads(broken.read_bytes())["batch"] == "foreign"
        with owner.running():
            owner.online()
            refused = owner.job("after-forget", "apply", **original)
            assert refused["state"] == "not_completed" and "forgotten" in refused["error"]
            assert len(calls) == 1
        write(output / "provider.json", calls)
        return {"review": review, "cut_host_receipt": saved, "facts": [["tea", 1]],
                "outside_scope_denied": True, "changed_subset_denied": True,
                "pause_resume_cancel": True, "local_source_erasure_verified": True,
                "host_erasure_acknowledged": True, "unresolved_inbox_then_original_watermark": True,
                "mismatched_receipt_not_confirmed": True,
                "explicit_resume_same_receipt": True, "loopback_requests": 1}


def prepare(root, output):
    system, arch = target()
    cache = Path(os.environ["YUKI_CRATE_CACHE"])
    lock_path = root / "plugins/memory-maintenance/Cargo.lock"
    for item in tomllib.loads(lock_path.read_text(encoding="utf-8"))["package"]:
        if "checksum" not in item or item["name"] == "yuki-plugin-sdk":
            continue
        name = f"{item['name']}-{item['version']}.crate"
        if not any(p.is_file() and sha(p) == item["checksum"] for p in [cache / name, *cache.glob("*/" + name)]):
            raise ValueError("missing locked offline crate " + name)
    with tempfile.TemporaryDirectory(prefix="r034-", dir="/tmp" if system == "darwin" else None) as name:
        working = Path(name).resolve()
        host, lock, producer_receipts = candidate(root, working)
        release = build(root, PLUGIN, output / "packages")
        package = output / "packages"
        binary = "yuki-memory-maintenance.exe" if system == "windows" else "yuki-memory-maintenance"
        plugin = package / binary
        declaration = tomllib.loads((package / "plugin-rebuild.toml").read_text(encoding="utf-8"))
        assert declaration["args"] == declaration["erasure_args"] == ["--rebuild-only"]
        assert set(declaration["grants"]) == {*METHODS, "forget.owner", "llm.complete", "llm.result"}
        assert declaration["version"] == release["version"]
        cases = {
            label: check(root, output / label, working / label, host, plugin, declaration, evidence)
            for label, evidence in [("denied", False), ("authorized", True)]
        }
    sources = [
        root / "ci/rebuild_intake.py", root / "ci/check.py", root / "ci/package.py",
        root / "catalog/memory-maintenance.json", root / "tests/peers/rebuild_stdio.py",
        root / f"tests/fixtures/EXT-034/{system}-{arch}.lock.json", Path(__file__).resolve(),
    ]
    unit = root / "plugins/memory-maintenance"
    sources.extend(unit / name for name in ["Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "plugin.toml", "plugin-rebuild.toml", "README.md"])
    sources.extend(sorted((unit / "src").glob("*.rs")))
    sdk = json.loads((root / "compat/core-035/source.lock.json").read_bytes())
    write(output / "source-files.json", {p.relative_to(root).as_posix(): sha(p) for p in sources if not p.name.startswith("._")})
    return "rebuild-subset.json", {
        "status": "PASS", "card_status": "partial", "published": False,
        "candidate": lock, "producer_receipts": producer_receipts,
        "plugin": release["artifacts"],
        "consumer_sdk": {"version": sdk["sdk"]["rust"], "sha256": sdk["rust_crate_sha256"]},
        "legacy_source_commit": lock["legacy_source_commit"],
        "extraction_fixture_sha256": lock["extraction_fixture_sha256"],
        "cases": cases, "paid_calls": 0,
        "remaining": ["published producer contract and installation qualification"],
    }


def run(root, output):
    name, result = prepare(root, output)
    result["status"] = "BLOCKED"
    return name, result
