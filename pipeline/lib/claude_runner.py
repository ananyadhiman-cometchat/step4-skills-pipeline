"""claude_runner — the ONLY place the pipeline shells out to an LLM.

Everything else in this package is deterministic control flow. A `build` or
`integrate` stage renders a prompt (string substitution, no LLM) then calls
run_headless() once per component to actually write the code. Phase A omits
skills/docs-mcp; Phase B adds them (settings.phaseB_extra_args).
"""
from __future__ import annotations
import json, os, subprocess, time
from pathlib import Path


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
                 model_key: str, label: str, log_dir: Path) -> dict:
    """Run one headless claude -p. Returns {label, exitCode, durationS, tokens, tail, logFile}.
    Never raises on model failure — records the exit code so the caller's gate decides."""
    cwd.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    if phase == "B":
        link_skills(settings, cwd)
    argv = build_argv(settings, phase=phase, cwd=cwd, model_key=model_key)
    log_file = log_dir / f"{label}.log"
    t0 = time.time()
    with open(log_file, "w") as lf:
        proc = subprocess.run(argv, input=prompt, text=True, cwd=str(cwd),
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        lf.write(proc.stdout or "")
    dur = round(time.time() - t0, 1)
    tokens, tail, term = _parse_output(proc.stdout or "")
    return {"label": label, "exitCode": proc.returncode, "durationS": dur,
            "tokens": tokens, "tail": tail, "logFile": str(log_file), "phase": phase,
            "terminalReason": term, "hitMaxTurns": term == "max_turns"}


def _parse_output(out: str):
    """claude -p --output-format json emits a JSON envelope; pull token usage + a text tail + why it stopped."""
    tokens, tail, term = None, out[-2000:], None
    try:
        obj = json.loads(out.strip().splitlines()[-1])
        usage = obj.get("usage") or obj.get("total_usage") or {}
        tokens = (usage.get("output_tokens", 0) or 0) + (usage.get("input_tokens", 0) or 0) or None
        term = obj.get("terminal_reason")
        if isinstance(obj.get("result"), str):
            tail = obj["result"][-2000:]
    except Exception:
        pass
    return tokens, tail, term
