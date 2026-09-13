"""
image_providers.py — طبقة عزل مصدر توليد الصور عن خط إنتاج الفيديو.
main.py ينادي دالة واحدة فقط: generate_image(prompt).
اختيار المزوّد الفعلي (Pollinations المجاني / Gemini / أي مزوّد جديد
مستقبلاً) بيتحدد بمتغير بيئة IMAGE_PROVIDER فقط — من غير أي تعديل
في خط الإنتاج نفسه (main.py) لما نغيّر أو نبدّل النموذج.
"""
from __future__ import annotations

import os
import time
import urllib.error
import urllib.parse
import urllib.request


class FactoryError(RuntimeError):
    def __init__(self, message: str, status: int = 500):
        super().__init__(message)
        self.status = status


IMAGE_PROVIDER = os.environ.get("IMAGE_PROVIDER", "pollinations").strip().lower()
IMAGE_PROVIDER_FALLBACK = os.environ.get("IMAGE_PROVIDER_FALLBACK", "").strip().lower()

_EDU_STYLE_SUFFIX = (
    ". Clean flat vector educational diagram style for a science/optics academy, "
    "accurate anatomy/physics, soft teal and navy blue color palette, no embedded "
    "text or labels, no watermark, high quality textbook illustration, 16:9 composition."
)


def _pollinations_generate(prompt: str, width: int = 1024, height: int = 576, retries: int = 3) -> bytes:
    full_prompt = prompt + _EDU_STYLE_SUFFIX
    encoded = urllib.parse.quote(full_prompt, safe="")
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={width}&height={height}&model=flux&nologo=true&seed=42"
    )
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "optics-video-factory/1.0"})
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = resp.read()
                if len(data) < 500:
                    raise FactoryError(f"Pollinations رجع صورة صغيرة جدًا ({len(data)} bytes)", 502)
                return data
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code == 429 and attempt < retries - 1:
                time.sleep(16)
                continue
            break
        except Exception as exc:
            last_err = exc
            if attempt < retries - 1:
                time.sleep(3)
                continue
            break
    raise FactoryError(f"فشل توليد صورة Pollinations: {last_err}", 502)


def _gemini_generate(prompt: str) -> bytes:
    import gemini_helpers
    return gemini_helpers.gemini_generate_image(prompt)


_PROVIDERS = {
    "pollinations": _pollinations_generate,
    "gemini": _gemini_generate,
}


def generate_image(prompt: str) -> bytes:
    primary = _PROVIDERS.get(IMAGE_PROVIDER)
    if primary is None:
        raise FactoryError(f"IMAGE_PROVIDER='{IMAGE_PROVIDER}' غير معروف. المتاح: {', '.join(_PROVIDERS)}", 500)
    try:
        return primary(prompt)
    except Exception as primary_exc:
        if IMAGE_PROVIDER_FALLBACK and IMAGE_PROVIDER_FALLBACK in _PROVIDERS and IMAGE_PROVIDER_FALLBACK != IMAGE_PROVIDER:
            try:
                return _PROVIDERS[IMAGE_PROVIDER_FALLBACK](prompt)
            except Exception as fallback_exc:
                raise FactoryError(
                    f"فشل المزوّد الأساسي ({IMAGE_PROVIDER}): {primary_exc} | وفشل الاحتياطي ({IMAGE_PROVIDER_FALLBACK}): {fallback_exc}",
                    502,
                ) from fallback_exc
        raise
