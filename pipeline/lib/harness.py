"""Harness readiness registry (PIPELINE_RESILIENCE_PLAN §6 Phase 5).

Issue B from the review: verify harnesses were stack-specific and hand-built MID-RUN, stalling waves.
This registry declares, per stack family, which verify-harness files must already exist (and be
non-empty) BEFORE a wave starts. ``check`` is called in preflight; a missing harness fails fast with a
precise list, so no wave ever authors a harness on the fly.

Paths are relative to the pipeline root (the dir containing e2e/). Tune the lists as harnesses land;
the point is the GATE, so coverage is explicit instead of discovered late.
"""
from __future__ import annotations

from pathlib import Path

# stack/kind keyword -> the verify-harness files that family needs to exist
_FAMILY_FILES = {
    "flutter": [
        "e2e/mobile_flows/chat_receive.flow.yaml",
        "e2e/mobile_flows/place_call.flow.yaml",
        "e2e/mobile_flows/accept_call.flow.yaml",
        "e2e/call_matrix_flutter.py",
        "e2e/webdriver/flutter_chat_receive.mjs",
    ],
    "web-react": ["e2e/twoparty_chat.web.mjs", "e2e/chatcall.web.mjs", "e2e/webdriver/root_shot.mjs"],
    "web-node": ["e2e/twoparty_chat.web.mjs", "e2e/twoparty.web.mjs"],
    "rn": ["e2e/twoparty_mobile.py", "e2e/mobile_flows/chat_receive.flow.yaml"],
    "android-native": ["e2e/mobile_flows/chat_receive.flow.yaml", "e2e/mobile_flows/place_call.flow.yaml"],
    "ios-native": ["e2e/mobile_flows/chat_receive.flow.yaml", "e2e/mobile_flows/accept_call.flow.yaml"],
}

# how a component (kind, stack) maps to a family
_MATCH = [
    ("app", "flutter", "flutter"),
    ("mobile", "native", "rn"),
    ("mobile", "expo", "rn"),
    ("android", "", "android-native"),
    ("ios", "", "ios-native"),
    ("web", "react", "web-react"),
    ("web", "next", "web-react"),
    ("web", "astro", "web-react"),
    ("web", "angular", "web-node"),
    ("web", "vue", "web-node"),
]


def family(kind: str, stack: str) -> str | None:
    k, s = (kind or "").lower(), (stack or "").lower()
    for mk, ms, fam in _MATCH:
        if mk == k and (ms == "" or ms in s):
            return fam
    return None


def required(components: list[dict]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for c in components:
        fam = family(c.get("kind", ""), c.get("stack", ""))
        if fam and fam in _FAMILY_FILES:
            out[fam] = _FAMILY_FILES[fam]
    return out


def check(pipeline_root: Path, components: list[dict]) -> dict:
    """Return {ready, byFamily[], missing[]}. A harness file must EXIST and be non-empty (>0 bytes)."""
    by_family, missing = [], []
    for fam, files in required(components).items():
        absent = []
        for rel in files:
            p = pipeline_root / rel
            if not p.exists() or p.stat().st_size == 0:
                absent.append(rel)
        by_family.append({"family": fam, "files": files, "absent": absent})
        missing.extend(absent)
    return {"ready": len(missing) == 0, "byFamily": by_family, "missing": sorted(set(missing))}
