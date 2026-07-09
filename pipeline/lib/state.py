"""state — the on-disk ledger. All cross-stage state lives here (+ the git repo),
so the worker is stateless between invocations: re-running a stage just re-reads
the prior stage's JSON. Idempotent recovery = re-run.
"""
from __future__ import annotations
import json, os
from pathlib import Path


def _root(settings: dict) -> Path:
    p = Path(os.path.expanduser(settings["state_dir"]))
    p.mkdir(parents=True, exist_ok=True)
    return p


def repo_dir(settings: dict, slug: str) -> Path:
    return Path(os.path.expanduser(settings["work_root"])) / slug


def reports_dir(settings: dict, slug: str) -> Path:
    d = repo_dir(settings, slug) / settings["reports_dir"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def write(settings: dict, slug: str, name: str, obj: dict) -> Path:
    """Write a stage result to <repo>/_reports/<name>.json AND mirror to the
    global ledger pipeline-state/<slug>-<name>.json (for disk-admission + resume)."""
    f = reports_dir(settings, slug) / f"{name}.json"
    f.write_text(json.dumps(obj, indent=2))
    (_root(settings) / f"{slug}-{name}.json").write_text(json.dumps(obj, indent=2))
    return f


def read(settings: dict, slug: str, name: str) -> dict | None:
    f = reports_dir(settings, slug) / f"{name}.json"
    if f.exists():
        return json.loads(f.read_text())
    return None


def phase_status(settings: dict, slug: str) -> dict:
    """What's completed on disk for this use case — drives resume + the conductor's view."""
    return {s: read(settings, slug, s) is not None
            for s in ["build", "boot", "push-main", "integrate", "verify", "push-branch"]}
