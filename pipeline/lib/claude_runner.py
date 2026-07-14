"""claude_runner — the ONLY place the pipeline shells out to an LLM.

Everything else in this package is deterministic control flow. A `build` or
`integrate` stage renders a prompt (string substitution, no LLM) then calls
run_headless() once per component to actually write the code. Phase A omits
skills/docs-mcp; Phase B adds them (settings.phaseB_extra_args).
"""
from __future__ import annotations
import json, os, subprocess, time
from pathlib import Path
from lib import secrets


def _expand(s: str, settings: dict) -> str:
    return os.path.expanduser(s.format(mcp_config=os.path.expanduser(settings.get("mcp_config", ""))))


def build_argv(settings: dict, *, phase: str, cwd: Path, model_key: str) -> list[str]:
    """Deterministic argv assembly. phase in {'A','B'}; model_key in {build,integrate,judge}."""
    argv = [settings["claude_bin"], "-p",
            "--model", settings["models"][model_key],
            "--max-turns", str(settings["max_turns"][model_key]),
            "--permission-mode", settings["permission_mode"],
            "--add-dir", str(cwd)]
    argv += list(settings.get("common_claude_args", []))
    extra = settings["phaseB_extra_args"] if phase == "B" else settings["phaseA_extra_args"]
    argv += [_expand(a, settings) for a in extra]
    return argv


def link_skills(settings: dict, cwd: Path) -> None:
    """Phase B skill loading via .claude/skills symlinks (used when link_skills_into_project=true).
    Loads ONLY the skills this component's use-case declares — keeps trigger metrics honest."""
    if not settings.get("link_skills_into_project"):
        return
    skills_dir = Path(os.path.expanduser(settings["skills_dir"]))
    dest = cwd / ".claude" / "skills"
    dest.mkdir(parents=True, exist_ok=True)
    # link the whole catalog dir; skill activation is measured, not pre-filtered
    for sk in skills_dir.iterdir():
        if sk.is_dir():
            link = dest / sk.name
            if not link.exists():
                try:
                    link.symlink_to(sk)
                except OSError:
                    pass


def run_headless(prompt: str, *, settings: dict, phase: str, cwd: Path,
                 model_key: str, label: str, log_dir: Path, deny_env: tuple = ()) -> dict:
    """Run one headless claude -p. Returns a rich outcome incl. agentOk (the gate signal).
    Never raises on model failure — records the outcome so the caller's gate decides.

    Hardening vs the original: (1) a per-stage subprocess TIMEOUT so a wedged agent can't hang the
    whole conductor forever; (2) an agentOk flag folding exit code + is_error + truncation, so a
    'stopped-midway-but-compiles' integration is caught (it was previously ignored); (3) secret
    redaction of the log + tail; (4) an env allowlist (deny_env) so a codegen agent only sees the
    creds its phase needs (integrate must not see the automation/REST/webhook secrets)."""
    cwd.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    if phase == "B":
        link_skills(settings, cwd)
    argv = build_argv(settings, phase=phase, cwd=cwd, model_key=model_key)
    log_file = log_dir / f"{label}.log"
    timeout_s = (settings.get("stage_timeout_s", {}) or {}).get(model_key,
                 settings.get("stage_timeout_default_s", 2400))
    child = secrets.child_env(deny_env)
    env_file = os.environ.get("COMETCHAT_ENV_FILE")
    t0, timed_out = time.time(), False
    try:
        proc = subprocess.run(argv, input=prompt, text=True, cwd=str(cwd),
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              env=child, timeout=timeout_s)
        out, code = (proc.stdout or ""), proc.returncode
    except subprocess.TimeoutExpired as e:
        raw = e.output or ""
        out = raw if isinstance(raw, str) else raw.decode(errors="ignore")
        code, timed_out = 124, True
    dur = round(time.time() - t0, 1)
    with open(log_file, "w") as lf:
        lf.write(secrets.redact(out, env_file))
    info = _parse_output(out)
    hit_max = info["subtype"] == "error_max_turns" or info["terminalReason"] in ("max_turns", "error_max_turns")
    is_err = bool(info["isError"]) or timed_out
    if timed_out:
        info["terminalReason"] = "timeout"
    agent_ok = (code == 0) and not is_err and not hit_max
    return {"label": label, "exitCode": code, "durationS": dur, "tokens": info["tokens"],
            "tail": secrets.redact(info["tail"], env_file), "logFile": str(log_file), "phase": phase,
            "terminalReason": info["terminalReason"], "subtype": info["subtype"], "isError": is_err,
            "hitMaxTurns": hit_max, "numTurns": info["numTurns"], "costUsd": info["costUsd"],
            "sessionId": info["sessionId"], "timedOut": timed_out, "agentOk": agent_ok}


def _parse_output(out: str) -> dict:
    """claude -p --output-format json emits a JSON envelope. Scan from the END for the last line that
    actually parses as a JSON object (a trailing stderr/warning line must not defeat the parse), and
    pull tokens + tail + WHY it stopped + is_error/num_turns/cost/session — fields the original threw
    away, so truncation was invisible and cost/timing were unrecorded."""
    tokens, tail = None, (out or "")[-2000:]
    subtype = term = session = is_err = num_turns = cost = None
    for line in reversed((out or "").strip().splitlines()):
        line = line.strip()
        if not (line.startswith("{") and line.endswith("}")):
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        usage = obj.get("usage") or obj.get("total_usage") or {}
        tokens = (usage.get("output_tokens", 0) or 0) + (usage.get("input_tokens", 0) or 0) or None
        subtype = obj.get("subtype")
        term = obj.get("terminal_reason") or obj.get("stop_reason")
        is_err = obj.get("is_error"); num_turns = obj.get("num_turns")
        cost = obj.get("total_cost_usd"); session = obj.get("session_id")
        if isinstance(obj.get("result"), str):
            tail = obj["result"][-2000:]
        break
    return {"tokens": tokens, "tail": tail, "subtype": subtype, "terminalReason": term,
            "isError": is_err, "numTurns": num_turns, "costUsd": cost, "sessionId": session}
