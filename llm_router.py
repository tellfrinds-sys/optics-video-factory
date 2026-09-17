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

Gemini فضل احتياطي ثانوي (معطّل حاليًا عبر GEMINI_FALLBACK_DISABLED=1 لحد ما رصيده يرجع).

⚠️ درس مستفاد فعليًا (2026-09-17): إعادة المحاولة على 429 لازم تكون **حلقة واحدة بميزانية
وقت إجمالية محدودة**، مش حلقتين متداخلتين (كانت النتيجة قبل الإصلاح: حلقة خارجية 4
محاولات × حلقة داخلية 5 محاولات = حتى 20 انتظارة، كل واحدة ممكن توصل لعشرات الثواني
لو Groq نفسه طلب انتظار طويل -- درس واحد استنى 21+ دقيقة بسبب كده بالظبط). البنية دلوقتي:
حلقة واحدة فقط في _groq()، بميزانية إجمالية (GROQ_MAX_WAIT_SECONDS)، فمفيش انفجار مضاعف.

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
# أقصى وقت إجمالي (كل المحاولات مجتمعة) قبل الاستسلام والرفع لدالة الاستدعاء --
# يحمي من انتظار عشرات الدقائق على نداء واحد (لوحظ فعليًا 21-37 دقيقة قبل هذا السقف).
GROQ_MAX_WAIT_SECONDS = int(os.environ.get("GROQ_MAX_WAIT_SECONDS", "120"))
# تباعد استباقي بين نداءات Groq المتتالية -- نداء واحد فعلي بيستهلك ~91% من حصة
# الدقيقة (~7300 من 8000 توكن)، فنداءان متتاليان بلا تباعد بيتصادموا كل مرة تقريبًا.
GROQ_MIN_CALL_INTERVAL = float(os.environ.get("GROQ_MIN_CALL_INTERVAL", "20"))
_last_call_ts = 0.0


def _extract_retry_after(he: urllib.error.HTTPError, default: float) -> float:
    try:
        msg = he.read().decode("utf-8", "ignore")
        m = re.search(r"try again in ([\d.]+)s", msg)
        if m:
            return float(m.group(1)) + 1
    except Exception:
        pass
    return default


def _groq_request(system: str, user: str, model: str) -> str:
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
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read())
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
    """حلقة إعادة محاولة واحدة فقط (مش متداخلة) بميزانية وقت إجمالية GROQ_MAX_WAIT_SECONDS.
    429/503: نستنى بالظبط الوقت اللي Groq طلبه (لو متاح) طالما مازال جوه الميزانية.
    413: فشل حتمي (الحمولة أكبر من حد الموديل) -- رفع فوري بلا انتظار.
    غير كده (رد فاضي/JSON تالف): إعادة محاولة سريعة (3 ثواني) طالما جوه الميزانية."""
    global _last_call_ts
    since_last = time.monotonic() - _last_call_ts
    if since_last < GROQ_MIN_CALL_INTERVAL:
        time.sleep(GROQ_MIN_CALL_INTERVAL - since_last)
    m = model or GROQ_MODEL
    t0 = time.monotonic()
    last_err = None
    while True:
        try:
            txt = _groq_request(system, user, m)
            _last_call_ts = time.monotonic()
            if not txt.strip():
                raise RuntimeError("Groq: رد فاضي")
            return _parse_json_lenient(txt)
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 413:
                raise
            wait = _extract_retry_after(e, default=10.0) if e.code in (429, 503) else 5.0
        except Exception as e:
            last_err = e
            wait = 3.0
        elapsed = time.monotonic() - t0
        if elapsed + wait > GROQ_MAX_WAIT_SECONDS:
            _last_call_ts = time.monotonic()
            raise last_err
        time.sleep(wait)


def llm(system: str, user: str, gemini_fn=None, gemini_kwargs: dict | None = None,
        groq_model: str | None = None) -> dict:
    try:
        return _groq(system, user, model=groq_model)
    except Exception as e:
        groq_err = e
        # لو معروف إن رصيد Gemini مقفول فعليًا (GEMINI_FALLBACK_DISABLED=1) -- مفيش داعي
        # نستنى دورة إعادة محاولات Gemini الكاملة (تصل لدقايق) على مفتاح هيفشل أكيد؛
        # نرفع خطأ Groq فورًا بدل الانتظار بلا فايدة.
        if os.environ.get("GEMINI_FALLBACK_DISABLED") == "1":
            print(f"[llm_router] Groq فشل ({groq_err}) -- Gemini معطّل (رصيده منتهي)، رفع الخطأ فورًا", flush=True)
            raise groq_err
        print(f"[llm_router] Groq فشل ({groq_err}) -- تجربة Gemini كاحتياطي", flush=True)
    if gemini_fn is None:
        raise RuntimeError("Groq فشل ومفيش دالة Gemini احتياطية متاحة")
    return gemini_fn(system, user, **(gemini_kwargs or {}))
