"""Compare installed read_webpage and default web_fetch on the signed base Host."""

import argparse
import contextlib
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import threading
import tomllib
from urllib.parse import quote

from joint_base import digest, exchange, published_host, wait_until, write
from personal_preview import free_address

ROOT = Path(__file__).resolve().parents[2]
V4 = "329ca7c487414d2f54ddd98ff4727446ed2446cd"
V4_DECLARATION = "c0e371edbf802081e05b00dac37e5aece23c8557cd9914e54f501a6fabf9fd40"
ORIGIN = "93.184.216.34:8100"
PAGE = b"<html><style>hidden</style><p>Original &amp; public</p></html>"
UNICODE_PATH = "/网页"
UNICODE_REQUEST = quote(UNICODE_PATH)
UNICODE_REDIRECT = "/轉址?需求=原文%20段"
UNICODE_REDIRECT_REQUEST = quote(UNICODE_REDIRECT, safe="/?=%")
REDIRECTS = {
    "/redirect": "/page",
    "/private-redirect": "http://127.0.0.1:8100/tripwire",
    UNICODE_REDIRECT_REQUEST: UNICODE_REQUEST,
}
FIXTURES = {
    "/page": ("text/html", PAGE),
    "/plain": ("text/plain", "原文 one\n  next\u2028末行 ".encode()),
    "/title-lines": (
        "text/html",
        (
            "<html><head><title>Article&nbsp;title</title><style>hidden</style></head>"
            "<body><p> First\r\n Second\u2028 第三</p><noscript>hidden</noscript>"
            "<p>Last\u001fline</p></body></html>"
        ).encode(),
    ),
    UNICODE_REQUEST: ("text/plain", b"ordinary page text"),
    "/empty": ("text/html", b"<style>hidden</style><script>hidden</script>"),
    "/unsupported": ("application/octet-stream", b"opaque"),
    "/large": ("text/plain", b"x" * (2 * 1024 * 1024 + 1)),
    "/paged": ("text/plain", b"Original page " * 1300),
    "/frame-limit": ("text/plain", b"x" * 33_000),
}


def url(path):
    return f"http://{ORIGIN}{path}"


CASES = {
    "default-question": ({"url": url("/page") + "#fragment"}, ["/page"]),
    "question": (
        {"url": url("/plain"), "question": "  看\u3000标题\t与内容 "},
        ["/plain"],
    ),
    "redirect": ({"url": url("/redirect")}, ["/redirect", "/page"]),
    "unicode-path": ({"url": url(UNICODE_PATH)}, [UNICODE_REQUEST]),
    "escaped-path": ({"url": url(UNICODE_REQUEST)}, [UNICODE_REQUEST]),
    "unicode-redirect": (
        {"url": url(UNICODE_REDIRECT) + "#原始位置"},
        [UNICODE_REDIRECT_REQUEST, UNICODE_REQUEST],
    ),
    "title-lines": ({"url": url("/title-lines")}, ["/title-lines"]),
    "blank-question": ({"url": url("/page"), "question": " \u3000 "}, []),
    "invalid-url": ({"url": "file:///fixture"}, []),
    "missing-authority": ({"url": "http:93.184.216.34:8100/page"}, []),
    "userinfo": ({"url": "http://@93.184.216.34:8100/page"}, []),
    "private-url": ({"url": "http://127.0.0.1:8100/tripwire"}, []),
    "private-redirect": ({"url": url("/private-redirect")}, ["/private-redirect"]),
    "empty": ({"url": url("/empty")}, ["/empty"]),
    "unsupported": ({"url": url("/unsupported")}, ["/unsupported"]),
    "http-error": ({"url": url("/http-error")}, ["/http-error"]),
    "oversized": ({"url": url("/large")}, ["/large"]),
    "paged": ({"url": url("/paged")}, ["/paged"]),
    "frame-limit": ({"url": url("/frame-limit")}, ["/frame-limit"]),
}


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def oracle(legacy, output):
    source = subprocess.check_output(
        ["git", "-C", legacy, "rev-parse", "HEAD"], text=True
    ).strip()
    assert source == V4
    sys.path.insert(0, str(legacy / "src"))
    import asyncio
    from types import SimpleNamespace
    import httpx
    from yuki.services.agent_tools import AgentToolService, ToolRuntime
    from yuki.services.media_resolver import MediaResolver
    from yuki.web.base import WebSearchError
    from yuki.web.bridge_state import BridgeState
    from yuki.web.models import WebMode
    from yuki.web.page_extractor import DirectPageExtractor

    requests = []

    def recorded(request):
        assert request.url.netloc.decode() == ORIGIN
        path = request.url.raw_path.decode("ascii")
        requests.append(path)
        if path in REDIRECTS:
            return httpx.Response(302, headers={"Location": REDIRECTS[path]})
        if path == "/http-error":
            return httpx.Response(403)
        mime, raw = FIXTURES[path]
        return httpx.Response(200, headers={"Content-Type": mime}, content=raw)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(recorded)) as client:
            resolver = MediaResolver(
                max_download_bytes=2 * 1024 * 1024,
                timeout_seconds=2,
                client=client,
                host_resolver=lambda host, _port: [host],
            )
            extractor = DirectPageExtractor(
                state=BridgeState(output / "oracle-pages.sqlite3"),
                timeout_seconds=2,
                media=resolver,
            )
            service = AgentToolService.__new__(AgentToolService)
            service._memory_mutations = None
            service._settings = SimpleNamespace(
                web=SimpleNamespace(mode=WebMode.NATIVE)
            )
            service._web_provider = extractor
            runtime = ToolRuntime(None)
            tool = next(
                item
                for item in service.definitions(runtime)
                if item.name == "read_webpage"
            )
            declaration = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            assert hashlib.sha256(canonical(declaration)).hexdigest() == V4_DECLARATION
            cases = {}
            try:
                for name, (args, paths) in CASES.items():
                    start = len(requests)
                    try:
                        result = await service._read_webpage(args, runtime)
                    except WebSearchError as exc:
                        result = service._web_result(error=exc.code, detail=exc.detail)
                    assert requests[start:] == paths, (name, requests[start:])
                    cases[name] = {"payload": result.model_payload(), "requests": paths}
            finally:
                await extractor.close()
        return {"source_commit": source, "declaration": declaration, "cases": cases}

    return asyncio.run(run())


