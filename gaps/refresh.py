#!/usr/bin/env python3
"""Refresh the shareable gaps/ bundle from the LIVE ledger.

Regenerates MASTER_GAPS.md (+ lint), then copies each per-UC ledger into by-use-case/ with a short
use-case + tech-stack intro prepended. Run after any UC's gaps change:

    python3 gaps/refresh.py

The intros live here (not in the live ledger) so the pipeline's own files stay untouched, and a
refresh never silently drops them.
"""
from __future__ import annotations
import os, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIVE = ROOT / "pipeline-state" / "gaps"
OUT = ROOT / "gaps" / "by-use-case"

# slug -> (output filename, intro block)
INTROS = {
    "mkt": ("UC1-mkt-marketplace.md", """> **UC1 · Marketplace (`mkt`)** — buyer/seller marketplace: listings, orders, and in-app chat + calls between buyer and seller.
> **Stack:** Next.js web · React Native (Expo) for Android + iOS (one shared codebase) · Python backend — **2 codebases**.
> **CometChat:** React UI Kit (web) + React Native UI Kit (mobile) + Calls SDK.
"""),
    "com": ("UC2-com-community-forum.md", """> **UC2 · Community forum (`com`)** — threaded community forum: group discussion with chat + voice/video calls.
> **Stack:** Flutter v6 for web + Android + iOS (**one** codebase spanning all three) · PHP backend — **1 codebase**.
> **CometChat:** Flutter v6 UI Kit + Calls. *Richest ledger — most of the Flutter-calls / go_router cluster lives here.*
"""),
    "del": ("UC3-del-delivery.md", """> **UC3 · Delivery (`del`)** — delivery app: orders tracked across customer, courier and store, with chat + calls.
> **Stack:** Angular web · Android (Kotlin/Compose, UI Kit v6) · iOS (native Swift) · Node backend — **3 separate codebases**.
> **CometChat:** Angular UI Kit · Android v6 Compose · iOS Swift UI Kit + Calls SDK. *Most iOS-native packaging/calls gaps.*
"""),
    "dat": ("UC4-dat-dating.md", """> **UC4 · Dating (`dat`)** — dating app: browse profiles → like → match → chat + voice/video call with your match.
> **Stack:** React web · React Native (Expo SDK 52 / RN 0.76) for Android + iOS (one shared codebase) · Python (FastAPI) backend — **2 codebases**.
> **CometChat:** React UI Kit v6 (web) + React Native UI Kit v5 (mobile) + Calls SDK.
"""),
    "fin": ("UC5-fin-fintech-support.md", """> **UC5 · Fintech support (`fin`)** — fintech customer-support: real-time support chat + calls between customers and agents.
> **Stack:** Vue 3 web · Android (Kotlin/Compose, UI Kit v6) · iOS (native Swift) · Java (Spring) backend — **3 separate codebases**.
> **CometChat:** ⚠️ **no `cometchat-vue` skill exists** (known, pre-seeded gap — expect none to fire on the Vue slice) · Android v6 Compose · iOS Swift + Calls SDK. _**In progress** — ledger still filling._
"""),
    # add future UCs here (cre / fld / rea / rid / evt) as their ledgers appear
}

MARKERS = ("SDK-gap:", "missedTrigger:", "falseTrigger:", "coverageGap:",
           "staleness:", "docsEscape:", "variant:", "hallucination:")


def main() -> int:
    # 1. regenerate the rollup (+ lint) from the live ledger
    sys.path.insert(0, str(ROOT / "pipeline"))
    from lib import gaps  # noqa: E402
    r = gaps.rebuild({"gaps_dir": str(LIVE), "master_gaps": str(ROOT / "MASTER_GAPS.md")})
    total = sum(r["counts"].values())
    print(f"rollup: {total} markers · lint clean: {r['lint']['clean']}")
    if not r["lint"]["clean"]:
        for v in r["lint"]["violations"]:
            print(f"  ⚠ unmarked entry {v['file']}:{v['line']}  {v['text']}")

    shutil.copy(ROOT / "MASTER_GAPS.md", ROOT / "gaps" / "MASTER_GAPS.md")
    OUT.mkdir(parents=True, exist_ok=True)

    # 2. copy each ledger with its intro prepended
    for slug, (fname, intro) in INTROS.items():
        src = LIVE / f"{slug}.md"
        if not src.exists():
            print(f"  skip {slug}: no {src.name} yet")
            continue
        body = src.read_text()
        n = sum(body.count(m) for m in MARKERS)
        header = f"{intro}> **Gaps recorded: {n}.** _Source: `pipeline-state/gaps/{slug}.md` — edit there, not here._\n\n---\n\n"
        (OUT / fname).write_text(header + body)
        print(f"  {fname}: {n} gaps")

    missing = [s for s in (p.stem for p in LIVE.glob("*.md")) if s not in INTROS]
    if missing:
        print(f"NOTE: ledger(s) with no intro configured — add to INTROS in this script: {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
