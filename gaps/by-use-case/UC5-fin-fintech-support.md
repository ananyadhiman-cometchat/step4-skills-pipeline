> **UC5 · Fintech support (`fin`)** — fintech customer-support: real-time support chat + calls between customers and agents.
> **Stack:** Vue 3 web · Android (Kotlin/Compose, UI Kit v6) · iOS (native Swift) · Java (Spring) backend — **3 separate codebases**.
> **CometChat:** ⚠️ **no `cometchat-vue` skill exists** (known, pre-seeded gap — expect none to fire on the Vue slice) · Android v6 Compose · iOS Swift + Calls SDK. _**In progress** — ledger still filling._
> **Gaps recorded: 1.** _Source: `pipeline-state/gaps/fin.md` — edit there, not here._

---

# fin — CometChat skills/SDK/docs inconsistencies (self-heal witnessed)

## Auto-repaired (self-heal witnessed — the fix's existence IS the finding)
<!-- selfheal:web-call-css-vars -->
- **`SDK-gap:`** [self-heal:web-call-css-vars] The CometChat web calls SDK (@cometchat/calls-sdk-javascript) sizes its tile-grid <div> with an INLINE height: calc(100% - var(--cometchat-calls-call-footer-height) - var(--cometchat-calls-call-header-height)) but references those two custom properties WITHOUT ever defining them (each appears exactly once — this calc — in the SDK bundle; the UI Kit doesn't define them either). An undefined var() in calc() is invalid at computed-value time → height computes to 0px → the ongoing-call grid collapses → the SDK's ResizeObserver throws "Container dimensions and number of tiles must be positive" and the call renders collapsed (proven: undefined-var calc → 0px, defined → 674px). The SDK must define these variables itself, or use fallbacks in the calc (var(--x, 0px)). Workaround (auto-applied by the web build gate): define both in the app's global stylesheet :root.
  - _auto-repaired by the harness (fix's existence IS the finding)_: defined call-height CSS vars in src/assets/main.css
  - _trigger evidence_: `proactive guard — pre-empts the known failure signature`

