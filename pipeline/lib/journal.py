"""Durable journal — the execution-durability core of the resilience layer (Phase 1).

One append-only journal per use case at ``<state_dir>/<slug>/journal.jsonl``. Every line is a
COMPLETED boundary the supervisor can resume from:

    {"ts", "stage", "step", "status", "idempotency_key", "sha", "caused_by", "note"}

The supervisor uses it to (a) RESUME — skip stages already marked ``ok`` — and (b) guarantee a
side-effecting stage (push / provision / docker) never runs twice. This is the hand-rolled Option-1
journal from PIPELINE_RESILIENCE_PLAN.md; it is framework-agnostic, so the Agent-SDK harness (the
"brain") sits on top of it and it can later be swapped for DBOS without touching the harness.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

OK = "ok"
FAIL = "fail"
UNVERIFIED = "unverified"
SKIPPED = "skipped"


def _dir(settings: dict, slug: str) -> Path:
    d = Path(os.path.expanduser(settings["state_dir"])) / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def _journal(settings: dict, slug: str) -> Path:
    return _dir(settings, slug) / "journal.jsonl"


def append(settings: dict, slug: str, stage: str, status: str, *, step: str = "",
           idempotency_key: str = "", sha: str = "", caused_by: str = "", note: str = "") -> dict:
    """Append one boundary. ``ts`` is stamped here so callers never pass a clock."""
    entry = {"ts": round(time.time(), 3), "stage": stage, "step": step, "status": status,
             "idempotency_key": idempotency_key, "sha": sha, "caused_by": caused_by, "note": note}
    with _journal(settings, slug).open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def entries(settings: dict, slug: str) -> list[dict]:
    p = _journal(settings, slug)
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def last(settings: dict, slug: str, stage: str) -> dict | None:
    """Most recent journal entry for a stage (or None)."""
    hit = None
    for e in entries(settings, slug):
        if e.get("stage") == stage:
            hit = e
    return hit


def is_done(settings: dict, slug: str, stage: str, idempotency_key: str = "") -> bool:
    """True if this stage has an ``ok`` boundary. When an idempotency key is given it must match —
    so a stage whose inputs changed (new key) is NOT considered done and will re-run."""
    for e in entries(settings, slug):
        if e.get("stage") == stage and e.get("status") == OK:
            if not idempotency_key or e.get("idempotency_key") == idempotency_key:
                return True
    return False


def next_stage(settings: dict, slug: str, order: list[str]) -> str | None:
    """First stage in ``order`` without an ``ok`` boundary — the resume cursor."""
    for stage in order:
        if not is_done(settings, slug, stage):
            return stage
    return None


def invalidate_from(settings: dict, slug: str, order: list[str], stage: str) -> None:
    """Mark ``stage`` and everything downstream as needing a re-run (a redirect/rewind directive).
    We don't delete history — we append a ``skipped`` marker so ``is_done`` stops returning True."""
    try:
        idx = order.index(stage)
    except ValueError:
        return
    for s in order[idx:]:
        if is_done(settings, slug, s):
            append(settings, slug, s, SKIPPED, note="invalidated by rewind/redirect")


# ---- HALT packet (Phase 1: recovery stays in-automation, resumable by a fresh process) ----

def write_halt(settings: dict, slug: str, packet: dict) -> Path:
    packet = {"ts": round(time.time(), 3), **packet}
    p = _dir(settings, slug) / "HALT.json"
    p.write_text(json.dumps(packet, indent=2))
    return p


def read_halt(settings: dict, slug: str) -> dict | None:
    p = _dir(settings, slug) / "HALT.json"
    return json.loads(p.read_text()) if p.exists() else None


def clear_halt(settings: dict, slug: str) -> None:
    p = _dir(settings, slug) / "HALT.json"
    if p.exists():
        p.unlink()


# ---- heartbeat (Phase 6: the communicator reads this to report "running" vs "stuck") ----

def heartbeat(settings: dict, slug: str, status: str, stage: str = "") -> None:
    p = _dir(settings, slug) / "heartbeat.json"
    p.write_text(json.dumps({"ts": round(time.time(), 3), "status": status, "stage": stage}))


def read_heartbeat(settings: dict, slug: str) -> dict | None:
    p = _dir(settings, slug) / "heartbeat.json"
    return json.loads(p.read_text()) if p.exists() else None
