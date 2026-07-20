"""verify — deterministic build gates + boot/health + e2e dispatch. No LLM.

Every result is machine evidence (exit code + last-20-lines tail), never a
self-assessment. Per STEP4_PIPELINE §3. e2e runner commands come from
settings.verify.e2e; if unset, we record 'not-configured' rather than fake a pass.
"""
from __future__ import annotations
import json, os, re, shlex, shutil, subprocess, time, urllib.request
from pathlib import Path
from lib import cometchat, mobile


def _run(cmd, cwd=None, timeout=1800, env=None) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=cwd, timeout=timeout, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           env={**os.environ, **(env or {})})
        return p.returncode, p.stdout or ""
    except subprocess.TimeoutExpired as e:
        return 124, f"TIMEOUT after {timeout}s\n{(e.output or '')[-1500:]}"
    except FileNotFoundError as e:
        return 127, f"missing tool: {e}"


def _tail(s: str, n=20) -> str:
    return "\n".join((s or "").splitlines()[-n:])


# ---------- build gates (per component kind) ----------
def _scripts(comp_dir: Path) -> dict:
    pj = comp_dir / "package.json"
    if not pj.exists():
        return {}
    try:
        return json.loads(pj.read_text()).get("scripts", {})
    except Exception:
        return {}


def _pick(scripts: dict, prefer: list[str]) -> str | None:
    for s in prefer:
        if s in scripts:
            return s
    return None


def _npm_gate(comp_dir: Path, prefer: list[str], fallback_tsc=True) -> tuple[int, str]:
    """Ensure deps, then run the best-available script. RN has no 'build' — it uses type-check."""
    d = str(comp_dir)
    if not (comp_dir / "package.json").exists():
        return 127, "no package.json"
    if not (comp_dir / "node_modules").exists():
        _run(["npm", "install"], cwd=d, timeout=900)
    script = _pick(_scripts(comp_dir), prefer)
    if script:
        code, out = _run(["npm", "run", script], cwd=d)
        # A type-check that only fails INSIDE node_modules is a broken-library-types issue
        # (e.g. CometChat UI Kit ships type-imperfect .tsx), NOT an app/integration failure.
        # RELAX ONLY when the failure genuinely IS that: there ARE `error TS` lines and every one is
        # inside node_modules. A non-TS failure (exit!=0 with ZERO `error TS` lines — OOM, tsconfig
        # resolution error, tool crash) is a REAL failure and must NOT be swallowed into a pass.
        if code != 0 and any(k in script for k in ("type", "check", "tsc")):
            ts_lines = [l for l in out.splitlines() if "error TS" in l]
            app_errs = [l for l in ts_lines if "node_modules" not in l]
            if ts_lines and not app_errs:
                return 0, "type-check: only node_modules (library) type errors — app code clean\n" + _tail(out)
        return code, out
    if fallback_tsc and (comp_dir / "tsconfig.json").exists():
        return _run(["npx", "--yes", "tsc", "--noEmit"], cwd=d)
    return 0, f"no build/typecheck script among {prefer} — scaffolding present, passing"


def build_gate(kind: str, comp_dir: Path, env: dict | None = None) -> dict:
    """`env` (optional) is threaded to the native toolchains so a self-heal (e.g. JAVA_HOME=JDK17)
    actually takes effect on the re-gate — previously the heal wrote JAVA_HOME into a dict build_gate
    never read, so the most-common UC1 gradle failure was structurally unrecoverable."""
    d = str(comp_dir)
    if kind == "web":
        # CometChat calls guard (proactive): the calls SDK sizes its video grid with an inline
        # height:calc() referencing two CSS vars it never defines → 0px collapse → the ongoing-call
        # ResizeObserver throws "Container dimensions and number of tiles must be positive". Define the
        # vars in the app's global stylesheet BEFORE building so the built bundle ships them; self-heal
        # records the SDK-packaging gap each time it fires.
        try:
            from lib import selfheal
            _wc = selfheal.ensure_web_call_css_vars(comp_dir)
            if _wc:
                print(f"  web build gate: call-css-vars guard → {[x['rule'] for x in _wc]}")
        except Exception as _e:
            print(f"  web build gate: call-css-vars guard skipped ({_e})")
        code, out = _npm_gate(comp_dir, ["build", "type-check", "typecheck"])
    elif kind == "mobile":  # React Native — no 'build' script; typecheck is the real gate. NOT lint
        code, out = _npm_gate(comp_dir, ["type-check", "typecheck", "build:check", "tsc"])
    elif kind == "app":  # Flutter — errors are fatal; lint infos/warnings are NOT (they falsely RED the gate)
        code, out = _run(["flutter", "analyze", "--no-fatal-infos", "--no-fatal-warnings"], cwd=d, env=env)
    elif kind == "android":
        gw = comp_dir / "gradlew"
        code, out = _run(["./gradlew", "assembleDebug"], cwd=d, env=env) if gw.exists() else (127, "no gradlew")
    elif kind == "ios":
        code, out = _ios_gate(comp_dir, env=env)
    elif kind == "backend":
        code, out = _backend_build(comp_dir, env=env)
    else:
        code, out = 127, f"unknown kind {kind}"
    return {"kind": kind, "buildExitCode": code, "outputTail": _tail(out)}


