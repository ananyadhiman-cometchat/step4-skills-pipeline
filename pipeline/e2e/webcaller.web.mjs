// webcaller.web.mjs — web places an outgoing call to a target user and HOLDS the line so the
// other end (a mobile device driven by Maestro) has time to receive + accept. One browser context.
// Env: WEB_URL, CALL_TYPE(voice|video), CALLER_EMAIL, E2E_PASSWORD, HOLD_MS, SHOT_DIR, TAG.
// Prints a JSON verdict: {login, callStarted, callerOngoing}.
import { launchForCalls } from './browser.mjs'

const WEB = process.env.WEB_URL || 'http://localhost:3000'
const PW = process.env.E2E_PASSWORD || 'Mkt@seed2026!'
const CALL_TYPE = (process.env.CALL_TYPE || 'voice').toLowerCase()
const EMAIL = process.env.CALLER_EMAIL || 'bob.buyer@mkt.io'
const HOLD_MS = parseInt(process.env.HOLD_MS || '45000', 10)
const SHOT_DIR = process.env.SHOT_DIR || '/tmp'
const TAG = process.env.TAG || 'mobilecall'

const R = { login: false, callStarted: false, callerOngoing: false, callType: CALL_TYPE }
const b = await launchForCalls()
try {
  const ctx = await b.newContext({ permissions: ['microphone', 'camera'] })
  const p = await ctx.newPage({ viewport: { width: 1280, height: 900 } })
  await p.goto(`${WEB}/login`, { waitUntil: 'networkidle' })
  await p.getByTestId('email-input').fill(EMAIL)
  await p.getByTestId('password-input').fill(PW)
  await p.getByTestId('login-submit').click()
  await p.waitForFunction(() => !/\/login\/?$/.test(location.pathname), null, { timeout: 20000 }); R.login = true
  await p.goto(`${WEB}/conversations`, { waitUntil: 'networkidle' })
  await p.waitForTimeout(4000)
  await p.locator('.cometchat-conversation-item, .cometchat-conversations__list-item-wrapper, .cometchat-conversations__list-item, .cometchat-list-item').first().click()
  await p.waitForTimeout(3000)
  const sel = CALL_TYPE === 'video'
    ? '.cometchat-call-buttons__video button, button[aria-label="Video call"], .cometchat-call-button__video'
    : '.cometchat-call-buttons__voice button, button[aria-label="Voice call"], .cometchat-call-button__voice'
  await p.locator(sel).first().click()
  R.callStarted = true
  // hold the line while the mobile end receives + accepts
  const start = Date.now()
  while (Date.now() - start < HOLD_MS) {
    await p.waitForTimeout(3000)
    R.callerOngoing = (await p.locator('[class*="ongoing-call" i], .cometchat-ongoing-call, [class*="call-screen" i], video').count()) > 0
    if (R.callerOngoing) break
  }
  await p.waitForTimeout(3000)
  R.callerOngoing = (await p.locator('[class*="ongoing-call" i], .cometchat-ongoing-call, [class*="call-screen" i], video').count()) > 0
  await p.screenshot({ path: `${SHOT_DIR}/webcaller-${TAG}.png` })
  await p.waitForTimeout(4000)   // stay connected a bit longer for the mobile screenshot
} catch (e) { R.error = String(e).slice(0, 200) }
console.log(JSON.stringify(R))
await b.close()
