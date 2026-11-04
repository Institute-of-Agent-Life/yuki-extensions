"""Consume actual versioned Host bytes with the Rust media processor and original decoders."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
import zipfile

from personal_preview import Owner


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def prepare(root, output):
    lock = json.loads((root / "plugins/media/packaging/codecs.lock").read_bytes())
    wheels = Path(os.environ["YUKI_MEDIA_CODEC_WHEELS"])
    backend = output / "work" / "codecs"
    python = backend / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    owner = Owner(
        root,
        output,
        "media",
        ["media.process", "media.open", "media.publish", "forget.owner"],
        contract="core-038",
        environment={
            "YUKI_MEDIA_PYTHON": str(python),
            "YUKI_MEDIA_FFMPEG": str(backend / "ffmpeg.exe"),
            "YUKI_MEDIA_TEMP": str(backend / "temporary"),
        },
        relay="media_stdio.py",
        command_timeout=40,
    )
    backend.mkdir()

    def execute(*args):
        p = subprocess.run(args, text=True, capture_output=True, timeout=90)
        if p.returncode:
            raise RuntimeError(
                f"codec setup command failed {str(args[:2])}: {p.stderr[-350:]}"
            )
        return p.stdout

    execute("uv", "venv", "--python", sys.executable, str(backend))
    packages = []
    for item in lock["document_backend"]["packages"].values():
        wheel = wheels / item["filename"]
        assert sha(wheel) == item["sha256"]
        packages.append(str(wheel))
    execute(
        "uv",
        "pip",
        "install",
        "--python",
        str(python),
        "--no-index",
        "--no-deps",
        *packages,
    )
    ff = lock["ffmpeg"]["platforms"]["windows-x86_64"]
    wheel = wheels / ff["filename"]
    assert sha(wheel) == ff["sha256"]
    with zipfile.ZipFile(wheel) as z:
        binary = z.read(ff["member"])
    ffmpeg = backend / "ffmpeg.exe"
    ffmpeg.write_bytes(binary)
    assert sha(ffmpeg) == ff["binary_sha256"]
    temporary = backend / "temporary"
    temporary.mkdir()
    # Independent original decoder fixtures. The core owns only the copied inputs.
    make = root / "tests/peers/media_fixtures.py"
    execute(python, str(make), str(backend))
    execute(
        str(ffmpeg),
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=red:s=80x60:r=2:d=6",
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(backend / "video.mp4"),
    )
    codec_version = execute(str(ffmpeg), "-version").splitlines()[0]
    inputs = owner.data / "media-inputs"
    inputs.mkdir(exist_ok=True)
    actor = str(uuid.uuid4())
    records = []

    def op(*args):
        result = owner.cli("operator", *map(str, args))
        records.append({"command": list(map(str, args[:3])), "result": result})
        return result

    def snapshot():
        return [json.loads(line) for line in owner.trace.read_text().splitlines()]

    def event(name, selected="good.pdf"):
        frame = {
            "source": name,
            "account": user["account"],
            "bot_stage": bot["assignment"],
            "kind": "message",
            "reply_bot": "100",
            "occurred": 100,
            "observed": 100,
            "segments": [
                {"type": "media", "kind": "file", "reference": "unselected-" + name},
                {"type": "media", "kind": "file", "reference": "selected-" + name},
            ],
        }
        eid = op("ingress", "record", json.dumps(frame), "--accept")["event"]
        ex = op("ingress", "claim", eid)["execution"]
        for slot, filename, ref in [
            (0, "unselected.pdf", "unselected-" + name),
            (1, selected, "selected-" + name),
        ]:
            (inputs / filename).write_bytes((backend / filename).read_bytes())
            cached = op(
                "media",
                "cache-file",
                ex,
                actor,
                eid,
                slot,
                bot["assignment"],
                ref,
                filename,
            )
            assert cached["digest"] == sha(inputs / filename)
        return eid, ex

    def process(e, ex, name, purpose="inspect"):
        return op(
            "host",
            "process",
            "media",
            ex,
            actor,
            name,
            json.dumps({"event": e, "slot": 1}),
            purpose,
        )

    with owner.running():
        op("person", "create", actor)
        user = op(
            "account",
            "open",
            "qq",
            "media-fixture",
            "200",
            1,
            "--person",
            actor,
            "--start",
            1,
        )
        bot = op("account", "open", "qq", "media-fixture", "100", 1, "--start", 1)
        e, ex = event("pdf")
        pdf = process(e, ex, "pdf")
        assert pdf["state"] == "confirmed"
        data = pdf["result"]["data"]
        assert data["source"] == {"event": e, "slot": 1} and data["version"] == sha(
            backend / "good.pdf"
        )
        assert (
            "Selected page one" in data["text"] and "Selected page two" in data["text"]
        )
        assert (
            "[page 1]" in data["text"]
            and "[page 2]" in data["text"]
            and "UNSELECTED" not in data["text"]
        )
        faults = {}
        for name, file in [
            ("corrupt", "corrupt.pdf"),
            ("encrypted", "encrypted.pdf"),
            ("empty", "empty.pdf"),
        ]:
            fe, fx = event(name, file)
            faults[name] = process(fe, fx, name)
            assert faults[name]["result"]["ok"] is False
        ve, vx = event("video", "video.mp4")
        video = process(ve, vx, "frames", "frames")
        assert video["state"] == "confirmed" and video["result"]["ok"] is True
        images = video["result"]["data"]
        assert (
            len(images["frames"]) == 2
            and images["frames"][0]["seconds"] == 0
            and images["frames"][1]["seconds"] == 5
        )
        assert len(images["images"]) == 2
        re, rx = event("erase-race")
        with ThreadPoolExecutor(max_workers=1) as pool:
            active = pool.submit(process, re, rx, "erase-race")
            deadline = time.monotonic() + 15
            while (
                not (owner.work / "control/held").exists()
                and time.monotonic() < deadline
            ):
                if active.done():
                    raise AssertionError("race completed before second chunk was held")
                time.sleep(0.02)
            assert (owner.work / "control/held").exists()
            # The current media.open does not itself register an owner obligation.
            # Exercise the real callback via the protected operator registration.
            op("privacy", "acquire", "media", "volatile-decoder-fixture", re)
            erased = op("privacy", "erase", "remove-original", actor, json.dumps([re]))
            (owner.work / "control/release").touch()
            late = active.result(timeout=15)
            assert late.get("result") is None or late["result"].get("ok") is False
        denied = owner.command(
            "operator",
            "host",
            "process",
            "media",
            rx,
            actor,
            "retry-erased",
            json.dumps({"event": re, "slot": 1}),
            "inspect",
        )
        assert denied.returncode != 0
        deadline = time.monotonic() + 8
        while (
            op("privacy", "pending", "media")["obligations"]
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)
        assert not op("privacy", "pending", "media")["obligations"]
        assert not list(temporary.iterdir())
        wire = snapshot()
        media_calls = [
            r["frame"]["params"]
            for r in wire
            if r["frame"].get("method") == "media.process"
        ]
        assert all(c["arguments"]["media"]["slot"] == 1 for c in media_calls)
        assert len(media_calls) == 6
        opens = [r["frame"] for r in wire if r["frame"].get("method") == "media.open"]
        assert all(
            o["params"]["handle"] in {c["handle"] for c in media_calls} for o in opens
        )
        assert any(r["frame"].get("method") == "forget.request" for r in wire)
    receipt = {
        **owner.evidence(),
        "status": "PASS",
        "card_status": "UNPUBLISHED_DECODE_CANDIDATE",
        "codecs": {
            "ffmpeg": codec_version,
            "ffmpeg_sha256": sha(ffmpeg),
            "document_lock": lock["document_backend"],
            "document_source_sha256": sha(
                root / "plugins/media/backend/document_reader.py"
            ),
        },
        "pdf": pdf,
        "video": video,
        "faults": faults,
        "erasure": {"late": late, "new_call_denied": True, "temporary_empty": True},
        "selected_slot": 1,
        "media_calls": len(media_calls),
        "media_reads": len(opens),
        "operator_transcript": records,
        "pending": [
            "original model pixel presentation through a selected profile",
            "automatic volatile media ownership registration; this callback fixture uses operator privacy acquire",
            "public producer release and full cross-platform runtime",
        ],
    }
    # Current decoder uses ephemeral files only. Shared transcripts have a separate core owner.
    disposition = {
        "synthetic_old_cache": {
            "classification": "discardable_cache",
            "proof": "decoded a synthetic source with the pinned original reader; isolated temporary directory empty after calls and erase",
        },
        "shared_transcripts": {
            "classification": "other_authoritative_owner",
            "owner": "yuki-core",
            "copied": False,
        },
        "empty_private_store": {
            "classification": "empty_private_store",
            "proof": "new media installation creates no persistent plugin database",
        },
        "deployed_unknown_data": {
            "classification": "inspection_required",
            "imported": False,
        },
    }
    (output / "owner-disposition.json").write_text(
        json.dumps(disposition, indent=2) + "\n"
    )
    return "media-inspection.json", receipt


def run(root, output):
    return "media-inspection.json", {
        "status": "BLOCKED",
        "card_status": "AWAITING_PUBLIC_MEDIA_RELEASE_AND_MODEL_PRESENTATION",
    }
