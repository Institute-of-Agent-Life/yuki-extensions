"""Build the independent Rust unit while the pinned original Manager serves its own socket."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="yuki-env-check-") as tmp:
        tmp=Path(tmp);backend=tmp/"source";state=tmp/"state";address=tmp/"manager.sock"
        spec=importlib.util.spec_from_file_location("source_package",root/"deploy/env/inspect-source.py")
        source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)
        source.extract(root/"deploy/env/manager-source.zip",root/"plugins/env/backend/source.lock.json",backend)
        peer=subprocess.Popen([sys.executable,"-I",root/"tests/peers/env_manager_probe.py",backend,state,address])
        try:
            end=time.monotonic()+15
            while not address.is_socket():
                if peer.poll() is not None or time.monotonic()>end:
                    raise RuntimeError("original Manager did not open its Unix socket")
                time.sleep(.05)
            env=dict(os.environ,YUKI_ENV_TEST_MANAGER="1",YUKI_ENV_MANAGER_SOCKET=str(address))
            subprocess.run([sys.executable,root/"ci/package.py","--unit","env","--out",args.out],env=env,check=True)
            if not (state/"observed").is_file():
                raise RuntimeError("the original Manager did not process the Rust request")
            print("Original Manager socket received environment_status. Rust returned only ready=false.")
        finally:
            peer.terminate();peer.wait(timeout=5)


if __name__=="__main__":
    main()
