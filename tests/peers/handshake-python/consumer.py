"""Exercise the installed preview SDK as an extension-side test consumer."""
from dataclasses import asdict
import json
from pathlib import Path
import sys

from yuki_plugin_sdk import Binding, Peer, encode, read_frame


def main():
    binding = Binding.from_json(json.loads(Path(sys.argv[1]).read_bytes()))
    peer = Peer(binding)
    offer = binding.offer()
    offer.optional_features.append("ext002.optional")
    out = sys.stdout.buffer
    out.write(encode(peer.request(1, offer)))
    out.flush()
    while (frame := read_frame(sys.stdin.buffer)) is not None:
        received = peer.receive(frame)
        if received.reply is not None:
            out.write(encode(received.reply))
            out.flush()
        elif received.error is not None:
            raise ValueError(received.error)
        elif received.result is not None:
            print(json.dumps({"id": received.response_id, "accepted": asdict(received.result)}),
                  file=sys.stderr)
    peer.finish()


if __name__ == "__main__":
    main()
