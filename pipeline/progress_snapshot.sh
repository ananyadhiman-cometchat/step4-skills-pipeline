#!/usr/bin/env bash
# progress_snapshot.sh — ONE-SHOT, plain-text (no ANSI, no clear) pipeline snapshot for inline display
# inside the Claude desktop. Reads pipeline-state ledger + the live driver log. Usage: bash progress_snapshot.sh <slug>
SLUG="${1:-com}"
ROOT="$HOME/Desktop/automate"
STATE="$ROOT/pipeline-state"
LOG="/tmp/$SLUG-pipeline.log"
stages=(preflight provision-app build containerize boot push-main integrate verify push-branch)

echo "STEP4 pipeline · $SLUG · $(date '+%H:%M:%S')"
echo "------------------------------------------------------------"
# running stage = the one currently in the driver log without a ledger yet
cur=$(grep -oE ">>> stage (\w[-\w]*)" "$LOG" 2>/dev/null | tail -1 | awk '{print $3}')
for s in "${stages[@]}"; do
  if [ -f "$STATE/$SLUG-$s.json" ]; then mark="[x] done   "
  elif [ "$s" = "$cur" ];              then mark="[>] RUNNING"
  else                                      mark="[ ] pending"; fi
  printf "  %s  %s\n" "$mark" "$s"
done
echo "------------------------------------------------------------"
# live tail of the driver log (last few meaningful lines)
if [ -f "$LOG" ]; then
  echo "recent:"
  grep -viE "^\s*$" "$LOG" | tail -8 | sed 's/^/  | /'
fi
# codegen + docker pulse
procs=$(ps aux | grep -c "[c]laude -p")
cont=$(docker ps --format '{{.Names}} {{.Status}}' 2>/dev/null | grep -i "$SLUG" | tr '\n' ' ')
echo "------------------------------------------------------------"
echo "  codegen procs: $procs | docker: ${cont:-none}"
