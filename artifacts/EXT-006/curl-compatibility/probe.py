"""Reproduce Windows curl configuration truncation using public loopback fixtures."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import subprocess
import threading

seen = []
body = json.dumps({'msg_type': 'text', 'content': json.dumps({'text': '雪\n"\\🌨' * 8330}, ensure_ascii=False, separators=(',', ':'))}, ensure_ascii=False, separators=(',', ':')).encode()
class API(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_POST(self):
        data = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        seen.append({'path': self.path, 'authorization_matches': self.headers.get('Authorization') == 'Bearer fixture-feishu-1',
                     'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
        self.send_response(200)
        self.send_header('Content-Length', '2')
        self.end_headers()
        self.wfile.write(b'{}')
server = ThreadingHTTPServer(('127.0.0.1', 0), API)
threading.Thread(target=server.serve_forever, daemon=True).start()
url = 'http://127.0.0.1:' + str(server.server_port) + '/native'
quoted = body.decode().replace('\\', '\\\\').replace('"', '\\"')
config = ('url = "' + url + '"\nrequest = "POST"\nheader = "Content-Type: application/json"\ndata = "' + quoted + '"\nheader = "Authorization: Bearer fixture-feishu-1"\n').encode()
results = {}
try:
    for name, curl, binary in [
        ('system-config', 'C:/Windows/System32/curl.exe', False),
        ('git-config', 'C:/Program Files/Git/mingw64/bin/curl.exe', False),
        ('git-binary', 'C:/Program Files/Git/mingw64/bin/curl.exe', True),
        ('system-binary', 'C:/Windows/System32/curl.exe', True),
    ]:
        before = len(seen)
        args = [curl, '--disable', '--silent', '--globoff', '--max-time', '12', '--max-filesize', '131072', '--write-out', '%{http_code}', '--noproxy', '*']
        env = dict(os.environ, YUKI_FEISHU_REQUEST_URL=url, YUKI_FEISHU_REQUEST_TOKEN='fixture-feishu-1')
        if binary:
            args += ['--variable', '%YUKI_FEISHU_REQUEST_URL', '--expand-url', '{{YUKI_FEISHU_REQUEST_URL}}', '--request', 'POST', '--variable', '%YUKI_FEISHU_REQUEST_TOKEN', '--expand-header', 'Authorization: Bearer {{YUKI_FEISHU_REQUEST_TOKEN}}', '--header', 'Content-Type: application/json', '--data-binary', '@-']
        else:
            args += ['--config', '-']
        result = subprocess.run(args, input=body if binary else config, capture_output=True, env=env, timeout=20)
        version = subprocess.check_output([curl, '--version']).decode().splitlines()[0]
        results[name] = {'version': version, 'exit_code': result.returncode, 'requests': seen[before:]}
    assert results['system-config']['requests'][0]['bytes'] == 0
    assert not results['system-config']['requests'][0]['authorization_matches']
    for name in ['git-config', 'git-binary']:
        row, = results[name]['requests']
        assert results[name]['exit_code'] == 0 and row['authorization_matches']
        assert row['bytes'] == len(body) and row['sha256'] == hashlib.sha256(body).hexdigest()
    assert results['system-binary']['exit_code'] != 0 and results['system-binary']['requests'] == []
    print(json.dumps({'status': 'PASS', 'source_sha256': hashlib.sha256(open(__file__, 'rb').read()).hexdigest(),
        'expected_bytes': len(body), 'expected_sha256': hashlib.sha256(body).hexdigest(), 'cases': results}, indent=2))
finally:
    server.shutdown()
    server.server_close()
