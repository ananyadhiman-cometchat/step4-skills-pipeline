#!/usr/bin/env bash
set -o pipefail
SLUG="${1:-com}"
cd "$HOME/Desktop/automate/pipeline" || exit 9
LOG="/tmp/$SLUG-pipeline.log"
for s in verify push-branch; do
  echo ">>> stage $s  ($(date '+%H:%M:%S'))" | tee -a "$LOG"
  python3 run_usecase.py --use-case "$SLUG" --stage "$s" 2>&1 | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  if [ "$rc" -ne 0 ]; then echo "<<< stage $s FAILED (rc=$rc) — stopping" | tee -a "$LOG"; exit "$rc"; fi
  echo "<<< stage $s OK" | tee -a "$LOG"
done
echo "=== VERIFY + PUSH-BRANCH COMPLETE ===" | tee -a "$LOG"
