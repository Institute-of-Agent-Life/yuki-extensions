"""Witness original entries through the Rust Client and fixed Host."""
import sys


def prepare(root, output):
    sys.path.insert(0, str(root / 'tests/peers'))
    from client_selected import exercise
    return exercise(root, output)


def run(root, output):
    return 'original-uuid-entry.json', {
        'status': 'BLOCKED',
        'card_status': 'AWAITING_COMPLETE_H24_AND_PUBLISHED_TUPLE',
        'reason': 'Use --preparation for the pinned Client9 candidate. ACP/legacy NULL, full target conflicts and a published tuple still require evidence.',
    }
