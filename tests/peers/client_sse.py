"""Read original Client9 SSE frames; SSE ids are never durable cursors."""
from http.client import HTTPConnection
import json
import threading
import time


class Stream:
    def __init__(self, address, token, headers=None):
        self.connection = HTTPConnection(address, timeout=12)
        self.connection.request('GET', '/client/v1/stream', headers={
            'Authorization': 'Bearer ' + token, 'Accept': 'text/event-stream', **(headers or {})})
        self.response = self.connection.getresponse()
        assert self.response.status == 200, self.response.status
        assert self.response.getheader('Content-Type').split(';')[0] == 'text/event-stream'
        self.frames, self.error = [], None
        self.ended = threading.Event()
        self.thread = threading.Thread(target=self.read, daemon=True)
        self.thread.start()

    def read(self):
        frame, data = {}, []
        try:
            while line := self.response.readline():
                line = line.decode('utf-8').rstrip('\r\n')
                if not line:
                    if data:
                        frame['data'] = json.loads('\n'.join(data))
                        self.frames.append(frame)
                    frame, data = {}, []
                elif not line.startswith(':'):
                    name, _, value = line.partition(':')
                    value = value.removeprefix(' ')
                    if name == 'data': data.append(value)
                    else: frame[name] = value
        except Exception as error:
            self.error = type(error).__name__
        finally:
            self.ended.set()

    def wait(self, predicate, label):
        until = time.monotonic() + 12
        while time.monotonic() < until:
            result = next((f for f in self.frames if predicate(f)), None)
            if result is not None: return result
            if self.ended.is_set(): break
            time.sleep(.02)
        raise AssertionError(f'SSE {label}: {self.frames}, {self.error}')

    def close(self):
        self.connection.close()
