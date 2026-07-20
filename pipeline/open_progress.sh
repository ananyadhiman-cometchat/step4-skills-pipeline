#!/usr/bin/env bash
# open_progress.sh — open a NEW, cleanly-sized Terminal window that live-tails the pipeline progress
# dashboard (watch.sh) for a use case. Claude runs this at the start of a run so the user watches
# progress in a dedicated window instead of scrolling the agent transcript.
#   Usage:  bash pipeline/open_progress.sh <slug>
SLUG="${1:-mkt}"
DIR="$HOME/Desktop/automate/pipeline"
# Keep this a PLAIN command: an ANSI window-title escape here does not survive command substitution
# and makes osascript fail with a bogus -2741 syntax error that masks the real problem.
CMD="clear; bash '$DIR/watch.sh' '$SLUG'"

# AppleScript: open a fresh window, size it generously, run the watcher.
# NB this needs macOS Automation permission (Apple events -> Terminal). Without it osascript fails
# "Not authorised to send Apple events to Terminal. (-1743)". This used to send stderr to /dev/null
# and echo "opened ..." REGARDLESS of exit status, so a blocked run was indistinguishable from a
# successful one and the user hunted for a window that never existed. Report the real failure.
ERR=$(osascript 2>&1 >/dev/null <<APPLESCRIPT
tell application "Terminal"
    activate
    set w to do script "$CMD"
    delay 0.3
    try
        set bounds of front window to {120, 80, 1080, 860}
    end try
end tell
APPLESCRIPT
)

if [ -n "$ERR" ]; then
    echo "could NOT open a progress window: $ERR" >&2
    case "$ERR" in
      *-1743*|*"ot auth"*)
        echo "macOS is blocking Apple events. Grant it in System Settings -> Privacy & Security ->" >&2
        echo "Automation -> (this app) -> Terminal, or just run the dashboard yourself:" >&2 ;;
    esac
    echo "    bash $DIR/watch.sh $SLUG" >&2
    exit 1
fi
echo "opened live-progress Terminal window for '$SLUG' (watch.sh)"
