"""Verify the exact owner-reader inputs on one native platform."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

archive, expected, destination = sys.argv[1:]
root = Path(destination).resolve()
root.mkdir(parents=True, exist_ok=False)
assert hashlib.sha256(Path(archive).read_bytes()).hexdigest() == expected
with zipfile.ZipFile(archive) as bundle:
    assert bundle.testzip() is None
    assert all((root / name).resolve().is_relative_to(root) for name in bundle.namelist())
    bundle.extractall(root)
files = json.loads((root / 'source.json').read_bytes())
assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == files['runner/verify_owner.py']
assert all(hashlib.sha256((root / name).read_bytes()).hexdigest() == digest for name, digest in files.items())
source = root / 'src'
env = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', YUKI_SOURCE_SNAPSHOT_SHA256=expected)
commands = [
    ([sys.executable, 'ci/feishu_owner_check.py', '--out', str(root / 'evidence/standalone')], 0),
    ([sys.executable, 'ci/check.py', 'EXT-006', '--out', str(root / 'evidence/card')], 1),
]
observed = []
for index, (command, expected_code) in enumerate(commands):
    result = subprocess.run(command, cwd=source, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (root / f'command-{index}.log').write_bytes(result.stdout)
    observed.append({'command': command, 'exit_code': result.returncode, 'expected_exit': expected_code})
    assert result.returncode == expected_code, result.stdout.decode(errors='replace')
owner = json.loads((root / 'evidence/card/owners/owner-disposition-index.json').read_bytes())
manifest = json.loads((root / 'evidence/card/manifest.json').read_bytes())
assert owner['status'] == 'PASS' and owner['legacy_oracle_cases'] == 55
assert manifest['status'] == 'BLOCKED' and manifest['card_status'] == 'OWNER_VERIFIED_STRUCTURED_MENTIONS_PENDING'
for relative, digest in manifest['files'].items():
    assert hashlib.sha256((root / 'evidence/card' / relative).read_bytes()).hexdigest() == digest
assert all(hashlib.sha256((root / name).read_bytes()).hexdigest() == digest for name, digest in files.items())
(root / 'source-verification.json').write_text(json.dumps({'status': 'PASS', 'platform': sys.platform,
    'snapshot_sha256': expected, 'files': files, 'commands': observed,
    'acceptance_status': manifest['status'], 'owner_status': owner['card_status']}, indent=2)+'\n', encoding='utf8')
with zipfile.ZipFile(root / 'evidence.zip', 'x', zipfile.ZIP_DEFLATED) as bundle:
    for path in [root / 'source-verification.json', *root.glob('command-*.log'), *(root / 'evidence').rglob('*')]:
        if path.is_file() and not any(part.startswith('._') for part in path.relative_to(root).parts):
            bundle.write(path, path.relative_to(root))
print('PASS', sys.platform, hashlib.sha256((root / 'evidence.zip').read_bytes()).hexdigest())