# REQUIRED on Xcode 16/26: with only `-sdk iphonesimulator` and no destination, xcodebuild aborts
# "Found no destinations for the scheme '<x>'" (exit 70) before building anything. The GENERIC simulator
# destination needs no booted sim. mobile.build_ios already passed this; the compile gate never did.
#
# EXCLUDED_ARCHS=x86_64 is the necessary companion to that destination: `generic/platform=iOS Simulator`
# builds BOTH arm64 and x86_64, and the x86_64 pass fails to resolve CometChatCardsSwift out of
# CometChatUIKitSwift's .swiftinterface ("cannot find type 'CometChatCardsSwift' in scope") even with the
# I7 companion pods installed — while the arm64 pass compiles cleanly. Every simulator on Apple Silicon
# is arm64, so the x86_64 slice is dead weight that only breaks the build. (Adding the destination
# without this is what turned a passing iOS gate into a failing one on fin.)
_IOS_DEST = ("-destination", "generic/platform=iOS Simulator", "EXCLUDED_ARCHS=x86_64")


def _ios_dd(d: Path) -> str:
    """A FRESH per-component derivedDataPath for the iOS gate.

    Xcode's shared DerivedData caches xcframework extraction under XCFrameworkIntermediates/. When a
    build runs before `pod install` has settled, it can materialise an EMPTY
    XCFrameworkIntermediates/CometChatSDK/CometChatStarscream.framework binary (from the Starscream
    .swiftinterface files that ship inside the SDK's dSYMs) and then link against it forever after:
    `ld: file is empty`. That poisoned cache survives retries, so a self-heal that fixes the real
    problem still reports failure. Wiping a per-run path makes each attempt honest."""
    dd = f"/tmp/step4-iosgate-{d.resolve().parent.name}-{d.name}"
    shutil.rmtree(dd, ignore_errors=True)
    return dd


# Markers that an OUTGOING call can actually be placed from this client, in two families.
#
# EXPLICIT — the app itself places the call or mounts a call surface.
_CALL_MARKERS_EXPLICIT = (
    "initiateCall",            # SDK call placement, every stack
    "CometChatCallButtons",    # kit call button (React / RN / Compose / Flutter)
    "CometChatOutgoingCall",
    "CometChatOngoingCall",
    "startCall", "startSession",
    "launchOutgoingCallScreen",
)
# KIT-MANAGED — the calling MODULE is initialised and the kit renders/presents the call surfaces
# itself, so no explicit marker ever appears in app source. iOS is the case in point:
# CometChatMessageHeader auto-renders its call buttons and presents outgoing→ongoing once
# CometChatCalls.init has run, so gating on the explicit family alone REJECTED a correct integration.
# This family is also the more meaningful signal: the integrate prompt's own rule is that a call
# button without its prerequisites is an INERT no-op — initialisation is what makes calling real.
_CALL_MARKERS_INIT = (
    "CometChatCalls.init", "CallAppSettingsBuilder", "callsAppSettings",   # iOS / native
    "CometChatUIKitCalls.init", "enableCalls",                             # Flutter v6
    "setCallingEnabled", "setEnableCalling",                               # Angular / Android v6
    "inAppIncomingCall",
)
# The incoming-call banner is deliberately in NEITHER family: mounting it alone, with no init and no
# outgoing surface, is precisely the false positive this gate exists to catch (fin shipped exactly
# that on both native clients and passed a compile-only gate).
_CALL_MARKERS = _CALL_MARKERS_EXPLICIT + _CALL_MARKERS_INIT
_CALL_SRC_EXT = {".swift", ".kt", ".java", ".ts", ".tsx", ".js", ".jsx", ".vue", ".dart"}
_CALL_SKIP_DIR = {"node_modules", "Pods", "build", "dist", ".git", "DerivedData", ".gradle", "target"}


