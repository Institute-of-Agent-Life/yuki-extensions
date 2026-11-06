"""Run the two-package base witness through the normal acceptance command."""
from runpy import run_path


def run(root, output):
    return run_path(str(root/'ci/base-witness.py'))['run'](root, output)


prepare = run
