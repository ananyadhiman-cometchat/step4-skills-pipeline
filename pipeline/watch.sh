#!/usr/bin/env bash
# watch.sh — live progress dashboard for a running use case.
# Usage:  bash pipeline/watch.sh mkt      (Ctrl-C to stop)
# Refreshes every 4s. Reads files-on-disk + pipeline-state (the real-time signals;
# the claude -p json logs only flush at stage end, so file growth is the live pulse).
SLUG="${1:-mkt}"
ROOT="$HOME/Desktop/automate"
RUN="$ROOT/runs/$SLUG"
STATE="$ROOT/pipeline-state"

stages=(preflight provision-app build boot push-main integrate verify push-branch)

while true; do
  clear
  printf "\033[1m STEP4 · %s · live\033[0m   %s\n" "$SLUG" "$(date '+%H:%M:%S')"
  printf -- "------------------------------------------------------------\n"

  # infer the running stage: first stage with no ledger json yet whose work is in progress
  running=""
  if [ ! -f "$STATE/$SLUG-build.json" ] && [ -d "$RUN/backend" ]; then running="build"
  elif [ -f "$STATE/$SLUG-build.json" ] && [ ! -f "$STATE/$SLUG-boot.json" ]; then running="boot"
  elif [ -f "$STATE/$SLUG-boot.json" ] && [ ! -f "$STATE/$SLUG-integrate.json" ]; then running="integrate?"
  fi

  # stage ledger: green=done, yellow=running now, grey=pending
  printf " stages: "
  for s in "${stages[@]}"; do
    if [ -f "$STATE/$SLUG-$s.json" ]; then printf "\033[32m%s\033[0m " "$s"
    elif [ "$s" = "$running" ]; then printf "\033[33m%s◀running\033[0m " "$s"
    else printf "\033[90m%s\033[0m " "$s"; fi
  done
  printf "\n"
  [ -n "$running" ] && printf " \033[33m▶ %s in progress (ledger writes on completion)\033[0m\n" "$running"
  printf "\n"

  # per-component file growth (the live pulse)
  for d in backend web mobile ios android app; do
    [ -d "$RUN/$d" ] || continue
    n=$(find "$RUN/$d" -type f -not -path '*/node_modules/*' -not -path '*/.venv/*' -not -path '*/.git/*' 2>/dev/null | wc -l | tr -d ' ')
    recent=$(find "$RUN/$d" -type f -not -path '*/node_modules/*' -not -path '*/.venv/*' -mmin -1 2>/dev/null | wc -l | tr -d ' ')
    last=$(find "$RUN/$d" -type f -not -path '*/node_modules/*' -not -path '*/.venv/*' 2>/dev/null -exec stat -f '%m' {} \; 2>/dev/null | sort -rn | head -1)
    lastfile=$(find "$RUN/$d" -type f -not -path '*/node_modules/*' -not -path '*/.venv/*' 2>/dev/null -exec stat -f '%m %N' {} \; 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
    ts=$([ -n "$last" ] && date -r "$last" '+%H:%M:%S' || echo "—")
    printf "  \033[1m%-8s\033[0m %3s files  | +%s in last min | last %s  %s\n" \
      "$d" "$n" "$recent" "$ts" "$(basename "${lastfile:-}")"
  done

  # active codegen
  procs=$(ps aux | grep -c "[c]laude -p")
  printf "\n  codegen procs: %s\n" "$procs"

  # docker: live container + build activity (boot / verify stages)
  printf "\n  \033[1mdocker\033[0m\n"
  containers=$(docker ps -a --format '{{.Names}}|{{.Status}}' 2>/dev/null | grep -i "$SLUG")
  if [ -n "$containers" ]; then
    echo "$containers" | while IFS='|' read -r n s; do
      case "$s" in
        *healthy*)   c="\033[32m" ;;   # green
        *starting*|*Restarting*) c="\033[33m" ;;  # yellow
        *Exited*|*unhealthy*) c="\033[31m" ;;      # red
        *) c="\033[90m" ;;
      esac
      printf "    ${c}%-20s %s\033[0m\n" "$n" "$s"
    done
  elif [ "$running" = "boot" ] || [ "$running" = "integrate?" ] || pgrep -f "docker.*build\|buildkit" >/dev/null 2>&1; then
    printf "    \033[33mbuilding images / starting stack…\033[0m\n"
  else
    printf "    \033[90m(no containers up)\033[0m\n"
  fi
  imgs=$(docker images --format '{{.Repository}}' 2>/dev/null | grep -ci "$SLUG")
  bcache=$(docker system df --format '{{.Type}} {{.Size}}' 2>/dev/null | grep -i "build" | awk '{print $NF}')
  printf "    %s images built · build-cache %s\n" "${imgs:-0}" "${bcache:-0B}"

  # last stage result if any
  latest=$(ls -t "$STATE/$SLUG-"*.json 2>/dev/null | head -1)
  [ -n "$latest" ] && printf "  last ledger write: %s\n" "$(basename "$latest")"

  printf -- "------------------------------------------------------------\n"
  printf " Ctrl-C to stop · refreshes 4s\n"
  sleep 4
done
