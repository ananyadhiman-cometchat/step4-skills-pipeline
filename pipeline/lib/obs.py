"""obs — observability spine: a per-run JSONL manifest + failure records + a deterministic
cause classifier. Plain files, no DB, no daemon, no new deps.

Before this, the ledger was flat <slug>-<stage>.json snapshots with no run id, no timestamps, no
timing, no cost, and no ordering — a failure could only be diagnosed by hand-grepping raw log tails,
and boot/harness failures were mis-tagged 'skills', poisoning the gaps ledger. This module makes
every stage outcome an explicit, timestamped, correlated event, and centralises the cause taxonomy
in ONE deterministic function.

  runs/<slug>/_run/manifest.jsonl   append-only event log (the spine)
  runs/<slug>/_run/failures/<stage>.json   one record per gate-fail/error, with a classified cause
"""
from __future__ import annotations
import json, os, traceback
from datetime import datetime, timezone
from pathlib import Path
from lib import state, secrets


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_id() -> str:
    """One id per run_usecase.py process (one stage). Minted in main(), stamped on every event so a
    stage's events + artifacts + the claude session_id correlate. Deterministic within a process."""
    rid = os.environ.get("STEP4_RUN_ID")
    if not rid:
        rid = "run-" + _utc().replace(":", "").replace("-", "") + f"-{os.getpid()}"
        os.environ["STEP4_RUN_ID"] = rid
    return rid


def _run_dir(S: dict, slug: str) -> Path:
    d = state.repo_dir(S, slug) / "_run"
    d.mkdir(parents=True, exist_ok=True)
    return d


def event(S: dict, slug: str, stage: str, evt: str, **kw) -> None:
    """Append one JSONL event. Secret values are redacted defensively before write."""
    try:
        line = {"ts": _utc(), "runId": run_id(), "waveId": os.environ.get("STEP4_WAVE_ID"),
                "slug": slug, "stage": stage, "evt": evt, **kw}
        raw = secrets.redact(json.dumps(line), os.environ.get("COMETCHAT_ENV_FILE"))
        with open(_run_dir(S, slug) / "manifest.jsonl", "a") as f:
            f.write(raw + "\n")
    except Exception:
        pass  # observability must never break a stage


def classify_cause(signals: dict, err: str = "") -> str:
    """The ONE place a failure cause is decided — skills | agent | harness | infra | setup.

    Precedence matters: a boot/harness failure must NEVER be attributable to 'skills' (that
    corrupts the gaps ledger the whole pipeline exists to produce). Deterministic string/flag logic,
    replacing the scattered, wrong tagging (verify boot failures were tag=skills; selector timeouts
    were charged to CometChat skills)."""
    err = err or ""
    # infra: the system didn't come up
    if signals.get("dockerUp") is False or signals.get("allServicesHealthy") is False:
        return "infra"
    # agent: codegen truncated / errored / hung
    if signals.get("hitMaxTurns") or signals.get("isError") or signals.get("exit") in (124, 127):
        return "agent"
    # harness: OUR test rig broke (module/selector/timeout/spawn) — NOT a CometChat defect
    if _re_any(err, (r"ERR_MODULE", r"ENOENT", r"Cannot find", r"Traceback", r"spawn",
                     r"no verdict json", r"locator .*exceeded", r"waiting for (selector|locator)",
                     r"Timeout .*exceeded", r"strict mode violation", r"net::ERR", r"missing tool")):
        return "harness"
    # skills: only a genuine integration/e2e failure on a healthy system with completed codegen
    if signals.get("stage") in ("integrate", "verify"):
        return "skills"
    return "setup"


def _re_any(text: str, patterns) -> bool:
    import re
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def record_failure(S: dict, slug: str, stage: str, *, gate: str, summary: str,
                   signals: dict, err: str = "", evidence: list | None = None) -> str:
    """Write runs/<slug>/_run/failures/<stage>.json with a deterministic cause class + evidence
    pointers. Returns the classified cause so the caller can tag its die_gate consistently."""
    signals = {**signals, "stage": stage}
    cause = classify_cause(signals, err)
    rec = {"runId": run_id(), "waveId": os.environ.get("STEP4_WAVE_ID"), "slug": slug, "stage": stage,
           "ts": _utc(), "class": cause, "gate": gate, "summary": secrets.redact(summary, os.environ.get("COMETCHAT_ENV_FILE")),
           "evidence": evidence or [], "signals": signals}
    try:
        fdir = _run_dir(S, slug) / "failures"; fdir.mkdir(parents=True, exist_ok=True)
        (fdir / f"{stage}.json").write_text(json.dumps(rec, indent=2))
        event(S, slug, stage, "failure", cause=cause, gate=gate, summary=summary[:200])
    except Exception:
        pass
    return cause
