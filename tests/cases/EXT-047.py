"""Run the isolated Rust game against the pinned CORE-051 Host candidate."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import threading
import time
import tomllib
import uuid

from personal_preview import Owner

MOVES = [
    ("search", "Search the storeroom for the missing lens.", "The crate contains the lens. You pick it up."),
    ("fit", "Fit the lens and align the lamp.", "The lens clicks into place. The lamp is aligned."),
    ("signal", "Signal the boat with the lighthouse lamp.", "The boat follows the beam away from the reef."),
]


@contextmanager
def provider():
    requests = []
    counts = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append({"path": self.path, "request": request})
            if self.path == "/game":
                messages = request["messages"]
                user = [row["content"] for row in messages if row["role"] == "user"]
                move = user[-1]
                counts[move] = counts.get(move, 0) + 1
                if move == MOVES[0][1] and len(user) == 1 and counts[move] == 2:
                    # The second player loses the reply after physical dispatch.
                    self.connection.shutdown(socket.SHUT_RDWR)
                    return
                expected = [item[1] for item in MOVES[:len(user)]]
                text = MOVES[len(user) - 1][2] if user == expected else "The lamp is still dark."
            else:
                text = ""
            raw = json.dumps({
                "id": f"fixture-{len(requests)}",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": text,
                                                       "reasoning_content": "GAME_PROVIDER_PRIVATE"},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def write(output, name, body):
    (output / name).write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def until(check, label):
    deadline = time.monotonic() + 24
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.08)
    raise AssertionError(f"missing {label}")


def wire(owner):
    try:
        return [json.loads(line) for line in owner.trace.read_text(encoding="utf-8").splitlines()]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def configure(owner, endpoint, declaration):
    config = owner.data / "yuki.toml"
    baseline = config.read_text(encoding="utf-8").replace('mode = "hybrid"', 'mode = "lexical-only"')
    main = f"""
