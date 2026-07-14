"""Control plane + two-tier command scope (PIPELINE_RESILIENCE_PLAN §3-§4, Phase 1).

You never edit state directly — the communication agent (Claude) translates your plain-language
directive into a scoped command here, and the supervisor reads the inbox at each SAFE BOUNDARY.

Two scopes, two PHYSICALLY SEPARATE stores — so nothing is ever mixed:
  - global : <state_dir>/global/{POLICY.md, COMMANDS.jsonl}   read by EVERY use case
  - per-UC : <state_dir>/<slug>/{DIRECTIVES.md, COMMANDS.jsonl}   read only by that use case

A global command is stored ONCE; each use case applies it independently (applied-tracking is per-UC),
which is how a global directive reaches current AND future use cases. Every applied command is recorded
in the journal via ``caused_by`` for provenance.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

# command kinds the supervisor knows how to act on at a boundary
KINDS = {"pause", "resume", "abort", "autonomy", "redirect", "rewind", "override_fix", "tweak", "note"}
AUTONOMY_LEVELS = {"auto", "gated", "checkpoint"}


def _state_root(settings: dict) -> Path:
    return Path(os.path.expanduser(settings["state_dir"]))


def _global_dir(settings: dict) -> Path:
    d = _state_root(settings) / "global"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _uc_dir(settings: dict, slug: str) -> Path:
    d = _state_root(settings) / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def _commands_file(settings: dict, scope: str) -> Path:
    if scope == "global":
        return _global_dir(settings) / "COMMANDS.jsonl"
    slug = scope.split(":", 1)[1]
    return _uc_dir(settings, slug) / "COMMANDS.jsonl"


def _read_jsonl(p: Path) -> list[dict]:
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


# ---- writing a command (the communicator calls this AFTER confirming scope with the human) ----

def add_command(settings: dict, scope: str, kind: str, *, target: str = "", body: str = "") -> dict:
    """Append a scoped command. ``scope`` is 'global' or 'usecase:<slug>'; it is PINNED here, at
    capture time, so the journal never has to guess. Returns the stored command (with its id)."""
    assert kind in KINDS, f"unknown command kind {kind!r}"
    if scope != "global" and not scope.startswith("usecase:"):
        raise ValueError(f"scope must be 'global' or 'usecase:<slug>', got {scope!r}")
    f = _commands_file(settings, scope)
    n = len(_read_jsonl(f)) + 1
    cid = f"G-{n:03d}" if scope == "global" else f"{scope.split(':',1)[1]}-{n:03d}"
    cmd = {"id": cid, "ts": round(time.time(), 3), "scope": scope, "kind": kind,
           "target": target, "body": body}
    with f.open("a") as fh:
        fh.write(json.dumps(cmd) + "\n")
    return cmd


# ---- applied-tracking is PER use case (so a global command is applied once per UC) ----

def _applied_ids(settings: dict, slug: str) -> set[str]:
    p = _uc_dir(settings, slug) / "applied_commands.jsonl"
    return {r["id"] for r in _read_jsonl(p) if "id" in r}


def mark_applied(settings: dict, slug: str, cmd_id: str) -> None:
    p = _uc_dir(settings, slug) / "applied_commands.jsonl"
    with p.open("a") as fh:
        fh.write(json.dumps({"id": cmd_id, "ts": round(time.time(), 3)}) + "\n")


def pending(settings: dict, slug: str) -> list[dict]:
    """Commands this use case has not yet applied = (all global defs) + (this UC's own defs),
    minus what it already applied. Global first (the policy floor is considered before UC tweaks)."""
    applied = _applied_ids(settings, slug)
    g = _read_jsonl(_commands_file(settings, "global"))
    u = _read_jsonl(_commands_file(settings, f"usecase:{slug}"))
    return [c for c in (g + u) if c.get("id") not in applied]


# ---- the supervisor calls this at every safe boundary ----

def resolve_boundary(settings: dict, slug: str, order: list[str]) -> dict:
    """Consume pending commands and return an ACTION for the supervisor. Marks each consumed command
    applied and returns its id in ``caused_by`` so the journal records provenance. Precedence: a
    hard 'abort'/'pause' wins; otherwise the earliest rewind target (deepest re-entry) wins."""
    action = {"pause": False, "abort": False, "autonomy": None, "redirect": None,
              "rewind": None, "override_fix": False, "tweaks": [], "notes": [], "caused_by": []}
    rewind_idx = None
    for c in pending(settings, slug):
        kind, tgt = c.get("kind"), c.get("target", "")
        if kind == "pause":
            action["pause"] = True
        elif kind == "resume":
            action["pause"] = False
        elif kind == "abort":
            action["abort"] = True
        elif kind == "autonomy" and tgt in AUTONOMY_LEVELS:
            action["autonomy"] = tgt
        elif kind == "override_fix":
            action["override_fix"] = True
        elif kind in ("redirect", "rewind") and tgt in order:
            i = order.index(tgt)
            if rewind_idx is None or i < rewind_idx:
                rewind_idx = i
                action["rewind" if kind == "rewind" else "redirect"] = tgt
        elif kind == "tweak":
            action["tweaks"].append(c.get("body", ""))
        elif kind == "note":
            action["notes"].append(c.get("body", ""))
        action["caused_by"].append(c.get("id"))
        mark_applied(settings, slug, c.get("id"))
    return action


# ---- effective directive CONTEXT (injected into codegen + diagnose prompts) ----

def _read(p: Path) -> str:
    return p.read_text().strip() if p.exists() else ""


def effective_context(settings: dict, slug: str) -> str:
    """GLOBAL policy (hard floor) ⊕ per-UC directives (may override defaults) — the layered rule set,
    like CLAUDE.md global+project memory. Empty string when neither store has content."""
    policy = _read(_global_dir(settings) / "POLICY.md")
    uc = _read(_uc_dir(settings, slug) / "DIRECTIVES.md")
    parts = []
    if policy:
        parts.append("## GLOBAL POLICY (applies to every use case — a hard floor, do not violate)\n" + policy)
    if uc:
        parts.append(f"## USE-CASE DIRECTIVES ({slug} — may override defaults, never the policy floor)\n" + uc)
    return "\n\n".join(parts)
