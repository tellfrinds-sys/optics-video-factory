# -*- coding: utf-8 -*-
"""google_tts.py — تركيب صوت عبر Google Cloud Text-to-Speech (ar-XA، Chirp3-HD/Neural2).

واجهة مطابقة لـ narrated_render._eleven_tts:
    google_tts(text, dest_path, speed=1.0) -> [[word, t0, t1], ...] | None

المتغيّرات:
    GOOGLE_TTS_API_KEY=...           (مفتاح API من Google Cloud Console)
    GOOGLE_TTS_VOICE=ar-XA-Chirp3-HD-Charon   (اختياري)
"""
import base64
import json
import os
import re
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

API_KEY = os.environ.get("GOOGLE_TTS_API_KEY", "")
VOICE = os.environ.get("GOOGLE_TTS_VOICE", "ar-XA-Chirp3-HD-Charon")
_SPEAKING_RATE = float(os.environ.get("GOOGLE_TTS_RATE", "0.92"))  # أبطأ شوية من الافتراضي


def google_tts(text: str, dest_path, speed: float = 1.0):
    if not API_KEY:
        raise RuntimeError("GOOGLE_TTS_API_KEY غير مضبوط")
    t = re.sub(r"\s+", " ", str(text)).strip()
    body = json.dumps({
        "input": {"text": t},
        "voice": {"languageCode": "ar-XA", "name": VOICE},
        "audioConfig": {
            "audioEncoding": "MP3",
            "speakingRate": max(0.5, min(2.0, _SPEAKING_RATE / max(0.7, speed))),
            "pitch": 0.0,
        },
    }).encode("utf-8")
    url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={API_KEY}"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"فشل Google TTS ({exc.code}): {exc.read().decode('utf-8','ignore')[:400]}") from exc
    audio_b64 = result.get("audioContent")
    if not audio_b64:
        raise RuntimeError(f"Google TTS لم يرجّع صوت: {json.dumps(result, ensure_ascii=False)[:300]}")
    raw = base64.b64decode(audio_b64)
    dest_path = Path(dest_path)
    tmp = dest_path.with_suffix(".raw.mp3")
    tmp.write_bytes(raw)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp), "-af",
                     "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "44100", "-b:a", "160k",
                     str(dest_path)], check=True)
    tmp.unlink(missing_ok=True)
    if not dest_path.exists() or dest_path.stat().st_size < 1200:
        raise RuntimeError("google_tts: صوت فارغ")
    return None  # لا توقيت كلمات — يُحسب لاحقًا بـ Whisper لو احتجنا


if __name__ == "__main__":
    import sys
    t = sys.argv[1] if len(sys.argv) > 1 else "القرنية هي النافذة الشفافة قدام العين، وسمكها في المنتصف حوالي نص مليمتر."
    d = sys.argv[2] if len(sys.argv) > 2 else "/var/www/opticsgate.online/html/ttslab/google_test.mp3"
    google_tts(t, d)
    print("OK", d)
