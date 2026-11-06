"""Observe the installed original Connector; no driver/backend replacements."""
import asyncio
from dataclasses import replace
import importlib.metadata
import json
from pathlib import Path
import ssl
import sys

from websockets.asyncio.client import connect
from yuki_agent_connector.config import Config, Instance
from yuki_agent_connector.connector import Connector
from yuki_agent_connector.journal import Journal


async def main():
    private, control = map(Path, sys.argv[1:3])
    settings = json.loads(private.read_bytes())
    specs = [Instance(item['id'], 'codex', item.get('label', item['id']), 'fixture')
             for item in settings.get('instances', [])]
    config = Config(settings['url'], settings['device_id'], settings['token'], specs)
    namespace = config.device_id  # Original CLI's journal owner, independent of URL.
    journal = Journal(private.with_suffix('.db'), namespace=namespace)
    connector = Connector(config, journal)
    automatic = settings.get('automatic', False)
    assert not automatic or not specs  # No native program is started by the renewal case.

    async def commands(owner, initial_socket=None):
        sequence, seen, previous = 0, 0, None
        while not owner.done():
            socket = initial_socket or connector.stream
            initial_socket = None
            if socket is not None and socket is not previous:
                previous = socket
                seen += 1
                secure = socket.transport.get_extra_info('ssl_object')
                tls = None if secure is None else {'version': secure.version(),
                    'certificate_required': secure.context.verify_mode == ssl.CERT_REQUIRED,
                    'hostname_check': secure.context.check_hostname}
                value = {'journal_namespace': namespace, 'connector_version':
                    importlib.metadata.version('yuki-agent-connector'), 'tls': tls,
                    'connection': seen, 'automatic_run': automatic,
                    'owner_stopped': connector.stopped.is_set()}
                (control / f'connection-{seen}.json').write_text(json.dumps(value), encoding='utf-8')
                if seen == 1:
                    (control / 'connected.json').write_text(json.dumps(value), encoding='utf-8')
            path = control / f'command-{sequence + 1}.json'
            if path.exists():
                command = json.loads(path.read_bytes())
                if command['action'] == 'catalog':
                    connector.config = replace(connector.config, instances=[
                        Instance(x['id'], 'codex', x.get('label', x['id']), 'fixture')
                        for x in command['instances']])
                    connector.catalog_changed.set()
                elif command['action'] == 'close':
                    if automatic:
                        connector.stopped.set()
                    if socket is not None:
                        await socket.close()
                elif command['action'] == 'event':
                    journal.append({'type': 'event', 'event_id': command['id'], 'kind': 'progress',
                                    'operation_id': 'not-an-authorized-work', 'payload': {'text': 'retained'}})
                    connector.pending_events.set()
                else:
                    raise RuntimeError('invalid fixture command')
                sequence += 1
            await asyncio.sleep(.05)
        try:
            await owner
        except Exception as error:
            received = getattr(error, 'rcvd', None)
            (control / 'closed.json').write_text(json.dumps({'kind': type(error).__name__,
                'code': getattr(received, 'code', None), 'reason': getattr(received, 'reason', None)}), encoding='utf-8')
        (control / 'result.json').write_text(json.dumps({'journal_namespace': namespace,
            'pending_event': journal.next_event() is not None, 'connections_seen': seen,
            'automatic_run': automatic, 'owner_stopped': connector.stopped.is_set()}), encoding='utf-8')

    try:
        if automatic:
            owner = asyncio.create_task(connector.run())
            await commands(owner)
        else:
            async with connect(config.url, additional_headers={'Authorization': 'Bearer ' + config.token},
                               open_timeout=15, close_timeout=2) as socket:
                await commands(asyncio.create_task(connector.connection(socket)), socket)
    finally:
        journal.close()


if __name__ == '__main__':
    asyncio.run(main())
