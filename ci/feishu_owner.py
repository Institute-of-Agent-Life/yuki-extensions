"""Classify original Feishu owners without writing the selected legacy data."""

import hashlib
import json
from contextlib import closing
from pathlib import Path
import sqlite3

BASELINE = "329ca7c487414d2f54ddd98ff4727446ed2446cd"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_fixture(root):
    folder = root / "tests/fixtures/feishu-owner"
    lock = json.loads((folder / "source.lock.json").read_bytes())
    if lock["baseline"] != BASELINE:
        raise ValueError("different legacy source")
    for name, expected in lock["files"].items():
        path = folder / name
        if path.parent != folder or path.is_symlink() or digest(path) != expected:
            raise ValueError("legacy owner fixture differs")
    oracle = json.loads((folder / "original-owner-oracle.json").read_bytes())
    if (
        oracle["source_commit"] != BASELINE
        or oracle["status"] != "PASS"
        or oracle["exit_code"] != 0
    ):
        raise ValueError("legacy owner oracle did not pass")
    return folder, lock, oracle


def private_inventory(directory):
    directory = Path(directory)
    if not directory.exists():
        return {
            "status": "UNKNOWN",
            "reason": "private directory not observed",
            "files": None,
        }
    if directory.is_symlink() or not directory.is_dir():
        return {
            "status": "BLOCKED",
            "reason": "private path is not an original directory",
            "files": None,
        }
    # Every entry needs an original reader. Empty directories also retain their presence.
    items = sorted(
        path.relative_to(directory).as_posix() for path in directory.iterdir()
    )
    return {
        "status": "BLOCKED" if items else "EMPTY_VERIFIED",
        "files": items,
        "reason": (
            "additional private entries require their original reader"
            if items
            else "observed empty private directory"
        ),
    }


def original_receipts(database, platform, application):
    database = Path(database).resolve()
    if platform not in {"feishu", "lark"} or not application or ":" in application:
        raise ValueError("invalid original application scope")
    if any(
        Path(str(database) + suffix).exists() for suffix in ["-wal", "-shm", "-journal"]
    ):
        raise ValueError("supply a closed consistent legacy snapshot")
    before = digest(database)
    with closing(
        sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True)
    ) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN")
        rows = [
            dict(row)
            for row in conn.execute(
                "SELECT r.ingress_account_id,r.transport_namespace,r.ingress_presence_id,r.event_type,"
                "r.ingress_key,r.canonical_event_id,a.platform,a.external_account_id "
                "FROM canonical_event_receipts r JOIN accounts a ON a.id=r.ingress_account_id "
                "WHERE a.platform=? AND substr(a.external_account_id,1,?)=? ORDER BY r.id",
                (platform, len(application) + 1, application + ":"),
            )
        ]
    if digest(database) != before or any(
        Path(str(database) + suffix).exists() for suffix in ["-wal", "-shm", "-journal"]
    ):
        raise ValueError("legacy snapshot changed during inventory")
    return {
        "database_sha256": before,
        "platform": platform,
        "application": application,
        "rows": rows,
        "count": len(rows),
        "owner": "legacy core SQLite",
        "handoff": "CORE-041 instance mapping",
        "tenant_from_receipt": None,
    }


def report(private_directory, original):
    inventory = private_inventory(private_directory)
    return {
        "schema_revision": 1,
        "source_commit": BASELINE,
        "status": (
            "BLOCKED"
            if inventory["status"] != "EMPTY_VERIFIED"
            else "VERIFIED_DEVELOPMENT_DISPOSITION"
        ),
        "private_inventory": inventory,
        "rebuildable": [
            {
                "state": "incomplete native WebSocket fragments",
                "storage": "process memory",
                "end": "disconnect or expiry",
            },
            {
                "state": "tenant access token",
                "storage": "process memory",
                "end": "expiry, rejection or forget",
            },
            {
                "state": "selected resource and upload pages",
                "storage": "process memory",
                "end": "completion, failure or forget",
            },
        ],
        "authoritative_elsewhere": [
            {"state": "original admission and native delivery receipts", **original},
            {
                "state": "deployment secret",
                "legacy_reference": "env:FEISHU_APP_SECRET",
                "candidate_reference": "env:YUKI_FEISHU_APP_SECRET",
                "values_exported": False,
                "owner": "original deployment configuration",
            },
        ],
        "field_review": [
            "Original receipt schema has no tenant field. Bind the original deployment tenant in CORE-041.",
            "The deployed private directory and deployment secret reference require instance-specific evidence.",
        ],
        "private_rows_imported": 0,
        "cursor_created": False,
        "deployment_migration_complete": False,
    }
