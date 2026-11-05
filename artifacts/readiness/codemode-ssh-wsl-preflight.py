"""Read-only Windows/WSL prerequisite inspection; this is not isolation acceptance."""
import argparse
import base64
import hashlib
import json
import os
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def readable(data):
    return data.decode("utf-16-le" if b"\0" in data else "utf-8", errors="replace")


def run(args, stdin=None):
    try:
        result = subprocess.run(args, input=stdin, capture_output=True, timeout=60)
        return {
            "command": args,
            "exit_code": result.returncode,
            "stdout": readable(result.stdout),
            "stderr": readable(result.stderr),
            "stdout_base64": base64.b64encode(result.stdout).decode(),
            "stderr_base64": base64.b64encode(result.stderr).decode(),
        }
    except subprocess.TimeoutExpired:
        return {"command": args, "timeout_seconds": 60}


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--distro", default="Arch")
args = parser.parse_args()
if platform.system() != "Windows":
    parser.error("Run on the Windows test host through SSH.")

candidates = [
    Path(os.environ["ProgramFiles"]) / "WSL/wsl.exe",
    Path(os.environ["LOCALAPPDATA"]) / "Microsoft/WindowsApps/wsl.exe",
]
path_wsl = shutil.which("wsl")
if path_wsl:
    candidates.append(Path(path_wsl))
selected = next((path for path in candidates if path.is_file()), None)
report = {
    "task": "EXT-023",
    "observed_utc": datetime.now(timezone.utc).isoformat(),
    "host": "hjw",
    "transport": "SSH / Windows Python / packaged WSL / Arch sh",
    "platform": platform.platform(),
    "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "windows_docker": shutil.which("docker"),
    "path_wsl": path_wsl,
    "selected_wsl": str(selected) if selected else None,
    "distro": args.distro,
    "status": "WSL_NOT_FOUND",
    "isolation_acceptance": False,
    "operations": "Read files and run inspection commands; starting the selected WSL distro may occur.",
}
wslconfig = Path.home() / ".wslconfig"
report["wslconfig"] = [
    line for line in wslconfig.read_text(encoding="utf-8-sig").splitlines()
    if line.strip().lower().startswith(("[", "memory", "processors", "kernel"))
] if wslconfig.is_file() else None
ssh_config = Path.home() / ".ssh/config"
report["windows_ssh_hosts"] = [
    line for line in ssh_config.read_text(encoding="utf-8-sig").splitlines()
    if line.strip() and line.split()[0].lower() in ("host", "hostname", "port", "include")
] if ssh_config.is_file() else []

if selected:
    report["version"] = run([str(selected), "--version"])
    report["distros"] = run([str(selected), "--list", "--verbose"])
    probe = b"""uname -srm
id
printf '\nCOMMANDS\n'
command -v docker bwrap aa-status apparmor_parser python3 cargo || true
printf '\nAPPARMOR\n'
cat /sys/module/apparmor/parameters/enabled
printf '\nPROCESS_SECURITY\n'
grep -E '^(NoNewPrivs|Seccomp|CapEff|CapBnd)' /proc/self/status
printf '\nLSM\n'
cat /sys/kernel/security/lsm 2>&1
printf '\nCMDLINE\n'
cat /proc/cmdline
printf '\nKERNEL_CONFIG\n'
if test -r /proc/config.gz; then
 zcat /proc/config.gz | grep -E '^(CONFIG_(SECCOMP|SECURITY_APPARMOR|LSM=|USER_NS|NAMESPACES)|# CONFIG_SECURITY_APPARMOR)'
fi
printf '\nPACKAGES\n'
pacman -Q apparmor bubblewrap docker python rust gcc 2>&1 || true
printf '\nSPACE\n'
df -h / /tmp
"""
    report["linux"] = run([str(selected), "-d", args.distro, "--exec", "/bin/sh"], probe)
    if report["linux"].get("exit_code") == 0:
        stdout = report["linux"]["stdout"]
        report["linux_reachable"] = True
        report["apparmor_enabled"] = "\nAPPARMOR\nY\n" in stdout
        report["apparmor_compiled"] = "CONFIG_SECURITY_APPARMOR=y" in stdout
        report["seccomp_filter_compiled"] = "CONFIG_SECCOMP_FILTER=y" in stdout
        report["status"] = (
            "LINUX_REACHABLE_NEEDS_RUNTIME_VALIDATION" if report["apparmor_enabled"]
            else "LINUX_REACHABLE_APPARMOR_DISABLED"
        )
    else:
        report["status"] = "WSL_DISTRO_PROBE_FAILED"

args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report))
