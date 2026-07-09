"""visual_baseline — screenshot regression baseline ("did it change?").

Pairs with `vision` ("is it correct?"). This answers the orthogonal question: did this surface
change vs. the last known-good run? First run establishes the golden; later runs diff against it.

Two backends:
  - "local" (default, no account): a perceptual dHash + normalized pixel diff via Pillow. Robust to
    tiny anti-aliasing noise; flags real layout/content changes. Golden PNGs live under
    pipeline-state/baselines/<slug>/<name>.png.
  - "applitools" / "percy": managed Visual-AI baselines (anti-flake, review UI). Enabled when
    APPLITOOLS_API_KEY / PERCY_TOKEN is set — see `_saas_note`. The local backend is the fallback so
    the pipeline works offline; swap to SaaS for cross-device baselines + a review dashboard.
"""
from __future__ import annotations
import os
from pathlib import Path


def _dhash(img, size: int = 8):
    """64-bit difference hash — perceptual, tolerant of scaling/compression noise."""
    from PIL import Image
    g = img.convert("L").resize((size + 1, size), Image.LANCZOS)
    px = list(g.getdata()); w = size + 1
    bits = 0
    for r in range(size):
        for c in range(size):
            bits = (bits << 1) | (1 if px[r * w + c] < px[r * w + c + 1] else 0)
    return bits


def _pixel_delta(a, b) -> float:
    """Mean absolute per-pixel luminance difference (0..1) on a downscaled grayscale pair."""
    from PIL import Image
    n = (64, 64)
    ga = a.convert("L").resize(n, Image.LANCZOS); gb = b.convert("L").resize(n, Image.LANCZOS)
    da, db = list(ga.getdata()), list(gb.getdata())
    return sum(abs(x - y) for x, y in zip(da, db)) / (len(da) * 255.0)


def _saas_note(backend: str) -> str:
    return (f"{backend} backend requested but no key set. Set "
            f"{'APPLITOOLS_API_KEY' if backend == 'applitools' else 'PERCY_TOKEN'} and install the SDK "
            f"({'@applitools/eyes-playwright' if backend == 'applitools' else '@percy/cli + @percy/playwright'}); "
            f"then the e2e harness uploads the shot for a managed Visual-AI baseline. Falling back to local diff.")


def compare(shot_path: str, name: str, baselines_dir: str, slug: str,
            backend: str = "local", threshold: float = 0.06) -> dict:
    """Compare `shot_path` to the stored golden for (slug, name).
    Returns {status, changed, score, hammingDist, baseline, note?}.
    status ∈ {baseline-established, unchanged, CHANGED, error}."""
    shot = Path(shot_path)
    if not shot.exists() or shot.stat().st_size < 1000:
        return {"status": "error", "changed": False, "error": f"missing/empty: {shot_path}"}

    # SaaS backends: only if a key is present; otherwise note + fall through to local.
    note = None
    if backend in ("applitools", "percy"):
        key = os.environ.get("APPLITOOLS_API_KEY" if backend == "applitools" else "PERCY_TOKEN")
        if not key:
            note = _saas_note(backend); backend = "local"
        else:
            # Managed backends run in the JS e2e layer (SDK uploads the shot). The Python worker only
            # records intent here; the harness reports the SaaS verdict back. Kept as an explicit seam.
            return {"status": "delegated-saas", "changed": None, "backend": backend,
                    "note": f"{backend} baseline handled by the e2e SDK (key present)."}

    try:
        from PIL import Image
    except Exception:
        return {"status": "error", "changed": False, "error": "Pillow not installed (pip install --user Pillow)"}

    gold_dir = Path(os.path.expanduser(baselines_dir)) / slug
    gold_dir.mkdir(parents=True, exist_ok=True)
    gold = gold_dir / f"{name}.png"
    cur = Image.open(shot)
    if not gold.exists():
        cur.save(gold)
        return {"status": "baseline-established", "changed": False, "score": 0.0, "baseline": str(gold), "note": note}
    ref = Image.open(gold)
    ham = bin(_dhash(cur) ^ _dhash(ref)).count("1")   # 0..64
    delta = _pixel_delta(cur, ref)                     # 0..1
    changed = ham > 8 or delta > threshold
    return {"status": "CHANGED" if changed else "unchanged", "changed": changed,
            "score": round(delta, 4), "hammingDist": ham, "baseline": str(gold), "note": note}


def update_baseline(shot_path: str, name: str, baselines_dir: str, slug: str) -> bool:
    """Promote a screenshot to the golden (call after a human approves an intended change)."""
    try:
        from PIL import Image
    except Exception:
        return False
    gold_dir = Path(os.path.expanduser(baselines_dir)) / slug
    gold_dir.mkdir(parents=True, exist_ok=True)
    Image.open(shot_path).save(gold_dir / f"{name}.png")
    return True
