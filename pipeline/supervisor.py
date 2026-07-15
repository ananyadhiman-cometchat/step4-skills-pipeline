#!/usr/bin/env python3
"""Durable supervisor harness — the "brain" of the resilience layer (hybrid Option 3).

This replaces batch_runner's halt-and-return with a resumable, steerable driver:

  • DURABLE   — every completed stage is a journal boundary; a fresh invocation RESUMES from the cursor
                (``journal.next_stage``), so a crash / laptop-sleep / halt never restarts from zero.
  • STEERABLE — at each SAFE BOUNDARY it consumes the command inbox (global ⊕ per-UC) and acts:
                pause / abort / set-autonomy / redirect / rewind / override-fix / tweak / note.
  • SELF-HEALING — a codegen/build stage that fails writes a HALT packet, then runs the
                diagnose→patch→re-gate loop; it only escalates to the human when that is exhausted.
  • MEMORY    — PROGRESS + LEARNINGS are updated each step and injected into every worker session.

The "Agent SDK harness" role: the supervisor orchestrates claude -p workers (the existing stage codegen
+ the diagnose worker) and a file-based memory layer, and is itself resumable — the durable brain sitting
on the durable journal (the hands). Swap the journal for DBOS later without touching this file.

CLI (the communicator — me — drives these on your behalf):
  supervisor.py run     --use-case com [--autonomy auto|gated|checkpoint]
  supervisor.py run     --wave 1 [--autonomy ...]
  supervisor.py status  --use-case com
  supervisor.py command --scope global|usecase:com --kind redirect --target build [--body "..."]
  supervisor.py approve --use-case com      # clears the current checkpoint/gate pause, then resume
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import behavioral, diagnose, directives, journal, memory, prompts, state  # noqa: E402

# the linear stage plan (single occurrence each → clean journal keys). cp = human checkpoint after it.
PLAN = [
    {"stage": "provision-app"}, {"stage": "preflight"}, {"stage": "build"}, {"stage": "containerize"},
    {"stage": "boot"}, {"stage": "demo"}, {"stage": "push-main", "cp": "CP1"}, {"stage": "integrate"},
    {"stage": "verify"}, {"stage": "readme", "cp": "CP2"}, {"stage": "push-branch"}, {"stage": "teardown"},
]  # provision-app (create the per-UC CometChat app) is journaled so resume never re-creates it. A
#   checkpoint fires BEFORE its stage — CP1 gates the baseline push (after demo), CP2 gates the feature
#   push (after verify). Human approval of a checkpoint = the "auto-push on approval" gate.
ORDER = [p["stage"] for p in PLAN]
DIAGNOSABLE = {"build", "integrate", "demo"}          # stages a codegen fix can re-gate
SIDE_EFFECTING = {"push-main", "push-branch", "provision-app"}  # never re-run if journaled ok


def _load(name: str) -> dict:
    return json.loads((HERE / "config" / name).read_text())


def _git(repo: Path, *a: str) -> tuple[int, str]:
    p = subprocess.run(["git", "-C", str(repo), *a], text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.returncode, p.stdout.strip()


def _run_stage(slug: str, stage: str) -> int:
    return subprocess.call([sys.executable, str(HERE / "run_usecase.py"),
                            "--use-case", slug, "--stage", stage], env=dict(os.environ))


def _await_id(step: dict, autonomy: str) -> str | None:
    if autonomy == "auto":
        return None
    if autonomy == "gated":
        return f"stage:{step['stage']}"
    return f"cp:{step['cp']}" if step.get("cp") else None            # checkpoint autonomy


def _find_failing_component(S: dict, uc: dict, repo: Path):
    from lib import verify
    for c in prompts.expand_components(uc):
        cdir = repo / c["dir"]
        if not cdir.exists():
            continue
        try:
            g = verify.build_gate(c["kind"], cdir)
            if g.get("buildExitCode", 0) != 0:
                return c, g.get("outputTail", "")
        except Exception:
            continue
    return None, ""


def _halt_packet(repo: Path, slug: str, stage: str, rc: int, gate_output: str) -> dict:
    _, diff = _git(repo, "diff", "--stat")
    logs = sorted((repo / "_logs").glob(f"*{stage}*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    tail = ""
    if logs:
        tail = "\n".join(logs[0].read_text(errors="ignore").splitlines()[-40:])
    return {"slug": slug, "stage": stage, "exit": rc, "gate_output": gate_output or tail,
            "repo_diff": diff[:2000], "summary": f"stage {stage} failed (exit {rc})"}


def _behavioral_pass(S: dict, uc: dict, slug: str) -> tuple[bool, list]:
    """After verify, record the behavioral checklist (pass/fail/unverified) to the journal."""
    comps = prompts.expand_components(uc)
    v = state.read(S, uc["slug"], "verify") or {}
    results = v.get("behavioral") or {}     # verify stage may publish per-feature bools; else all unverified
    statuses = behavioral.run(comps, results)
    for s in statuses:
        journal.append(S, slug, f"behavior:{s['key']}",
                       journal.OK if s["status"] == "pass" else
                       (journal.UNVERIFIED if s["status"] == "unverified" else journal.FAIL),
                       note=s["detail"])
    return behavioral.gate(statuses), statuses


def run_usecase(S: dict, uc: dict, autonomy: str, dry: bool = False) -> str:
    # --dry-run walks the whole durable loop but stubs stage execution and writes to a SEPARATE
    # '<slug>-dryrun' state namespace, so the real use case is never touched.
    real_slug = uc["slug"]
    slug = f"{real_slug}-dryrun" if dry else real_slug
    repo = state.repo_dir(S, real_slug)
    journal.heartbeat(S, slug, "running")
    memory.update_progress(S, slug, ORDER)

    while True:
        stage = journal.next_stage(S, slug, ORDER)
        if stage is None:
            journal.heartbeat(S, slug, "done")
            memory.update_progress(S, slug, ORDER)
            print(f"✔ {slug}: complete")
            return "done"
        step = next(p for p in PLAN if p["stage"] == stage)

        # --- SAFE BOUNDARY: consume the command inbox (control plane) ---
        act = directives.resolve_boundary(S, slug, ORDER)
        cb = ",".join(act["caused_by"]) if act["caused_by"] else ""
        for note in act["notes"]:
            memory.append_learning(S, slug, "Directive note", note)
        if act["autonomy"]:
            autonomy = act["autonomy"]
        if act["abort"]:
            journal.heartbeat(S, slug, "aborted")
            print(f"■ {slug}: aborted by command {cb}")
            return "aborted"
        target = act["rewind"] or act["redirect"]
        if target:
            journal.invalidate_from(S, slug, ORDER, target)
            memory.append_learning(S, slug, f"Re-entry to {target}",
                                   f"{'rewind' if act['rewind'] else 'redirect'} caused_by {cb}")
            continue                              # re-resolve the cursor from the new re-entry point
        if act["pause"]:
            journal.heartbeat(S, slug, "paused", stage)
            print(f"⏸ {slug}: paused by command {cb} (resume with a 'resume' command)")
            return "paused"

        # --- checkpoint / gated pause (autonomy) ---
        aid = _await_id(step, autonomy)
        if aid and not journal.is_done(S, slug, f"approved:{aid}"):
            journal.heartbeat(S, slug, "awaiting", aid)
            print(f"🛑 {slug}: awaiting approval for {aid} (run: supervisor.py approve --use-case {slug})")
            return "checkpoint"

        # --- run the stage ---
        journal.heartbeat(S, slug, "running", stage)
        print(f"▶ {slug} :: {stage}")
        if dry:
            print(f"  [dry] would run stage {stage} (no codegen/docker/git executed)")
            rc = 0
        else:
            rc = _run_stage(real_slug, stage)

        if rc == 0:
            sha = "dry" if dry else _git(repo, "rev-parse", "HEAD")[1]
            journal.append(S, slug, stage, journal.OK, sha=sha, caused_by=cb)
            journal.clear_halt(S, slug)
            memory.update_progress(S, slug, ORDER)
            if stage == "verify":
                ok, statuses = _behavioral_pass(S, uc, slug)
                bad = [s for s in statuses if s["status"] != "pass"]
                if bad:
                    print("  behavioral:", ", ".join(f"{s['key']}={s['status']}" for s in bad))
                if not ok:
                    journal.write_halt(S, slug, {"slug": slug, "stage": "verify",
                                                 "summary": "a behavioral assertion FAILED",
                                                 "gate_output": json.dumps(statuses, indent=2)})
                    journal.heartbeat(S, slug, "halted", "verify")
                    return "halted"
            continue

        # --- FAILURE: HALT packet → diagnose loop → escalate ---
        comp, gate_out = (None, "")
        if stage in DIAGNOSABLE:
            comp, gate_out = _find_failing_component(S, uc, repo)
        packet = _halt_packet(repo, slug, stage, rc, gate_out)
        journal.write_halt(S, slug, packet)

        if stage in DIAGNOSABLE and comp:
            res = diagnose.diagnose_and_fix(S, slug, repo, stage, comp, packet, ORDER,
                                            max_attempts=int(S.get("max_retries", 2)),
                                            override=act["override_fix"])
            if res["landed"]:
                print(f"  ✔ diagnose landed a fix for {stage}/{comp['name']} — continuing")
                memory.update_progress(S, slug, ORDER)
                continue
            print(f"  ✗ diagnose could not fix {stage}: {res['notes']}")

        journal.heartbeat(S, slug, "halted", stage)
        print(f"🚑 {slug}: HALTED at {stage} — see pipeline-state/{slug}/HALT.json (escalated to you)")
        return "halted"


# ------------------------------- CLI -------------------------------

def cmd_run(S, args):
    ucs = {u["slug"]: u for u in _load("use_cases.json")["use_cases"]}
    if args.wave is not None:
        slugs = [s for w in [_load("use_cases.json")["waves"][args.wave]] for s in w if s in ucs]
    else:
        slugs = [args.use_case]
    for slug in slugs:
        if slug not in ucs:
            print(f"unknown use case {slug}", file=sys.stderr); sys.exit(3)
        status = run_usecase(S, ucs[slug], args.autonomy, dry=getattr(args, "dry_run", False))
        if status not in ("done",):
            break            # a pause/halt/checkpoint stops the wave until the human/communicator acts


def cmd_status(S, args):
    slug = args.use_case
    hb = journal.read_heartbeat(S, slug) or {}
    halt = journal.read_halt(S, slug)
    nxt = journal.next_stage(S, slug, ORDER)
    done = [e["stage"] for e in journal.entries(S, slug) if e.get("status") == journal.OK
            and e["stage"] in ORDER]
    print(json.dumps({"slug": slug, "heartbeat": hb, "next_stage": nxt,
                      "completed": done, "halted": bool(halt),
                      "halt": halt, "pending_commands": directives.pending(S, slug)}, indent=2))


def cmd_command(S, args):
    c = directives.add_command(S, args.scope, args.kind, target=args.target or "", body=args.body or "")
    print(f"queued {c['id']} scope={c['scope']} kind={c['kind']} target={c['target']!r}")


def cmd_approve(S, args):
    slug = args.use_case
    hb = journal.read_heartbeat(S, slug) or {}
    if hb.get("status") != "awaiting":
        print(f"{slug} is not awaiting approval (status={hb.get('status')})"); return
    aid = hb.get("stage")
    journal.append(S, slug, f"approved:{aid}", journal.OK, note="human approved")
    print(f"approved {aid} for {slug} — re-run 'supervisor.py run --use-case {slug}' to continue")


def main():
    ap = argparse.ArgumentParser(description="Durable supervisor harness")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("--use-case"); r.add_argument("--wave", type=int)
    r.add_argument("--autonomy", default="checkpoint", choices=["auto", "gated", "checkpoint"])
    r.add_argument("--dry-run", action="store_true",
                   help="walk the durable loop without running stages; writes to <slug>-dryrun state")
    s = sub.add_parser("status"); s.add_argument("--use-case", required=True)
    c = sub.add_parser("command")
    c.add_argument("--scope", required=True); c.add_argument("--kind", required=True)
    c.add_argument("--target", default=""); c.add_argument("--body", default="")
    a = sub.add_parser("approve"); a.add_argument("--use-case", required=True)
    args = ap.parse_args()

    S = _load("settings.json")
    {"run": cmd_run, "status": cmd_status, "command": cmd_command, "approve": cmd_approve}[args.cmd](S, args)


if __name__ == "__main__":
    main()
