# -*- coding: utf-8 -*-
"""llm_router.py — طبقة توجيه موحّدة لكل نداءات النص (كتابة/مراجعة/اختيار بصري/إصلاح)،
2026-09-17: بعد نفاد رصيد Gemini المدفوع مرارًا ("غارم")، Groq بقى المحرك الأساسي --
مجاني حقيقي (بدون بطاقة ائتمان)، وحده استخدام يومي/دقيقي يتجدد تلقائيًا بدل محفظة بتخلص،
فمستحيل تتكرر نفس أزمة "الرصيد خلص". الموديل الافتراضي groq/compound-mini: حصة توكن/دقيقة
سخية جدًا (70K) تكفي عدة نداءات متتالية لكل درس (كتابة+تدقيق+مراجعة)، على عكس allam-2-7b
(6K TPM بس -- جودة لهجة ممتازة لكن حصة ضيقة جدًا لعبء الإنتاج الفعلي) أو qwen/gpt-oss
(8K TPM). العيب: موديل "compound" وكيلي (agentic) أحيانًا بيرجّع رد فاضي/مقطوع لأسباب
داخلية (خطوات أدوات مخفية) -- اتعامل معاه بإعادة محاولة على فشل تحليل JSON برضه، مش بس
أخطاء HTTP. Gemini فضل احتياطي ثانوي بس لو مفتاحه/رصيده اشتغلوا يومًا.

الاستخدام: استبدل أي `_gemini(system, user, ...)` بـ `llm_router.llm(system, user,
gemini_fn=_gemini, gemini_kwargs={...})` -- نفس عقد الإرجاع بالظبط (dict مُفكّك من JSON)،
ونفس سلوك رفع الاستثناء عند الفشل الكامل.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "groq/compound-mini")
GROQ_MAX_TOKENS = 8192  # أقصى سقف مسموح فعليًا لهذا الموديل (context_window)


def _groq_once(system: str, user: str, model: str) -> str:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY غير مضبوط")
    body = json.dumps({
        "model": model,
        "response_format": {"type": "json_object"},
        "temperature": 0.4,
        "max_completion_tokens": GROQ_MAX_TOKENS,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode("utf-8")
    req = urllib.request.Request(
        GROQ_URL, data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "User-Agent": "curl/8.5.0"},  # urllib الافتراضي بيتحجب بخطأ Cloudflare 1010
    )
    d = None
    for _try in range(5):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read())
                break
        except urllib.error.HTTPError as he:
            if he.code in (429, 503) and _try < 4:
                time.sleep(15 * (_try + 1))
                continue
            raise
    if d is None:
        raise RuntimeError("Groq: تعذّر الاتصال بعد محاولات")
    try:
        return d["choices"][0]["message"]["content"] or ""
    except Exception:
        raise RuntimeError("Groq: رد بلا محتوى: " + json.dumps(d, ensure_ascii=False)[:400])


def _parse_json_lenient(txt: str) -> dict:
    try:
        return json.loads(txt)
    except Exception:
        t = txt.strip()
        if t.startswith("{"):
            t = t.rstrip(", \n")
            t += "]" * max(0, t.count("[") - t.count("]"))
            t += "}" * max(0, t.count("{") - t.count("}"))
            try:
                return json.loads(t)
            except Exception:
                pass
        raise RuntimeError("Groq: رد غير قابل لتحليل JSON: " + txt[:300])


def _groq(system: str, user: str, model: str | None = None) -> dict:
    """موديل compound-mini الوكيلي أحيانًا بيرجّع محتوى فاضي/مقطوع (خطوات أدوات داخلية
    بتاكل الميزانية) -- إعادة محاولة قصيرة هنا تحل الغالبية العظمى من الحالات دون
    اللجوء لـ Gemini الاحتياطي بلا داعٍ."""
    m = model or GROQ_MODEL
    last_err = None
    for _attempt in range(6):
        try:
            txt = _groq_once(system, user, m)
            if not txt.strip():
                raise RuntimeError("Groq: رد فاضي")
            return _parse_json_lenient(txt)
        except Exception as e:
            last_err = e
            if _attempt < 5:
                time.sleep(6)
                continue
    raise last_err


def llm(system: str, user: str, gemini_fn=None, gemini_kwargs: dict | None = None,
        groq_model: str | None = None) -> dict:
    try:
        return _groq(system, user, model=groq_model)
    except Exception as e:
        print(f"[llm_router] Groq فشل ({e}) -- تجربة Gemini كاحتياطي", flush=True)
    if gemini_fn is None:
        raise RuntimeError("Groq فشل ومفيش دالة Gemini احتياطية متاحة")
    return gemini_fn(system, user, **(gemini_kwargs or {}))
