// flutter_chat_receive.mjs — CROSS-PARTY real-time RECEIVE proof for a Flutter CanvasKit web app.
//
// Flutter web has no real DOM — it emits a flt-semantics accessibility tree (needs the app to call
// SemanticsBinding.instance.ensureSemantics()). We drive login through it (email/password fields wrapped
// in Semantics(identifier:'email-input'/'password-input')), then a peer sends a UNIQUE nonce via REST and
// the logged-in Flutter web app must RENDER it — proving its live CometChat socket delivered the message
// (catches "socket dead but REST login works" for Flutter, the same class as the RN F-mobile-creds bug).
//
// The send is REST (deterministic, from the seeded peer) so we don't drive the fragile Flutter composer;
// the RECEIVE (a real message landing in A's live UI) is the thing being proven. One Flutter context.
// Env: URL, A_EMAIL, A_PASSWORD, SUBMIT, APP_ID, REGION, REST_API_KEY, SENDER_UID, RECEIVER_UID, NONCE, OUT.
import { chromium } from 'playwright';

const URL = process.env.URL || 'http://localhost:3000/';
const A_EMAIL = process.env.A_EMAIL || 'chat-b@com.io';
const A_PASSWORD = process.env.A_PASSWORD || 'Mkt@seed2026!';
const SUBMIT = process.env.SUBMIT || 'Sign In';
const NONCE = process.env.NONCE || ('rx-' + Date.now());
const OUT = process.env.OUT || '/tmp/flutter-chat-receive.png';
const APP_ID = process.env.APP_ID, REGION = process.env.REGION || 'us';
const REST_API_KEY = process.env.REST_API_KEY;
const SENDER_UID = process.env.SENDER_UID, RECEIVER_UID = process.env.RECEIVER_UID;

const R = { loggedIn: false, sdkReady: false, sent: false, received: false };

async function fillSemanticField(page, identifier, ariaHint, value) {
  // Flutter web exposes Semantics(identifier:) as the `flt-semantics-identifier` attribute (NOT id),
  // and the real editable field is an <input> with an aria-label (e.g. "Email"/"Password"). The catch:
  // after focusing, Flutter needs a beat to attach the editable, so the FIRST keystroke is dropped if
  // you type immediately (observed: "Com@..." typed as "om@..."). So: focus, wait, clear, type, then
  // VERIFY the value and retry until it matches — robust to dropped chars.
  // Flutter keeps TWO inputs per field — a DISABLED placeholder and the active editable. Target the
  // enabled one by its aria-label (identifier '${identifier}' is on the wrapper, not the input).
  const el = page.locator(`input[aria-label*="${ariaHint}" i]:not([disabled])`).first();
  if (await el.count() === 0) return false;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      await el.click({ timeout: 4000 });
      await page.waitForTimeout(attempt === 0 ? 400 : 700);  // let Flutter attach the editable (else 1st key drops)
      const cur = await el.inputValue().catch(() => '');      // clear any stale/partial text char-by-char
      for (let i = 0; i < cur.length + 2; i++) await page.keyboard.press('Backspace');
      await page.keyboard.type(value, { delay: 45 });
      if ((await el.inputValue().catch(() => '')) === value) return true;
    } catch { /* retry */ }
  }
  return (await el.inputValue().catch(() => '')) === value;
}

async function restSend() {
  // CometChat REST v3 — send NONCE from the seeded peer to the logged-in receiver.
  const api = `https://${APP_ID}.api-${REGION}.cometchat.io/v3/messages`;
  const res = await fetch(api, {
    method: 'POST',
    headers: { apiKey: REST_API_KEY, appId: APP_ID, onBehalfOf: SENDER_UID,
               'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ category: 'message', type: 'text', receiverType: 'user',
                           receiver: RECEIVER_UID, data: { text: NONCE } }),
  });
  return res.ok;
}

const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1280, height: 900 } });
try {
  await p.goto(URL, { waitUntil: 'load', timeout: 30000 });
  await p.waitForSelector('flt-semantics-host, flutter-view', { timeout: 30000 });
  await p.waitForTimeout(5000);                       // first frame + semantics build
  // login as the seeded receiver account
  const okE = await fillSemanticField(p, 'email-input', 'mail', A_EMAIL);
  const okP = await fillSemanticField(p, 'password-input', 'assword', A_PASSWORD);
  if (!okE || !okP) R.note = 'could not fill login semantics fields';
  // submit: Enter in the password field triggers Flutter onFieldSubmitted; the Sign In button is a fallback
  await p.keyboard.press('Enter').catch(() => {});
  try { const btn = p.getByRole('button', { name: SUBMIT, exact: false }).first();
        if (await btn.count() > 0) await btn.click({ timeout: 5000 }); } catch { /* Enter already sent */ }
  // logged in = the email-input semantics node is gone (navigated off the login screen)
  await p.waitForFunction(() => !(document.body.innerText || '').includes('Sign in to continue'),
                          { timeout: 25000 }).catch(() => {});
  await p.waitForTimeout(3000);
  R.loggedIn = okE && okP && (await p.locator('[flt-semantics-identifier="email-input"]').count()) === 0;
  // best-effort: open a messages/chat surface so the incoming message renders (thread OR list preview)
  for (const rx of [/messages?/i, /chats?/i, /conversations?/i, /inbox/i]) {
    const nav = p.getByRole('button', { name: rx }).first();
    try { if (await nav.count() > 0) { await nav.click({ timeout: 4000 }); await p.waitForTimeout(2500); break; } } catch { /* next */ }
  }
  const firstConv = p.getByText(/Chat A|Chat B|automated call-test seed/i).first();
  try { if (await firstConv.count() > 0) { await firstConv.click({ timeout: 4000 }); await p.waitForTimeout(2500); } } catch { /* stay on list */ }
  R.sdkReady = /message|chat|conversation|automated call-test seed/i.test(await p.evaluate(() => document.body.innerText || ''));

  // peer sends the unique nonce — A must render it over its live socket
  R.sent = await restSend().catch(() => false);
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline) {
    const text = await p.evaluate(() => document.body.innerText || '');
    if (text.includes(NONCE)) { R.received = true; break; }
    await p.waitForTimeout(1500);
  }
  await p.screenshot({ path: OUT }).catch(() => {});
} catch (e) {
  R.error = String(e).split('\n')[0].slice(0, 160);
  await p.screenshot({ path: OUT }).catch(() => {});
}
R.chatWorks = R.received;
console.log(JSON.stringify(R));
await b.close();
process.exit(0);
