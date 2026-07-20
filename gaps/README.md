# CometChat Gaps — shareable bundle

All CometChat **skills / MCP-docs / SDK** gaps found while building the Step-4 use cases, collected in one
place. **Start with [`CONSOLIDATED_GAPS.md`](CONSOLIDATED_GAPS.md).**

## What's here

| File | What it is | Read it when |
|---|---|---|
| **[CONSOLIDATED_GAPS.md](CONSOLIDATED_GAPS.md)** | **Start here.** All findings de-duplicated into **17 themes**, ranked by impact × recurrence, each with symptom → workaround → *the ask for CometChat*. | You want the actionable picture / to hand to the CometChat team |
| [MASTER_GAPS.md](MASTER_GAPS.md) | Auto-generated rollup: the marker tally + every per-UC file concatenated verbatim. | You want the raw, complete record |
| [by-use-case/](by-use-case/) | The per-use-case ledgers, each with a short use-case + tech-stack intro. | You're digging into one use case |
| [refresh.py](refresh.py) | Re-syncs this bundle from the live ledger (rollup + lint + intros). | The ledgers changed |

## Tally (as of this export)

| UC | Use case | Stack (web / mobile / backend) | Codebases | Gap markers |
|---|---|---|:--:|--:|
| UC1 | Marketplace (`mkt`) | Next.js / React Native (Expo) / Python | 2 | **7** |
| UC2 | Community forum (`com`) | Flutter v6 (all 3) / PHP | 1 | **16** |
| UC3 | Delivery (`del`) | Angular / Android-Compose-v6 + iOS-Swift / Node | 3 | **11** |
| UC4 | Dating (`dat`) | React / React Native (Expo 52) / Python | 2 | **8** |
| UC5 | Fintech support (`fin`) | Vue 3 / Android-Compose-v6 + iOS-Swift / Java-Spring | 3 | **1** *(in progress)* |
| | | | **Total** | **43** |

**By bucket:** docs-mcp 12 (coverageGap 4 · staleness 4 · docsEscape 4) · skills 15 (missedTrigger 14 ·
falseTrigger 1) · sdk 15 (SDK-gap).

**Biggest lever:** *calling*. 6 of the top-10 recurring gaps are in the calls path (self-positioning, silent
no-op, virtual-device media, overlay touch-intercept, the iOS 26 crash, lifecycle traps). Fixing call-component
placement + the prerequisite story in the skills would retire most repeat offenders.

## ⚠️ These are COPIES — don't edit them here

The **live** ledger the pipeline reads/writes is `pipeline-state/gaps/<slug>.md`, and the rollup is the
repo-root `MASTER_GAPS.md`. Edit those; this folder is an export for sharing and will go stale.

Refresh this bundle — **one command** (regenerates the rollup, runs the lint, re-copies each ledger and
re-applies its intro header):

```bash
cd ~/Desktop/automate && python3 gaps/refresh.py
```

When a new use case starts recording gaps, add its intro to the `INTROS` dict in
[`refresh.py`](refresh.py) — the script tells you which ledgers have no intro configured yet.

## What is / isn't in scope

- **In:** genuine CometChat **skill**, **MCP-docs**, and **SDK** (packaging/behaviour) gaps.
- **Out:** codegen misses where the skill was *correct*, and harness/environment issues — those live in
  `pipeline-state/pipeline-notes/<slug>.md`.
- **Retracted** items (investigated → not a real CometChat gap) stay in the per-UC files, marked, and are not
  counted in the tally.

## Status

- UC1–UC4 complete. **UC5 (`fin`) is in progress** — 1 gap recorded so far (it has already re-hit the
  recurring web calls-CSS-vars SDK gap on its Vue slice, making that **4 use cases**: mkt · del · dat · fin).
- **Known open item:** del's iOS in-call crash (theme **C7**) has a confirmed one-line fix
  (`CometChatCallsSDK ~> 5.0`) that is **not yet written into `del.md`** — another session owns that edit.
- Every entry carries a canonical marker (`SDK-gap:` · `missedTrigger:` · `coverageGap:` · `staleness:` ·
  `docsEscape:` · `falseTrigger:`); `gaps.lint()` rejects entries that don't, so the tally stays trustworthy.
