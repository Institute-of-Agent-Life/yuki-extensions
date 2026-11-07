"""Reproduce the EXT-006 synthetic and empty-private owner dispositions."""

import argparse
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile

from feishu_owner import digest, load_fixture, original_receipts, report


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf8")


def run(root, output):
    output.mkdir(parents=True, exist_ok=False)
    folder, lock, oracle = load_fixture(root)
    database = folder / "synthetic-legacy-core.db"
    original = original_receipts(database, "feishu", "cli_test")
    expected = json.loads((folder / "synthetic-receipts.json").read_bytes())
    assert (
        sorted(original["rows"], key=lambda row: row["canonical_event_id"])
        == sorted(expected["rows"], key=lambda row: row["canonical_event_id"])
        and original["count"] == 2
    )
    with tempfile.TemporaryDirectory(prefix="fs-owner-") as temporary:
        work = Path(temporary)
        private = work / "empty"
        private.mkdir()
        synthetic = report(private, original)
        empty = report(
            private,
            {
                "owner": "legacy core SQLite",
                "status": "NOT_INSPECTED",
                "count": None,
                "rows": None,
            },
        )
        for name, value in [("synthetic-legacy", synthetic), ("empty-private", empty)]:
            assert value["status"] == "VERIFIED_DEVELOPMENT_DISPOSITION"
            assert value["private_inventory"]["files"] == []
            assert (
                value["private_rows_imported"] == 0 and value["cursor_created"] is False
            )
            assert value["deployment_migration_complete"] is False
            write(output / name / "owner-disposition.json", value)
        missing = report(work / "missing", original)
        assert (
            missing["status"] == "BLOCKED"
            and missing["private_inventory"]["files"] is None
        )
        unknown = work / "unknown"
        unknown.mkdir()
        original_file = unknown / "private.sqlite"
        original_file.write_bytes(b"original private data")
        before = digest(original_file)
        blocked = report(unknown, original)
        assert blocked["status"] == "BLOCKED" and blocked["private_inventory"][
            "files"
        ] == ["private.sqlite"]
        assert digest(original_file) == before
        write(output / "unknown-private" / "owner-disposition.json", blocked)
        write(output / "missing-private" / "owner-disposition.json", missing)
        assert original_receipts(database, "feishu", "foreign")["rows"] == []
        assert original_receipts(database, "lark", "cli_test")["rows"] == []
        active = work / "active.db"
        shutil.copyfile(database, active)
        for suffix in ["-wal", "-shm", "-journal"]:
            sidecar = Path(str(active) + suffix)
            sidecar.write_bytes(b"original pending state")
            before = digest(sidecar)
            try:
                original_receipts(active, "feishu", "cli_test")
            except ValueError as error:
                assert "closed consistent" in str(error)
            else:
                raise AssertionError("open legacy snapshot accepted")
            assert digest(sidecar) == before
            sidecar.unlink()
        assert digest(active) == digest(database)
        malformed = work / "unsupported.db"
        with closing(sqlite3.connect(malformed)) as conn:
            conn.execute("CREATE TABLE unknown(value TEXT)")
        before = digest(malformed)
        try:
            original_receipts(malformed, "feishu", "cli_test")
        except sqlite3.DatabaseError:
            pass
        else:
            raise AssertionError("unsupported legacy schema accepted")
        assert digest(malformed) == before
        corrupt = work / "corrupt/tests/fixtures/feishu-owner"
        shutil.copytree(folder, corrupt, ignore=shutil.ignore_patterns("._*"))
        with (corrupt / "synthetic-legacy-core.db").open("ab") as stream:
            stream.write(b"changed")
        try:
            load_fixture(work / "corrupt")
        except ValueError:
            pass
        else:
            raise AssertionError("changed legacy source accepted")
    assert load_fixture(root)[1] == lock
    inputs = [
        Path(__file__).resolve(),
        root / "ci/feishu_owner.py",
        *sorted(folder.iterdir()),
    ]
    result = {
        "status": "PASS",
        "card": "EXT-006",
        "card_status": "OWNER_DISPOSITION_VERIFIED",
        "baseline": lock["baseline"],
        "legacy_oracle_cases": len(oracle["cases"]),
        "assertions": {
            "original_receipts_retained": 2,
            "original_scope_isolation": True,
            "empty_private_observed": True,
            "missing_private_unknown": True,
            "unknown_private_blocked_and_preserved": True,
            "unsupported_reader_rejected": True,
            "open_snapshot_rejected_and_preserved": True,
            "changed_fixture_rejected": True,
            "source_unchanged": True,
        },
        "source_files": {
            path.relative_to(root).as_posix(): digest(path)
            for path in inputs
            if path.is_file() and not path.name.startswith("._")
        },
        "files": {
            path.relative_to(output).as_posix(): digest(path)
            for path in sorted(output.rglob("*"))
            if path.is_file() and not path.name.startswith("._")
        },
        "deployment_inputs_pending": [
            "original deployed tenant binding",
            "deployment secret reference",
            "private directory inventory",
            "CORE-041 instance mapping",
        ],
        "deployed_data_inspected": False,
        "data_modified": False,
        "paid_calls": 0,
    }
    write(output / "owner-disposition-index.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = run(Path(__file__).resolve().parents[1], args.out.resolve())
    print(result["status"], result["card_status"])
