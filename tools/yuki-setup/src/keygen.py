"""Choose the local SSHSIG verifier and bound the producer's subprocess call."""
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace


def use_pinned_verifier(module):
    if os.name == "nt":
        git = Path(os.environ["ProgramFiles"]) / "Git/usr/bin/ssh-keygen.exe"
        system = Path(os.environ["SystemRoot"]) / "System32/OpenSSH/ssh-keygen.exe"
        program = git if git.is_file() else system
    else:
        program = shutil.which("ssh-keygen")
    if not program:
        raise ValueError("OpenSSH signature verifier unavailable")

    def run(args, **kwargs):
        if args[:3] != ["ssh-keygen", "-Y", "verify"]:
            raise ValueError("unexpected signature verifier command")
        kwargs["timeout"] = min(kwargs.get("timeout") or 15, 15)
        return subprocess.run([str(program), *args[1:]], **kwargs)
    module.subprocess = SimpleNamespace(run=run)
