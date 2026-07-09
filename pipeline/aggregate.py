#!/usr/bin/env python3
"""aggregate.py — roll all verify.json + report-*.json into aggregate.{json,md}.

The surviving role of the old orchestrator.py: --aggregate-only. Dedupes/ranks
blockers by frequency, rolls per-platform ease scores, and folds in the live
MASTER_GAPS counts. Pure Python, no LLM.

Usage:  python3 aggregate.py
"""
from __future__ import annotations
import json, os, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from lib import gaps  # noqa: E402

HERE = Path(__file__).resolve().parent
S = json.loads((HERE / "config" / "settings.json").read_text())
LEDGER = Path(os.path.expanduser(S["state_dir"]))


def main():
    verify_files = sorted(LEDGER.glob("*-verify.json"))
    runs = [json.loads(f.read_text()) for f in verify_files]
    blocker_freq = Counter()
    ease_by_platform = defaultdict(list)
    halluc = Counter()
    for r in runs:
        for b in r.get("blockers", []):
            blocker_freq[(b.get("desc", "?"), b.get("tag", "?"))] += 1
        for a in r.get("hallucinatedAPIs", []):
            halluc[a] += 1
        if r.get("easeScore") is not None:
            ease_by_platform[r["slug"]].append(r["easeScore"])
    ranked = [{"fix": d, "tag": t, "frequency": n}
              for (d, t), n in blocker_freq.most_common()]
    g = gaps.rebuild(S)
    agg = {
        "runsAggregated": len(runs),
        "rankedFixBacklog": ranked,
        "mostFrequentHallucinations": halluc.most_common(10),
        "perUseCaseEase": {k: round(sum(v) / len(v), 2) for k, v in ease_by_platform.items()},
        "worstCoveredUseCases": sorted(ease_by_platform, key=lambda k: sum(ease_by_platform[k])/len(ease_by_platform[k]))[:3],
        "gapCounts": g["counts"],
        "needsAttention": [r["slug"] for r in runs if r.get("refuted") is True],
    }
    out = LEDGER / "aggregate.json"; out.write_text(json.dumps(agg, indent=2))
    md = ["# Aggregate — STEP4 skills review", "",
          f"Runs aggregated: **{agg['runsAggregated']}**", "",
          "## Ranked fix backlog (frequency × tag)"]
    md += [f"- ({n}×) [{t}] {d}" for d, t, n in [(x['fix'], x['tag'], x['frequency']) for x in ranked]] or ["- none yet"]
    md += ["", "## Per-use-case ease (1–5)"]
    md += [f"- {k}: {v}" for k, v in agg["perUseCaseEase"].items()] or ["- none yet"]
    md += ["", f"## Gap counts", f"```json\n{json.dumps(agg['gapCounts'], indent=2)}\n```"]
    (LEDGER / "aggregate.md").write_text("\n".join(md))
    print(f"wrote {out} and aggregate.md ({len(runs)} runs)")


if __name__ == "__main__":
    main()
