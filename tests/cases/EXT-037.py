"""Real trace query and versioned export replay."""
import os

from control_intake import prepare as exercise


def prepare(root, output):
    export = os.environ.get('YUKI_TRACE_EXPORT') == '1'
    name = 'trace-export.json' if export else 'trace-query.json'
    return name, exercise(root, output, real_plugin=True, export=export)


def run(root, output):
    raise RuntimeError('EXT-037 full acceptance needs public trace subscription and retention/forget; use --preparation for query and export')
