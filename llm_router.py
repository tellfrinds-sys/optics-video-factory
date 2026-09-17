# -*- coding: utf-8 -*-
"""llm_router.py — طبقة توجيه موحّدة لكل نداءات النص (كتابة/مراجعة/اختيار بصري/إصلاح).

تاريخ القرار (2026-09-17): بعد نفاد رصيد Gemini المدفوع مرارًا ("غارم")، جرّبنا Groq
(مجاني حقيقي بلا بطاقة) وثبت إنه شغّال لكن حصته صغيرة جدًا لمشروع بحجمنا (200K توكن/يوم
لكل موديل -- استهلكناها في ساعات من الاختبار الفعلي، ومحتاجين موديل واحد يغطي كل
النداءات فمفيش تنويع بين موديلات بحصص منفصلة). بطلب صريح من المسؤول: **DeepSeek بقى
المحرك الأساسي دلوقتي** -- منحة تسجيل لمرة واحدة (5 مليون توكن، 30 يوم، بلا بطاقة) أكبر
بكتير من حصة Groq اليومية، وجودته وسرعته أعلى. **مش مجاني للأبد** (بعد المنحة لازم بطاقة
دفع) -- قرار واعٍ من المسؤول يقبل استخدام المنحة دلوقتي، مش نفس فلسفة "مجاني للأبد" اللي
حلت مشكلة الصوت/الصور. Groq فضل احتياطي ثانوي (لسه شغال ومجاني حقيقي)، Gemini معطّل
(GEMINI_FALLBACK_DISABLED=1) لحد ما رصيده يرجع.

⚠️ تصميم الحد الأقصى من توفير التوكن (بطلب صريح من المسؤول 2026-09-17)، لاستمرار المنحة
أطول فترة ممكنة:
  1) دليل الأسلوب المحقون مقصوص لآخر جزء بس (_style_tail في agents.py) -- كان بيتقصّ
     لـ Groq أصلًا (413)، هنا بيوفّر توكن حتى لو DeepSeek مش هيرفض الطلب.
  2) proofread_scenes بقى دفعة واحدة لكل الدرس (مش 3 نداءات منفصلة) -- DeepSeek سياق أكبر
     بكتير من Gemini/Groq فمعندوش مشكلة كسر JSON اللي كانت سبب التقسيم الأصلي.
  3) جولات force-resolve اتقلّصت لجولة واحدة بس (كانت 2) -- التصحيح الحتمي
     (force_resolve_issues، بلا نموذج خالص) بيفضل شغال زي ما هو كحل أخير مجاني.
  4) system prompt ثابت قد الإمكان بين النداءات (نفس WORD_MIN/WORD_MAX ونفس ذيل دليل
     الأسلوب) عشان يستفيد من الـ prompt caching التلقائي عند DeepSeek (خصم ~97% على
     التوكن المكرر في الجزء الثابت من البرومبت).

⚠️ درس مستفاد من تجربة Groq (لسه سارٍ هنا): إعادة المحاولة على 429 لازم تكون **حلقة
واحدة بميزانية وقت إجمالية محدودة**، مش حلقتين متداخلتين (كان السبب في انتظار 21+ دقيقة
على نداء واحد قبل الإصلاح).

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

# ---------------- DeepSeek: المحرك الأساسي (2026-09-17) ----------------
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_MAX_COMPLETION_TOKENS = int(os.environ.get("DEEPSEEK_MAX_COMPLETION_TOKENS", "6000"))
DEEPSEEK_MAX_WAIT_SECONDS = int(os.environ.get("DEEPSEEK_MAX_WAIT_SECONDS", "120"))

# ---------------- Groq: احتياطي ثانوي (مجاني حقيقي، حصته أصغر) ----------------
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
GROQ_MAX_COMPLETION_TOKENS = int(os.environ.get("GROQ_MAX_COMPLETION_TOKENS", "4000"))
GROQ_MAX_WAIT_SECONDS = int(os.environ.get("GROQ_MAX_WAIT_SECONDS", "120"))
GROQ_MIN_CALL_INTERVAL = float(os.environ.get("GROQ_MIN_CALL_INTERVAL", "20"))
_last_groq_call_ts = 0.0


def _extract_retry_after(he: urllib.error.HTTPError, default: float) -> float:
    try:
        msg = he.read().decode("utf-8", "ignore")
        m = re.search(r"try again in ([\d.]+)s", msg)
        if m:
            return float(m.group(1)) + 1
    except Exception:
        pass
    return default


def _chat_request(url: str, key: str, model: str, system: str, user: str,
                   max_completion_tokens: int, extra_headers: dict | None = None,
                   max_tokens_field: str = "max_tokens") -> str:
    body = json.dumps({
        "model": model,
        "response_format": {"type": "json_object"},
        "temperature": 0.4,
        max_tokens_field: max_completion_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode("utf-8")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read())
    try:
        return d["choices"][0]["message"]["content"] or ""
    except Exception:
        raise RuntimeError("رد بلا محتوى: " + json.dumps(d, ensure_ascii=False)[:400])


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
        raise RuntimeError("رد غير قابل لتحليل JSON: " + txt[:300])


def _deepseek(system: str, user: str, model: str | None = None) -> dict:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY غير مضبوط")
    m = model or DEEPSEEK_MODEL
    t0 = time.monotonic()
    last_err = None
    while True:
        try:
            txt = _chat_request(DEEPSEEK_URL, key, m, system, user, DEEPSEEK_MAX_COMPLETION_TOKENS)
            if not txt.strip():
                raise RuntimeError("DeepSeek: رد فاضي")
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
        if elapsed + wait > DEEPSEEK_MAX_WAIT_SECONDS:
            raise last_err
        time.sleep(wait)


def _groq(system: str, user: str, model: str | None = None) -> dict:
    """حلقة إعادة محاولة واحدة فقط (مش متداخلة) بميزانية وقت إجمالية GROQ_MAX_WAIT_SECONDS،
    مع تباعد استباقي بين النداءات (نداء واحد بيستهلك ~91% من حصة الدقيقة لبعض الموديلات)."""
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY غير مضبوط")
    global _last_groq_call_ts
    since_last = time.monotonic() - _last_groq_call_ts
    if since_last < GROQ_MIN_CALL_INTERVAL:
        time.sleep(GROQ_MIN_CALL_INTERVAL - since_last)
    m = model or GROQ_MODEL
    t0 = time.monotonic()
    last_err = None
    while True:
        try:
            txt = _chat_request(GROQ_URL, key, m, system, user, GROQ_MAX_COMPLETION_TOKENS,
                                 extra_headers={"User-Agent": "curl/8.5.0"},  # Cloudflare 1010
                                 max_tokens_field="max_completion_tokens")
            _last_groq_call_ts = time.monotonic()
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
            _last_groq_call_ts = time.monotonic()
            raise last_err
        time.sleep(wait)


def llm(system: str, user: str, gemini_fn=None, gemini_kwargs: dict | None = None,
        groq_model: str | None = None) -> dict:
    """DeepSeek أولًا (المحرك الأساسي الحالي) -> Groq احتياطي -> Gemini (لو مش معطّل)."""
    errors = []
    if os.environ.get("DEEPSEEK_API_KEY"):
        try:
            return _deepseek(system, user)
        except Exception as e:
            errors.append(f"DeepSeek: {e}")
            print(f"[llm_router] DeepSeek فشل ({e}) -- تجربة Groq", flush=True)
    try:
        return _groq(system, user, model=groq_model)
    except Exception as e:
        errors.append(f"Groq: {e}")
        if os.environ.get("GEMINI_FALLBACK_DISABLED") == "1":
            print(f"[llm_router] Groq فشل ({e}) -- Gemini معطّل (رصيده منتهي)، رفع الخطأ فورًا", flush=True)
            raise RuntimeError(" | ".join(errors))
        print(f"[llm_router] Groq فشل ({e}) -- تجربة Gemini كاحتياطي", flush=True)
    if gemini_fn is None:
        raise RuntimeError(" | ".join(errors) or "كل المحركات فشلت")
    return gemini_fn(system, user, **(gemini_kwargs or {}))
