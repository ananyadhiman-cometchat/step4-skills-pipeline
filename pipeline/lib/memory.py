"""Memory layer — context durability (PIPELINE_RESILIENCE_PLAN §6 Phase 3).

The Agent-SDK "brain" keeps long-term notes in markdown (the memory-tool model: files the agent reads
back on demand). Two kinds:
  - PROGRESS.md   (per-UC)  — what's done / next, derived from the journal. Cheap situational awareness.
  - LEARNINGS.md  (per-UC + global) — root-caused bugs and their fixes, so a resume (or another use
    case) never re-discovers the same thing. e.g. "avatar:null breaks CometChat provisioning".

``session_context`` bundles POLICY ⊕ DIRECTIVES ⊕ PROGRESS ⊕ recent LEARNINGS into one block that is
injected at the start of every supervisor session and every diagnose call — so nothing is lost on a halt.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from lib import directives, journal


def _state_root(settings: dict) -> Path:
    return Path(os.path.expanduser(settings["state_dir"]))


def _uc_dir(settings: dict, slug: str) -> Path:
    d = _state_root(settings) / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def _global_dir(settings: dict) -> Path:
    d = _state_root(settings) / "global"
    d.mkdir(parents=True, exist_ok=True)
    return d


def update_progress(settings: dict, slug: str, order: list[str]) -> Path:
    """Regenerate PROGRESS.md from the journal — the single source of truth for 'where are we'."""
    done = {e["stage"]: e for e in journal.entries(settings, slug) if e.get("status") == journal.OK}
    nxt = journal.next_stage(settings, slug, order)
    lines = [f"# PROGRESS — {slug}", "", "| stage | status |", "|---|---|"]
    for s in order:
        mark = "done" if s in done else ("→ next" if s == nxt else "pending")
        lines.append(f"| {s} | {mark} |")
    halt = journal.read_halt(settings, slug)
    if halt:
        lines += ["", f"**HALTED at `{halt.get('stage')}`** — {halt.get('summary', '')}"]
    p = _uc_dir(settings, slug) / "PROGRESS.md"
    p.write_text("\n".join(lines) + "\n")
    return p


def append_learning(settings: dict, slug: str, title: str, body: str, *, scope: str = "usecase") -> Path:
    """Record a durable lesson. scope='global' shares it with every use case (future ones included)."""
    d = _global_dir(settings) if scope == "global" else _uc_dir(settings, slug)
    p = d / "LEARNINGS.md"
    stamp = time.strftime("%Y-%m-%d", time.localtime())
    block = f"\n## {title} ({stamp})\n{body.strip()}\n"
    with p.open("a") as f:
        f.write(block)
    return p


def _read(p: Path, limit: int = 4000) -> str:
    if not p.exists():
        return ""
    t = p.read_text().strip()
    return t if len(t) <= limit else "…(older trimmed)…\n" + t[-limit:]


def session_context(settings: dict, slug: str) -> str:
    """The context block injected at the start of every supervisor / diagnose session."""
    parts = []
    ctx = directives.effective_context(settings, slug)
    if ctx:
        parts.append(ctx)
    prog = _read(_uc_dir(settings, slug) / "PROGRESS.md")
    if prog:
        parts.append("## PROGRESS\n" + prog)
    gl = _read(_global_dir(settings) / "LEARNINGS.md")
    if gl:
        parts.append("## GLOBAL LEARNINGS (apply to every use case)\n" + gl)
    ul = _read(_uc_dir(settings, slug) / "LEARNINGS.md")
    if ul:
        parts.append(f"## LEARNINGS ({slug})\n" + ul)
    return "\n\n".join(parts)
