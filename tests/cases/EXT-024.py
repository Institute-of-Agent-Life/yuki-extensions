"""EXT-024 original native receipt replay and paired unknown regression."""
import sys


def run(root, out):
    sys.path.insert(0, str(root / "tests/peers"))
    from codemode_cases import run_cases
    report = run_cases(root, out, ["before-feed", "after-feed-twice", "unknown"])
    report["remaining"] = ["light frozen alias projection without eager schemas", "Work/run futures",
                           "full H14 stop/budget and authority parity witness", "formal publication"]
    return "vm-real-resume.json", report
