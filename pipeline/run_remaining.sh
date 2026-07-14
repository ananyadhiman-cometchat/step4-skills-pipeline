#!/usr/bin/env bash
# run_remaining.sh — drive com's remaining pipeline stages in order, stop on first failure.
# Logs to /tmp/<slug>-pipeline.log so progress_snapshot.sh + watch.sh can read live progress.
set -o pipefail
SLUG="${1:-com}"
cd "$HOME/Desktop/automate/pipeline" || exit 9
LOG="/tmp/$SLUG-pipeline.log"
: > "$LOG"
stages=(push-main integrate verify push-branch)
for s in "${stages[@]}"; do
  echo ">>> stage $s  ($(date '+%H:%M:%S'))" | tee -a "$LOG"
  python3 run_usecase.py --use-case "$SLUG" --stage "$s" 2>&1 | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  if [ "$rc" -ne 0 ]; then
    echo "<<< stage $s FAILED (rc=$rc) — stopping" | tee -a "$LOG"
    exit "$rc"
  fi
  echo "<<< stage $s OK" | tee -a "$LOG"
done
echo "=== ALL REMAINING STAGES COMPLETE ===" | tee -a "$LOG"
