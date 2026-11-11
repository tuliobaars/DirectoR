"""Inter (SIL OFL, stage/INTER_LICENSE.txt), stored as base64 text so it survives any copy or sync tool."""
import base64, functools, os

from .util import STAGE_SRC

B64 = os.path.join(STAGE_SRC, "inter.woff2.b64")


@functools.lru_cache(None)
def inter_woff2():
    """bytes of the Inter variable font (woff2), or None (system fonts are used then)"""
    if os.path.exists(B64):
        return base64.b64decode("".join(open(B64).read().split()))
    return None


def inter_ttf(dest_dir):
    """a static TTF instance (for libass captions); None if fontTools is missing"""
    out = os.path.join(dest_dir, "Inter-SemiBold.ttf")
    if os.path.exists(out): return dest_dir
    data = inter_woff2()
    if not data: return None
    try:
        import io
        from fontTools.ttLib import TTFont
        from fontTools.varLib import instancer
        f = TTFont(io.BytesIO(data))
        if "fvar" in f: f = instancer.instantiateVariableFont(f, {"wght": 650})
        f.flavor = None
        os.makedirs(dest_dir, exist_ok=True)
        f.save(out)
        return dest_dir
    except Exception:  # noqa: BLE001  (brotli or fontTools missing)
        return None
