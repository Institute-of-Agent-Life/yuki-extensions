"""Compare pinned Desktop source witnesses with verified CORE-002 contracts."""
import importlib.util


def run(root, output):
    spec = importlib.util.spec_from_file_location("desktop_probe", root / "compat/desktop/probe.py")
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    return probe.run(root, output)
