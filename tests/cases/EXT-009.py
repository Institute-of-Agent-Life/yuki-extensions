"""Check Claude native SDK transport, permissions, stream end and history ownership."""
from driver_case import installed_case


def run(root, output):
    nodes = ["tests/test_claude_contract.py", "tests/test_claude_driver.py"]
    return "claude-driver-wire.json", installed_case(root, output, "native_case.py", nodes)
