#!/usr/bin/env python3
"""regate.py — re-run the build gate on ALREADY-generated code and advance the ledger.

For when codegen was fine but the gate logic had a bug (no need to pay to regenerate).
Runs the (fixed) build_gate on each existing component; if all pass, commits main and
writes build.json so the run can proceed to boot. No LLM calls.

Usage:  python3 regate.py --use-case mkt
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from lib import prompts, verify, state, gates  # noqa: E402

HERE = Path(__file__).resolve().parent


def git(repo, *a):
    return subprocess.run(["git", "-c", "user.email=pipeline@step4.local",
                           "-c", "user.name=step4-pipeline", *a], cwd=str(repo),
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--use-case", required=True)
    args = ap.parse_args()
    S = json.loads((HERE / "config" / "settings.json").read_text())
    uc = {u["slug"]: u for u in json.loads((HERE / "config" / "use_cases.json").read_text())["use_cases"]}[args.use_case]
    repo = state.repo_dir(S, uc["slug"])
    comps, worst, runs = prompts.expand_components(uc), 0, []
    for c in comps:
        cdir = repo / c["dir"]
        g = verify.build_gate(c["kind"], cdir)
        runs.append({**c, **g}); worst = max(worst, g["buildExitCode"])
        print(f"  {c['name']:8} ({c['kind']}) gate exit = {g['buildExitCode']}")
    sha = ""
    if worst == 0:
        git(repo, "add", "-A"); git(repo, "commit", "-q", "-m", f"baseline {uc['name']} (no CometChat)")
        sha = git(repo, "rev-parse", "HEAD").strip()
    res = {"useCase": uc["name"], "slug": uc["slug"], "stack": uc["archetype"],
           "buildExitCode": worst, "committedSha": sha, "components": runs,
           "outputTail": (runs[-1]["outputTail"] if runs else ""), "regated": True}
    state.write(S, uc["slug"], "build", res)
    ok = gates.baseline(res)
    print(f"{'OK' if ok else 'GATE-FAIL'} build:{uc['slug']} worst={worst} sha={sha[:9] or 'none'}")
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
