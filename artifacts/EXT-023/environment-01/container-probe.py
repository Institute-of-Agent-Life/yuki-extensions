"""Check the prepared test environment, before any Monty worker acceptance."""
import ctypes
import json
import os
import socket
from pathlib import Path

status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines() if ":" in line)
profile = Path("/proc/self/attr/current").read_text().strip()
assert "yuki-bot-codemode" in profile and "(enforce)" in profile, profile
assert os.geteuid() == 10001
assert all(int(status[key], 16) == 0 for key in ("CapEff", "CapPrm", "CapBnd"))
assert status["NoNewPrivs"].strip() == "1"
assert status["Seccomp"].strip() == "2"
assert [name for _, name in socket.if_nameindex()] == ["lo"]
with socket.socket() as connection:
    connection.settimeout(1)
    try:
        connection.connect(("1.1.1.1", 443))
    except OSError as error:
        network_error = {"errno": error.errno, "type": type(error).__name__}
    else:
        raise AssertionError("Network escape succeeded")
try:
    Path("/var/tmp/yuki-ext023/host-only-canary").read_bytes()
except OSError as error:
    host_read_error = {"errno": error.errno, "type": type(error).__name__}
else:
    raise AssertionError("Unshared host file was visible")
try:
    Path("/etc/ext023-write-probe").write_text("should be read-only")
except OSError as error:
    root_write_error = {"errno": error.errno, "type": type(error).__name__}
else:
    raise AssertionError("Image root was writable")
libc = ctypes.CDLL(None, use_errno=True)
# x86_64 keyctl is not allowed by the pinned seccomp policy.
assert libc.syscall(250, 0, 0, 0, 0, 0) == -1 and ctypes.get_errno() == 1
print(json.dumps({
    "scope": "Prepared HJW Arch container environment; no Monty VM has run in this probe.",
    "status": "PASS",
    "apparmor": profile,
    "uid": os.geteuid(),
    "security": {key: status[key].strip() for key in ("CapEff", "CapPrm", "CapBnd", "NoNewPrivs", "Seccomp")},
    "network_interfaces": socket.if_nameindex(),
    "outbound_connection_denied": network_error,
    "host_file_unavailable": host_read_error,
    "image_write_denied": root_write_error,
    "keyctl_errno": ctypes.get_errno(),
    "ext023_acceptance": False,
}))
