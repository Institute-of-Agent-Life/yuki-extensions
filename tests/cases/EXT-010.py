"""Native direction B, using a real ACP v1 subprocess and the installed driver."""
from driver_case import installed_case


def run(root, output):
    nodes = ["tests/test_native_acp.py", "tests/test_acp_driver.py"]
    return "native-acp-v1.json", installed_case(root, output, "native_case.py", nodes)
