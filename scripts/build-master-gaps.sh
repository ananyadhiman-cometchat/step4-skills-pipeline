#!/usr/bin/env bash
# build-master-gaps.sh — regenerate MASTER_GAPS.md from per-use-case section files.
# Runs alongside app creation: each integrate/verify agent appends to
# pipeline-state/gaps/<slug>.md; this concatenates them into one live ledger.
# Safe to run any time (dashboard loop calls it on a cadence).
set -euo pipefail
cd "$(dirname "$0")/.."
GAPS_DIR="pipeline-state/gaps"
OUT="MASTER_GAPS.md"
TS="$(date '+%Y-%m-%d %H:%M:%S %Z')"

mkdir -p "$GAPS_DIR"

# --- rollup counts (grep the section files for the tag markers agents write) ---
count() { { grep -rhio "$1" "$GAPS_DIR" 2>/dev/null || true; } | grep -c . || true; }
MCP_COV=$(count 'coverageGap:'); MCP_STALE=$(count 'staleness:'); MCP_ESC=$(count 'docsEscape:')
SK_MISS=$(count 'missedTrigger:'); SK_FALSE=$(count 'falseTrigger:'); SK_VAR=$(count 'variant:'); SK_HALL=$(count 'hallucination:')

{
cat <<HEADER
# MASTER_GAPS.md — live gaps ledger (MCP + skills)

> **Auto-generated** by \`scripts/build-master-gaps.sh\` — do not hand-edit; edits are overwritten.
> Regenerated: **$TS**. Source: \`pipeline-state/gaps/<slug>.md\` (one per use case, written by the integrate/verify agents as they run).

Two buckets, exactly the brief's metric families (§5.1 skill activation · §5.4 docs-mcp):

| Bucket | Tag markers agents emit | This run |
|---|---|--:|
| **docs-mcp** | \`coverageGap:\` (query returned nothing) · \`staleness:\` (doc vs SDK) · \`docsEscape:\` (left mcp to web-search/guess) | $MCP_COV / $MCP_STALE / $MCP_ESC |
| **skills** | \`missedTrigger:\` (no skill fired) · \`falseTrigger:\` (wrong skill) · \`variant:\` (v5/v6 mis-pick) · \`hallucination:\` (non-existent API) | $SK_MISS / $SK_FALSE / $SK_VAR / $SK_HALL |

## Known / expected gaps (pre-seeded, verify during run)
- **\`missedTrigger:\` Vue has no \`cometchat-vue\` skill** → UC5 (Fintech) & UC10 (Event). Expect NO skill to fire on the Vue 3 web slice — **record it, don't treat as agent failure** (STEP4_PIPELINE §1). CometChat *ships* a Vue UI Kit, so this is the sharpest coverage gap.

---

## Per-use-case findings
HEADER

if ls "$GAPS_DIR"/*.md >/dev/null 2>&1; then
  for f in "$GAPS_DIR"/*.md; do echo; cat "$f"; echo; done
else
  echo; echo "_No section files yet — populated once Baseline/Integrate agents start writing._"
fi

cat <<FOOTER

---
_Rollup feeds Consolidate → \`rankedFixBacklog\` (each fix tied to the blocker that motivated it, §5.5)._
FOOTER
} > "$OUT"

echo "wrote $OUT  (mcp: $MCP_COV cov / $MCP_STALE stale / $MCP_ESC esc | skills: $SK_MISS miss / $SK_FALSE false / $SK_VAR variant / $SK_HALL halluc)"
