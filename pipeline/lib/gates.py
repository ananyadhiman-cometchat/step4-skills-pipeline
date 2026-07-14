"""gates — my gate contract (STEP4_PIPELINE §4) as deterministic Python.

Pure functions over the on-disk stage results. No LLM. A stage asserts the
prior gate at its top; on failure it records outcome + tag and exits non-zero
so the conductor halts (never advances past a red gate).
"""
from __future__ import annotations


def _all_agents_ok(items) -> bool:
    # every codegen unit finished cleanly — NOT truncated (max_turns), NOT errored, NOT timed out.
    # agentOk is absent on legacy records → default True so old ledgers still read.
    return all(x.get("agentOk", True) for x in (items or []))


def baseline(r: dict) -> bool:
    # GATE.baseline: compiles + committed locally + no component's codegen was truncated/errored
    return bool(r) and r.get("buildExitCode") == 0 and bool(r.get("committedSha")) \
        and _all_agents_ok(r.get("components"))


def containerize(r: dict) -> bool:
    # GATE.containerize: a docker-compose was actually produced (boot depends on it)
    return bool(r) and r.get("composeCreated") is True


def baseline_up(b: dict) -> bool:
    # GATE.baselineUp: the false-positive guard — whole system boots + login smoke
    return bool(b) and (b.get("dockerUp") or b.get("emulatorUp")) \
        and b.get("allServicesHealthy") is True and b.get("loginSmokePassed") is True


def integrate(r: dict) -> bool:
    # GATE.integrate: integrated code compiles AND no component's codegen was truncated/errored.
    # (A 120-turn-truncated integration that happens to compile must NOT pass — that was the #1
    # "success reported when functionality is broken" mechanism.)
    return bool(r) and r.get("compileExitCode") == 0 and _all_agents_ok(r.get("reports"))


def integrated_up(v: dict) -> bool:
    # GATE.integratedUp: modified system boots AND SDK inits — checked BEFORE any chat/call test
    return bool(v) and (v.get("dockerUp") or v.get("emulatorUp")) \
        and v.get("allServicesHealthy") is True and v.get("sdkInitOk") is True


def verify(v: dict) -> bool:
    # GATE.verify: integrated system up AND the DETERMINISTIC scorecard did not refute it
    # (refuted = not(sdkInit and cross-party-receive and two-party-call); + vision teeth). No LLM judge.
    return integrated_up(v) and v.get("refuted") is False


# Tagging a stopped run — a dead baseline is 'agent', a modified system that
# won't boot is 'skills' (STEP4_PIPELINE §2 / §4).
def stop_tag(stage: str) -> str:
    return {"build": "agent", "boot": "agent",
            "integrate": "skills", "verify": "skills"}.get(stage, "agent")
