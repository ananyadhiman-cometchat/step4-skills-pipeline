// chatcall.web.mjs — the canonical web chat/call verify (login → open chat → send → call).
// Proves the CometChat integration at runtime. Reads config from env:
//   E2E_EMAIL, E2E_PASSWORD, WEB_URL, SHOT (screenshot path). Prints a JSON verdict.
import { chromium } from '@playwright/test'

const EMAIL = process.env.E2E_EMAIL || 'bob.buyer@mkt.io'
const PW = process.env.E2E_PASSWORD || 'Mkt@seed2026!'
const WEB = process.env.WEB_URL || 'http://localhost:3000'
const SHOT = process.env.SHOT || ''

const R = { login: false, sdkReady: false, seedMsgVisible: false, composerFound: false, msgSent: false, callUI: false }
const b = await chromium.launch()
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
  // the ACTUAL seeded message text (cometchat.seed_conversation), not a coincidental /camera/ substring
  R.seedMsgVisible = (await p.getByText('automated call-test seed', { exact: false }).count()) > 0
  const input = p.locator('.cometchat-message-composer [contenteditable="true"], .cometchat-message-composer__input, .cometchat-message-composer textarea').first()
  R.composerFound = (await input.count()) > 0
  const msg = 'Yes it is available! (e2e ' + Date.now().toString().slice(-5) + ')'
  await input.click(); await input.type(msg, { delay: 20 })
  const send = p.locator('.cometchat-message-composer__send-button, [class*="send-button" i]').first()
  if (await send.count() > 0) await send.click(); else await p.keyboard.press('Enter')
  await p.waitForTimeout(3000)
  R.msgSent = (await p.getByText(msg, { exact: false }).count()) > 0   // the FULL unique text, not a 20-char prefix
  const call = p.locator('.cometchat-call-button__voice button, .cometchat-call-button__voice, .cometchat-call-button__video button').first()
  await call.click()
  await p.waitForTimeout(4000)
  // a REAL call-session surface that appears AFTER the click — NOT `[class*=cometchat-call]`, which
  // matches the call BUTTON that is always present the moment the conversation opens (false green).
  R.callUI = (await p.locator('.cometchat-outgoing-call, .cometchat-ongoing-call, [class*="outgoing-call" i], [class*="ongoing-call" i], [class*="calling" i]').count()) > 0
  if (SHOT) await p.screenshot({ path: SHOT })
} catch (e) { R.error = String(e).slice(0, 160) }
R.pageErrors = errs.slice(0, 5)
R.chatWorks = R.login && R.seedMsgVisible && R.msgSent
R.callWorks = R.callUI
console.log(JSON.stringify(R))
await b.close()