# Accounts that exist ONLY to satisfy the test harness. `chat-a@<slug>.io` / `chat-b@<slug>.io` and the
# `<slug>-cha-001` / `<slug>-chb-001` uids are precisely what cometchat.call_test_accounts() invents when
# a use case has no `chatPair`, so seeing them in APP source means codegen wrote fake users to make the
# harness pass.
_SYNTHETIC_ACCOUNT_PATTERNS = (
    r"chat-a@", r"chat-b@", r"-cha-00", r"-chb-00",
    r"Chat Alpha", r"Chat Beta", r"\bChat A\b", r"\bChat B\b",
)
_SEED_HINTS = ("seed", "fixture", "bootstrap", "demo")
_SRC_EXT = {".java", ".kt", ".swift", ".ts", ".tsx", ".js", ".jsx", ".vue", ".dart", ".py", ".php", ".go",
            ".sql", ".json", ".yaml", ".yml"}
# `_run` holds the harness's OWN failure records, which quote the offending account names verbatim —
# scanning it makes the gate flag its own bug reports. Only APP source counts.
_SKIP_DIR = {"node_modules", "Pods", "build", "dist", ".git", "DerivedData", ".gradle", "target",
             "_demo", "_logs", "_reports", "_run", "pipeline-state", ".claude"}


def synthetic_seed_accounts(repo: Path) -> list[str]:
    """Find harness-only test accounts that codegen baked into the APP.

    The failure this prevents (observed on fin): the use case had no `chatPair`, so the harness fell back
    to inventing chat-a@fin.io / chat-b@fin.io — and codegen, seeing the harness expect them, SEEDED
    those users into the backend, complete with their own tickets and transactions. Chat was then
    "proven" between two users that the app's own demo-login screen could not even reach, while the real
    personas went untested. An app that grows fake users to satisfy its test suite is a rigged pass, and
    it is invisible to every compile/boot gate.

    Returns a list of "path:line: snippet" hits (empty = clean)."""
    hits: list[str] = []
    rx = re.compile("|".join(_SYNTHETIC_ACCOUNT_PATTERNS))
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIR and not d.startswith(".")]
        for fn in files:
            if os.path.splitext(fn)[1] not in _SRC_EXT:
                continue
            p = Path(root) / fn
            try:
                lines = p.read_text(errors="ignore").splitlines()
            except Exception:
                continue
            for i, line in enumerate(lines, 1):
                if rx.search(line):
                    hits.append(f"{p.relative_to(repo)}:{i}: {line.strip()[:110]}")
    return hits


def chat_pair_seeded(repo: Path, chat_pair: list[str]) -> list[str]:
    """Which of the use case's REAL demo accounts are missing from the app's seed.

    The mirror of synthetic_seed_accounts: chat/call tests must run between accounts the app genuinely
    ships, so every chatPair email has to appear somewhere in the seed source."""
    if not chat_pair:
        return []
    blob = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIR and not d.startswith(".")]
        for fn in files:
            if os.path.splitext(fn)[1] in _SRC_EXT and any(h in fn.lower() or h in root.lower()
                                                           for h in _SEED_HINTS):
                try:
                    blob.append((Path(root) / fn).read_text(errors="ignore"))
                except Exception:
                    pass
    text = "\n".join(blob)
    return [e for e in chat_pair if e not in text]


def calls_wired(comp_dir: Path) -> bool:
    """True if this client can actually PLACE a call.

    Deterministic source scan — the compile gate proves the code builds, never that the feature is
    there. fin's iOS client shipped chat plus a `CometChatIncomingCall` banner and no outgoing calling
    whatsoever, and passed integrate twice on compileExit=0."""
    d = Path(comp_dir)
    for root, dirs, files in os.walk(d):
        dirs[:] = [x for x in dirs if x not in _CALL_SKIP_DIR and not x.startswith(".")]
        for fn in files:
            if os.path.splitext(fn)[1] not in _CALL_SRC_EXT:
                continue
            try:
                t = (Path(root) / fn).read_text(errors="ignore")
            except Exception:
                continue
            if any(m in t for m in _CALL_MARKERS):
                return True
    return False


