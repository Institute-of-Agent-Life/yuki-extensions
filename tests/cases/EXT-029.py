"""Exercise the selected model-native search route on the signed public Rust Host."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import runpy
import socket
import subprocess
import threading

from personal_preview import free_address


def run(root, output):
    shared = runpy.run_path(str(root / "tests/peers/joint_base.py"))
    work = output / "work"
    work.mkdir()
    owner = work / "owner"
    archive = Path(os.environ["YUKI_STABLE_BASE_ZIP"]).resolve()
    host, pin, _ = shared["published_host"](root, archive, work)
    main_requests, searches, responses = [], [], []
    environment = dict(os.environ, YUKI_NATIVE_SEARCH_KEY="loopback-fixture",
                       NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost")
    private = "PRIVATE EXT-029 Main event"
    original = "https://example.org/witness/029"
    person = "00000000-0000-4000-8000-000000000029"
    main_done = threading.Event()

    class Model(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            code = 200
            if self.path == "/v1/chat/completions":
                main_requests.append(body)
                call = {"id": "main-search", "type": "function", "function": {
                    "name": "web_search", "arguments": json.dumps({"query": "qualified query"})}}
                first = len(main_requests) == 1
                message = {"role": "assistant", "content": None if first else "finished"}
                if first:
                    message["tool_calls"] = [call]
                reply = {"id": "main-completion", "choices": [{"index": 0, "message": message,
                    "finish_reason": "tool_calls" if first else "stop"}],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}}
            elif self.path == "/v1/responses":
                searches.append(body)
                prompt = body["input"][-1]["content"]
                if "disconnect query" in prompt:
                    responses.append({"outcome": "disconnected_before_headers"})
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                if "limited query" in prompt:
                    code, reply = 429, {"error": {"message": "fixture rate limit"}}
                else:
                    items = [{"type": "message", "role": "assistant", "content": [{
                        "type": "output_text", "text": "Unverified https://example.org/prose-only",
                        "annotations": []}]}]
                    if "qualified query" in prompt:
                        items.insert(0, {"type": "web_search_call", "id": "search-one",
                            "status": "completed", "action": {"type": "search", "query": "qualified query",
                            "sources": [{"type": "url", "url": original, "title": "Witness 029"}]}})
                    reply = {"id": "native-result", "status": "completed", "output": items,
                             "usage": {"input_tokens": 4, "output_tokens": 2, "total_tokens": 6}}
            else:
                self.send_error(404)
                return
            if self.path == "/v1/responses":
                responses.append({"http_status": code, "body": reply})
            wire = json.dumps(reply).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(wire)))
            self.end_headers()
            self.wfile.write(wire)
            if self.path == "/v1/chat/completions" and len(main_requests) == 2:
                main_done.set()

    def cli(*args, ready=False):
        result = subprocess.run([host, "--data", owner, *args], cwd=work, env=environment,
                                capture_output=True, text=True, encoding="utf-8", timeout=30)
        if ready and result.returncode:
            return None
        if result.returncode:
            raise RuntimeError(f"{args[:3]}: {result.stderr}")
        return json.loads(result.stdout) if result.stdout.strip() else None

    @contextmanager
    def running():
        with (output / "host.log").open("ab") as log:
            proc = subprocess.Popen([host, "--data", owner, "run"], cwd=work, env=environment,
                                    stdout=log, stderr=log)
            try:
                def ready():
                    if proc.poll() is not None:
                        raise RuntimeError(f"Host exited {proc.returncode}")
                    return cli("operator", "database-info", ready=True)
                shared["wait_until"](ready)
                yield
                cli("operator", "shutdown")
                assert proc.wait(timeout=12) == 0
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()

    cli("init", "--memory-mode", "lexical-only")
    cfg = owner / "yuki.toml"
    cfg.write_text(cfg.read_text(encoding="utf-8").replace('"127.0.0.1:0"', json.dumps(free_address())), encoding="utf-8")
    with running():
        cli("operator", "person", "create", person)
        human = cli("operator", "account", "open", "telegram", "native-witness", "200", "1",
                    "--person", person, "--start", "1")
        bot = cli("operator", "account", "open", "telegram", "native-witness", "101", "1", "--start", "1")
        cli("operator", "entry", "private", human["assignment"], bot["assignment"])

    def search(operation, query):
        return cli("operator", "search", execution, person, operation, json.dumps({"query": query}))

    reports = {}
    with ThreadingHTTPServer(('127.0.0.1', 0), Model) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            address = f"http://127.0.0.1:{server.server_port}"
            template = (root / "deploy/search/model-native.example.toml").read_text(encoding="utf-8")
            selected = template.replace("https://model.example.invalid/v1/responses", address + "/v1/responses")
            selected = selected.replace("replace-with-search-capable-model", "native-fixture")
            with cfg.open("a", encoding="utf-8") as file:
                file.write(f'\n[main]\nendpoint="{address}/v1/chat/completions"\nmodel="main-fixture"\n'
                           'name="Yuki"\nmerge_ms=0\nroot_slots=18\nmax_input_units=200000\nmax_output=128\n')
                file.write(selected)
            with running():
                assert cli("operator", "host", "status")["plugins"] == []
                envelope = {"source": "ext-029", "native_id": "native-search-1", "kind": "message",
                            "account": human["account"], "bot_stage": bot["assignment"],
                            "occurred": 10, "observed": 11, "segments": [{"type": "text", "text": private}]}
                reports["ingress"] = cli("operator", "ingress", "record", json.dumps(envelope), "--accept")
                if not main_done.wait(30):
                    raise AssertionError("Main did not consume the search result")
                reports["main_receipt"] = json.loads(main_requests[1]["messages"][-1]["content"])
                execution = reports["main_receipt"]["namespace"]

                def settled_main():
                    usage = cli("operator", "model", "usage", execution)
                    return usage if usage["usage_attempts"] == 3 else None

                reports["usage_after_main"] = shared["wait_until"](settled_main)
                for key, query in [("no_source", "plain query"), ("limited", "limited query"),
                                   ("disconnected", "disconnect query")]:
                    reports[key] = search(key, query)
                    reports[key + "_usage"] = cli("operator", "model", "usage", execution)
            with running():
                reports["cold"] = search("disconnected", "disconnect query")
                reports["cold_usage"] = cli("operator", "model", "usage", execution)
        finally:
            server.shutdown()
            thread.join()
            for name, value in (("main-wire", main_requests), ("search-wire", searches),
                                ("native-responses", responses), ("operations", reports)):
                shared["write"](output / (name + ".json"), value)
    tools = [item.get("function", {}).get("name") for item in main_requests[0]["tools"]]
    assert tools.count("web_search") == 1 and "tavily_search" not in tools
    assert len(main_requests) == 2 and len(searches) == 4
    for wire, q in zip(searches, ["qualified query", "plain query", "limited query", "disconnect query"], strict=True):
        assert wire["tools"] == [{"type": "web_search"}] and q in wire["input"][-1]["content"]
        assert wire["model"] == "native-fixture" and private not in json.dumps(wire)
    main = reports["main_receipt"]
    assert main["state"] == "confirmed" and main["result"]["status"] == "complete"
    assert [s["url"] for s in main["result"]["sources"]] == [original]
    assert reports["no_source"]["status"] == "no_search_evidence" and reports["no_source"]["sources"] == []
    assert reports["limited"]["status"] == "rejected" and reports["limited"]["http_status"] == 429
    assert reports["limited"]["sources"] == []
    assert reports["disconnected"]["status"] == "unknown" and reports["disconnected"] == reports["cold"]
    assert reports["disconnected_usage"] == reports["cold_usage"]
    for total, key in enumerate(["usage_after_main", "no_source_usage", "limited_usage", "disconnected_usage"], 3):
        usage = reports[key]
        assert usage["root"] == execution and len(usage["physical_receipts"]) == usage["reserved_requests"] == total
    assert reports["cold_usage"]["cost_usd"] is None
    ledger = {row["attempt"]: row for row in reports["cold_usage"]["physical_receipts"]}
    for result, state, code in [(main["result"], "response", 200), (reports["no_source"], "response", 200),
                                (reports["limited"], "rejected", 429), (reports["cold"], "unknown", None)]:
        row = ledger[result["attempt"]]
        assert row["logical"] == result["logical"] and row["ordinal"] == 0
        assert row["state"] == state and row["status_code"] == code
    return "native-search.json", {"status": "PASS", "card_status": "VERIFIED_MODEL_NATIVE_SCOPE",
        "release": pin["tag"], "source": pin["source_commit"], "host_sha256": shared["digest"](host),
        "zip_sha256": shared["digest"](archive), "root": execution, "main_calls": len(main_requests),
        "native_calls": len(searches), "search_plugins": [], "paid_calls": 0,
        "owner": "CORE-024", "template_sha256": shared["digest"](root / "deploy/search/model-native.example.toml")}
