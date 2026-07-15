"""readiness — Phase 0 stack-aware readiness check (deterministic, no LLM).

Given a use case, expand its components and confirm the exact toolchains THAT use
case's stacks need are present BEFORE any codegen token is spent. A missing tool
for a stack this use case doesn't use is irrelevant — we only gate on what it needs.
"""
from __future__ import annotations
import shutil

# keyword in the stack string -> tools that stack needs
STACK_TOOLS = {
    "next": ["node", "npm"], "react": ["node", "npm"], "angular": ["node", "npm"],
    "astro": ["node", "npm"], "vue": ["node", "npm"],
    "expo": ["node", "npm", "npx"], "native": ["node", "npm"],  # React Native (Expo/bare)
    "flutter": ["flutter", "dart"],
    "swift": ["xcodebuild", "xcrun"], "ios": ["xcodebuild", "xcrun"],
    "kotlin": ["adb"], "compose": ["adb"], "android": ["adb"],
    "python": ["python3"], "node": ["node"], "php": ["php"],
    "go": ["go"], "golang": ["go"], "java": ["java", "mvn"], "spring": ["java", "mvn"],
}
# a component kind implies extra platform tools regardless of stack wording.
# `maestro` drives the mobile LOGIN behavioral check (login_shot.flow.yaml) — without it the demo can
# only screenshot the login screen, never verify login works (which hid del's iOS decode crash).
KIND_EXTRA = {
    "ios": ["xcodebuild", "xcrun", "maestro"],
    "android": ["adb", "maestro"],
    "mobile": ["node", "npm", "adb", "xcodebuild", "maestro"],   # RN → both platforms
    "app": ["flutter", "dart", "adb", "xcodebuild", "maestro"],    # Flutter → both platforms
}


def _tools_for(kind: str, stack: str) -> set[str]:
    need = set()
    s = (stack or "").lower()
    for kw, tools in STACK_TOOLS.items():
        if kw in s:
            need.update(tools)
    need.update(KIND_EXTRA.get(kind, []))
    return need


def check(uc: dict, components: list[dict], *, need_docker: bool = True) -> dict:
    """Return {ready, byComponent[], missing[]}. ready is the Phase-0 gate."""
    by_comp, missing = [], set()
    for c in components:
        tools = _tools_for(c["kind"], c["stack"])
        present = {t: bool(shutil.which(t)) for t in sorted(tools)}
        absent = [t for t, ok in present.items() if not ok]
        missing.update(absent)
        by_comp.append({"component": c["name"], "kind": c["kind"], "stack": c["stack"],
                        "needs": sorted(tools), "missing": absent})
    if need_docker and not shutil.which("docker"):
        missing.add("docker")
    return {"ready": len(missing) == 0, "byComponent": by_comp, "missing": sorted(missing)}
