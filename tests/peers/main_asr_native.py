"""Replay foreground audio with the exact Rust media binary from EXT-030."""
import base64
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from zipfile import ZipFile

from personal_preview import Owner


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_fixture(root):
    fixture = Path(os.environ["YUKI_ASR_CORE_FIXTURES"])
    lock = json.loads((root / "compat/core-038-main-audio/fixtures.json").read_bytes())
    for name, expected in lock["files"].items():
        assert sha(fixture / name) == expected, name
    sys.path.insert(0, str(fixture / "tests/peers"))
    from chat.recorder import Recorder
    from onebot.peer import Peer
    return fixture, lock, Recorder, Peer


def replay(root, output, prepare, approve):
    fixture, lock, Recorder, Peer = load_fixture(root)
    # Reuse the previously verified plugin bytes from the package archive.
    package_path = Path(os.environ["YUKI_MEDIA_ASR_PACKAGE"])
    receipt = json.loads((root / "artifacts/EXT-030/native-asr-01/asr-source.json").read_bytes())
    system = {"darwin": "macos", "win32": "windows", "linux": "linux"}[sys.platform]
    expected = receipt["platforms"][system]
    assert sha(package_path) == expected["sha256"]
    with ZipFile(package_path) as package:
        aggregate = package.read("manifest.json")
        assert hashlib.sha256(aggregate).hexdigest() == expected["manifest_sha256"]
        prefix = "EXT-030/packages/"
        manifest_bytes = package.read(prefix + "package-manifest.json")
        manifest = json.loads(manifest_bytes)
        binary = "yuki-media.exe" if os.name == "nt" else "yuki-media"
        assert manifest["artifacts"][binary] == expected["binary_sha256"]
        packed = {n: package.read(prefix + n) for n in manifest["artifacts"]}
        assert all(hashlib.sha256(b).hexdigest() == manifest["artifacts"][n] for n, b in packed.items())

    def pinned_package(_root, ident, destination):
        assert ident == "media"
        destination.mkdir()
        (destination / "package-manifest.json").write_bytes(manifest_bytes)
        for name, raw in packed.items():
            target = destination / name
            assert target.resolve().is_relative_to(destination.resolve())
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        (destination / binary).chmod(0o700)
        return manifest

    # Exercise a second Host call over the same event/slot on this exact tuple.
    paid = output / "distinct-call"
    paid.mkdir()
    name, duplicate_receipt = prepare(
        root, paid, original_source_replay=True, package_builder=pinned_package,
        contract="core-038-main-audio",
    )
    save(paid / name, duplicate_receipt)
    assert duplicate_receipt["status"] == "PASS"

    codec = Path(os.environ["YUKI_MEDIA_FFMPEG"]).resolve(strict=True)
    codec_lock = json.loads(packed["packaging/codecs.lock"])["ffmpeg"]["platforms"]
    core_lock = json.loads((root / "compat/core-038-main-audio/source.lock.json").read_bytes())
    target = next(key for key, row in core_lock["platforms"].items() if row["sha256"] == sha(
        Path(os.environ["YUKI_HOST_CANDIDATE"])
    ))
    codec_target = target.replace("darwin-", "macos-")
    assert sha(codec) == codec_lock[codec_target]["binary_sha256"]
    temporary = output / "decoder"
    temporary.mkdir()
    encoded = temporary / "original.mp3"
    subprocess.run([codec, "-nostdin", "-hide_banner", "-v", "error", "-f", "lavfi",
                    "-i", "sine=frequency=400:sample_rate=16000", "-t", "0.1",
                    "-c:a", "libmp3lame", "-threads", "1", encoded],
                   capture_output=True, check=True, timeout=25)
    recording = encoded.read_bytes()
    encoded.unlink()
    foreground = output / "foreground"
    foreground.mkdir()
    grants = ["media.process", "media.open", "media.publish", "forget.owner", "llm.complete", "llm.result"]
    owner = Owner(root, foreground, "media", grants, contract="core-038-main-audio",
                  environment={"YUKI_MEDIA_ASR_ROUTE": "asr", "YUKI_MEDIA_FFMPEG": str(codec),
                               "YUKI_MEDIA_TEMP": str(temporary)},
                  package_builder=pinned_package, command_timeout=40)
    assert owner.binary_sha == expected["binary_sha256"]
    actor = "00000000-0000-4000-8000-000000000022"
    quoter = "00000000-0000-4000-8000-000000000023"
    config = owner.data / "yuki.toml"
    config.write_text(config.read_text().replace('mode = "hybrid"', 'mode = "lexical-only"'),
                      encoding="utf-8")
    owner.env.update(ASR_QQ_A="loopback-asr-a", ASR_QQ_B="loopback-asr-b")
    with owner.running():
        for ident, native in [(actor, 200), (quoter, 201)]:
            owner.cli("operator", "person", "create", ident)
            owner.cli("operator", "account", "open", "qq", "asr-fixture", str(native), "1",
                      "--person", ident, "--start", "1")
        stages = {str(bot): owner.cli("operator", "account", "open", "qq", "asr-fixture",
                  str(bot), "1", "--start", "1")["assignment"] for bot in (100, 300)}
        space = json.dumps(["qq", "asr-fixture", "702"], separators=(",", ":"))
        entry = owner.cli("operator", "entry", "group", space)["entry"]

    def packet(bot, native, parts, *, user=200, group=702, sequence=None):
        return {"post_type": "message", "message_type": "group", "self_id": bot,
                "time": 100, "message_id": native, "message_seq": sequence or native,
                "user_id": user, "group_id": group, "message": parts}

    # The original key evaluator receives independently labeled synthetic packets.
    evaluator = fixture / "baseline/qq-key/decision.py"
    peer_digest = "sha256:" + lock["files"]["tests/peers/onebot/peer.py"]
    originals = []
    for index, (label, session, bot, native, seq) in enumerate([
        ("a", "A", 100, 1, 91), ("a", "B", 300, 19, 91), ("b", "A", 100, 2, 92),
        ("b", "B", 300, 20, 92), ("a", "A2", 100, 1, 91), ("echo", "B", 300, 21, 93),
    ]):
        frame = packet(bot, native, [{"type": "record", "data": {"file": "fixture"}},
                                    {"type": "at", "data": {"qq": "300"}}], sequence=seq)
        if label == "echo":
            frame.update(post_type="message_sent", user_id=bot)
        path = foreground / f"receiver-{index}.json"
        save(path, frame)
        originals.append({"occurrence": label, "session": session, "file": path.name, "sha256": sha(path)})
    capture = foreground / "receiver-input.json"
    save(capture, {"kind": "target_capture", "target_image_digest": peer_digest,
                   "capture_image_digest": peer_digest, "sequence_field": "message_seq",
                   "observations": originals})
    decision = subprocess.check_output([sys.executable, "-B", evaluator, capture], timeout=20)
    assert json.loads(decision)["group"]["mode"] == "scoped_shared_key"
    (foreground / "receiver-decision.json").write_bytes(decision)
    (owner.data / "receiver-decision.json").write_bytes(decision)

    def rows(sql, *arguments):
        with closing(sqlite3.connect((owner.data / "core.sqlite").as_uri() + "?mode=ro", uri=True)) as db:
            return db.execute(sql, arguments).fetchall()

    def until(probe):
        end = time.monotonic() + 15
        while time.monotonic() < end:
            value = probe()
            if value:
                return value
            time.sleep(0.025)
        raise AssertionError(rows("SELECT x.source,x.state,t.diagnostic FROM executions x LEFT JOIN main_turns t ON t.execution=x.id"))

    def event(native):
        return until(lambda: rows("SELECT event_id FROM event_locators WHERE native_id=?", str(native)))[0][0]

    def completed(source):
        return until(lambda: rows("SELECT id FROM executions WHERE source=? AND state='completed'", source))[0][0]

    transcript = "/ai admin fixture voice; no command authority"
    calls = []
    witnesses = []

    def receive(provider, name, timeout=14):
        body, answer = provider.receive(timeout=timeout)
        value = json.loads(body)
        save(foreground / (name + ".json"), value)
        return body, value, answer

    def reply(answer, value):
        answer.put(({"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": value}}],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 8, "total_tokens": 12}}, 0))

    def record(peer, native, key, data):
        peer.send(packet(100, native, [{"type": "record", "data": {"file": key}}]))
        request = peer.receive()
        assert request["action"] == "get_record" and request["params"] == {"file": key, "out_format": "mp3"}
        calls.append(request)
        peer.send({"echo": request["echo"], "status": "ok", "retcode": 0,
                   "data": {"base64": base64.b64encode(data).decode()}})
        return event(native)

    with Recorder() as main, Recorder() as upstream:
        text = config.read_text(encoding="utf-8")
        text = text.replace("\n[[plugins]]", f'''
[main]
endpoint="{main.url}"
model="fixture-main"
name="Yuki"
max_output=128
root_slots=8
max_input_units=4000000
merge_ms=2
audio_processor="media"

[[plugins]]''')
        text += f'''
[plugins.aux_routes.asr]
entries={json.dumps([entry])}
purposes=["transcript"]
origins=["call"]
media=["audio"]
[plugins.aux_routes.asr.profile]
endpoint="{upstream.url}"
protocol="chat"
model="fixture-asr"
name="ASR fixture"
max_output=128
root_slots=8
max_input_units=4000000
merge_ms=1

[qq]
namespace="asr-fixture"
designated_ingress="100"
[qq.groups]
"702"="open"
"703"="open"
[[qq.bots]]
self_id="100"
stage="{stages['100']}"
token_env="ASR_QQ_A"
[[qq.bots]]
self_id="300"
stage="{stages['300']}"
token_env="ASR_QQ_B"
[qq.shared_decision]
file="receiver-decision.json"
sha256="{hashlib.sha256(decision).hexdigest()}"
target_image_digest="{peer_digest}"
'''
        config.write_text(text, encoding="utf-8")
        approve(owner, foreground, lambda *args: owner.cli("operator", *args))
        with owner.running(), closing(Peer(owner.address, "100", owner.env["ASR_QQ_A"])) as a, \
                closing(Peer(owner.address, "300", owner.env["ASR_QQ_B"])) as b:
            source = record(a, 101, "original-silk-key", recording)
            _, model, answer = receive(upstream, "asr-first")
            audio = model["messages"][-1]["content"][0]["input_audio"]
            waveform = base64.b64decode(audio["data"], validate=True)
            assert audio["format"] == "wav" and waveform[:4] == b"RIFF"
            a.send(packet(100, 102, [{"type": "text", "data": {"text": "independent ordinary text"}}], group=703))
            independent = event(102)
            wire, _, pending = receive(main, "independent-text")
            assert "independent ordinary text" in wire and transcript not in wire
            reply(pending, "text completed")
            completed(independent)
            reply(answer, transcript)
            wire, _, pending = receive(main, "foreground-first")
            assert transcript in wire and f'\\"source_event\\":{source}' in wire
            reply(pending, "voice completed")
            execution = completed(source)
            assert rows("SELECT text FROM history_transcripts WHERE source=? AND segment=0", source) == [(transcript,)]
            assert rows("SELECT root FROM model_requests WHERE id LIKE 'plugin-aux:%'") == [(execution,)]
            assert rows("SELECT count(*) FROM main_controls") == [(0,)]
            assert rows("SELECT count(*) FROM host_command_events") == [(0,)]
            witnesses.append({"case": "first_turn", "event": source, "root": execution,
                              "codec_input_sha256": hashlib.sha256(recording).hexdigest(),
                              "provider_wav_sha256": hashlib.sha256(waveform).hexdigest()})
            witnesses.append({"case": "independent_text_while_asr_held", "event": independent})

            b.send(packet(300, 901, [{"type": "record", "data": {"file": "different-receiver-key"}}], sequence=101))
            assert event(901) == source
            a.send(packet(100, 103, [{"type": "reply", "data": {"id": 101}},
                                    {"type": "text", "data": {"text": "quote earlier speech"}}], user=201))
            quoted = event(103)
            wire, _, pending = receive(main, "quote")
            assert transcript in wire and "quote earlier speech" in wire
            reply(pending, "quoted source completed")
            quote_root = completed(quoted)
            history = owner.cli("operator", "history", "query", quote_root, quoter,
                                json.dumps({"kind": "search", "text": "fixture voice"}))
            assert any(item["source_event"] == source for item in history["items"])
            save(foreground / "history-query.json", history)
            assert rows("SELECT count(*) FROM host_calls WHERE method='media.process'") == [(1,)]
            assert upstream.wires.empty()
            witnesses.extend([{"case": "other_person_quote", "event": quoted, "source": source},
                              {"case": "paired_receivers", "native": [101, 901], "event": source}])

            bad = record(a, 104, "corrupt-media-key", b"unrecognizable audio")
            wire, _, pending = receive(main, "malformed")
            assert f'\\"source_event\\":{bad},\\"state\\":\\"not_ready\\"' in wire
            reply(pending, "metadata received")
            completed(bad)
            assert upstream.wires.empty() and not rows("SELECT text FROM history_transcripts WHERE source=?", bad)
            witnesses.append({"case": "invalid_audio", "event": bad})

            stalled = record(a, 105, "slow-asr-key", recording)
            _, _, answer = receive(upstream, "asr-timeout")
            wire, _, pending = receive(main, "timeout")
            assert f'\\"source_event\\":{stalled},\\"state\\":\\"not_ready\\"' in wire
            answer.put(({"error": "fixture rejected original request"}, 0, 503))
            reply(pending, "metadata received")
            stalled_root = completed(stalled)
            until(lambda: rows("SELECT m.state FROM model_attempts m JOIN model_requests r ON r.id=m.logical "
                               "WHERE r.root=? AND r.id LIKE 'plugin-aux:%' AND m.state='rejected'", stalled_root))
            assert not rows("SELECT text FROM history_transcripts WHERE source=?", stalled)
            witnesses.append({"case": "bounded_wait_and_provider_rejection", "event": stalled, "root": stalled_root})

            revoked = record(a, 106, "revoked-asr-key", recording)
            _, _, answer = receive(upstream, "asr-forget")
            erased = owner.cli("operator", "privacy", "erase", "foreground-voice-forget", actor, json.dumps([revoked]))
            reply(answer, "late speech must not be indexed")
            until(lambda: rows("SELECT source FROM invalidated_sources WHERE source=?", revoked))
            until(lambda: rows("SELECT count(*) FROM host_calls WHERE method='media.process' AND state='dispatched'")[0][0] == 0)
            assert not rows("SELECT text FROM history_transcripts WHERE source=?", revoked)
            assert main.wires.empty() and upstream.wires.empty()
            witnesses.append({"case": "forget_during_asr", "event": revoked, "receipt": erased})
    save(foreground / "qq-get-record.json", calls)
    assert not list(temporary.iterdir())
    return "asr-source.json", {"status": "PASS", "card_status": "UNPUBLISHED_ORIGINAL_MAIN_REPLAY",
        "published": False, "host": owner.evidence(), "extension_package_sha256": expected["sha256"],
        "fixture_commit": lock["source_commit"], "model_fixture": "loopback Chat Completions",
        "gateway_fixture": "two authenticated OneBot sockets; pinned FFmpeg MP3 stands in for adapter output",
        "distinct_host_call": "distinct-call/distinct-call.json", "paid_calls": 0, "cases": witnesses,
        "pending": ["published producer and plugin tuple", "SILK conversion by the actual QQ adapter"]}