@contextlib.contextmanager
def serve(handler):
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join()


def replay(host, plugin, manifest, output, work):
    output.mkdir()
    data = work / "owner"
    work.mkdir()
    trace = output / "wire.jsonl"
    (definition,) = manifest["tools"]
    tool = definition["name"]
    requests, models, completions, active = [], [], {}, []
    expected = (
        CASES
        if tool == "read_webpage"
        else {"default": ({"url": url("/page")}, ["/page"])}
    )
    env = dict(
        os.environ, NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost"
    )

    class Http(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_):
            pass

        def respond(self, status, body=b"", mime="text/plain", location=None):
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Type", mime)
            if location:
                self.send_header("Location", location)
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    class Proxy(Http):
        def do_CONNECT(self):
            requests.append({"connect": self.path})
            if self.path != ORIGIN:
                self.respond(403)
                return
            self.send_response(200, "Connection established")
            self.end_headers()
            self.close_connection = False

        def do_GET(self):
            requests.append({"get": self.path, "host": self.headers["Host"]})
            if self.path in REDIRECTS:
                self.respond(302, location=REDIRECTS[self.path])
            elif self.path == "/http-error":
                self.respond(403)
            else:
                mime, body = FIXTURES[self.path]
                self.respond(200, body, mime)

    class Model(Http):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            models.append(body)
            (name,) = active
            call_id = "fixture-" + name
            original = next(
                (m for m in body["messages"] if m.get("tool_call_id") == call_id), None
            )
            message = {"role": "assistant", "content": "complete"}
            if original is None:
                message.update(
                    content=None,
                    tool_calls=[
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": tool,
                                "arguments": json.dumps(
                                    expected[name][0], ensure_ascii=False
                                ),
                            },
                        }
                    ],
                )
            reply = {
                "choices": [
                    {
                        "index": 0,
                        "message": message,
                        "finish_reason": "stop" if original else "tool_calls",
                    }
                ],
                "usage": {
                    "prompt_tokens": 2,
                    "completion_tokens": 1,
                    "total_tokens": 3,
                },
            }
            self.respond(200, canonical(reply), "application/json")
            if original:
                completions[name] = json.loads(original["content"])

    def cli(*args, check=True):
        process = subprocess.run(
            [host, "--data", data, *map(str, args)],
            env=env,
            cwd=work,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )
        if process.returncode and check:
            raise RuntimeError(f"{args[:2]}: {process.stderr.strip()}")
        return (
            json.loads(process.stdout)
            if process.returncode == 0 and process.stdout
            else None
        )

    @contextlib.contextmanager
    def running():
        with (output / "host.log").open("ab") as log:
            owner = subprocess.Popen(
                [host, "--data", data, "run"], env=env, cwd=work, stdout=log, stderr=log
            )
            try:
                wait_until(
                    lambda: cli("operator", "database-info", check=False), seconds=20
                )
                yield
                cli("operator", "shutdown")
                assert owner.wait(timeout=10) == 0
            finally:
                if owner.poll() is None:
                    owner.kill()
                    owner.wait(timeout=10)

    try:
        with serve(Proxy) as proxy, serve(Model) as model:
            env.update(YUKI_WEB_FETCH_HTTP_PROXY=proxy, YUKI_WEB_FETCH_NO_PROXY="")
            cli("init", "--memory-mode", "lexical-only")
            config = data / "yuki.toml"
            config.write_text(
                config.read_text(encoding="utf-8").replace(
                    '"127.0.0.1:0"', json.dumps(free_address())
                ),
                encoding="utf-8",
            )
            person = "00000000-0000-4000-8000-000000000028"
            with running():
                cli("operator", "person", "create", person)
                human = cli(
                    "operator",
                    "account",
                    "open",
                    "telegram",
                    "web-test",
                    "17",
                    1,
                    "--person",
                    person,
                    "--start",
                    1,
                )
                bot = cli(
                    "operator",
                    "account",
                    "open",
                    "telegram",
                    "web-test",
                    "101",
                    1,
                    "--start",
                    1,
                )
                entry = cli(
                    "operator",
                    "entry",
                    "private",
                    human["assignment"],
                    bot["assignment"],
                )["entry"]
            install = {
                "id": manifest["id"],
                "namespace": "official.web-fetch",
                "program": sys.executable,
                "grants": manifest["grants"],
                "args": [
                    str(ROOT / "tests/peers/observe_stdio.py"),
                    str(plugin),
                    str(trace),
                ],
                "env": manifest["env"],
            }

            def object_toml(value):
                return (
                    "{"
                    + ",".join(f"{k}={object_toml(v)}" for k, v in value.items())
                    + "}"
                    if isinstance(value, dict)
                    else json.dumps(value, ensure_ascii=False)
                )

            with config.open("a", encoding="utf-8") as config_file:
                config_file.write(
                    f'\n[main]\nendpoint="{model}/v1/chat/completions"\nmodel="fixture"\nname="Yuki"\n'
                    "merge_ms=0\nroot_slots=8\nroot_tool_calls=8\nmax_input_units=4000000\n"
                    "max_output=128\nresult_page_budget=8000\nresult_storage_bytes=262144\n[[plugins]]\n"
                )
                for key, value in install.items():
                    config_file.write(f"{key}={object_toml(value)}\n")
                config_file.write("[[plugins.tools]]\n")
                for key, value in definition.items():
                    config_file.write(f"{key}={object_toml(value)}\n")
            with running():
                wait_until(
                    lambda: (status := cli("operator", "host", "status", check=False))
                    and any(p["online"] for p in status["plugins"])
                )
                cases = {}
                cli("operator", "main", "register", "plugin", "web-reader", entry)
                for index, (name, (_, paths)) in enumerate(expected.items(), 1):
                    active[:] = [name]
                    before_models, before_requests = len(models), len(requests)
                    ingress = {
                        "source": name,
                        "native_id": name,
                        "account": human["account"],
                        "bot_stage": bot["assignment"],
                        "occurred": index,
                        "observed": index,
                        "kind": "message",
                        "segments": [{"type": "text", "text": f"Read fixture {name}"}],
                    }
                    receipt = (
                        cli(
                            "operator",
                            "main",
                            "trigger",
                            "web-reader",
                            name,
                            json.dumps({"text": "Read the paged fixture"}),
                        )
                        if name == "paged"
                        else cli(
                            "operator",
                            "ingress",
                            "record",
                            json.dumps(ingress),
                            "--accept",
                        )
                    )
                    reply = wait_until(lambda: completions.get(name), seconds=40)
                    assert len(models) == before_models + 2, name
                    declared = [
                        d
                        for d in models[before_models]["tools"]
                        if d["function"]["name"]
                        in {"read_webpage", "web_fetch", "web_search"}
                    ]
                    assert [d["function"]["name"] for d in declared] == [tool], declared
                    if tool == "read_webpage":
                        assert (
                            hashlib.sha256(canonical(declared[0])).hexdigest()
                            == V4_DECLARATION
                        )
                    expected_requests = [
                        item
                        for path in paths
                        for item in ({"connect": ORIGIN}, {"get": path, "host": ORIGIN})
                    ]
                    assert requests[before_requests:] == expected_requests, (
                        name,
                        requests[before_requests:],
                    )
                    cases[name] = {
                        "ingress": receipt,
                        "result": reply,
                        "requests": expected_requests,
                    }
            frames = [json.loads(line) for line in trace.read_bytes().splitlines()]
            calls = list(exchange(frames, "tool.call", "from_host"))
            checks = list(exchange(frames, "tool.status", "from_plugin"))
            assert len(calls) == len(cases)
            assert len({call["params"]["operation"] for call, _ in calls}) == len(cases)
            for (name, case), (call, reply) in zip(cases.items(), calls, strict=True):
                assert call["params"]["name"] == tool
                assert call["params"]["arguments"] == expected[name][0]
                model_result = case["result"]["result"]
                if name == "paged":
                    assert (
                        model_result["truncated"] and model_result["reason"] == "size"
                    )
                    artifact = model_result["artifact"]
                    rows = []
                    offset = 0
                    with running():
                        while offset is not None:
                            row = cli(
                                "operator",
                                "tools",
                                "read-artifact",
                                case["ingress"]["execution"],
                                "web-reader",
                                json.dumps(
                                    {
                                        "handle": artifact["handle"],
                                        "version": artifact["version"],
                                        "path": "/result/data/sources/0/relevant_content",
                                        "offset": offset,
                                        "limit": 1024,
                                    }
                                ),
                            )
                            rows.append(row)
                            offset = row["next_offset"]
                    assert len(rows) > 1
                    assert (
                        "".join(row["value"] for row in rows)
                        == (reply["result"]["data"]["sources"][0]["relevant_content"])
                    )
                    case["artifact_pages"] = len(rows)
                    case["original_result"] = reply["result"]
                else:
                    assert reply["result"] == model_result
                handle = call["params"]["handle"]
                expected_checks = 2 if expected[name][1] else 0
                state_checks = [
                    r["result"] for q, r in checks if q["params"]["handle"] == handle
                ]
                assert len(state_checks) == expected_checks, (name, state_checks)
                assert all(
                    r["handle"] == handle and r["state"] == "dispatched"
                    for r in state_checks
                )
            return {"tool": tool, "cases": cases, "wire_sha256": digest(trace)}
    finally:
        write(
            output / "native.json",
            {"requests": requests, "models": models, "results": completions},
        )


