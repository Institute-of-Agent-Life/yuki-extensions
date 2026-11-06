"""Real trace query candidate; full private-store acceptance is still gated."""
from control_intake import prepare as exercise


def prepare(root, output):
    return 'trace-query.json', exercise(root, output, real_plugin=True)


def run(root, output):
    raise RuntimeError('EXT-037 full acceptance needs public trace retention/forget and export contracts; use --preparation for the implemented query candidate')
