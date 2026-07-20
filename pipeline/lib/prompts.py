"""prompts — deterministic component expansion + prompt rendering.

No LLM decides what runs. Given a use case + archetype we expand the exact
component list, and render each stage's prompt by string substitution from the
use-case record + the spec-pinned requirements.md.
"""
from __future__ import annotations
import os
from pathlib import Path

# archetype -> ordered components. kind drives verify dispatch + build gate.
LAYOUT = {
    "N": [("backend", "backend"), ("web", "web"), ("android", "android"), ("ios", "ios")],
    "R": [("backend", "backend"), ("web", "web"), ("mobile", "mobile")],
    "F": [("backend", "backend"), ("web", "web"), ("app", "app")],
}
STACK_KEY = {"backend": "backend", "web": "web", "android": "android",
             "ios": "ios", "mobile": "mobile", "app": "app"}


def expand_components(uc: dict) -> list[dict]:
    """Deterministic: same use case -> same component list, always in this order.
    backend first (clients depend on its contract), then platforms."""
    out = []
    for comp_name, kind in LAYOUT[uc["archetype"]]:
        out.append({
            "name": comp_name,
            "kind": kind,
            "stack": uc.get(STACK_KEY[kind], uc.get("backend") if kind == "backend" else "?"),
            "dir": comp_name,
        })
    return out


def _requirements(settings, slug: str) -> str:
    f = Path(os.path.dirname(os.path.dirname(__file__))) / "requirements" / f"{slug}.md"
    return f.read_text() if f.exists() else "(no requirements.md pinned — generate a realistic spec first)"


def _tmpl(name: str) -> str:
    return (Path(os.path.dirname(os.path.dirname(__file__))) / "prompts" / name).read_text()


def render_requirements(settings, uc: dict) -> str:
    comps = expand_components(uc)
    non_backend = [c["name"] for c in comps if c["kind"] != "backend"]
    return _tmpl("requirements.md.tmpl").format(
        name=uc["name"], slug=uc["slug"], Slug=uc["slug"].capitalize(),
        web=uc.get("web", "(Flutter web)"),
        mobile=uc.get("mobile") or uc.get("app") or f"{uc.get('android','')}/{uc.get('ios','')}",
        backend=uc["backend"],
        a=non_backend[0] if non_backend else "client",
        b=non_backend[1] if len(non_backend) > 1 else "")


def render_provision(settings, uc: dict | None = None) -> str:
    uc = uc or {}
    return _tmpl("provision.md.tmpl").format(name=uc.get("name", "use case"), slug=uc.get("slug", "app"))


def render_containerize(settings, uc: dict) -> str:
    comps = expand_components(uc)
    web_stack = uc.get("web") or (f"{uc.get('app')} (web target)" if uc.get("app") else "none")
    web_dir = "web" if any(c["kind"] == "web" for c in comps) else \
              ("app" if any(c["kind"] == "app" for c in comps) else "none")
    layout = ", ".join(f"{c['dir']}/ ({c['stack']}, {c['kind']})" for c in comps)
    return _tmpl("containerize.md.tmpl").format(
        name=uc["name"], slug=uc["slug"], backend=uc["backend"],
        web=web_stack, web_dir=web_dir, layout=layout)


def render_readme(settings, uc: dict, repo: str) -> str:
    comps = expand_components(uc)
    layout = ", ".join(f"{c['dir']}/ ({c['stack']}, {c['kind']})" for c in comps)
    mobile = uc.get("mobile") or uc.get("app") or "/".join(
        x for x in (uc.get("android"), uc.get("ios")) if x) or "none"
    return _tmpl("readme.md.tmpl").format(
        name=uc["name"], slug=uc["slug"], backend=uc["backend"],
        web=uc.get("web", "none"), mobile=mobile, layout=layout, repo=repo)


def render_build(settings, uc: dict, comp: dict) -> str:
    return _tmpl("build.md.tmpl").format(
        name=uc["name"], slug=uc["slug"], comp=comp["name"], kind=comp["kind"],
        stack=comp["stack"], requirements=_requirements(settings, uc["slug"]))


def render_integrate(settings, uc: dict, comp: dict) -> str:
    vue_note = ("NOTE: this Vue web slice has NO cometchat-vue skill — expect no skill to trigger; "
                "record 'missedTrigger: vue-web' in the gap log (this is the deliberate gap-probe). "
                "STRATEGY (there is no Vue UI Kit — do NOT hand-roll chat/call UI on the raw SDK): mount the "
                "CometChat **React** UI Kit + Calls SDK as a React ISLAND inside Vue. Render a React root "
                "(ReactDOM.createRoot into a Vue component's DOM ref; unmount in onBeforeUnmount) for the "
                "conversation/message UI AND — this is the part that MUST be React-wrapped — the call "
                "surfaces (CometChatIncomingCall / CometChatOutgoingCall / CometChatOngoingCall + "
                "CometChatCallButtons). Initialize CometChatUIKit ONCE globally (guard against Vite HMR "
                "double-init); bridge auth-token + logged-in user into the island via props. Follow "
                "cometchat-react + cometchat-react-calls. Apply the known call-overlay CSS (full-viewport "
                "fixed overlay + define the --cometchat-calls-* height vars) so the ring/ongoing surfaces "
                "self-position. Still record the vue-web missedTrigger above — the gap is real even though "
                "the React-island workaround makes it functional. "
                if "vue-GAP" in uc.get("skills", []) and comp["kind"] == "web" else "")
    return _tmpl("integrate.md.tmpl").format(
        name=uc["name"], slug=uc["slug"], comp=comp["name"], kind=comp["kind"],
        stack=comp["stack"], skills=", ".join(uc.get("skills", [])),
        gaps_file=f"pipeline-state/gaps/{uc['slug']}.md", vue_note=vue_note)


def _skill_family(stack: str, kind: str) -> str:
    s = (stack or "").lower()
    if "flutter" in s:    return "flutter-v6"
    if "react native" in s or "expo" in s: return "native"
    if "compose" in s or "kotlin" in s or "android" in s: return "android-v6"
    if "swift" in s or "ios" in s: return "ios"
    if "angular" in s:    return "angular"
    return "react"        # next/react/vue web default → the React kit family


def render_skills_critic(settings, uc: dict, comp: dict, log_tail: str, compile_exit: int,
                         selfheal_ids: str) -> str:
    return _tmpl("skills_critic.md.tmpl").format(
        name=uc["name"], slug=uc["slug"], comp=comp["name"], stack=comp["stack"],
        platform=comp["kind"], comp_dir=comp["dir"],
        log_tail=(log_tail or "(no log captured)")[-4000:], compile_exit=compile_exit,
        selfheal_ids=selfheal_ids or "none",
        skill_family=_skill_family(comp["stack"], comp["kind"]),
        gaps_file=f"pipeline-state/gaps/{uc['slug']}.md")


# NOTE: the adversarial LLM judge was removed. The verify verdict is now a DETERMINISTIC scorecard of
# cross-party machine evidence (cross-party receive + two-party call + real SDK-init + vision), not an
# LLM opinion. render_judge / judge.md.tmpl / _parse_judge (all previously dead code with zero callers)
# were deleted so the code no longer implies a second, non-existent LLM verifier runs.
