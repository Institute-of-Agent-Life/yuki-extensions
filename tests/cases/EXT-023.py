"""EXT-023 real native candidate; runtime image is an independent install."""
import sys


def run(root, out):
    sys.path.insert(0, str(root / "tests/peers"))
    from codemode_cases import run_cases
    report = run_cases(root, out, ["normal", "missing-runtime", "malformed-frame"])
    report["remaining"] = ["published compatible producer/runtime tuple", "full EXT-024 acceptance"]
    return "monty-sandbox.json", report
