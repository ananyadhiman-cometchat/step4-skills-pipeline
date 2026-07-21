// chatcall.web.mjs — the canonical web chat/call verify (login → open chat → send → call).
// Proves the CometChat integration at runtime. Reads config from env:
//   E2E_EMAIL, E2E_PASSWORD, WEB_URL, SHOT (screenshot path). Prints a JSON verdict.
import { launchForCalls } from './browser.mjs'

const EMAIL = process.env.E2E_EMAIL || 'bob.buyer@mkt.io'
const PW = process.env.E2E_PASSWORD || 'Mkt@seed2026!'
const WEB = process.env.WEB_URL || 'http://localhost:3000'
const SHOT = process.env.SHOT || ''

const R = { login: false, sdkReady: false, threadHasHistory: false, composerFound: false, msgSent: false, callUI: false }
const b = await launchForCalls()
const p = await b.newPage({ viewport: { width: 1280, height: 900 } })
const errs = []
p.on('pageerror', e => errs.push(String(e).slice(0, 120)))
try {
  await p.goto(`${WEB}/login`, { waitUntil: 'networkidle' })
  await p.getByTestId('email-input').fill(EMAIL)
  await p.getByTestId('password-input').fill(PW)
  await p.getByTestId('login-submit').click()
  await p.waitForFunction(() => !/\/login\/?$/.test(location.pathname), null, { timeout: 20000 })
  R.login = true
  await p.goto(`${WEB}/conversations`, { waitUntil: 'networkidle' })
  await p.waitForTimeout(5000)
  // SDK-init signal: the kit's own conversation list rendered (falls back to the kit class if the app
  // didn't add the testid). App login alone is NOT proof the CometChat SDK initialised.
  R.sdkReady = (await p.getByTestId('cometchat-conversation-list').count()) > 0 ||
               (await p.locator('.cometchat-conversations, .cometchat-conversations__list').count()) > 0
  await p.locator('.cometchat-conversation-item, .cometchat-conversations__list-item-wrapper, .cometchat-conversations__list-item, .cometchat-list-item').first().click()
  await p.waitForTimeout(3500)
  // The opened thread already has message history — the app seeds a few messages between the chatPair
  // personas, so a real (non-empty) conversation shows bubbles on open. Informational only; NOT a gate,
  // because whether THIS pair's thread is pre-seeded is a spec choice, and round-tripping our OWN message
  // (msgSent) is the load-bearing proof. (Was a hard check for the deleted synthetic seed_conversation
  // string 'automated call-test seed' — that account no longer exists, real demo accounts are used.)
  R.threadHasHistory = (await p.locator('.cometchat-message-bubble, [class*="message-bubble" i], .cometchat-message-list__message-container').count()) > 0
  const input = p.locator('.cometchat-message-composer [contenteditable="true"], .cometchat-message-composer__input, .cometchat-message-composer textarea').first()
  R.composerFound = (await input.count()) > 0
  const msg = 'Yes it is available! (e2e ' + Date.now().toString().slice(-5) + ')'
  await input.click(); await input.type(msg, { delay: 20 })
  const send = p.locator('.cometchat-message-composer__send-button, [class*="send-button" i]').first()
  if (await send.count() > 0) await send.click(); else await p.keyboard.press('Enter')
  await p.waitForTimeout(3000)
  R.msgSent = (await p.getByText(msg, { exact: false }).count()) > 0   // the FULL unique text, not a 20-char prefix
  const call = p.locator('.cometchat-call-buttons__voice button, button[aria-label="Voice call"], .cometchat-call-buttons__video button, button[aria-label="Video call"], .cometchat-call-button__voice').first()
  await call.click()
  await p.waitForTimeout(4000)
  // a REAL call-session surface that appears AFTER the click — NOT `[class*=cometchat-call]`, which
  // matches the call BUTTON that is always present the moment the conversation opens (false green).
  R.callUI = (await p.locator('.cometchat-outgoing-call, .cometchat-ongoing-call, [class*="outgoing-call" i], [class*="ongoing-call" i], [class*="calling" i]').count()) > 0
  if (SHOT) await p.screenshot({ path: SHOT })
} catch (e) { R.error = String(e).slice(0, 160) }
R.pageErrors = errs.slice(0, 5)
// chat is proven by: logged in + the CometChat SDK actually initialised (conversation list rendered) +
// we round-tripped our OWN message (typed → rendered in the thread). No dependency on a pre-seeded string.
R.chatWorks = R.login && R.sdkReady && R.msgSent
R.callWorks = R.callUI
console.log(JSON.stringify(R))
await b.close()
