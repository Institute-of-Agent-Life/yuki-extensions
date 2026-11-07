from pathlib import Path
import concurrent.futures,json,subprocess,fcntl

gate=Path(__file__).resolve().parent
meta=json.loads((gate/'feishu-owner-01.json').read_bytes())
core=Path('/Volumes/huawei/項目實戰/yuki-core')

def macos():
    subprocess.run(['python3.12',str(gate/'verify_owner.py'),meta['archive'],meta['sha256'],str(gate/'macos-owner-01')],check=True)

def linux():
    docker=['docker','--context','desktop-linux'];name='yuki-ext-feishu-owner-01'
    subprocess.run([*docker,'run','--detach','--name',name,'--network','none','--mount',f'type=bind,src={gate},dst=/gate,readonly','sha256:dfe19032c767b42cc4aebabea1b31da06a5443feb8e15f84cd756f5e12b2b866','python3','/gate/verify_owner.py','/gate/'+Path(meta['archive']).name,meta['sha256'],'/tmp/feishu-owner-01'],check=True)
    result=subprocess.check_output([*docker,'wait',name],text=True).strip()
    with (gate/'linux-owner-01.log').open('xb') as log:subprocess.run([*docker,'logs',name],stdout=log,stderr=subprocess.STDOUT,check=True)
    assert result=='0',(gate/'linux-owner-01.log').read_text()
    subprocess.run([*docker,'cp',name+':/tmp/feishu-owner-01/evidence.zip',str(gate/'linux-owner-01.zip')],check=True)
    subprocess.run([*docker,'rm',name],check=True)
    print('Linux PASS',flush=True)

def windows():
    with (core/'.cache/local-ci-windows.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        remote='D:/yuki-extension-tests/feishu-owner-20261107-01'
        subprocess.run(['ssh','hjw','cmd','/c','mkdir',remote.replace('/','\\')],check=True)
        subprocess.run(['scp','-q',meta['archive'],str(gate/'verify_owner.py'),'hjw:'+remote+'/'],check=True)
        with (gate/'windows-owner-01.log').open('xb') as log:
            result=subprocess.run(['ssh','hjw','py','-3.12',remote+'/verify_owner.py',remote+'/'+Path(meta['archive']).name,meta['sha256'],remote+'/owner-01'],stdout=log,stderr=subprocess.STDOUT)
        assert result.returncode==0,(gate/'windows-owner-01.log').read_text()
        subprocess.run(['scp','-q','hjw:'+remote+'/owner-01/evidence.zip',str(gate/'windows-owner-01.zip')],check=True)
        print('Windows PASS',flush=True)

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    tasks=[pool.submit(fn) for fn in [macos,linux,windows]]
    for task in tasks:task.result()
print('Three native owner readers PASS',flush=True)
