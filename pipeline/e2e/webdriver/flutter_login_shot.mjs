// Drive a Flutter CanvasKit web app's login through the accessibility (flt-semantics) tree — the only
// way to automate Flutter web since --web-renderer html was removed (no real DOM to query otherwise).
// The app must call SemanticsBinding.instance.ensureSemantics() at startup. Params via env:
//   URL (default http://localhost:3000/), ROLE (demo button label), SUBMIT, OUT (screenshot path).
import { chromium } from 'playwright';
const URL = process.env.URL || 'http://localhost:3000/';
const ROLE = process.env.ROLE || 'Member';
const SUBMIT = process.env.SUBMIT || 'Sign In';
const OUT = process.env.OUT || '/tmp/web-loggedin.png';
const b = await chromium.launch();
const p = await b.newPage({ viewport:{width:1280,height:900} });
let ok = false, note = '';
try {
  await p.goto(URL, { waitUntil:'load', timeout:30000 });
  await p.waitForSelector('flt-semantics-host, flutter-view', { timeout:30000 });
  await p.waitForTimeout(5000);                          // flutter first frame + semantics build
  // tap the demo-role button (fills creds) then submit — matches the mobile flow
  await p.getByRole('button', { name: ROLE, exact:true }).click({ timeout:15000 });
  await p.waitForTimeout(1500);
  await p.getByRole('button', { name: SUBMIT, exact:true }).click({ timeout:15000 });
  // logged in = the login copy is gone (Forums/home rendered). Poll the semantics text.
  await p.waitForFunction(
    () => !(document.body.innerText||'').includes('Sign in to continue'),
    { timeout:25000 });
  await p.waitForTimeout(4000);
  ok = true;
} catch (e) { note = e.message.split('\n')[0].slice(0,140); }
await p.screenshot({ path: OUT }).catch(()=>{});
await b.close();
console.log(JSON.stringify({ ok, note, out: OUT }));
process.exit(ok ? 0 : 1);
