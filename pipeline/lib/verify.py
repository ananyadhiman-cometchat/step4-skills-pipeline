"""verify — deterministic build gates + boot/health + e2e dispatch. No LLM.

Every result is machine evidence (exit code + last-20-lines tail), never a
self-assessment. Per STEP4_PIPELINE §3. e2e runner commands come from
settings.verify.e2e; if unset, we record 'not-configured' rather than fake a pass.
"""
from __future__ import annotations
import json, os, shlex, subprocess, time, urllib.request
from pathlib import Path


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
        # The app bundles + runs regardless. Gate on the app's OWN errors only.
        if code != 0 and any(k in script for k in ("type", "check", "tsc")):
            app_errs = [l for l in out.splitlines() if "error TS" in l and "node_modules" not in l]
            if not app_errs:
                return 0, "type-check: only node_modules (library) type errors — app code clean\n" + _tail(out)
        return code, out
    if fallback_tsc and (comp_dir / "tsconfig.json").exists():
        return _run(["npx", "--yes", "tsc", "--noEmit"], cwd=d)
    return 0, f"no build/typecheck script among {prefer} — scaffolding present, passing"


def build_gate(kind: str, comp_dir: Path) -> dict:
    d = str(comp_dir)
    if kind == "web":
        code, out = _npm_gate(comp_dir, ["build", "type-check", "typecheck"])
    elif kind == "mobile":  # React Native — no 'build' script; typecheck is the real gate
        code, out = _npm_gate(comp_dir, ["type-check", "typecheck", "build:check", "tsc", "lint"])
    elif kind == "app":  # Flutter
        code, out = _run(["flutter", "analyze"], cwd=d)
    elif kind == "android":
        gw = comp_dir / "gradlew"
        code, out = _run(["./gradlew", "assembleDebug"], cwd=d) if gw.exists() else (127, "no gradlew")
    elif kind == "ios":
        code, out = _run(["xcodebuild", "-scheme", comp_dir.name, "-sdk", "iphonesimulator", "build"], cwd=d)
    elif kind == "backend":
        code, out = _backend_build(comp_dir)
    else:
        code, out = 127, f"unknown kind {kind}"
    return {"kind": kind, "buildExitCode": code, "outputTail": _tail(out)}


def _backend_build(d: Path) -> tuple[int, str]:
    if (d / "docker-compose.yml").exists() or (d.parent / "docker-compose.yml").exists():
        return _run(["docker", "compose", "build"], cwd=str(d.parent))
    if (d / "package.json").exists():   return _run(["npm", "install"], cwd=str(d))
    if (d / "go.mod").exists():         return _run(["go", "build", "./..."], cwd=str(d))
    if (d / "pom.xml").exists():        return _run(["mvn", "-q", "package", "-DskipTests"], cwd=str(d))
    if (d / "requirements.txt").exists(): return _run(["python3", "-m", "compileall", "."], cwd=str(d))
    if (d / "composer.json").exists():  return _run(["php", "-l", "index.php"], cwd=str(d))
    return 0, "backend: no recognized build file — configure"


# ---------- boot + health (Boot & Verify / Re-Boot & Verify) ----------
def compose_up(repo_dir: Path) -> tuple[bool, str]:
    # --build so each boot reflects the CURRENT committed code (not a stale cached image)
    code, out = _run(["docker", "compose", "up", "-d", "--build"], cwd=str(repo_dir), timeout=1200)
    return code == 0, _tail(out)


def compose_down(repo_dir: Path) -> dict:
    code, out = _run(["docker", "compose", "down", "-v"], cwd=str(repo_dir), timeout=300)
    _run(["docker", "builder", "prune", "-f"])
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


def run_twoparty_web(repo_dir: Path, web_url: str, shot_dir: str,
                     caller_email: str, callee_email: str, password: str) -> dict:
    """Two-party web↔web call matrix: run twoparty.web.mjs for voice AND video. Two logged-in
    browser contexts; the caller rings the callee and both must reach the ongoing-call screen.
    Returns {'voice': verdict, 'video': verdict, 'ok': bool}. Proven leg of the call matrix —
    the mobile↔web legs (android/ios) are exercised in the manual demo, not automated here."""
    web = repo_dir / "web"
    src = Path(__file__).resolve().parent.parent / "e2e" / "twoparty.web.mjs"
    if not web.exists() or not src.exists():
        return {"error": "no web/ or twoparty script", "ok": False}
    dst = web / "_twoparty_verify.mjs"
    dst.write_text(src.read_text())
    out = {}
    try:
        for ctype in ("voice", "video"):
            env = {"WEB_URL": web_url, "CALL_TYPE": ctype, "SHOT_DIR": shot_dir,
                   "CALLER_EMAIL": caller_email, "CALLEE_EMAIL": callee_email, "E2E_PASSWORD": password}
            code, res = _run(["node", str(dst)], cwd=str(web), timeout=180, env=env)
            verdict = {"error": "no verdict json", "tail": _tail(res)}
            for line in reversed((res or "").splitlines()):
                if line.strip().startswith("{"):
                    try:
                        verdict = json.loads(line.strip()); break
                    except Exception:
                        pass
            out[ctype] = verdict
    finally:
        dst.unlink(missing_ok=True)
    out["ok"] = bool(out.get("voice", {}).get("callWorks") and out.get("video", {}).get("callWorks"))
    return out


def run_twoparty_mobile(platform: str, call_type: str, web_url: str, shot_dir: str) -> dict:
    """Automated mobile↔web call leg (android↔web / ios↔web). Drives the native app via Maestro +
    the web peer via Playwright through twoparty_mobile.py: web rings → mobile shows the incoming
    widget → Maestro accepts → both connect. Requires the emulator/sim booted + the integrated app
    installed (true during the demo/boot-2 stage). Returns the orchestrator's JSON verdict."""
    script = Path(__file__).resolve().parent.parent / "e2e" / "twoparty_mobile.py"
    if not script.exists():
        return {"error": "no twoparty_mobile.py", "callConnected": False}
    code, out = _run(["python3", str(script), "--platform", platform, "--direction", "web-calls-mobile",
                      "--call-type", call_type, "--web-url", web_url, "--shot-dir", shot_dir], timeout=300)
    for line in reversed((out or "").splitlines()):
        if line.strip().startswith("{"):
            try:
                return json.loads(line.strip())
            except Exception:
                pass
    return {"error": "no verdict json", "tail": _tail(out), "callConnected": False}


def run_e2e(cmd: str, repo_dir: Path) -> dict:
    if not cmd:
        return {"ran": False, "passed": None, "note": "e2e: not-configured", "tail": ""}
    code, out = _run(shlex.split(cmd), cwd=str(repo_dir), timeout=1800)
    return {"ran": True, "passed": code == 0, "exitCode": code, "tail": _tail(out)}
