#!/usr/bin/env python3
"""batch_runner.py — reproducible wave/checkpoint sequencer (runs OUTSIDE a session).

Encodes the conductor's loop deterministically so the orchestration is reproducible
from a plain terminal. It DOES pause for a typed human approval at each checkpoint —
this is the one place input() is allowed, because batch_runner is meant to be run
interactively by the human, NOT headless. The headless worker (run_usecase.py) never
blocks. In a Claude session, the SESSION plays this role instead (AskUserQuestion gates).

Wave-of-2: drives 2 use cases per wave; the next wave starts only after both reach
push-branch. Sequential within a wave on the first pass (shake out issues).

Usage:  python3 batch_runner.py                 # all waves, interactive
        python3 batch_runner.py --wave 0        # one wave
        python3 batch_runner.py --auto-approve   # CI/unattended (skips the human gate — dangerous)
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = json.loads((HERE / "config" / "use_cases.json").read_text())
KNOWN = {u["slug"] for u in CFG["use_cases"]}

# Phase 0 preflight runs first per use case; provision-app runs ONCE before wave 0.
# Each segment ends with `demo` (boots web+Android+iOS, screenshots, LEAVES UP for manual test).
# After the human approves the checkpoint, `teardown` cleanly closes everything before continuing.
#
# AUTO-PUSH on approval: the push stages are the FIRST thing each post-checkpoint segment runs,
# so approving a checkpoint auto-pushes to GitHub:
#   CP1 approved → SEG_B starts with `push-main`   → pushes the baseline `main` branch.
#   CP2 approved → SEG_C runs `push-branch`         → pushes `feature/cometchat-integration`.
# The `demo` in SEG_B is the MANDATORY boot-2 rebuild: it prebuild-cleans + rebuilds Android/iOS
# from the integration branch and gates on that build compiling (see stage_demo) before CP2.
SEG_A = ["preflight", "build", "containerize", "boot", "demo"]   # → CHECKPOINT 1 (manual verify)
SEG_B = ["push-main", "integrate", "verify", "demo"]             # push-main = auto-push on CP1 → CHECKPOINT 2
SEG_C = ["readme", "push-branch"]                                # readme (commit) then auto-push on CP2
# After SEG_C the wave ALWAYS runs a final `teardown` — the automatic last step: README shipped,
# then everything is cleaned up (docker down -v, apps uninstalled, sims/emulator shut).


def run(slug, stage) -> int:
    print(f"\n\033[1m▶ {slug} :: {stage}\033[0m")
    return subprocess.call([sys.executable, str(HERE / "run_usecase.py"),
                            "--use-case", slug, "--stage", stage])


def run_segment(slug, stages) -> bool:
    for st in stages:
        if run(slug, st) != 0:
            print(f"\033[31m✗ halted at {slug}:{st} (gate-fail or error). Fix + re-run this stage.\033[0m")
            return False
    return True


def checkpoint(label, slugs, auto) -> bool:
    print(f"\n\033[33m🛑 {label} — review {', '.join(slugs)} on disk "
          f"(work_root/<slug>/_reports/). Approve to continue.\033[0m")
    if auto:
        print("   --auto-approve: proceeding without human gate"); return True
    return input("   type 'go' to proceed (anything else halts): ").strip().lower() == "go"


def drive_wave(wave, auto):
    # FAIL LOUD on a mistyped/removed slug — silently dropping it (the old behaviour) meant a wave
    # believed to run 2 use cases actually ran 1, and aggregate metrics under-counted with no signal.
    unknown = [s for s in wave if s not in KNOWN]
    if unknown:
        print(f"\033[31m✗ wave {wave} names UNKNOWN slug(s) {unknown} — fix use_cases.json waves. Aborting.\033[0m",
              file=sys.stderr)
        sys.exit(3)
    slugs = [s for s in wave if s in KNOWN]
    if not slugs:
        print(f"(skipping empty wave {wave})"); return
    os.environ["STEP4_WAVE_ID"] = "wave-" + "-".join(slugs)   # correlate all stages of this wave
    # Segment A for both, then CP1, then B for both, then CP2, then C.
    for s in slugs:
        if not run_segment(s, SEG_A):
            return
    if not checkpoint("CHECKPOINT 1 (manual verify: web+Android+iOS up)", slugs, auto):
        print("halted at CP1."); return
    for s in slugs:            # approved → cleanly close the demo before continuing
        run(s, "teardown")
    for s in slugs:
        if not run_segment(s, SEG_B):
            return
    if not checkpoint("CHECKPOINT 2 (manual verify: integrated web+Android+iOS)", slugs, auto):
        print("halted at CP2."); return
    for s in slugs:            # approved → close the demo before push
        run(s, "teardown")
    for s in slugs:
        run_segment(s, SEG_C)
    # FINAL step — always cleanup at the end of the pipeline (apps + containers + sims), even if a
    # push-branch gate tripped, so a wave never leaves demo apps installed or docker running.
    for s in slugs:
        run(s, "teardown")
    print(f"\n\033[32m✔ wave complete (README shipped, cleaned up): {', '.join(slugs)}\033[0m")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wave", type=int, default=None)
    ap.add_argument("--auto-approve", action="store_true")
    args = ap.parse_args()
    waves = CFG["waves"]
    todo = [waves[args.wave]] if args.wave is not None else waves
    # one-time provisioning before the first wave (idempotent — no-op if already set)
    if args.wave in (None, 0):
        first = next((s for w in waves for s in w if s in KNOWN), None)
        if first:
            print("\n\033[1m▶ one-time provision-app\033[0m")
            subprocess.call([sys.executable, str(HERE / "run_usecase.py"),
                             "--use-case", first, "--stage", "provision-app"])
    for w in todo:
        drive_wave(w, args.auto_approve)


if __name__ == "__main__":
    main()
