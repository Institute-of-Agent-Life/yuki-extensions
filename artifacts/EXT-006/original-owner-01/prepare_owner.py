from pathlib import Path
import hashlib,json,subprocess,zipfile
repo=Path('/Volumes/huawei/項目實戰/yuki-extensions/.ci-transfer/work-feishu-owner')
gate=Path(__file__).resolve().parent
names={n for n in subprocess.check_output(['git','ls-files','-co','--exclude-standard','-z'],cwd=repo,stderr=subprocess.DEVNULL,text=True).split('\0') if n and not n.startswith('artifacts/') and not any(p.startswith('._') for p in Path(n).parts)}
locations={'src/'+n:repo/n for n in names}
locations['runner/verify_owner.py']=gate/'verify_owner.py'
files={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in sorted(locations.items())}
archive=gate/'feishu-owner-01.zip'
with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as bundle:
    bundle.writestr('source.json',json.dumps(files,indent=2)+'\n')
    for name,path in sorted(locations.items()):bundle.write(path,name)
meta={'archive':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'files':files}
(gate/'feishu-owner-01.json').write_text(json.dumps(meta,indent=2)+'\n')
print(meta['sha256'],len(files),archive.stat().st_size)
