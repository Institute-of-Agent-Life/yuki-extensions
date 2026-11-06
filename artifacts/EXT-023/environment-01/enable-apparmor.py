"""Authorized, narrow change to the existing HJW WSL2 kernel configuration."""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

path = Path.home() / ".wslconfig"
original = path.read_bytes()
text = original.decode("utf-8")
assert "[wsl2]" in text and "memory=4GB" in text
assert "kernelCommandLine" not in text, "Inspect any existing kernel command line before editing."
assert text.count("[") == 1, "Inspect new sections before appending a wsl2 setting."
newline = "\r\n" if "\r\n" in text else "\n"
updated = original + (b"" if original.endswith(b"\n") else newline.encode())
updated += ("kernelCommandLine=apparmor=1 security=apparmor" + newline).encode()
wsl = "C:/Program Files/WSL/wsl.exe"
running = subprocess.run([wsl, "--list", "--running"], capture_output=True, timeout=30)
path.write_bytes(updated)
assert path.read_bytes() == updated
shutdown = subprocess.run([wsl, "--shutdown"], capture_output=True, timeout=45)
report = {
    "observed_utc": datetime.now(timezone.utc).isoformat(),
    "authorization": "User explicitly approved Arch environment setup, AppArmor, Docker/bubblewrap and necessary WSL restart.",
    "config_path": str(path),
    "before_sha256": hashlib.sha256(original).hexdigest(),
    "after_sha256": hashlib.sha256(updated).hexdigest(),
    "change": "Append kernelCommandLine=apparmor=1 security=apparmor to existing wsl2 section; preserve all original bytes.",
    "running_before": running.stdout.decode("utf-16-le" if b"\0" in running.stdout else "utf-8", "replace"),
    "shutdown_exit": shutdown.returncode,
    "shutdown_stderr": shutdown.stderr.decode("utf-8", "replace"),
}
print(json.dumps(report))
if shutdown.returncode:
    raise SystemExit(shutdown.returncode)
