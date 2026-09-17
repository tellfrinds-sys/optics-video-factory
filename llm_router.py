# -*- coding: utf-8 -*-
"""llm_router.py — طبقة توجيه موحّدة لكل نداءات النص (كتابة/مراجعة/اختيار بصري/إصلاح)،
2026-09-17: بعد نفاد رصيد Gemini المدفوع مرارًا ("غارم")، Groq بقى المحرك الأساسي --
مجاني حقيقي (بدون بطاقة ائتمان)، وحصته حد استخدام يتجدد تلقائيًا بدل محفظة بتخلص، فمستحيل
تتكرر نفس أزمة "الرصيد خلص".

اختيار الموديل (بالتجربة الفعلية، مش تخمين):
- allam-2-7b (ALLaM/SDAIA): أفضل جودة لهجة مصرية، لكن حصته 6K توكن/دقيقة بس -- أصغر من
  حجم نداء واحد فعلي (برومبت+رد) فبترفض الطلب من الأساس (413).
- groq/compound / compound-mini: حصته المعلَنة سخية (70K TPM) لكنه موديل "وكيلي" بينادي
  داخليًا على موديلات فرعية (لوحظ فعليًا: llama-3.3-70b و gpt-oss-120b) وبيرتطم بحصصهم
  الصغيرة من جوه بشكل عشوائي غير متحكَّم فيه -- 429 متقطع لا يمكن الاعتماد عليه في
  إنتاج تلقائي غير مراقَب. تم استبعاده لهذا السبب بعد اختبار حي مباشر.
- qwen/qwen3.8-27b (المُعتمَد): موديل عادي (لا نداءات خفية)، حصته 8K TPM، وبعد تقليص
  حجم برومبت دليل الأسلوب المحقون (_style_tail في agents.py) بقى نداء الكتابة الكامل
  يستهلك ~7300 توكن -- بالظبط تحت السقف. جودة اللهجة عالية وطبيعية فعليًا (فُحصت مباشرة
  على محتوى درس حقيقي قبل الاعتماد).

Gemini فضل احتياطي ثانوي بس لو مفتاحه/رصيده اشتغلوا يومًا.

الاستخدام: استبدل أي `_gemini(system, user, ...)` بـ `llm_router.llm(system, user,
gemini_fn=_gemini, gemini_kwargs={...})` -- نفس عقد الإرجاع بالظبط (dict مُفكّك من JSON)،
ونفس سلوك رفع الاستثناء عند الفشل الكامل.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
# سقف رد أقل من حصة التوكن/الدقيقة للموديلات العادية (8K) بعد خصم حجم البرومبت --
# مقاس فعليًا: برومبت الكتابة الكامل ~4000 توكن، فسيب هامش أمان معقول للرد.
GROQ_MAX_COMPLETION_TOKENS = int(os.environ.get("GROQ_MAX_COMPLETION_TOKENS", "4000"))


def _groq_once(system: str, user: str, model: str) -> str:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY غير مضبوط")
    body = json.dumps({
        "model": model,
        "response_format": {"type": "json_object"},
        "temperature": 0.4,
        "max_completion_tokens": GROQ_MAX_COMPLETION_TOKENS,
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
                wait = 15 * (_try + 1)
                try:
                    body = he.read().decode("utf-8", "ignore")
                    m = re.search(r"try again in ([\d.]+)s", body)
                    if m:
                        wait = float(m.group(1)) + 1  # نلتزم بالوقت اللي السيرفر نفسه بيطلبه
                except Exception:
                    pass
                time.sleep(wait)
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
    m = model or GROQ_MODEL
    last_err = None
    for _attempt in range(4):
        try:
            txt = _groq_once(system, user, m)
            if not txt.strip():
                raise RuntimeError("Groq: رد فاضي")
            return _parse_json_lenient(txt)
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 413:
                # الحمولة أكبر من حد التوكن/الدقيقة للموديل -- إعادة نفس الطلب هترجّع
                # نفس الخطأ دايمًا، فمفيش داعي نستهلك محاولات.
                raise
            if _attempt < 3:
                time.sleep(6)
                continue
        except Exception as e:
            last_err = e
            if _attempt < 3:
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
