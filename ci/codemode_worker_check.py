"""Verify the completed Rust worker controller without promoting the unfinished Host adapter."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from handshake_cargo import vendor_sdk


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--image');p.add_argument('--contract',type=Path)
    p.add_argument('--socket',default='unix:///var/run/docker.sock');a=p.parse_args()
    root=Path(__file__).resolve().parents[1];out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    project=out/'project';project.mkdir()
    # Deliberately build the worker library only. The in-progress Host adapter
    # has no release entry until its original feed acknowledgement is accepted.
    names=['Cargo.toml','Cargo.lock','rust-toolchain.toml','src/lib.rs','src/worker.rs','tests/native_worker.rs']
    source={}
    for name in names:
        file=root/'plugins/codemode'/name;data=file.read_bytes();source[name]=hashlib.sha256(data).hexdigest()
        dest=project/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
    sdk=root/'compat/core-034/yuki-plugin-sdk-1.0.0-alpha.5.crate'
    vendor_sdk(sdk,project,project/'Cargo.lock')
    env=dict(os.environ)
    if os.name=='nt':
        tooling=Path('C:/Users/Hilbert/yuki-core-tooling')
        if tooling.exists():
            env['RUSTUP_HOME']=str(tooling/'rustup')
            env['PATH']=str(tooling/'cargo/bin')+os.pathsep+str(tooling/'winlibs/mingw64/bin')+os.pathsep+env['PATH']
    cargo=shutil.which('cargo',path=env.get('PATH'))
    if not cargo:raise RuntimeError('Rust toolchain unavailable')
    commands=[]
    def run(argv,label,extra=None):
        r=subprocess.run(argv,cwd=project,env=extra or env,capture_output=True,text=True,encoding='utf-8')
        (out/(label+'.txt')).write_text(r.stdout+r.stderr,encoding='utf-8')
        commands.append({'argv':argv,'exit_code':r.returncode,'log':label+'.txt'})
        if r.returncode:raise RuntimeError('worker check failed: '+label)
    passed=False
    try:
        run([cargo,'test','--locked','--offline','--test','native_worker'],'portable')
        if a.image:
            if platform.system()!='Linux' or not a.contract:raise RuntimeError('native Linux contract required')
            config=out/'runtime.json'
            config.write_text(json.dumps({'image_id':a.image,'docker_socket':a.socket,
                'seccomp_path':str(root/'images/monty-runtime/deploy/security/yuki-codemode-seccomp.json'),
                'contract':json.loads(a.contract.read_bytes())}),encoding='utf-8')
            binaries=[p for p in (project/'target/debug/deps').glob('native_worker-*') if p.is_file() and p.suffix=='' and os.access(p,os.X_OK)]
            if len(binaries)!=1:raise RuntimeError('expected one native test executable')
            # AppArmor profile inspection requires root; the dedicated test
            # process uses the existing daemon and never changes its policy.
            argv=['sudo','env','YUKI_CODE_RUNTIME_CONFIG='+str(config),str(binaries[0]),'--include-ignored','--nocapture']
            run(argv,'native')
        passed=True
    finally:
        report={'status':'PASS' if passed else 'FAIL','scope':'Rust native worker controller; Host composition not accepted',
            'platform':platform.platform(),'native_executed':bool(a.image),'formal_card_acceptance':False,'published':False,
            'source':source,'sdk_sha256':hashlib.sha256(sdk.read_bytes()).hexdigest(),'commands':commands}
        (out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        shutil.rmtree(project)

if __name__=='__main__':main()
