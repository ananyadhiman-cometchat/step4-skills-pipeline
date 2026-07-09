# STEP4 — Iterative Skills Reviewer Pipeline

A reusable agentic pipeline that builds a production-shaped app across **web + Android + iOS**,
integrates **CometChat** (chat + voice/video) via the `cometchat-skills` catalog, and captures
**structured findings** about where the CometChat *skills* and *MCP docs* fall short — so the skills
team gets an evidence-backed backlog, not anecdotes.

It is a **hybrid** design: deterministic **Python plumbing** (`run_usecase.py`) orchestrates the
stages and gates; the actual code is written by **`claude -p` headless codegen** driven by the
CometChat skills. Two human checkpoints (CP1 baseline, CP2 integrated) gate the GitHub pushes.

> Built and hardened end-to-end on **UC1 (Marketplace)** — web (Next.js) + Android/iOS (Expo RN) +
> FastAPI backend, all three connected to a real CometChat app with chat and cross-platform calling.

---

## Pipeline stages

```
preflight → provision-app → build → containerize → boot → 🛑CP1 →
push-main → integrate → verify → demo(boot-2) → 🛑CP2 → push-branch
```

- **preflight** — stack-readiness gate; installs the e2e toolchain (maestro / playwright / jdk17 …);
  `ensure_repo` inits the app repo on `main` **and writes `.gitignore` before anything is tracked**.
- **provision-app** — creates/configures the real CometChat app via automation keys; fills creds.
- **build** — baseline codegen (NO CometChat) for each component; compile-authoritative gate.
- **containerize / boot** — Dockerfiles + compose; health-check + login smoke → **CP1**.
- **integrate** — CometChat wired into every component via the skills; compile gate.
- **verify** — seeds CometChat users, then proves chat + calling in a real browser, runs the
  two-party call matrix (web↔web voice+video), and probes AI moderation.
- **demo (boot-2)** — mandatory rebuild of the mobile apps from the integration branch; boots
  web + Android emulator + iOS simulator, runs the **automated mobile↔web call matrix**
  (android↔web / ios↔web × voice+video), leaves everything up for hands-on test → **CP2**.
- **push-main / push-branch** — auto-push to GitHub on checkpoint approval.

Gates live in `pipeline/lib/gates.py`; a failed gate exits non-zero and the conductor halts.

---

## Layout

| Path | What |
|---|---|
| `pipeline/run_usecase.py` | the stage worker (one stage per invocation) |
| `pipeline/batch_runner.py` | reproducible wave/checkpoint sequencer (the conductor) |
| `pipeline/lib/` | `mobile` (standalone RN release builds), `verify` (e2e + call matrix), `cometchat` (REST seed + moderation probe), `gates`, `state`, `prompts`, … |
| `pipeline/prompts/` | the `claude -p` codegen templates (build / integrate / containerize / provision) |
| `pipeline/e2e/` | browser + device e2e: `chatcall.web.mjs`, `twoparty.web.mjs`, `twoparty_mobile.py` + `mobile_flows/*.yaml` (Maestro) |
| `pipeline/config/` | `settings.json` (models per stage, toolchain), `use_cases.json` |
| `pipeline-state/gaps/<slug>.md` | **curated skills / MCP / SDK inconsistency ledger** (the deliverable) |
| `pipeline-state/pipeline-notes/<slug>.md` | codegen-adherence / harness / operator-setup notes (NOT skills gaps) |
| `MASTER_GAPS.md` | auto-generated rollup of the per-use-case ledgers |
| `STEP4_PIPELINE.md` / `STEP4_USE_CASES.md` | the governing spec + the 10 use cases |
| `scripts/` | `build-master-gaps.sh`, `preflight.sh`, `setup-android-env.sh` |

---

## Screenshot testing — vision + baseline

DOM selectors proved brittle (kit class names differ per surface/platform) and the subtle visual
bugs (bottom-left call ring, chat bleeding under a call, app header over a full-screen call) were
only caught by a human eyeballing shots. Two complementary layers now automate that:

- **`lib/vision.py` — "is it correct?"** Claude-vision grades each screenshot against a named
  RUBRIC (`incoming_ring`, `ongoing_call`, `chat_thread`, `feed_loaded`, …) → structured
  per-check pass/fail with reasons. No selectors, no human in the loop. Reuses the pipeline's
  `claude -p` auth (no API key). Rubrics are position/platform tolerant (a centered web modal AND
  an android top-banner pass; only a corner-toast fails).
- **`lib/visual_baseline.py` — "did it change?"** Perceptual dHash + normalized pixel diff vs a
  stored golden (first run establishes it). Backend is pluggable: `local` (default, Pillow, offline)
  or `applitools`/`percy` when `APPLITOOLS_API_KEY`/`PERCY_TOKEN` is set.
- **`lib/shotreview.py`** runs both over a shot set and emits a self-contained **HTML gallery**
  (images inlined) for CP1/CP2 review, plus a compact machine summary folded into `verify.json`.

Wired into `stage_verify` (advisory, not a hard gate — `verify.vision_review` in settings). Visual
issues are recorded to `pipeline-state/pipeline-notes/<slug>.md`, never the skills ledger.

---

## Setup

1. **Clone the CometChat skills catalog** next to this repo (the pipeline loads it as invocable skills):
   ```bash
   git clone https://github.com/cometchat/cometchat-skills.git
   ```
2. **Provide creds** — copy `.env.pipeline.example` → `.env.pipeline` and fill the CometChat
   automation + app keys. This file is git-ignored and **must never be committed** (nor
   `cometchat-app-config.json`, which the provision stage writes with live keys).
3. **Toolchain** — Docker, JDK 17, Android SDK + an emulator AVD, Xcode + an iOS simulator,
   Node, Python 3. `preflight` self-installs the missing e2e tools (maestro / playwright / watchman).

## Run

```bash
# a single stage
python3 pipeline/run_usecase.py --use-case mkt --stage build

# the full conductor (interactive checkpoints)
python3 pipeline/batch_runner.py --wave 0
```

Generated app repos land under `runs/<slug>/` (git-ignored here — each is pushed to its own repo).

---

## Findings model

The whole point is the findings. Two files, kept strictly separate:

- **`pipeline-state/gaps/<slug>.md`** — ONLY genuine CometChat **skills / MCP-docs / SDK** gaps
  (incomplete guidance, missing triggers, SDK packaging). Each entry carries a concrete *skill ask*.
- **`pipeline-state/pipeline-notes/<slug>.md`** — everything that is **not** a CometChat defect:
  AI/codegen mistakes against a *correct* skill, our own harness bugs, and operator/dashboard setup.

`stage_verify` classifies every auto-detected failure by cause and routes it to the right file —
harness stack traces never pollute the skills ledger.

See `pipeline-state/gaps/mkt.md` for the UC1 results (5 skills gaps + 1 SDK packaging issue, each
with a fix and a skill ask) and `pipeline-state/pipeline-notes/mkt.md` for the rest.