[main]
endpoint = "{endpoint}/main"
model = "main-fixture"
name = "Main"
merge_ms = 1
root_slots = 4
max_input_units = 200000
max_output = 512
"""
    baseline = baseline.replace("\n[[plugins]]", main + "\n[[plugins]]", 1)
    baseline += "commands=" + json.dumps(declaration["commands"]) + "\n"
    config.write_text(baseline, encoding="utf-8")
    return baseline


def settings(profile, endpoint, entries):
    tail = profile[profile.index("\n[sessions]\n"):]
    return (tail.replace("[sessions]", "[plugins.sessions]")
            .replace("[aux_routes.", "[plugins.aux_routes.")
            .replace('["REPLACE_WITH_ORIGINAL_ENTRY_ID"]', json.dumps(entries))
            .replace("http://127.0.0.1:8080/v1/chat/completions", endpoint + "/game")
            .replace("REPLACE_WITH_GAME_MODEL_ID", "game-fixture"))


def prepare(root, output):
    profile = (root / "examples/scoped-session/plugin.toml").read_text(encoding="utf-8")
    declaration = tomllib.loads(profile)
    cases = []
    commands = []
    outcomes = []
    serial = 0

    with provider() as (endpoint, requests):
        owner = Owner(root, output, "lighthouse", declaration["grants"], contract="core-051",
                      command_timeout=18, binary_name=declaration["program"])
        baseline = configure(owner, endpoint, declaration)
        config = owner.data / "yuki.toml"

        def op(*args):
            result = owner.cli("operator", *map(str, args))
            commands.append({"args": args, "result": result})
            return result

        def physical(path):
            return [row["request"] for row in requests if row["path"] == path]

        def person(native):
            actor = str(uuid.uuid4())
            op("person", "create", actor)
            account = op("account", "open", "qq", "lighthouse-test", native, 1,
                         "--person", actor, "--start", 1)
            entry = op("entry", "private", account["assignment"], bot["assignment"])["entry"]
            return actor, account, entry

        def record(user, text, *, original=None):
            nonlocal serial
            if original is None:
                serial += 1
                original = {
                    "source": f"game-input-{serial}", "account": user[1]["account"],
                    "bot_stage": bot["assignment"], "reply_bot": "100", "kind": "message",
                    "occurred": 100 + serial, "observed": 100 + serial,
                    "segments": [{"type": "text", "text": text}],
                }
            event = op("ingress", "record", json.dumps(original), "--accept")
            return event, original

        def command(label, user, text):
            event, original = record(user, text)
            assert event["accepted"] and event["command"]["path"] == "/lighthouse", event
            execution = op("ingress", "claim", event["event"])["execution"]
            operation = f"command:{event['event']}"

            def ready():
                result = owner.command("operator", "effect", "read", execution, operation, user[0])
                if result.returncode:
                    return None
                receipt = json.loads(result.stdout)
                if receipt["state"] in {"confirmed", "failed", "unknown"}:
                    return receipt
                return None

            receipt = until(ready, label)
            outcome = {"label": label, "event": event["event"], "execution": execution,
                       "operation": operation, "receipt": receipt}
            outcomes.append(outcome)
            return receipt["result"], event, original

        def success(label, user, text):
            result, event, original = command(label, user, text)
            assert result["ok"], (label, result)
            cases.append(label)
            return result["data"], event, original

        def denied(label, user, text):
            before = len(physical("/game"))
            result, _, _ = command(label, user, text)
            assert result == {"ok": False, "error": "host_error:-32003"}, (label, result)
            assert len(physical("/game")) == before
            cases.append(label)

        def move(session, key, action, epoch=None):
            return f"/lighthouse/play {session['session']} {session['epoch'] if epoch is None else epoch} {key} {action}"

        try:
            with owner.running():
                bot = op("account", "open", "qq", "lighthouse-test", "100", 1, "--start", 1)
                alice = person("200")
                bob = person("201")
                other = person("202")
                denied("missing policy", alice, "/lighthouse/start")
            installed = baseline + settings(profile, endpoint, [alice[2], bob[2]])
            config.write_text(installed, encoding="utf-8")
            (output / "host-config.toml").write_text(installed, encoding="utf-8")

            with owner.running():
                a, start_event, _ = success("start approved caller", alice, "/lighthouse/start")
                assert a["state"] == "active" and a["persistence"] == "durable"
                assert a["epoch"] == 0 and a["context_profile"] == "none"
                denied("unlisted entry", other, "/lighthouse/start")
                denied("another person in listed entry", bob, f"/lighthouse/status {a['session']}")
                first, first_event, original = success("find original lens", alice, move(a, "move-1", "search"))
                assert first["state"] == "confirmed" and first["text"] == MOVES[0][2]
                assert first["sources"]["ids"] == [start_event["event"], first_event["event"]]
                duplicate, _ = record(alice, "", original=original)
                assert duplicate["event"] == first_event["event"]
                assert len(physical("/game")) == 1
                cases.append("same ingress reuses original event")
                denied("same key with changed move", alice, move(a, "move-1", "signal"))
                second, second_event, _ = success("align original lamp", alice, move(a, "move-2", "fit"))
                assert second["state"] == "confirmed" and second["text"] == MOVES[1][2]
                b, _, _ = success("start another isolated game", bob, "/lighthouse/start")
                assert b["session"] != a["session"]
                unknown, _, _ = success("provider closes after dispatch", bob, move(b, "b-1", "search"))
                assert unknown["state"] == "unknown" and "text" not in unknown
                assert not physical("/main")

            with owner.running():
                prior, _, _ = success("cold confirmed replay", alice, move(a, "move-2", "fit"))
                assert prior == second and len(physical("/game")) == 3
                retried, _, _ = success("cold unknown replay", bob, move(b, "b-1", "search"))
                assert retried == unknown and len(physical("/game")) == 3
                denied("stale session epoch", alice, move(a, "stale", "signal", 1))
                third, _, _ = success("cold resume signals boat", alice, move(a, "move-3", "signal"))
                assert third["state"] == "confirmed" and third["text"] == MOVES[2][2]
                page, _, _ = success("read authorized transcript", alice, f"/lighthouse/status {a['session']}")
                assert [row["role"] for row in page["items"]] == ["user", "assistant"] * 3
                assert [row["text"] for row in page["items"]] == [line for _, move_text, reply in MOVES
                                                                  for line in (move_text, reply)]
                for row in physical("/game"):
                    assert not row.get("tools") and "GAME_PROVIDER_PRIVATE" not in json.dumps(row)
                    assert [item["role"] for item in row["messages"]].count("system") == 1
                    assert "Run a short lighthouse rescue game." in row["messages"][0]["content"]
                final_history = [row["content"] for row in physical("/game")[-1]["messages"][1:]]
                assert final_history == [row["text"] for row in page["items"][:-1]]
                assert len(physical("/game")) == 4 and not physical("/main")
                physical_control, _ = record(alice, "ordinary turn after the isolated game")
                until(lambda: physical("/main"), "ordinary Main positive control")
                assert all(move_text not in json.dumps(physical("/main")) and reply not in json.dumps(physical("/main"))
                           for _, move_text, reply in MOVES)
                exec_id = op("ingress", "claim", physical_control["event"])["execution"]
                facts = op("memory", "read", exec_id, alice[0])
                assert all(reply not in json.dumps(facts) for _, _, reply in MOVES)
                cases.append("Main request and Memory omit isolated transcript")

                before_erase = len(wire(owner))
                erased = op("privacy", "erase", "lighthouse-turn-forget", alice[0],
                            json.dumps([second_event["event"]]))
                callbacks = until(lambda: [row["frame"] for row in wire(owner)[before_erase:]
                                             if row["direction"] == "from_host"
                                             and row["frame"].get("method") == "forget.request"
                                             and row["frame"]["params"]["watermark"] == erased["watermark"]],
                                  "original forget callback")
                assert callbacks[0]["params"]["sources"] == [second_event["event"]]
                callback = callbacks[0]
                proof = until(lambda: [row["frame"]["result"] for row in wire(owner)[before_erase:]
                                        if row["direction"] == "from_plugin"
                                        and row["frame"].get("id") == callback["id"]
                                        and "result" in row["frame"]], "plugin forget proof")[0]
                assert proof == {"key": erased["key"], "watermark": erased["watermark"],
                                 "proof": "lighthouse-request-worker-stopped-no-local-transcript"}
                until(lambda: op("privacy", "pending", "lighthouse")["obligations"] == [],
                      "original erasure proof settlement")
                denied("source erasure removes whole original transcript", alice,
                       f"/lighthouse/status {a['session']}")
                separate, _, _ = success("other original session survives", bob,
                                         f"/lighthouse/status {b['session']}")
                assert len(separate["items"]) == 1 and separate["items"][0]["role"] == "user"

            with owner.running():
                denied("cold erased session does not return", alice, f"/lighthouse/status {a['session']}")
                denied("cold erased turn cannot be rebought", alice, move(a, "move-2", "fit"))
                assert not op("privacy", "pending", "lighthouse")["obligations"]
            assert len(physical("/game")) == 4
            assert len(physical("/main")) == 1
            result = {"status": "PASS", "card_status": "UNPUBLISHED_GAME_CANDIDATE",
                      "core": owner.evidence(), "version": declaration["version"], "paid_calls": 0,
                      "cases": cases, "model_http_calls": {"game": 4, "main": 1},
                      "erasure": {**erased, "plugin_proof": proof}, "provider_reasoning_exported": False,
                      "remaining": ["R11 real Monitor and two target grants", "original API9 loading and old-host compatibility",
                                    "published producer and real external consumption"]}
            return "lighthouse-session.json", result
        finally:
            write(output, "model.json", requests)
            write(output, "operator.json", commands)
            write(output, "command-receipts.json", outcomes)


def run(root, output):
    raise RuntimeError("EXT-047 full acceptance needs the real external consumers and R11; use --preparation for the isolated game")
