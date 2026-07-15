# del — harness/environment notes (NOT CometChat gaps)

## Baseline android build failed on toolchain env, not code (2026-07-15, first durable-harness run)
The build stage HALTED because android (Compose) wouldn't compile — two chained environment issues,
both now self-healed; backend/web/iOS compiled first try.

1. **JDK too new.** Machine default is Java 26; Kotlin (AGP 8.7.3 / Gradle 8.11.1) throws
   `IllegalArgumentException: 26.0.1` from `JavaVersion.parse`. A compatible JDK existed (brew
   `openjdk@17`, Android Studio JBR 21) but wasn't default. Harness gap: the `jdk17` self-heal sig
   didn't match the `JavaVersion.parse` signature so it never fired. FIXED: extended sig; `_fix_jdk17`
   discovers a real 17-21 JDK and persists `org.gradle.java.home`. (Also: preflight checks java EXISTS,
   not that its VERSION is android-compatible.)
2. **Android SDK unset.** After the JDK fix: `SDK location not found`. Codegen omits machine-specific
   `local.properties`. Harness gap: no rule. FIXED: added `android-sdk` rule (writes `sdk.dir`).
3. **Diagnose no-HEAD crash.** Build failing before the baseline commit → no HEAD → `git worktree add …
   HEAD` failed. FIXED: `diagnose.py` makes a wip snapshot commit first.

Net: all three are harness/environment robustness fixes; none is a CometChat gap. Protects the remaining
android use cases (fin, evt, cre, rea).
