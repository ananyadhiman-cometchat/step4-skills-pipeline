// twoparty_chat.web.mjs — the CROSS-PARTY real-time RECEIVE proof (the keystone functional check).
//
// The old chatcall.web.mjs "proved" chat with getByText(/camera/i) + the SENDER's own optimistic echo —
// neither needs a working socket, so the exact bug the pipeline exists to catch (placeholder APP_ID →
// real-time socket dead, REST login still works) reported GREEN. This test makes that impossible:
//
//   A logs in (context 1)  →  opens the conversation with B  →  starts listening
//   B logs in (context 2)  →  opens the conversation with A  →  sends a UNIQUE per-run NONCE
//   PASS iff A's DOM renders that exact nonce within the timeout (a live WebSocket delivered it).
//
// If A's socket is dead, A never receives B's message in real time → the nonce never appears → FAIL.
// Env: WEB_URL, A_EMAIL, B_EMAIL, E2E_PASSWORD, NONCE, SHOT_DIR.
import { chromium } from '@playwright/test'

const WEB = process.env.WEB_URL || 'http://localhost:3000'
const PW = process.env.E2E_PASSWORD || 'Mkt@seed2026!'
const NONCE = process.env.NONCE || ('rx-' + Date.now())
const SHOT_DIR = process.env.SHOT_DIR || '/tmp'
const A = process.env.A_EMAIL || 'bob.buyer@mkt.io'      // receiver
const B = process.env.B_EMAIL || 'sara.seller@mkt.io'    // sender

const R = { aLogin: false, bLogin: false, aOpened: false, bOpened: false,
            sent: false, received: false, senderEcho: false }

async function login(ctx, email) {
  const p = await ctx.newPage({ viewport: { width: 1280, height: 900 } })
  const errs = []
  p.on('pageerror', e => errs.push(String(e).slice(0, 120)))
  await p.goto(`${WEB}/login`, { waitUntil: 'networkidle' })
  await p.getByTestId('email-input').fill(email)
  await p.getByTestId('password-input').fill(PW)
  await p.getByTestId('login-submit').click()
  await p.waitForFunction(() => !/\/login\/?$/.test(location.pathname), null, { timeout: 20000 })
  await p.goto(`${WEB}/conversations`, { waitUntil: 'networkidle' })
  await p.waitForTimeout(4000)
  return { page: p, errs }
}

async function openFirstConversation(p) {
  const item = p.locator('.cometchat-conversation-item, .cometchat-conversations__list-item-wrapper, .cometchat-conversations__list-item, .cometchat-list-item, .cometchat-conversations .cometchat-list-item').first()
  if (await item.count() === 0) return false
  await item.click()
  await p.waitForTimeout(2500)
  return true
}

const b = await chromium.launch()
try {
  const aCtx = await b.newContext(), bCtx = await b.newContext()
  const a = await login(aCtx, A); R.aLogin = true
  const bb = await login(bCtx, B); R.bLogin = true

  R.aOpened = await openFirstConversation(a.page)   // A watches the thread
  R.bOpened = await openFirstConversation(bb.page)   // B will send into it

  // B sends the unique nonce through the REAL composer (its own socket send).
  // Selector spans EVERY CometChat composer variant: the standard CometChatMessageComposer AND the
  // CometChatCompactMessageComposer (class `cometchat-compact-message-composer__input`, a contenteditable
  // DIV) — the old `.cometchat-message-composer*`-only selector missed the compact one entirely (sent=false).
  const input = bb.page.locator('[class*="composer" i] [contenteditable="true"], [class*="composer" i][contenteditable="true"], [class*="composer" i] textarea, .cometchat-message-composer__input, .cometchat-compact-message-composer__input').first()
  if (await input.count() > 0) {
    await input.click(); await input.type(NONCE, { delay: 15 })
    const send = bb.page.locator('.cometchat-message-composer__send-button, [class*="send-button" i]').first()
    if (await send.count() > 0) await send.click(); else await bb.page.keyboard.press('Enter')
    R.sent = true
    R.senderEcho = (await bb.page.getByText(NONCE, { exact: false }).count()) > 0   // local echo (weak)
  }

  // A must RECEIVE the nonce over its live socket — poll A's DOM for the exact text.
  const deadline = Date.now() + 15000
  while (Date.now() < deadline) {
    if ((await a.page.getByText(NONCE, { exact: false }).count()) > 0) { R.received = true; break }
    await a.page.waitForTimeout(1000)
  }
  await a.page.screenshot({ path: `${SHOT_DIR}/chat-receive.png` }).catch(() => {})
  R.aPageErrors = a.errs.slice(0, 4)
} catch (e) {
  R.error = String(e).slice(0, 200)
}
// chatWorks = the RECEIVER saw the sender's unique message (real cross-party delivery).
R.chatWorks = R.received
console.log(JSON.stringify(R))
await b.close()