def _ios_gate(d: Path, env: dict | None = None) -> tuple[int, str]:
    """iOS compile gate. When the app uses CocoaPods (a Podfile adding pods — e.g. CometChatUIKitSwift),
    the integrated code `import`s a pod module that ONLY exists after `pod install`, and the build must
    target the CocoaPods-generated `.xcworkspace`, not the bare `.xcodeproj`. The demo/providers paths
    (mobile.py / providers.py) already do this; the integrate/build compile gate did not — so every
    pod-based iOS integration failed here with "no such module 'CometChatUIKitSwift'". Mirror them."""
    # Bundle-id guard (proactive): a custom INFOPLIST_FILE without GENERATE_INFOPLIST_FILE yields an .app
    # with no CFBundleIdentifier — compiles clean, but `simctl install` rejects it ("Missing bundle ID"),
    # so the demo silently screenshots the simulator home screen instead of the app.
    try:
        from lib import selfheal
        _ip = selfheal.ensure_ios_infoplist_keys(d)
        if _ip:
            print(f"  ios build gate: Info.plist bundle-keys guard → {[x['rule'] for x in _ip]}")
    except Exception as _e:
        print(f"  ios build gate: Info.plist guard skipped ({_e})")
    if (d / "Podfile").exists():
        # I7 guard (proactive): CometChat's iOS pods reference CometChatStarscream / CometChatCardsSwift
        # but don't bundle/declare them, so a by-the-book `pod install` yields a target that fails to
        # compile ("no such module ..."). Inject the two companion pods BEFORE pod install so the build
        # never hits I7 — and self-heal records the SDK-packaging gap each time it fires.
        try:
            from lib import selfheal
            _ic = selfheal.ensure_ios_companion_pods(d)
            if _ic:
                print(f"  ios build gate: I7 companion-pods guard → {[x['rule'] for x in _ic]}")
        except Exception as _e:
            print(f"  ios build gate: companion-pods guard skipped ({_e})")
        # pod install is idempotent; run it so the pod module is available to swiftc. Login shell → PATH/rbenv.
        pc, po = _run(["bash", "-lc", "export LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8; pod install"], cwd=str(d), env=env)
        ws = next(iter(d.glob("*.xcworkspace")), None)
        if ws is None:  # pod install did not produce a workspace → surface its output, don't build the bare project
            return (pc or 1), "pod install did not produce an .xcworkspace:\n" + po
        return _run(["xcodebuild", "-workspace", ws.name, "-scheme", _ios_scheme(d, ws, env),
                     "-sdk", "iphonesimulator", *_IOS_DEST,
                     "-derivedDataPath", _ios_dd(d), "build"], cwd=str(d), env=env)
    return _run(["xcodebuild", "-scheme", _ios_scheme(d, None, env),
                 "-sdk", "iphonesimulator", *_IOS_DEST,
                 "-derivedDataPath", _ios_dd(d), "build"], cwd=str(d), env=env)


def _ios_scheme(d: Path, ws: Path | None = None, env: dict | None = None) -> str:
    """Resolve the Xcode SCHEME to build. The component dir is named for its KIND ("ios"), but codegen
    names the project after the APP (FinSupport.xcodeproj → scheme "FinSupport"), so assuming the dir
    name fails EVERY native-iOS use case with: 'does not contain a scheme named "ios"' (exit 65, before
    a single line is compiled). Ask xcodebuild for the authoritative scheme list and prefer, in order:
    the dir name (layouts that genuinely match), the workspace/project stem, then the first scheme."""
    proj = next(iter(d.glob("*.xcodeproj")), None)
    target = ["-workspace", ws.name] if ws else (["-project", proj.name] if proj else [])
    schemes: list[str] = []
    try:
        code, out = _run(["xcodebuild", "-list", "-json", *target], cwd=str(d), env=env)
        if code == 0 and "{" in out:
            info = json.loads(out[out.index("{"):out.rindex("}") + 1])
            schemes = (info.get("workspace") or info.get("project") or {}).get("schemes") or []
    except Exception:
        schemes = []
    for cand in (d.name, (ws.stem if ws else None), (proj.stem if proj else None)):
        if cand and cand in schemes:
            return cand
    if schemes:
        return schemes[0]
    return (ws or proj).stem if (ws or proj) else d.name   # -list unavailable → best on-disk guess


def _backend_build(d: Path, env: dict | None = None) -> tuple[int, str]:
    """LANGUAGE-NATIVE compile/syntax gate — the build stage checks the CODE, not that Docker builds
    (Docker is the containerize stage's job). Language checks come FIRST; docker-compose is only a
    last resort when no language toolchain is recognized (and it runs in the dir that HAS the compose
    file, not blindly in the parent — the UC2/Laravel bug that shipped its own backend/docker-compose.yml)."""
    if (d / "composer.json").exists():        # PHP / Laravel — lint all app PHP (syntax = PHP's compile check)
        # NB: php -l prints "No syntax errors detected in X" on success — do NOT grep "syntax error"
        # (it substring-matches the success line). Match only real failures.
        cmd = ('out=$(find app routes database config public bootstrap -name "*.php" -print0 2>/dev/null '
               '| xargs -0 -r -n1 php -l 2>&1 | grep -iE "Parse error|Fatal error|Errors parsing" || true); '
               '[ -z "$out" ] && echo "php lint clean" || { echo "$out"; exit 1; }')
        return _run(["bash", "-lc", cmd], cwd=str(d), env=env)
    if (d / "go.mod").exists():               return _run(["go", "build", "./..."], cwd=str(d), env=env)
    if (d / "pom.xml").exists():              return _run(["mvn", "-q", "-B", "compile", "-DskipTests"], cwd=str(d), env=env)
    if (d / "requirements.txt").exists() or (d / "pyproject.toml").exists():
        return _run(["python3", "-m", "compileall", "-q", "."], cwd=str(d), env=env)
    if (d / "package.json").exists():
        # NOT just `npm install`: a Node/TS backend must actually type-check/build, else a backend
        # with type/syntax errors passes the gate as long as deps resolve. Reuse the JS typecheck gate.
        return _npm_gate(d, ["build", "type-check", "typecheck", "compile"])
    for cd in (d, d.parent):                  # last resort: docker, in the dir that actually has the compose file
        if (cd / "docker-compose.yml").exists() or (cd / "compose.yaml").exists():
            return _run(["docker", "compose", "build"], cwd=str(cd), env=env)
    return 0, "backend: no recognized build file — configure"


