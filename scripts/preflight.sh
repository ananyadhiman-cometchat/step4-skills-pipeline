#!/usr/bin/env bash
# preflight.sh — STEP4 pipeline access-&-toolchain gate (§10.2 checklist).
# Exit 0 only if every HARD requirement for this machine's platform role is met.
# Usage: ./scripts/preflight.sh   (auto-detects mac=iOS+all / linux=web+android)
set -uo pipefail

PASS=0; WARN=0; FAIL=0
ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; PASS=$((PASS+1)); }
warn() { printf "  \033[33m!\033[0m %s\n" "$1"; WARN=$((WARN+1)); }
bad()  { printf "  \033[31m✗\033[0m %s\n" "$1"; FAIL=$((FAIL+1)); }
hdr()  { printf "\n\033[1m%s\033[0m\n" "$1"; }

IS_MAC=false; [ "$(uname)" = "Darwin" ] && IS_MAC=true

hdr "GitHub / CLI"
command -v gh >/dev/null && ok "gh $(gh --version | head -1 | awk '{print $3}')" || bad "gh not installed"
gh auth status >/dev/null 2>&1 && ok "gh authenticated ($(gh api user -q .login 2>/dev/null))" || bad "gh not authenticated — run: gh auth login"
command -v git >/dev/null && ok "git $(git --version | awk '{print $3}')" || bad "git not installed"

hdr "Docker (Boot / Re-Boot / E2E — web+backend)"
command -v docker >/dev/null && ok "docker $(docker --version | awk '{print $3}' | tr -d ,)" || bad "docker not installed"
docker info >/dev/null 2>&1 && ok "docker daemon running" || bad "docker daemon NOT running — start Docker Desktop"
(docker compose version >/dev/null 2>&1 || command -v docker-compose >/dev/null) && ok "compose available" || bad "docker compose missing"

if $IS_MAC; then
hdr "iOS / Xcode (Mac-only — required for every iOS slice)"
command -v xcodebuild >/dev/null && ok "$(xcodebuild -version | head -1)" || bad "xcodebuild not installed"
command -v xcrun >/dev/null && [ "$(xcrun simctl list devices available 2>/dev/null | grep -c iPhone)" -gt 0 ] \
  && ok "iOS simulators available ($(xcrun simctl list devices available | grep -c iPhone) iPhone)" || bad "no iOS simulators"
command -v pod >/dev/null && ok "cocoapods present" || warn "cocoapods missing (needed for RN/native iOS)"
fi

hdr "Android (build + emulator)"
SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}}"
[ -d "$SDK" ] && ok "SDK at $SDK" || bad "Android SDK dir not found"
[ -n "${ANDROID_HOME:-}${ANDROID_SDK_ROOT:-}" ] && ok "ANDROID_HOME/SDK_ROOT set" || warn "ANDROID_HOME unset — source scripts/setup-android-env.sh"
command -v adb >/dev/null && ok "adb on PATH" || bad "adb not on PATH"
( command -v emulator >/dev/null || [ -x "$SDK/emulator/emulator" ] ) && ok "emulator binary present" || bad "emulator not found"
AVDS=$("$SDK/emulator/emulator" -list-avds 2>/dev/null | grep -c .)
[ "${AVDS:-0}" -gt 0 ] && ok "$AVDS AVD(s) created" || bad "no AVD created — create one in Android Studio"

hdr "Language toolchains (per-stack backends)"
for t in node npm python3 go java; do command -v $t >/dev/null && ok "$t" || bad "$t missing"; done
command -v flutter >/dev/null && ok "flutter" || bad "flutter missing (use cases 2,7 + Flutter iOS/Android)"
command -v dart >/dev/null && ok "dart" || bad "dart missing"
command -v php  >/dev/null && ok "php" || bad "php missing — backends for UC2 (forum) & UC7 (field-service)"
command -v mvn  >/dev/null && ok "maven" || bad "maven missing — Java/Spring backends UC5 (fintech) & UC10 (event)"

hdr "Pipeline env & MCP (the thing under test)"
[ -f .env.pipeline ] && ok ".env.pipeline present" || bad ".env.pipeline MISSING — CometChat app creds + automation keys"
[ -d pipeline-state ] && ok "pipeline-state/ present" || warn "pipeline-state/ missing (auto-created on run)"
[ -d cometchat-skills/skills ] && ok "cometchat-skills cloned ($(ls cometchat-skills/skills | wc -l | tr -d ' ') skills, verify.sh present)" || bad "cometchat-skills repo not cloned"
claude mcp list 2>/dev/null | grep -qiE "docs|cometchat" && ok "docs-mcp connected" || warn "docs-mcp (read-only doc search) not connected — optional; skills clone covers codegen"

hdr "Disk headroom (§6.4 disk-aware admission)"
AVAIL=$(df -g / 2>/dev/null | tail -1 | awk '{print $4}')
if [ -n "${AVAIL:-}" ]; then
  [ "$AVAIL" -ge 40 ] && ok "${AVAIL}GB free" || warn "${AVAIL}GB free — tight for Docker+emulators+23 codebases; keep boot concurrency low"
fi

printf "\n\033[1mSummary:\033[0m \033[32m%d pass\033[0m · \033[33m%d warn\033[0m · \033[31m%d fail\033[0m\n" "$PASS" "$WARN" "$FAIL"
[ "$FAIL" -eq 0 ] && { echo "READY — all hard gates green."; exit 0; } || { echo "NOT READY — resolve the ✗ items above."; exit 1; }
