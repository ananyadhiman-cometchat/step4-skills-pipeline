#!/usr/bin/env bash
# open_progress.sh — open a NEW, cleanly-sized Terminal window that live-tails the pipeline progress
# dashboard (watch.sh) for a use case. Claude runs this at the start of a run so the user watches
# progress in a dedicated window instead of scrolling the agent transcript.
#   Usage:  bash pipeline/open_progress.sh <slug>
SLUG="${1:-mkt}"
DIR="$HOME/Desktop/automate/pipeline"
CMD="clear; printf '\\033]0;STEP4 · $SLUG · live progress\\007'; bash '$DIR/watch.sh' '$SLUG'"

# AppleScript: open a fresh window, size it generously, run the watcher.
osascript >/dev/null 2>&1 <<APPLESCRIPT
tell application "Terminal"
    activate
    set w to do script "$CMD"
    delay 0.3
    try
        set bounds of front window to {120, 80, 1080, 860}
    end try
end tell
APPLESCRIPT
echo "opened live-progress Terminal window for '$SLUG' (watch.sh)"