# ---------- boot + health (Boot & Verify / Re-Boot & Verify) ----------
def compose_up(repo_dir: Path) -> tuple[bool, str]:
    # --build so each boot reflects the CURRENT committed code (not a stale cached image)
    code, out = _run(["docker", "compose", "up", "-d", "--build"], cwd=str(repo_dir), timeout=1200)
    # Transient registry/metadata timeouts ('DeadlineExceeded'/'context deadline exceeded'/'failed to
    # solve' while loading base-image metadata) are infra flakes, not code errors — the base images are
    # already local after the first boot. Retry ONCE offline (--pull=false) before declaring the boot dead.
    if code != 0 and re.search(r"DeadlineExceeded|context deadline exceeded|failed to (solve|fetch)|"
                               r"i/o timeout|TLS handshake timeout|temporary failure", out or "", re.I):
        b_code, b_out = _run(["docker", "compose", "build", "--pull=false"], cwd=str(repo_dir), timeout=1200)
        if b_code == 0:
            code, out = _run(["docker", "compose", "up", "-d", "--no-build"], cwd=str(repo_dir), timeout=600)
        else:
            out = (out or "") + "\n[retry --pull=false] " + _tail(b_out)
    return code == 0, _tail(out)


def compose_down(repo_dir: Path) -> dict:
    # `--rmi local` ALSO removes the images this compose built (<proj>-web, <proj>-backend, …) — without it
    # every use case leaves ~0.5–1GB of images behind and the Nth UC hits disk-full inside the Docker VM.
    # `builder prune -af` reclaims ALL build cache (not just dangling) — usually the biggest single reclaim
    # (several GB). Base images (python/node/nginx) are kept, so the next UC doesn't re-pull them.
    code, out = _run(["docker", "compose", "down", "-v", "--rmi", "local"], cwd=str(repo_dir), timeout=300)
    _run(["docker", "builder", "prune", "-af"])
    _run(["docker", "image", "prune", "-f"])
    return {"dockerCleanupDone": code == 0, "tail": _tail(out)}


def health_check(base_url: str, paths, timeout_s: int):
    """Poll base_url+path for any 2xx. paths may be a str or list (tries each — apps mount
    /health under /api, /healthz, etc.). Returns (ok, path_that_worked)."""
    if isinstance(paths, str):
        paths = [paths]
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        for p in paths:
            try:
                with urllib.request.urlopen(base_url + p, timeout=5) as r:
                    if 200 <= r.status < 300:
                        return True, p
            except Exception:
                pass
        time.sleep(3)
    return False, None


