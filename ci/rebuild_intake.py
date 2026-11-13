"""Isolated Host and loopback model used by EXT-034 replays."""

from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import threading
import time

ACTOR = "00000000-0000-4000-8000-000000000034"
PRIMARY = "我每天喝烏龍茶。我每天散步。"
CONTEXT = "上下文只用來理解原句。"
FOREIGN = "另一個來源不屬於此範圍。"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def wait_for(path, error=None, timeout=12):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        try:
            return json.loads(path.read_bytes())
        except (FileNotFoundError, json.JSONDecodeError):
            if error is not None and error.is_file():
                raise RuntimeError(error.read_text(encoding="utf-8"))
            time.sleep(0.025)
    raise TimeoutError(path.name)


class Owner:
    def __init__(self, workspace, executable, output):
        self.root = workspace
        self.data = workspace / "owner"
        self.probe_root = workspace / "jobs"
        self.probe_root.mkdir(parents=True)
        self.executable = executable
        self.output = output
        self.env = {k: v for k, v in os.environ.items() if "proxy" not in k.lower()}
        self.env["NO_PROXY"] = "127.0.0.1,localhost"
        self.env["PYTHONDONTWRITEBYTECODE"] = "1"
        self.cli("init", "--memory-mode", "lexical-only")

    def cli(self, *args, required=True):
        result = subprocess.run([self.executable, "--data", self.data, *map(str, args)],
                                cwd=self.root, env=self.env, text=True, capture_output=True, timeout=12)
        if required:
            if result.returncode:
                raise RuntimeError(f"{args[:3]}: {result.stderr}")
            return json.loads(result.stdout)
        return result

    @contextmanager
    def running(self):
        with (self.output / "host.log").open("ab") as log:
            p = subprocess.Popen([self.executable, "--data", self.data, "run"], cwd=self.root,
                                 env=self.env, stdout=log, stderr=log)
            try:
                until = time.monotonic() + 12
                while time.monotonic() < until:
                    if p.poll() is not None:
                        raise RuntimeError("candidate Host exited before startup")
                    status = self.cli("operator", "database-info", required=False)
                    if status.returncode == 0:
                        break
                    time.sleep(0.05)
                else:
                    raise TimeoutError("candidate Host readiness")
                yield
            finally:
                if p.poll() is None:
                    self.cli("operator", "shutdown", required=False)
                    try:
                        p.wait(timeout=6)
                    except subprocess.TimeoutExpired:
                        p.kill()
                        p.wait()

    def op(self, *args):
        return self.cli("operator", *args)

    def facts(self):
        connection = sqlite3.connect((self.data / "core.sqlite").as_uri() + "?mode=ro", uri=True)
        try:
            return connection.execute("SELECT fact_key,revision FROM memory_facts ORDER BY fact_key").fetchall()
        finally:
            connection.close()

    def admit(self):
        self.op("person", "create", ACTOR)
        user = self.op("account", "open", "qq", "rebuild-intake", "200", 1, "--person", ACTOR, "--start", 1)
        bot = self.op("account", "open", "qq", "rebuild-intake", "100", 1, "--start", 1)
        entry = None
        events = []
        for index, text in enumerate([PRIMARY, CONTEXT, FOREIGN], start=1):
            space = json.dumps(["qq", "rebuild-intake", "702" if index < 3 else "703"], separators=(",", ":"))
            if index == 1:
                entry = self.op("entry", "group", space)["entry"]
            if index == 3:
                self.op("entry", "group", space)
            frame = {"source": f"event-{index}", "account": user["account"], "bot_stage": bot["assignment"],
                     "reply_bot": "100", "space": space, "kind": "message", "occurred": index * 100,
                     "observed": index * 100, "segments": [{"type": "text", "text": text}]}
            events.append(self.op("ingress", "record", json.dumps(frame, ensure_ascii=False), "--accept")["event"])
        return entry, events


@contextmanager
def provider(primary):
    calls = []

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(body)
            claims = [
                {"source_event_id": primary, "claim": {
                    "subject_ref": "speaker", "scope_type": "person", "memory_key": key,
                    "category": "preference", "content": content, "evidence_quote": quote,
                }}
                for key, content, quote in [
                    ("tea", "每天喝烏龍茶", "我每天喝烏龍茶。"),
                    ("walk", "每天散步", "我每天散步。"),
                ]
            ]
            raw = json.dumps({
                "choices": [{"message": {"role": "assistant", "content": json.dumps({"claims": claims}, ensure_ascii=False)},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 31, "completion_tokens": 7},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
