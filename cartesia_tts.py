# -*- coding: utf-8 -*-
"""cartesia_tts.py — تركيب صوت المستخدم الحقيقي المستنسخ عبر Cartesia (Sonic).

واجهة مطابقة لـ narrated_render._eleven_tts:
    cartesia_tts(text, dest_path, speed=1.0) -> [[word, t0, t1], ...] | None

المتغيّرات:
    CARTESIA_API_KEY=...
    CARTESIA_VOICE_ID=7010376c-87f3-49de-8dea-21e1fa048445   (صوت المستخدم المستنسخ)
    CARTESIA_MODEL=sonic-3.6
"""
import json
import os
import re
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

API_KEY = os.environ.get("CARTESIA_API_KEY", "")
VOICE_ID = os.environ.get("CARTESIA_VOICE_ID", "7010376c-87f3-49de-8dea-21e1fa048445")
MODEL = os.environ.get("CARTESIA_MODEL", "sonic-3.6")
API_VERSION = os.environ.get("CARTESIA_VERSION", "2026-08-14")
_SPEED = float(os.environ.get("CARTESIA_SPEED", "1.0"))


def cartesia_tts(text: str, dest_path, speed: float = 1.0):
    if not API_KEY:
        raise RuntimeError("CARTESIA_API_KEY غير مضبوط")
    t = re.sub(r"[ \t]+", " ", str(text)).strip()
    body = json.dumps({
        "model_id": MODEL,
        "transcript": t,
        "voice": {"mode": "id", "id": VOICE_ID},
        "output_format": {"container": "wav", "encoding": "pcm_s16le", "sample_rate": 24000},
        "generation_config": {"speed": max(0.5, min(2.0, _SPEED / max(0.7, speed))), "volume": 1},
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.cartesia.ai/tts/bytes",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": API_KEY,
            "Cartesia-Version": API_VERSION,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"فشل Cartesia TTS ({exc.code}): {exc.read().decode('utf-8','ignore')[:400]}") from exc

    dest_path = Path(dest_path)
    tmp = dest_path.with_suffix(".raw.wav")
    tmp.write_bytes(raw)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp), "-af",
                     "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "44100", "-b:a", "160k",
                     str(dest_path)], check=True)
    tmp.unlink(missing_ok=True)
    if not dest_path.exists() or dest_path.stat().st_size < 1200:
        raise RuntimeError("cartesia_tts: صوت فارغ")
    return None  # لا توقيت كلمات من Cartesia — fallback التوزيع النسبي في narrated_render يغطّيه


if __name__ == "__main__":
    import sys
    t = sys.argv[1] if len(sys.argv) > 1 else "القرنية هي النافذة الشفافة قدام العين، وسمكها في المنتصف حوالي نص مليمتر."
    d = sys.argv[2] if len(sys.argv) > 2 else "/var/www/opticsgate.online/html/ttslab/cartesia_smoke.mp3"
    cartesia_tts(t, d)
    print("OK", d)
