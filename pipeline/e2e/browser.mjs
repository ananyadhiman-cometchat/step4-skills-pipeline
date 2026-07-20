// browser.mjs — one place that decides HOW the pipeline opens a browser.
//
// WHY THIS EXISTS: call tests must run in a REAL (headed) Chromium, not headless.
//
// Headless Chromium does not negotiate WebRTC media the way a real browser does: the ongoing-call
// surface may never mount, the media stream drops after a beat, and the call screens are not
// reliably renderable for a screenshot. That produced repeated FALSE signals on fin — legs reported
// as "not connected" that had genuinely connected, and call screenshots that could not be graded.
// A headed browser removes that whole class of ambiguity, so a red call leg means a real defect.
//
// Chat-only / screenshot-only scripts do not need this and stay headless (faster, and they have been
// reliable) — the distinction is deliberate, not an oversight.
//
// Override with STEP4_HEADLESS=1 for an environment with no display (CI). Doing so re-introduces the
// headless WebRTC ambiguity, so call verdicts from such a run should be treated as advisory.
import { chromium } from '@playwright/test'

const MEDIA_ARGS = [
  '--use-fake-ui-for-media-stream',     // auto-accept the camera/mic permission prompt
  '--use-fake-device-for-media-stream', // synthetic camera/mic so a real stream exists
  '--autoplay-policy=no-user-gesture-required',
  '--disable-features=IsolateOrigins,site-per-process',
]

/** Headed by default — for anything that places, receives or renders a CALL. */
export async function launchForCalls(extraArgs = []) {
  const headless = process.env.STEP4_HEADLESS === '1'
  if (headless) {
    console.error('[browser] STEP4_HEADLESS=1 — call verdicts from a headless run are ADVISORY: '
      + 'headless Chromium does not negotiate WebRTC media reliably.')
  }
  return chromium.launch({ headless, args: [...MEDIA_ARGS, ...extraArgs] })
}

/** Headless is fine for chat/screenshot work that never touches WebRTC. */
export async function launchForChat(extraArgs = []) {
  return chromium.launch({ headless: true, args: extraArgs })
}
