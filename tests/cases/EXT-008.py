"""Codex app-server parity, using the installed Connector and local native peer."""
from driver_case import installed_case


def run(root, output):
    original = "tests/test_codex_driver.py::"
    nodes = [
        original + "test_original_turn_steer_queue_cancel_and_detach_have_distinct_effects",
        original + "test_native_request_exact_original_and_cannot_answer_twice",
        original + "test_selected_cli_prepares_default_owner_then_uses_only_its_proxy",
        "tests/test_codex_contract.py",
        "tests/test_codex_discovery.py",
    ]
    return "codex-driver-wire.json", installed_case(root, output, "codex_wire.py", nodes)
