"""secrets — the pre-push secret-scan gate + log redaction + child-env filtering.

STEP4_PIPELINE §4.6 promised "a pre-push secret-scan blocks if REST_API_KEY/tokens appear in the
diff" and "only .env.example is ever committed" — but nothing implemented it, and push stages pushed
to a PUBLIC repo with no scan. This module is that missing control, plus two defence-in-depth helpers:
redaction of secret VALUES from logs, and a minimal-env filter so codegen agents only see the creds
their phase legitimately needs.

Everything is deterministic (no LLM, no network). The secret VALUES are read from .env.pipeline.
"""
from __future__ import annotations
import os, re, subprocess
from pathlib import Path

# Env-var names whose VALUES must never land in a commit or a log. (Names alone are harmless; the
# VALUES are the secrets.) The scan/redact operate on the concrete values loaded from .env.pipeline.
SECRET_KEYS = (
    "COMETCHAT_AUTOMATION_KEY", "COMETCHAT_AUTOMATION_SECRET", "COMETCHAT_REST_API_KEY",
    "COMETCHAT_AUTH_KEY", "COMETCHAT_WEBHOOK_SECRET", "FCM_SERVER_KEY",
    "APNS_KEY_ID", "APNS_TEAM_ID", "APNS_AUTH_KEY",
)
# Creds the INTEGRATE codegen agent has no legitimate use for (it only wires the client with
# APP_ID/REGION/AUTH_KEY). Denied from its subprocess env so a prompt-injected agent can't exfiltrate
# the management/REST keys. provision-app is exempt (it needs the automation keys).
INTEGRATE_DENY_ENV = (
    "COMETCHAT_AUTOMATION_KEY", "COMETCHAT_AUTOMATION_SECRET", "COMETCHAT_REST_API_KEY",
    "COMETCHAT_WEBHOOK_SECRET", "FCM_SERVER_KEY", "APNS_KEY_ID", "APNS_TEAM_ID", "APNS_AUTH_KEY",
)


def secret_values(env_file: str | None = None) -> list[str]:
    """The concrete secret VALUES to scan/redact — from the loaded env, plus .env.pipeline if given.
    Only values long enough to be real secrets (≥8 chars) are returned, so a short placeholder like
    'us' (region) never triggers a false positive."""
    vals = set()
    for k in SECRET_KEYS:
        v = os.environ.get(k, "").strip()
        if len(v) >= 8:
            vals.add(v)
    if env_file and os.path.exists(os.path.expanduser(env_file)):
        for line in open(os.path.expanduser(env_file)):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                if k.strip() in SECRET_KEYS and len(v.strip()) >= 8:
                    vals.add(v.strip())
    return sorted(vals)


def redact(text: str, env_file: str | None = None) -> str:
    """Replace any known secret VALUE in `text` with ***REDACTED*** (for logs)."""
    if not text:
        return text
    for v in secret_values(env_file):
        text = text.replace(v, "***REDACTED***")
    return text


def child_env(deny: tuple | list = ()) -> dict:
    """A copy of os.environ with the denied secret keys removed — hand to subprocess.run(env=...) so a
    codegen agent never sees creds it doesn't need."""
    deny = set(deny)
    return {k: v for k, v in os.environ.items() if k not in deny}


def scan_repo(repo_dir: Path, env_file: str | None = None) -> dict:
    """Scan the repo's TRACKED files (what a push would ship) for any secret value. Returns
    {clean: bool, hits: [{file, key}]}. Deterministic; the gate blocks the push if not clean.

    Only tracked files are scanned — .env / build outputs / node_modules are gitignored and never
    pushed, so scanning the working tree would false-positive on the injected build-time .env."""
    repo_dir = Path(repo_dir)
    vals = secret_values(env_file)
    if not vals:
        return {"clean": True, "hits": [], "note": "no secret values loaded to scan for"}
    try:
        tracked = subprocess.run(["git", "ls-files", "-z"], cwd=str(repo_dir),
                                 capture_output=True, text=True, timeout=60).stdout.split("\0")
    except Exception as e:
        return {"clean": False, "hits": [], "error": f"git ls-files failed: {e}"}
    val_key = {os.environ.get(k, "").strip(): k for k in SECRET_KEYS if os.environ.get(k, "").strip()}
    hits = []
    for rel in tracked:
        rel = rel.strip()
        if not rel:
            continue
        f = repo_dir / rel
        try:
            if not f.is_file() or f.stat().st_size > 5_000_000:
                continue
            blob = f.read_text(errors="ignore")
        except Exception:
            continue
        for v in vals:
            if v in blob:
                hits.append({"file": rel, "key": val_key.get(v, "?")})
    return {"clean": len(hits) == 0, "hits": hits}
