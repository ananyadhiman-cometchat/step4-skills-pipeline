# setup-android-env.sh — source this (don't execute) to put the Android SDK on PATH.
#   source scripts/setup-android-env.sh
# Fixes the two Android gaps preflight flags: ANDROID_HOME unset + emulator not on PATH.
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export PATH="$ANDROID_HOME/emulator:$ANDROID_HOME/platform-tools:$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"
echo "ANDROID_HOME=$ANDROID_HOME"
echo "AVDs: $("$ANDROID_HOME/emulator/emulator" -list-avds 2>/dev/null | tr '\n' ' ')"
