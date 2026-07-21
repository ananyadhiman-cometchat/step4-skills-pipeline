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
> **CometChat:** ⚠️ **no `cometchat-vue` skill exists** (known gap) → React UI Kit + Calls SDK mounted as a **React island** inside Vue · Android v6 Compose · iOS Swift + Calls SDK. *Most iOS incoming-call + web session-lifecycle gaps.*
"""),
    # add future UCs here (cre / fld / rea / rid / evt) as their ledgers appear
}

MARKERS = ("SDK-gap:", "missedTrigger:", "falseTrigger:", "coverageGap:",
           "staleness:", "docsEscape:", "variant:", "hallucination:")

# Buckets (must mirror pipeline/lib/gaps.py MARKERS) and the tally-table metadata per UC.
BUCKETS = {"docs-mcp": ("coverageGap:", "staleness:", "docsEscape:"),
           "skills": ("missedTrigger:", "falseTrigger:", "variant:", "hallucination:"),
           "sdk": ("SDK-gap:",)}
UC_META = {  # slug -> (UC#, display name, stack, #codebases)
    "mkt": ("UC1", "Marketplace (`mkt`)", "Next.js / React Native (Expo) / Python", "2"),
    "com": ("UC2", "Community forum (`com`)", "Flutter v6 (all 3) / PHP", "1"),
    "del": ("UC3", "Delivery (`del`)", "Angular / Android-Compose-v6 + iOS-Swift / Node", "3"),
    "dat": ("UC4", "Dating (`dat`)", "React / React Native (Expo 52) / Python", "2"),
    "fin": ("UC5", "Fintech support (`fin`)", "Vue 3 / Android-Compose-v6 + iOS-Swift / Java-Spring", "3"),
}


def _live_counts() -> dict:
    """Per-UC per-tag counts straight from the live ledger."""
    import re
    return {f.stem: {m: len(re.findall(re.escape(m), f.read_text())) for m in MARKERS}
            for f in sorted(LIVE.glob("*.md"))}


def _regen_readme_tally(per_uc: dict) -> int:
    """Rewrite the README tally table + bucket line between <!-- TALLY:START/END --> from live counts.
    Returns the live total. Without this the hand-written tally silently rots when a UC's gaps change."""
    import re
    readme = ROOT / "gaps" / "README.md"
    if not readme.exists():
        return sum(sum(c.values()) for c in per_uc.values())
    rows, total = [], 0
    for slug, (uc, name, stack, cbs) in UC_META.items():
        n = sum(per_uc.get(slug, {}).values()); total += n
        rows.append(f"| {uc} | {name} | {stack} | {cbs} | **{n}** |")
    def tagc(t): return sum(per_uc.get(s, {}).get(t, 0) for s in per_uc)
    bsum = {b: sum(tagc(t) for t in ts) for b, ts in BUCKETS.items()}
    block = ("| UC | Use case | Stack (web / mobile / backend) | Codebases | Gap markers |\n"
             "|---|---|---|:--:|--:|\n" + "\n".join(rows) +
             f"\n| | | | **Total** | **{total}** |\n\n"
             f"**By bucket:** docs-mcp {bsum['docs-mcp']} (coverageGap {tagc('coverageGap:')} · "
             f"staleness {tagc('staleness:')} · docsEscape {tagc('docsEscape:')}) · "
             f"skills {bsum['skills']} (missedTrigger {tagc('missedTrigger:')} · "
             f"falseTrigger {tagc('falseTrigger:')} · hallucination {tagc('hallucination:')}) · "
             f"sdk {bsum['sdk']} (SDK-gap).")
    txt = readme.read_text()
    if "<!-- TALLY:START -->" in txt:
        txt = re.sub(r"<!-- TALLY:START -->.*?<!-- TALLY:END -->",
                     f"<!-- TALLY:START -->\n{block}\n<!-- TALLY:END -->", txt, flags=re.DOTALL)
        readme.write_text(txt)
    return total


def _check_consolidated(per_uc: dict, total: int) -> list[str]:
    """CONSOLIDATED_GAPS.md is a HAND-CURATED thematic analysis refresh.py cannot regenerate — but it
    CAN detect when it has gone stale (count drift or a whole UC missing) and say so loudly."""
    import re
    cons = ROOT / "gaps" / "CONSOLIDATED_GAPS.md"
    if not cons.exists():
        return []
    txt = cons.read_text(); warns = []
    m = re.search(r"\((\d+) marker-tagged findings", txt)
    if m and int(m.group(1)) != total:
        warns.append(f"CONSOLIDATED_GAPS.md header says {m.group(1)} findings, live total is {total} "
                     f"— STALE. It's hand-curated by THEME; fold the new gaps in and update the count.")
    for slug, c in per_uc.items():
        if sum(c.values()) > 0 and re.search(rf'\b{slug}\b', txt) is None:
            warns.append(f"CONSOLIDATED_GAPS.md never mentions UC '{slug}' ({sum(c.values())} gaps) — STALE.")
    return warns


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

    # 3. regenerate the README tally from live counts, and flag the hand-curated CONSOLIDATED if stale
    per_uc = _live_counts()
    live_total = _regen_readme_tally(per_uc)
    print(f"README tally regenerated · total {live_total}")
    stale = _check_consolidated(per_uc, live_total)
    for w in stale:
        print(f"  ⚠ STALE: {w}")
    if stale:
        print("  → CONSOLIDATED_GAPS.md needs a manual thematic update (see warnings above).")
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
