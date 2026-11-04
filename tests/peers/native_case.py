"""Collect named contract observations and pytest outcomes from installed drivers."""
import argparse
import json
from importlib.metadata import version
from pathlib import Path

import pytest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("nodes", nargs="+")
    args = parser.parse_args()
    cases = {}

    class Results:
        def pytest_runtest_logreport(self, report):
            case = cases.setdefault(report.nodeid, {})
            case[report.when] = report.outcome
            case.update(report.user_properties)

    status = pytest.main(["-q", *args.nodes], plugins=[Results()])
    args.output.write_bytes((json.dumps({"distribution": version("yuki-agent-connector"),
        "cases": cases}, indent=2) + "\n").encode())
    return int(status)


if __name__ == "__main__":
    raise SystemExit(main())
