# DEFERRED — work parked for later (surfaced when its trigger fires)

## Requirements-depth upgrade across all use cases  ·  TRIGGER: end of the del pipeline
Deferred 2026-07-15 at del/CP1 (user request: "take note and remind me at the end of this del pipeline").

**Problem:** generated apps are SHALLOW — no in-app create-record flows (e.g. no "create delivery"),
thin seed data, no images/avatars. Root cause: the spec-pins (`pipeline/requirements/<slug>.md`) that
drive codegen are thin, and the pipeline gates on "compiles + boots" so a thin spec passes.

**Scope:** upgrade ALL 10 use-case spec-pins for depth — full CRUD per core entity, role-complete flows
(every role can do its whole job in-app), N seeded records across states, images/avatars, empty/error
states — plus a **spec-depth gate** so thin specs can't pass preflight.

**Chosen rollout = PILOT:** author a depth standard/rubric → inject into `render_requirements` + add the
spec-depth gate → deepen del's spec (create-delivery, opt-in, images, more entities) → regenerate del to
prove it → then rewrite the other 9 spec-pins. Evidence: `pipeline-state/pipeline-notes/del.md`.

**REMIND the user to start this when del reaches the END of its pipeline** (CP2 approved → push-branch →
teardown → "wave complete").
