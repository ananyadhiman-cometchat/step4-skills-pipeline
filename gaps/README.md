# CometChat Gaps — shareable bundle

All CometChat **skills / MCP-docs / SDK** gaps found while building the Step-4 use cases, collected in one
place. **Start with [`CONSOLIDATED_GAPS.md`](CONSOLIDATED_GAPS.md).**

## What's here

| File | What it is | Read it when |
|---|---|---|
| **[CONSOLIDATED_GAPS.md](CONSOLIDATED_GAPS.md)** | **Start here.** All findings de-duplicated into **17 themes**, ranked by impact × recurrence, each with symptom → workaround → *the ask for CometChat*. | You want the actionable picture / to hand to the CometChat team |
| [MASTER_GAPS.md](MASTER_GAPS.md) | Auto-generated rollup: the marker tally + every per-UC file concatenated verbatim. | You want the raw, complete record |
| [by-use-case/](by-use-case/) | The four per-use-case ledgers, as written during each build. | You're digging into one use case |

## Tally (as of this export)

| UC | Use case | Stack (web / mobile / backend) | Gap markers |
|---|---|---|--:|
| UC1 | Marketplace (`mkt`) | Next.js / React Native (Expo) / Python | **7** |
| UC2 | Community forum (`com`) | Flutter v6 (all 3) / PHP | **16** |
| UC3 | Delivery (`del`) | Angular / Android-Compose-v6 + iOS-Swift / Node | **11** |
| UC4 | Dating (`dat`) | React / React Native / Python | **8** |
| | | **Total** | **42** |

**By bucket:** docs-mcp 12 (coverageGap 4 · staleness 4 · docsEscape 4) · skills 15 (missedTrigger 14 ·
falseTrigger 1) · sdk 15 (SDK-gap).

**Biggest lever:** *calling*. 6 of the top-10 recurring gaps are in the calls path (self-positioning, silent
no-op, virtual-device media, overlay touch-intercept, the iOS 26 crash, lifecycle traps). Fixing call-component
placement + the prerequisite story in the skills would retire most repeat offenders.

## ⚠️ These are COPIES — don't edit them here

The **live** ledger the pipeline reads/writes is `pipeline-state/gaps/<slug>.md`, and the rollup is the
repo-root `MASTER_GAPS.md`. Edit those; this folder is an export for sharing and will go stale.

Refresh this bundle:

```bash
cd ~/Desktop/automate
cp pipeline-state/gaps/mkt.md gaps/by-use-case/UC1-mkt-marketplace.md
cp pipeline-state/gaps/com.md gaps/by-use-case/UC2-com-community-forum.md
cp pipeline-state/gaps/del.md gaps/by-use-case/UC3-del-delivery.md
cp pipeline-state/gaps/dat.md gaps/by-use-case/UC4-dat-dating.md
cp MASTER_GAPS.md            gaps/MASTER_GAPS.md
# regenerate the rollup + lint first if the ledgers changed:
python3 -c "import sys;sys.path.insert(0,'pipeline');from lib import gaps;print(gaps.rebuild({'gaps_dir':'pipeline-state/gaps','master_gaps':'MASTER_GAPS.md'})['counts'])"
```

## What is / isn't in scope

- **In:** genuine CometChat **skill**, **MCP-docs**, and **SDK** (packaging/behaviour) gaps.
- **Out:** codegen misses where the skill was *correct*, and harness/environment issues — those live in
  `pipeline-state/pipeline-notes/<slug>.md`.
- **Retracted** items (investigated → not a real CometChat gap) stay in the per-UC files, marked, and are not
  counted in the tally.

## Status

- UC1–UC4 complete. **UC5 (`fin` — Fintech: Vue 3 / Android-Compose-v6 + iOS-Swift / Java-Spring) is in
  progress** — its gaps aren't recorded yet, so no `fin` file here.
- Every entry carries a canonical marker (`SDK-gap:` · `missedTrigger:` · `coverageGap:` · `staleness:` ·
  `docsEscape:` · `falseTrigger:`); `gaps.lint()` rejects entries that don't, so the tally stays trustworthy.
