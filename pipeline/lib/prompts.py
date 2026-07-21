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
    # Per-UC mandatory features (e.g. cre = group chat) — injected on top of the generic DEPTH STANDARD.
    # Empty for UCs that don't declare `features`, so the section simply disappears for them.
    feats = (uc.get("features") or "").strip()
    features_block = (
        f"\nUSE-CASE-SPECIFIC MANDATORY FEATURES ({uc['slug']}) — enforce these IN ADDITION to the DEPTH "
        f"STANDARD; they are as non-negotiable as A-E:\n  {feats}\n") if feats else ""
    # Pin the EXACT chatPair emails the harness will drive, so codegen seeds precisely those accounts.
    # Without this the spec only knows "nominate two personas" and can name any emails — which then don't
    # match the config's chatPair, and verify's seed_and_resolve_pair can't log them in.
    cp = uc.get("chatPair") or []
    chatpair_block = (
        f"\n   THIS use case's `chatPair` (from use_cases.json) is EXACTLY [`{cp[0]}`, `{cp[1]}`]. SEED both "
        f"as ordinary demo personas with roles that fit \"{uc['name']}\" — each with the shared seed password "
        f"and a real `avatar_url` — and make sure the two can open a 1:1 conversation. `{cp[0]}` is the "
        f"web/receiver, `{cp[1]}` is the mobile/sender. Use these LITERAL emails; do not rename them."
    ) if len(cp) >= 2 else ""
    return _tmpl("requirements.md.tmpl").format(
        name=uc["name"], slug=uc["slug"], Slug=uc["slug"].capitalize(),
        web=uc.get("web", "(Flutter web)"),
        mobile=uc.get("mobile") or uc.get("app") or f"{uc.get('android','')}/{uc.get('ios','')}",
        backend=uc["backend"],
        features=features_block,
        chatpair=chatpair_block,
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
        gaps_file=f"pipeline-state/gaps/{uc['slug']}.md", vue_note=vue_note,
        calls_note=_calls_note(uc, comp))


def _calls_in_scope(uc: dict) -> bool:
    """Does this use case ship voice/video? Read it off the spec-pin, which is the contract of record."""
    if "calls" in uc:
        return bool(uc["calls"])
    spec = Path(__file__).resolve().parent.parent / "requirements" / f"{uc.get('slug','')}.md"
    if not spec.exists():
        return False
    t = spec.read_text().lower()
    return ("voice/video" in t) or ("video call" in t) or ("voice call" in t)


def _calls_note(uc: dict, comp: dict) -> str:
    """Tell the agent EXPLICITLY whether calling is in scope.

    The template says "calls IF IN SCOPE" twice, but nothing in the rendered prompt ever told the agent
    which it was — the spec is not passed and there is no flag. On fin (spec: "voice/video call
    capability", "tap the voice/video call button → call UI renders") the iOS agent reasonably shipped
    chat + the incoming-call banner and NO outgoing calling, and the compile-only gate passed it twice.
    An unresolvable conditional in a prompt is a harness bug, not an agent error."""
    if comp["kind"] in ("backend",) or not _calls_in_scope(uc):
        return ""
    return (
        "CALLS ARE IN SCOPE for this use case — the spec pins voice/video calling, so chat alone is "
        "INCOMPLETE and will be rejected. Implement the FULL round trip on this client, not just the "
        "incoming-call banner (a banner on its own makes calling LOOK wired while no call can ever be "
        "placed):\n"
        "  1. initialize the calling module for this stack (per its calls skill),\n"
        "  2. a call BUTTON on the chat/message surface that actually invokes initiateCall,\n"
        "  3. the OUTGOING + ONGOING call surfaces, hosted so the call screen can present,\n"
        "  4. the INCOMING call surface mounted above the navigation graph.\n"
        "State in your final message which of these four you wired and where.")


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
