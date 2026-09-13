"""
gemini_helpers.py — إضافات مصنع فيديوهات بوابة البصريات
- توليد صورة واحدة لكل مشهد عبر Gemini (بديل Stability AI).
- توليد صوت سرد واحد متصل لكل الدرس عبر HeyGen (بديل استدعاء منفصل لكل مشهد)،
  مع تقطيع توقيتات الكلمات (word_timestamps) على المشاهد بالترتيب.
"""
from __future__ import annotations

import base64
import json
import os
import re
import unicodedata
import urllib.error
import urllib.request
from typing import Any


class FactoryError(RuntimeError):
    def __init__(self, message: str, status: int = 500):
        super().__init__(message)
        self.status = status


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_IMAGE_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
HEYGEN_API_KEY = os.environ.get("HEYGEN_API_KEY", "")
HEYGEN_VOICE_ID = os.environ.get("HEYGEN_VOICE_ID", "b36a99c25d2f4a45a92ccc7f158ff7ae")


def _find_base64_image(obj: Any) -> tuple[bytes, str] | None:
    """يبحث بشكل دفاعي داخل استجابة JSON عن أول صورة base64، أيًا كان اسم الحقل
    (بما إن واجهة Gemini الجديدة v1beta/interactions لسه بتتغيّر). يرجّع
    (bytes, mime_type) أو None لو مفيش."""
    if isinstance(obj, dict):
        data = obj.get("data") or obj.get("bytesBase64Encoded") or obj.get("inline_data", {}).get("data") if isinstance(obj.get("inline_data"), dict) else obj.get("data")
        mime = obj.get("mime_type") or obj.get("mimeType") or (obj.get("inline_data") or {}).get("mime_type") or "image/png"
        if isinstance(data, str) and len(data) > 500:
            try:
                return base64.b64decode(data), mime
            except Exception:
                pass
        for value in obj.values():
            found = _find_base64_image(value)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_base64_image(item)
            if found:
                return found
    return None


def gemini_generate_image(prompt: str, aspect_ratio: str = "16:9") -> bytes:
    """يولّد صورة واحدة عبر Gemini بناءً على وصف المشهد (visual_brief)."""
    if not GEMINI_API_KEY:
        raise FactoryError("GEMINI_API_KEY غير مضبوط في متغيرات البيئة", 500)
    full_prompt = (
        "Professional medical/scientific educational illustration for an Arabic optics "
        "academy video. " + prompt +
        ". Clean flat vector diagram style, accurate anatomy, soft teal and navy blue "
        "color palette, no embedded text or labels, no watermark, high quality textbook "
        "illustration, 16:9 composition."
    )
    body = json.dumps({
        "model": GEMINI_IMAGE_MODEL,
        "input": [{"type": "text", "text": full_prompt}],
        "response_format": {"type": "image", "mime_type": "image/jpeg", "aspect_ratio": aspect_ratio},
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        data=body,
        headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise FactoryError(f"فشل توليد صورة Gemini ({exc.code}): {exc.read().decode('utf-8', 'ignore')[:400]}", 502) from exc
    found = _find_base64_image(result)
    if not found:
        raise FactoryError(f"Gemini لم يرجع صورة صالحة: {json.dumps(result, ensure_ascii=False)[:400]}", 502)
    return found[0]


def heygen_tts_continuous(text: str, voice_id: str | None = None, speed: float = 1.17) -> tuple[bytes, list[dict]]:
    """استدعاء واحد لـ HeyGen Starfish TTS لكل نص السرد المُجمّع، يرجّع (صوت, توقيتات_الكلمات)."""
    if not HEYGEN_API_KEY:
        raise FactoryError("HEYGEN_API_KEY غير مضبوط في متغيرات البيئة", 500)
    body = json.dumps({
        "text": text,
        "voice_id": voice_id or HEYGEN_VOICE_ID,
        "input_type": "text",
        "speed": speed,
        "language": "ar",
        "locale": "ar-EG",
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.heygen.com/v3/voices/speech",
        data=body,
        headers={"X-Api-Key": HEYGEN_API_KEY, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise FactoryError(f"فشل HeyGen TTS ({exc.code}): {exc.read().decode('utf-8', 'ignore')[:400]}", 502) from exc
    data = result.get("data") or {}
    audio_url = data.get("audio_url")
    word_timestamps = data.get("word_timestamps") or []
    if not audio_url:
        raise FactoryError(f"HeyGen لم يرجع رابط صوت: {json.dumps(result, ensure_ascii=False)[:400]}", 502)
    with urllib.request.urlopen(audio_url, timeout=60) as resp:
        audio_bytes = resp.read()
    return audio_bytes, word_timestamps


def slice_timestamps_by_scene(
    scene_narrations: list[str], word_timestamps: list[dict]
) -> list[dict]:
    """يقطّع مصفوفة word_timestamps الواحدة (بتاعة السرد الكامل المُجمّع) على
    المشاهد بالترتيب، بمطابقة عدد الكلمات (مش بحث نصي هش) لأن النص اللي أرسلناه
    لهاي جين هو بالظبط تجميع نصوص المشاهد بنفس الترتيب. يرجّع لكل مشهد:
    {"start": float, "end": float, "duration": float}.
    """
    tokens = [w for w in word_timestamps if w.get("word") not in ("<start>", "<end>")]
    cursor = 0
    slices: list[dict] = []
    prev_end = 0.0
    for narration in scene_narrations:
        n_words = len(narration.split())
        chunk = tokens[cursor: cursor + n_words]
        cursor += n_words
        if chunk:
            start = float(chunk[0]["start"])
            end = float(chunk[-1]["end"])
        else:
            start = prev_end
            end = prev_end + 2.0
        start = max(start, prev_end)
        end = max(end, start + 0.5)
        slices.append({"start": start, "end": end, "duration": end - start})
        prev_end = end
    return slices