def run_chatcall_web(repo_dir: Path, email: str, password: str, web_url: str, shot: str) -> dict:
    """Run the canonical chat/call e2e (login→open chat→send→call) in the web dir. Returns the JSON verdict."""
    web = repo_dir / "web"
    src = Path(__file__).resolve().parent.parent / "e2e" / "chatcall.web.mjs"
    if not web.exists() or not src.exists():
        return {"error": "no web/ or e2e script"}
    # copy into web/ so `import '@playwright/test'` resolves against web/node_modules (ESM resolves by script path)
    dst = web / "_chatcall_verify.mjs"
    dst.write_text(src.read_text())
    env = {"E2E_EMAIL": email, "E2E_PASSWORD": password, "WEB_URL": web_url, "SHOT": shot}
    code, out = _run(["node", str(dst)], cwd=str(web), timeout=180, env=env)
    dst.unlink(missing_ok=True)
    for line in reversed((out or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except Exception:
                pass
    return {"error": "no verdict json", "tail": _tail(out)}


def run_twoparty_chat(repo_dir: Path, web_url: str, shot_dir: str, a_email: str, b_email: str,
                      password: str, nonce: str) -> dict:
    """CROSS-PARTY real-time RECEIVE proof: B sends a unique NONCE, A must render it (live socket).
    This is the source of truth for chat working — it catches the 'socket dead but REST login works'
    bug the single-browser heuristics silently passed. Returns the JSON verdict (chatWorks=received)."""
    web = repo_dir / "web"
    src = Path(__file__).resolve().parent.parent / "e2e" / "twoparty_chat.web.mjs"
    if not web.exists() or not src.exists():
        return {"error": "no web/ or twoparty_chat script", "chatWorks": False}
    dst = web / "_twoparty_chat_verify.mjs"
    dst.write_text(src.read_text())
    env = {"WEB_URL": web_url, "A_EMAIL": a_email, "B_EMAIL": b_email, "E2E_PASSWORD": password,
           "NONCE": nonce, "SHOT_DIR": shot_dir}
    code, out = _run(["node", str(dst)], cwd=str(web), timeout=180, env=env)
    dst.unlink(missing_ok=True)
    for line in reversed((out or "").splitlines()):
        if line.strip().startswith("{"):
            try:
                return json.loads(line.strip())
            except Exception:
                pass
    return {"error": "no verdict json", "tail": _tail(out), "chatWorks": False, "exitCode": code}


def run_flutter_chat_receive(web_url: str, a_email: str, password: str, cfg: dict, sender_uid: str,
                             receiver_uid: str, nonce: str, out_png: str, submit: str = "Sign In",
                             timeout: int = 180) -> dict:
    """CROSS-PARTY receive proof for a FLUTTER web app (no Node web/ dir). Drives the flt-semantics tree
    via the shared standalone Playwright (e2e/webdriver): A logs in as the receiver, a peer REST-sends a
    unique nonce, and A's live Flutter UI must render it. Returns {loggedIn, sdkReady, received, ...}."""
    wd = Path(__file__).resolve().parent.parent / "e2e" / "webdriver"
    driver = wd / "flutter_chat_receive.mjs"
    if not driver.exists() or not (wd / "node_modules").exists():
        return {"error": "flutter webdriver not set up (run boot/demo once to bootstrap it)",
                "received": False, "chatWorks": False}
    env = {"URL": web_url.rstrip("/") + "/", "A_EMAIL": a_email, "A_PASSWORD": password, "SUBMIT": submit,
           "APP_ID": cfg.get("COMETCHAT_APP_ID", ""), "REGION": cfg.get("COMETCHAT_REGION", "us"),
           "REST_API_KEY": cfg.get("COMETCHAT_REST_API_KEY", ""), "SENDER_UID": sender_uid,
           "RECEIVER_UID": receiver_uid, "NONCE": nonce, "OUT": out_png,
           "PLAYWRIGHT_BROWSERS_PATH": os.path.expanduser("~/Library/Caches/ms-playwright")}
    code, out = _run(["node", str(driver)], cwd=str(wd), timeout=timeout, env=env)
    for line in reversed((out or "").splitlines()):
        if line.strip().startswith("{"):
            try:
                return json.loads(line.strip())
            except Exception:
                pass
    return {"error": "no verdict json", "tail": _tail(out), "received": False, "chatWorks": False}


def _role_from_email(email: str) -> str:
    """Map a seeded receiver email to its demo-account quick-fill button label. Maestro can't type into
    the Flutter Key-based login fields, so login goes through the visible demo-role button; the role is
    encoded in the seed email local part (jamie.member@… → Member, marco.mod@… → Moderator)."""
    local = (email or "").split("@")[0].lower()
    for needle, role in (("admin", "Admin"), ("moderator", "Moderator"), ("mod", "Moderator"),
                         ("member", "Member"), ("guest", "Guest")):
        if needle in local:
            return role
    return "Member"


def run_flutter_chat_receive_mobile(repo_dir: Path, api_url: str, env_file: str, cfg: dict,
                                    a_email: str, sender_uid: str, receiver_uid: str, nonce: str,
                                    out_png: str, sender_name: str = "", submit: str = "Sign In",
                                    settings: dict | None = None, timeout: int = 240) -> dict:
    """CROSS-PARTY receive proof on the MOBILE Flutter client (android) — CometChat's SDK initialises on
    android/ios but NOT on Flutter web (shared_preferences MissingPluginException), so the real chat proof
    lives here. Build+install the integrated apk, REST-send a unique nonce from the peer, then drive
    Maestro: A logs in (demo-role button), opens Messages, and OPENS the sender's thread. CometChat renders
    bubbles on a canvas (their text is NOT in the a11y tree, so Maestro can't assert it) — instead we
    VISION-judge the thread screenshot for the nonce bubble. Catches a dead socket / wrong creds / missing
    CometChat login (all of which leave the list on 'Oops'). Returns {received, built, sent, shot}."""
    from lib import providers, vision
    b = providers.build_install_flutter_android(repo_dir / "app", api_url, env_file, integrated=True)
    if not b.get("ok"):
        return {"received": False, "chatWorks": False, "built": False,
                "error": f"android build/install failed (exit={b.get('buildExit')})", "tail": b.get("tail", "")}
    # peer B REST-sends the unique nonce to receiver A (persisted; also pushed over A's live socket)
    sent = cometchat.send_message(cfg, sender_uid, receiver_uid, nonce)
    role = _role_from_email(a_email)
    maestro = os.path.expanduser("~/.maestro/bin/maestro")
    flow = Path(__file__).resolve().parent.parent / "e2e" / "mobile_flows" / "chat_receive.flow.yaml"
    dev = subprocess.run([mobile.ADB, "devices"], capture_output=True, text=True).stdout
    serial = next((l.split()[0] for l in dev.splitlines()[1:] if "\tdevice" in l), None)
    # Maestro AUTO-APPENDS `.png` to the takeScreenshot path — strip our extension so it lands at out_png.
    maestro_out = out_png[:-4] if out_png.lower().endswith(".png") else out_png
    args = [maestro, *(["--device", serial] if serial else []), "test", str(flow),
            "-e", f"APP_ID={b['appId']}", "-e", f"ROLE={role}", "-e", f"SUBMIT={submit}",
            "-e", f"SENDER={sender_name or 'Chat'}", "-e", f"NONCE={nonce}", "-e", f"OUT={maestro_out}"]
    env = {**os.environ, "PATH": os.path.expanduser("~/.maestro/bin:") + os.environ.get("PATH", "")}
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env)
    navigated = os.path.exists(out_png) and os.path.getsize(out_png) > 1000
    # VISION verdict: the nonce bubble must be visibly rendered in A's thread (canvas text Maestro can't read)
    received, vis = False, {}
    if navigated:
        vis = vision.judge_screenshot(
            out_png,
            [{"id": "nonce", "check": f"A chat message bubble containing the exact text \"{nonce}\" is visible"}],
            context="Flutter CometChat conversation thread; proving a cross-party message was received",
            settings=settings)
        received = bool(vis.get("overallPass"))
    return {"received": received, "chatWorks": received, "built": True, "navigated": navigated,
            "sent": bool(sent), "role": role, "sdkReady": received, "shot": out_png,
            "visionReason": (vis.get("checks") or [{}])[0].get("reason") if vis else None,
            "tail": _tail(p.stdout + p.stderr)}


def run_twoparty_web(repo_dir: Path, web_url: str, shot_dir: str,
                     caller_email: str, callee_email: str, password: str,
                     env_file: str = "", slug: str = "", retries: int = 3,
                     reader_uid: str | None = None) -> dict:
    """Two-party web↔web call matrix (voice + video). SIGNALING verdict — deterministic, not
    media-dependent: a leg passes when the ring reached the callee, Accept succeeded, AND CometChat
    logged the call as ANSWERED server-side (REST). Retries up to `retries` (retry-until-pass) to
    absorb transient hiccups. The old flaky 'DOM ongoing element still present at 7s' is dropped —
    headless fake-media drops the stream after ~2s, which never meant the call failed."""
    web = repo_dir / "web"
    src = Path(__file__).resolve().parent.parent / "e2e" / "twoparty.web.mjs"
    if not web.exists() or not src.exists():
        return {"error": "no web/ or twoparty script", "ok": False}
    dst = web / "_twoparty_verify.mjs"
    # The script is COPIED into the app's web/ so `@playwright/test` resolves there — which means its
    # relative `./browser.mjs` import must be copied alongside it, under a `_`-prefixed name so the
    # repo's `web/_*.mjs` ignore rule keeps it untracked.
    (web / "_browser.mjs").write_text((src.parent / "browser.mjs").read_text())
    dst.write_text(src.read_text().replace("from './browser.mjs'", "from './_browser.mjs'"))
    out = {}
    try:
        for ctype in ("voice", "video"):
            attempts, leg = [], {}
            for a in range(retries):
                since = int(time.time())
                env = {"WEB_URL": web_url, "CALL_TYPE": ctype, "SHOT_DIR": shot_dir,
                       "CALLER_EMAIL": caller_email, "CALLEE_EMAIL": callee_email, "E2E_PASSWORD": password}
                _, res = _run(["node", str(dst)], cwd=str(web), timeout=180, env=env)
                v = {"error": "no verdict json", "tail": _tail(res)}
                for line in reversed((res or "").splitlines()):
                    if line.strip().startswith("{"):
                        try:
                            v = json.loads(line.strip()); break
                        except Exception:
                            pass
                # server-side confirmation (media-independent), anchored to this attempt's accept
                # reader_uid MUST be an actual participant in THIS call. Defaulting to
                # call_test_accounts() reads the log on behalf of the synthetic chat-a/chat-b user,
                # who is not in the call (and may not exist at all) — so the check could only ever
                # return answered=False and silently veto a call that genuinely connected.
                ans = cometchat.call_answered(env_file, slug, v.get("acceptedAt") or since,
                                              uid=reader_uid) if env_file else {"answered": None}
                v["serverAnswered"] = ans.get("answered")
                # Require the actual CONNECT (both ends on the ongoing-call surface), not just signaling —
                # Chromium does real WebRTC with fake media, so a call that rings+accepts but never reaches
                # the ongoing UI did NOT connect. connectOk comes from the browser script; server-answered
                # is an extra media-independent confirmation. Retry-until-pass absorbs connect timing.
                v["callWorks"] = bool(v.get("signalOk") and v.get("connectOk") and (ans.get("answered") is not False))
                v["attempt"] = a + 1
                attempts.append({"signalOk": v.get("signalOk"), "connectOk": v.get("connectOk"),
                                 "serverAnswered": ans.get("answered"), "pass": v["callWorks"]})
                leg = v
                if v["callWorks"]:
                    break
            leg["attempts"] = attempts
            out[ctype] = leg
    finally:
        dst.unlink(missing_ok=True)
        (web / "_browser.mjs").unlink(missing_ok=True)
    out["ok"] = bool(out.get("voice", {}).get("callWorks") and out.get("video", {}).get("callWorks"))
    return out


def run_twoparty_mobile(platform: str, call_type: str, web_url: str, shot_dir: str,
                        env_file: str = "", slug: str = "mkt", retries: int = 2,
                        app_id: str | None = None, mobile_email: str | None = None,
                        web_email: str | None = None, password: str | None = None,
                        caller_uid: str | None = None) -> dict:
    """Automated mobile↔web call leg (android↔web / ios↔web). Maestro drives the native app, the web
    peer rings it; the leg passes on the SIGNALING verdict — the mobile incoming widget appeared +
    Maestro accepted + CometChat logged the call ANSWERED (server-side, media-independent). Retries
    up to `retries` (retry-until-pass). Parameterized per use case (app_id + the two call-test
    accounts) so it is not mkt-specific. Requires the emulator/sim booted + integrated app installed."""
    script = Path(__file__).resolve().parent.parent / "e2e" / "twoparty_mobile.py"
    if not script.exists():
        return {"error": "no twoparty_mobile.py", "callConnected": False}
    extra = []
    if app_id:       extra += ["--app-id", app_id]
    if mobile_email: extra += ["--mobile-email", mobile_email]
    if web_email:    extra += ["--web-email", web_email]
    if password:     extra += ["--password", password]
    if caller_uid:   extra += ["--caller-uid", caller_uid]
    last = {"error": "no run", "callConnected": False}
    for a in range(retries):
        code, out = _run(["python3", str(script), "--platform", platform, "--direction", "web-calls-mobile",
                          "--call-type", call_type, "--web-url", web_url, "--shot-dir", shot_dir,
                          "--env-file", env_file, "--slug", slug, *extra], timeout=300)
        v = None
        for line in reversed((out or "").splitlines()):
            if line.strip().startswith("{"):
                try:
                    v = json.loads(line.strip()); break
                except Exception:
                    pass
        last = v or {"error": "no verdict json", "tail": _tail(out), "callConnected": False}
        last["attempt"] = a + 1
        if last.get("callConnected"):
            break
    return last


def run_e2e(cmd: str, repo_dir: Path, base_url: str = "http://localhost:3000") -> dict:
    if not cmd:
        return {"ran": False, "passed": None, "note": "e2e: not-configured", "tail": ""}
    # The default smoke is a Playwright web test. Only run it where Playwright is actually set up
    # (Node web stacks). For a Flutter/native web with no Playwright, skip → the caller falls back to
    # the page-200 health signal, instead of failing the gate on a missing test runner.
    if "playwright" in cmd:
        has_pw = any((repo_dir / f).exists() for f in
                     ("playwright.config.ts", "playwright.config.js", "playwright.config.mjs")) or \
                 ("@playwright/test" in (repo_dir / "package.json").read_text()
                  if (repo_dir / "package.json").exists() else False)
        if not has_pw:
            return {"ran": False, "passed": None, "note": "e2e: no Playwright setup (non-Node web) — page-200 fallback", "tail": ""}
    # Point the (parameterised) e2e config at the DEPLOYED web URL, not its dev-server default. Codegen
    # sets `baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:4200'`; without this the boot smoke
    # navigates to the dev port (4200) instead of the composed web (3000) and fails on nothing there.
    env = dict(os.environ)
    env["E2E_BASE_URL"] = base_url
    env.setdefault("PLAYWRIGHT_BASE_URL", base_url)
    env.setdefault("BASE_URL", base_url)
    code, out = _run(shlex.split(cmd), cwd=str(repo_dir), timeout=1800, env=env)
    return {"ran": True, "passed": code == 0, "exitCode": code, "tail": _tail(out)}
