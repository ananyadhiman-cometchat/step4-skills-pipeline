# GLOBAL POLICY — applies to every use case (a hard floor; per-UC directives may not override these)

Read by every use case's supervisor at startup and each boundary. Edit via the communicator
(`supervisor.py command --scope global --kind ...`) or directly here for standing policy.

## Security (non-negotiable)
- NEVER commit secrets. `.env`, `.env.cometchat`, `cometchat-app-config.json`, `runs/` stay git-ignored.
- Compose/config reference secrets as `${VAR}` env refs, never literal values.
- GitHub push is human-gated — a `push-*` stage only runs after an explicit human checkpoint approval.

## Verification (behavioral, not just build)
- A stage is not "green" because it compiles and boots. The behavioral-verify tier must run.
- A feature that cannot be proven in-harness is recorded `unverified` — NEVER reported as passing.

## Failure handling
- On a codegen/build failure the diagnose loop patches in an isolated worktree and re-gates before
  landing. A fix that does not re-gate green is never merged. Escalate with the HALT packet when exhausted.

## CometChat integration defaults (learned; carry forward to every use case)
- Provision a CometChat user for EVERY app user at creation/login; omit `avatar` when absent
  (CometChat rejects `avatar: null` with HTTP 400, leaving the user tokenless).
- Detect a duplicate uid via `ERR_UID_ALREADY_EXISTS` (CometChat returns 400, not 409).
- Flutter calling: do NOT eager-init the Calls SDK at startup (it hijacks incoming calls); lazy-init on
  the call path. `await CometChatCalls.getLoggedInUser()` (it is async). Resolve the incoming caller
  name via `CometChat.getUser(uid)` (the socket event carries only a uid).
- Don't stack `CometChatCallButtons` in `auxiliaryButtonView` — the message header already renders them.
