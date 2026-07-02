"""Run one cabt self-play match for the Bundle in the CWD — a clean-room subprocess.

Invoked by check_deployability with cwd set to the extracted Bundle. Because it loads
`cg`/`common`/`main` from the CWD in a fresh interpreter, it verifies the Bundle is
self-contained (nothing leaks in from src/). See ADR-0010.

Usage: python _run_bundle.py [replay_json_path]
Prints `STATUSES=<json>`; exits 0 iff both seats finished DONE.
"""
import importlib.util
import json
import logging
import os
import sys

sys.path.insert(0, os.getcwd())  # the extracted Bundle

# Silence kaggle_environments' noisy one-time env discovery: INFO logging (global disable — the
# library resets its own logger level on import) + native open_spiel stderr dump (fd-level).
logging.disable(logging.INFO)
sys.stdout.flush()
sys.stderr.flush()
_dn = os.open(os.devnull, os.O_WRONLY)
_saved = os.dup(1), os.dup(2)
os.dup2(_dn, 1)
os.dup2(_dn, 2)
try:
    from kaggle_environments import make
finally:
    os.dup2(_saved[0], 1)
    os.dup2(_saved[1], 2)
    for _fd in (_dn, *_saved):
        os.close(_fd)
    logging.disable(logging.NOTSET)
    _klog = logging.getLogger("kaggle_environments")
    _klog.handlers[:] = [logging.NullHandler()]
    _klog.setLevel(logging.WARNING)
    _klog.propagate = False


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(os.getcwd(), "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.agent


env = make("cabt")
env.run([_load("_b0"), _load("_b1")])
statuses = [s["status"] for s in env.state]
print("STATUSES=" + json.dumps(statuses))
if any(s != "DONE" for s in statuses) and len(sys.argv) > 1:
    with open(sys.argv[1], "w", encoding="utf-8") as fh:
        json.dump(env.toJSON(), fh)
sys.exit(0 if all(s == "DONE" for s in statuses) else 1)
