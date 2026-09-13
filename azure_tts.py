# -*- coding: utf-8 -*-
"""azure_tts.py — تركيب صوت مصري احترافي عبر Azure AI Speech (ar-EG) مع قاموس نطق.

واجهة مطابقة لـ narrated_render._eleven_tts:
    azure_tts(text, dest_path, speed) -> [[word, t0, t1], ...] أو None

المتغيّرات المطلوبة (pipeline/.env):
    AZURE_SPEECH_KEY=...
    AZURE_SPEECH_REGION=eastus            (أو المنطقة اللي أنشأت فيها المورد)
    AZURE_VOICE=ar-EG-SalmaNeural         (اختياري — Salma أنثى / Shakir ذكر)

قاموس النطق: pipeline/pron_lexicon.json  = { "الكلمة": "IPA", ... }
يُطبَّق كوسم <phoneme> داخل SSML على السرد قبل التركيب. الترجمة المحروقة لا تتأثر.
"""
import html
import json
import os
import re
import unicodedata as _ud
from pathlib import Path

ROOT = Path("/root/video-factory")
LEX_FILE = ROOT / "pipeline" / "pron_lexicon.json"

_VOICE = os.environ.get("AZURE_VOICE", "ar-EG-SalmaNeural")
_INVIS = re.compile(r"[​-‏‪-‮⁦-⁩﻿]")
# نزيل التشكيل الجزئي من الكاتب — Azure ar-EG عنده تنبؤ تشكيل قوي، والقاموس يغطّي الشاذّ
_TASHKEEL = re.compile("[ؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۨ-ۭـ]")


def _load_lex():
    try:
        return json.loads(LEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _clean(text: str) -> str:
    t = _ud.normalize("NFC", str(text))
    t = _INVIS.sub("", t).replace("ھ", "ه")
    t = _TASHKEEL.sub("", t)
    return re.sub(r"\s+", " ", t).strip()


# سوابق عربية منفصلة صوتيًا: تُضاف بادئتها للـ IPA تلقائيًا
_PFX = [("وال", "wel"), ("فال", "fel"), ("بال", "bel"), ("كال", "kel"), ("لل", "lel"),
        ("ال", "el"), ("و", "we"), ("ف", "fe"), ("ب", "be"), ("ك", "ke"), ("ل", "le")]


def _ssml(text: str, speed: float) -> str:
    lex = {k: v for k, v in _load_lex().items() if v and not k.startswith("_")}
    rate = "%+d%%" % int(round((speed - 1.0) * 100))
    plain = _clean(text)
    plain = re.sub(r"([.!؟])\s+", r"\1|BRK|", plain)

    # ابنِ خريطة موسّعة: الكلمة + صيغها بالسوابق -> IPA
    forms = {}
    for w, ipa in lex.items():
        forms.setdefault(w, ipa)
        bare = w[2:] if w.startswith("ال") else w      # جذر بلا "ال"
        base_ipa = ipa[2:] if ipa.startswith("el") else ipa
        for pfx, pph in _PFX:
            forms.setdefault(pfx + bare, pph + base_ipa)

    def _wrap(m):
        w = m.group(0)
        return '<phoneme alphabet="ipa" ph="%s">%s</phoneme>' % (
            html.escape(forms[w], quote=True), w)

    # الأطول أولاً
    keys = sorted(forms, key=len, reverse=True)
    esc = html.escape(plain, quote=False)
    for w in keys:
        esc = re.sub(r"(?<![ء-يٱ])" + re.escape(w) + r"(?![ء-يٱ])", _wrap, esc)

    esc = esc.replace("|BRK|", '<break time="320ms"/> ')

    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        'xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="ar-EG">'
        '<voice name="%s">'
        '<mstts:express-as style="calm" styledegree="1">'
        '<prosody rate="%s">%s</prosody>'
        '</mstts:express-as>'
        '</voice></speak>'
    ) % (_VOICE, rate, esc)


def azure_tts(text: str, dest_path, speed: float = 1.0):
    import azure.cognitiveservices.speech as speechsdk

    key = os.environ.get("AZURE_SPEECH_KEY")
    region = os.environ.get("AZURE_SPEECH_REGION", "eastus")
    if not key:
        raise RuntimeError("AZURE_SPEECH_KEY غير مضبوط")

    cfg = speechsdk.SpeechConfig(subscription=key, region=region)
    cfg.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Audio24Khz96KBitRateMonoMp3)
    cfg.set_property(speechsdk.PropertyId.SpeechServiceResponse_RequestWordBoundary, "true")

    dest_path = Path(dest_path)
    audio_cfg = speechsdk.audio.AudioOutputConfig(filename=str(dest_path))
    synth = speechsdk.SpeechSynthesizer(speech_config=cfg, audio_config=audio_cfg)

    words = []

    def _on_wb(evt):
        try:
            if evt.boundary_type == speechsdk.SpeechSynthesisBoundaryType.Word:
                t0 = evt.audio_offset / 1e7
                dur = evt.duration.total_seconds()
                words.append([evt.text, round(t0, 3), round(t0 + dur, 3)])
        except Exception:
            pass

    synth.synthesis_word_boundary.connect(_on_wb)

    ssml = _ssml(text, speed)
    result = synth.speak_ssml_async(ssml).get()

    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        detail = getattr(result, "cancellation_details", None)
        raise RuntimeError("Azure TTS فشل: %s | %s" % (
            result.reason, getattr(detail, "error_details", "")))

    if not dest_path.exists() or dest_path.stat().st_size < 1200:
        raise RuntimeError("Azure TTS: ملف صوت فارغ")

    return words or None


if __name__ == "__main__":
    import sys
    txt = sys.argv[1] if len(sys.argv) > 1 else "ده اختبار لصوت أكاديمية بوابة البصريات. القرنية نسيج شفاف، وسُمكها نص مليمتر."
    w = azure_tts(txt, "/tmp/azure_test.mp3", 1.0)
    print("OK — %d كلمة، %s" % (len(w or []), "/tmp/azure_test.mp3"))
    print(json.dumps((w or [])[:8], ensure_ascii=False))
