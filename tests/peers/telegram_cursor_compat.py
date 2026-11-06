"""Run old/new/old pollers against a signed Host and an isolated Telegram HTTP peer."""

import argparse
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading

from joint_base import digest, exchange, wait_until, write


OLD_WINDOWS_PACKAGE = "5227f287eb2afad02fe3295e251a1b21c79baa2460ad748531bef2b86cf94f84"


def exercise(root, archive, old_zip, package, output):
    import zipfile
    sys.path.insert(0, str(root / "compat/base"))
    from verify_dist import native_target, verify
    sys.path.insert(0, str(root / "ci"))
    from personal_preview import free_address

    output.mkdir()
    work = output / "work"
    work.mkdir()
    lock = json.loads((root / "compat/base/source.lock.json").read_bytes())
    target = "-".join(native_target())
    assert target == "windows-x86_64", target
    pin = lock["platforms"][target]
    key = work / "signer.pub"
    key.write_bytes((pin["signer"] + "\n").encode("ascii"))
    assert digest(key) == pin["signer_sha256"]
    meta = verify(archive, key, lock["source_commit"], pin["sha256"], lock["fixtures_sha256"],
                  destination=work / "host")
    assert not meta["dirty"] and meta["source_tree_sha256"] == lock["source_tree_sha256"]
    host = work / "host/bin/yuki-core.exe"
    assert digest(host) == pin["binary_sha256"]
    assert digest(old_zip) == OLD_WINDOWS_PACKAGE
    with zipfile.ZipFile(old_zip) as z:
        assert not z.testzip()
        old = work / "old.exe"
        old.write_bytes(z.read("yuki-telegram.exe"))
        previous = json.loads(z.read("package-manifest.json"))
    current = json.loads((package / "package-manifest.json").read_bytes())
    new = package / "yuki-telegram.exe"
    for binary, manifest in [(old, previous), (new, current)]:
        assert manifest["unit_id"] == "telegram" and digest(binary) == manifest["artifacts"][new.name]
    assert (previous["version"], current["version"]) == ("0.1.0-alpha.4", "0.1.0-alpha.5")

    phases = []
    requests = []
    class Native(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            method = self.path.removeprefix("/bot101:fixture/")
            params = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if method == "getMe":
                result = {"id": 101, "is_bot": True, "username": "OriginBot"}
            elif method == "getUpdates":
                update = self.server.update
                result = []
                if update is not None and len(self.server.polls) == 0:
                    result = [{"update_id": update, "message": {"date": 1, "message_id": max(1, update),
                               "from": {"id": 8}, "chat": {"id": -42, "type": "supergroup"},
                               "new_chat_title": str(update)}}]
                self.server.polls.append(params.get("offset"))
            else:
                return self.send_error(404)
            requests.append({"phase": self.server.phase, "method": method, "params": params})
            body = json.dumps({"ok": True, "result": result}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except ConnectionError:
                pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), Native)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    data = work / "owner"
    env = {**os.environ, "YUKI_TELEGRAM_BOT_ID": "101", "YUKI_TELEGRAM_TOKEN": "101:fixture",
           "YUKI_TELEGRAM_API": f"http://127.0.0.1:{http.server_port}"}
    def cli(*args, check=True):
        call = subprocess.run([host, "--data", data, *args], cwd=work, env=env,
                              capture_output=True, timeout=15)
        if check and call.returncode:
            raise RuntimeError(call.stderr.decode(errors="replace"))
        return json.loads(call.stdout) if call.returncode == 0 and call.stdout.strip() else None

    @contextmanager
    def owner():
        with (output / "host.log").open("ab") as log:
            proc = subprocess.Popen([host, "--data", data, "run"], cwd=work, env=env,
                                    stdout=log, stderr=log)
        try:
            wait_until(lambda: cli("operator", "database-info", check=False), 12)
            yield
        finally:
            if proc.poll() is None:
                cli("operator", "shutdown", check=False)
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

    def phase(label, binary, cursor_dir, update, first, *, error=None):
        # The Host binds the configured program and arguments to the installation.
        # Upgrade the stopped executable at its original path, keeping the manifest stable.
        installed = work / "installed-telegram.exe"
        shutil.copyfile(binary, installed)
        assert digest(installed) == digest(binary)
        trace, stderr = work / "current.jsonl", work / "current.stderr"
        exit_file = stderr.with_suffix(".exit")
        assert not any(p.exists() for p in (trace, stderr, exit_file))
        http.phase, http.update, http.polls = label, update, []
        env["YUKI_TELEGRAM_STATE"] = str(cursor_dir)
        fields = {"id": "telegram", "namespace": "tg.bot101", "program": sys.executable,
                  "args": [str(Path(__file__).resolve()), "--observe", str(installed), str(trace), str(stderr)],
                  "platform": "telegram", "bot_stage": stage, "grants": ["gateway.inbound"],
                  "env": ["YUKI_TELEGRAM_BOT_ID", "YUKI_TELEGRAM_TOKEN", "YUKI_TELEGRAM_API", "YUKI_TELEGRAM_STATE"]}
        cfg.write_text(top + "\n[[plugins]]\n" + "".join(k+"="+json.dumps(v)+"\n" for k,v in fields.items()), encoding="utf-8")
        path = cursor_dir / "101.offset"
        before = path.read_bytes() if path.exists() else None
        with owner():
            if error:
                wait_until(exit_file.exists)
            else:
                wait_until(lambda: len(http.polls) >= (2 if update is not None else 1))
        trace = trace.rename(output / (label + ".jsonl"))
        stderr = stderr.rename(output / (label + ".stderr"))
        exit_code = int(exit_file.read_text()) if exit_file.exists() else None
        exit_file.unlink(missing_ok=True)
        polls = http.polls.copy()
        frames = [json.loads(line) for line in trace.read_bytes().splitlines()]
        inbound = list(exchange(frames, "gateway.inbound", "from_plugin"))
        after = path.read_bytes() if path.exists() else None
        assert any(row["frame"].get("method") == "initialize" for row in frames)
        if error:
            assert exit_code == 1 and error in stderr.read_text(errors="replace")
            assert "Fatal Python error" not in stderr.read_text(errors="replace")
            assert not inbound and after == before
            assert polls == ([] if update is None else [first]), polls
        else:
            assert polls[0] == first, polls
            if update is not None:
                assert len(inbound) == 1
                request, reply = inbound[0]
                assert request["id"] == update and reply["result"]["event"] > 0
                assert polls[1] == update + 1 and after == f"{update+1}\n".encode()
            else:
                assert not inbound and after == before
        phases.append(dict(case=label, polls=polls, original=before.decode() if before else None,
                           after=after.decode() if after else None, inbound=inbound, expected_error=error, child_exit=exit_code))

    try:
        cli("init")
        cfg = data / "yuki.toml"
        top = cfg.read_text(encoding="utf-8").replace('"127.0.0.1:0"',json.dumps(free_address()))
        top = top.replace('mode = "hybrid"', 'mode = "lexical-only"')
        cfg.write_text(top, encoding="utf-8")
        with owner():
            person = "00000000-0000-4000-8000-000000000008"
            cli("operator", "person", "create", person)
            cli("operator", "account", "open", "telegram", "tg.bot101", "8", "1", "--person", person, "--start", "1")
            stage = cli("operator","account","open","telegram","tg.bot101","101","1","--start","1")["assignment"]
        origin = work / "origin"
        origin.mkdir()
        (origin / "202.offset").write_bytes(b"711\n")
        phase("old-writes", old, origin, 40, None)
        snapshot = work / "stopped-copy"
        shutil.copytree(origin, snapshot)
        phase("new-resumes", new, snapshot, 41, 41)
        rollback = work / "previous-reader"
        shutil.copytree(snapshot, rollback)
        phase("previous-reads-new", old, rollback, None, 42)
        assert (origin / "101.offset").read_bytes() == b"41\n"
        assert all((p / "202.offset").read_bytes() == b"711\n" for p in [origin,snapshot,rollback])
        for label, binary, contents, error in [
            ("old-negative-control",old,b"-2\n",None),
            ("new-negative",new,b"-2\n","negative saved Telegram offset"),
            ("new-truncated",new,b"x","InvalidDigit"),
        ]:
            state = work / label
            state.mkdir()
            (state / "101.offset").write_bytes(contents)
            phase(label, binary, state, None, -2 if binary == old else None, error=error)
        for label, update, error in [("negative-update",-5,"invalid update_id"),
                                     ("overflow-update",2**63-1,"offset overflow")]:
            state = work / label
            state.mkdir()
            phase(label, new, state, update, None, error=error)
        write(output/"result.json", dict(status="PASS", host_source=lock["source_commit"], host_sha256=digest(host),
              sdk_sha256=lock["rust_crate_sha256"], old_archive_sha256=digest(old_zip),
              old_binary_sha256=digest(old), new_binary_sha256=digest(new), phases=phases))
    finally:
        http.shutdown()
        http.server_close()
        write(output/"native.json", requests)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--observe"]:
        binary, trace, stderr = sys.argv[2:]
        from observe_stdio import observe
        with open(stderr, "ab") as errors:
            code = observe(binary, trace, stderr=errors)
        Path(stderr).with_suffix(".exit").write_text(str(code), encoding="ascii")
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        for name in ("archive", "old_zip", "package", "output"):
            parser.add_argument(name, type=Path)
        args = parser.parse_args()
        exercise(Path(__file__).resolve().parents[2], *[p.resolve() for p in vars(args).values()])
