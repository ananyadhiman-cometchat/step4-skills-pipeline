"""Diagnose → patch → re-gate loop (PIPELINE_RESILIENCE_PLAN §6 Phase 2).

Issue C from the review: any novel failure (a runtime bug, an un-encoded build signature) halted the wave
and handed off to a human — the automation degraded into a conversation. This generalises ``selfheal``
from a fixed signature list to arbitrary failures, while keeping recovery INSIDE the automation:

  1. Spin an ISOLATED git worktree on a throwaway branch (never touches the live tree mid-attempt).
  2. Hand a claude -p worker the HALT packet + the memory/context block, scoped to the failing component.
  3. Re-run ONLY the failed gate in the worktree.
  4. Green  → merge the fix back, record a LEARNING, clear the halt.
     Red    → discard the worktree; retry up to N; then ESCALATE with the packet intact.

Fixes only land after they re-gate green, so a bad fix is never committed silently. An ``override_fix``
command from the control plane skips the loop and escalates immediately (the human wants the wheel).
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

from lib import claude_runner, journal, memory, verify


def _git(repo: Path, *args: str) -> tuple[int, str]:
    p = subprocess.run(["git", "-C", str(repo), *args], text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.returncode, p.stdout.strip()


def _prompt(slug: str, comp: dict, gate_tail: str, ctx: str) -> str:
    return f"""You are the pipeline's DIAGNOSE-AND-FIX worker for use case `{slug}`.

A gate just FAILED for the `{comp['kind']}` component (stack: {comp['stack']}, dir: `{comp['dir']}/`).
Fix it so the component builds/gates clean. Change ONLY files under `{comp['dir']}/`; do not touch other
components. Prefer the smallest correct change. Do NOT commit — just edit the files.

--- FAILING GATE OUTPUT (tail) ---
{gate_tail[-3000:]}

--- PIPELINE MEMORY & DIRECTIVES (obey the global policy; reuse prior learnings) ---
{ctx[:6000]}
"""


def diagnose_and_fix(settings: dict, slug: str, repo: Path, stage: str, comp: dict,
                     halt_packet: dict, order: list[str], *, max_attempts: int = 2,
                     override: bool = False) -> dict:
    """Attempt an in-automation fix for a failed stage gate. Returns
    {landed, attempts, escalate, notes}. ``comp`` is the failing component record."""
    if override:
        return {"landed": False, "attempts": 0, "escalate": True,
                "notes": "override_fix: control plane requested human takeover"}

    logs = repo / "_logs"
    ctx = memory.session_context(settings, slug)
    gate_tail = str(halt_packet.get("gate_output", ""))
    _, base_sha = _git(repo, "rev-parse", "HEAD")
    attempts = 0

    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        wt = repo.parent / f".diagnose-{slug}-{stage}-{attempt}"
        branch = f"diagnose/{stage}-{attempt}-{int(time.time())}"
        # isolate: a fresh worktree on a throwaway branch at the current HEAD
        _git(repo, "worktree", "prune")
        code, out = _git(repo, "worktree", "add", "-b", branch, str(wt), "HEAD")
        if code != 0:
            return {"landed": False, "attempts": attempt, "escalate": True,
                    "notes": f"could not create worktree: {out[:200]}"}
        try:
            cdir = wt / comp["dir"]
            r = claude_runner.run_headless(_prompt(slug, comp, gate_tail, ctx), settings=settings,
                                           phase="B", cwd=cdir if cdir.exists() else wt,
                                           model_key="integrate", label=f"diagnose-{stage}-{attempt}",
                                           log_dir=logs)
            g = verify.build_gate(comp["kind"], cdir if cdir.exists() else wt)
            if g["buildExitCode"] == 0 and r.get("agentOk", True):
                # land it: commit in the worktree, merge back into the live branch
                _git(wt, "add", "-A")
                _git(wt, "commit", "-q", "-m", f"diagnose: fix {stage}/{comp['name']} (re-gate green)")
                _, fix_sha = _git(wt, "rev-parse", "HEAD")
                mcode, mout = _git(repo, "merge", "--no-edit", branch)
                if mcode == 0:
                    memory.append_learning(
                        settings, slug, f"Auto-fixed {stage}/{comp['name']}",
                        f"Gate `{comp['kind']}` failed; the diagnose loop patched `{comp['dir']}/` and "
                        f"re-gated green (attempt {attempt}). base={base_sha[:9]} fix={fix_sha[:9]}.")
                    journal.append(settings, slug, stage, journal.OK, sha=fix_sha,
                                   note=f"auto-fixed by diagnose loop (attempt {attempt})")
                    journal.clear_halt(settings, slug)
                    return {"landed": True, "attempts": attempt, "escalate": False,
                            "notes": f"merged {fix_sha[:9]}"}
                # merge conflict → treat as not landed; fall through to retry/escalate
                _git(repo, "merge", "--abort")
        finally:
            _git(repo, "worktree", "remove", "--force", str(wt))
            _git(repo, "branch", "-D", branch)

    # exhausted — keep the HALT packet, escalate to the communicator
    memory.append_learning(settings, slug, f"Diagnose loop exhausted at {stage}",
                           f"{max_attempts} attempts did not re-gate `{comp['kind']}` green. Escalated.")
    return {"landed": False, "attempts": attempts, "escalate": True,
            "notes": f"{max_attempts} attempts failed to re-gate green"}