def compare(original, observed):
    for name, case in observed["cases"].items():
        before = original["cases"][name]["payload"]
        after = case.get("original_result", case["result"]["result"])
        if name == "frame-limit":
            assert before["ok"] and after == {"ok": False, "error": "result_too_large"}
        elif before["ok"]:
            assert after == {"ok": True, "data": before["data"]}, name
        else:
            assert after == {"ok": False, "error": before["error_code"]}, name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    output = args.out.resolve()
    output.mkdir()
    package = args.package.resolve()
    receipt = json.loads((package / "package-manifest.json").read_bytes())
    assert receipt["unit_id"] == "web-fetch" and all(
        p["exit_code"] == 0 for p in receipt["commands"]
    )
    assert all(
        digest(package / name) == sha for name, sha in receipt["artifacts"].items()
    )
    plugin = package / ("yuki-web-fetch.exe" if os.name == "nt" else "yuki-web-fetch")
    original = json.loads(args.oracle.read_bytes())
    assert (
        original["source_commit"] == V4
        and hashlib.sha256(canonical(original["declaration"])).hexdigest()
        == V4_DECLARATION
    )
    with tempfile.TemporaryDirectory(
        prefix="yw-", dir="/tmp" if os.name != "nt" else None
    ) as tmp:
        scratch = Path(tmp).resolve()
        host, pin, schema = published_host(ROOT, args.host.resolve(), scratch)
        standard = tomllib.loads((package / "plugin.toml").read_text(encoding="utf-8"))
        selected = tomllib.loads(
            (package / "plugin-read-webpage.toml").read_text(encoding="utf-8")
        )
        default = replay(
            host, plugin, standard, output / "default", scratch / "default"
        )
        result = default["cases"]["default"]["result"]["result"]
        assert result["ok"] and result["data"]["state"] == "read"
        assert bytes.fromhex(result["data"]["original_hex"]) == PAGE
        assert result["data"]["observed_sha256"] == hashlib.sha256(PAGE).hexdigest()
        legacy = replay(
            host, plugin, selected, output / "selected", scratch / "selected"
        )
        compare(original, legacy)
        write(
            output / "read-webpage.json",
            {
                "status": "PASS",
                "scope": "original declaration and direct page projection",
                "source_commit": pin["source_commit"],
                "platform": platform.platform(),
                "host_sha256": digest(host),
                "host_zip_sha256": digest(args.host),
                "schema_sha256": schema,
                "plugin_sha256": digest(plugin),
                "package_manifest_sha256": digest(package / "package-manifest.json"),
                "v4_source": V4,
                "oracle_sha256": digest(args.oracle),
                "v4_declaration_sha256": V4_DECLARATION,
                "default": default,
                "selected": legacy,
                "paid_calls": 0,
                "published": False,
            },
        )


if __name__ == "__main__":
    main()
