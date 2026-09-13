import ast
p = "/root/video-factory/narrated_render.py"
s = open(p, encoding="utf-8").read()

# 1) الرجوع لسرعة الصوت الأصلية وفجوة المشهد الأصلية
s = s.replace('os.environ.get("TTS_SPEED", "0.90")', 'os.environ.get("TTS_SPEED", "1.0")')
s = s.replace('os.environ.get("TTS_SPEED", "0.9")', 'os.environ.get("TTS_SPEED", "1.0")')
s = s.replace('os.environ.get("SCENE_GAP", "0.70")', 'os.environ.get("SCENE_GAP", "0.45")')

# 2) توقفات بين الكلمات في نص النطق فقط (لا يمسّ الترجمة) عبر وسم <break> من HeyGen
if "_spaced" not in s:
    anchor = "TTS_SPEED = float(os.environ.get(\"TTS_SPEED\", \"1.0\"))"
    inject = anchor + '''
WORD_GAP = float(os.environ.get("WORD_GAP", "0.16"))    # توقف بين كل كلمة (ثوانٍ)
COMMA_GAP = float(os.environ.get("COMMA_GAP", "0.30"))  # توقف بعد فاصلة
SENT_GAP = float(os.environ.get("SENT_GAP", "0.42"))    # توقف بعد نهاية جملة


def _spaced(text: str) -> str:
    """يُدرج توقفات <break> بين كلمات نص النطق ليقترب إيقاع المتن من المقدمة/الخاتمة."""
    if WORD_GAP <= 0:
        return text
    toks = text.split()
    out = []
    for i, w in enumerate(toks):
        out.append(w)
        if i == len(toks) - 1:
            break
        if w.endswith((".", "!", "\\u061f", "?", ":")):
            g = SENT_GAP
        elif w.endswith(("\\u060c", "\\u061b")):
            g = COMMA_GAP
        else:
            g = WORD_GAP
        out.append('<break time="%.2fs"/>' % g)
    return " ".join(out)'''
    assert anchor in s
    s = s.replace(anchor, inject, 1)

# 3) استخدم النص المُوقَّت عند توليد صوت المشهد
s = s.replace("_heygen_tts(narration, a_path, TTS_SPEED)", "_heygen_tts(_spaced(narration), a_path, TTS_SPEED)")

open(p, "w", encoding="utf-8").write(s)
ast.parse(s)
for probe in ['"TTS_SPEED", "1.0"', '"SCENE_GAP", "0.45"', "def _spaced", "_heygen_tts(_spaced(narration)"]:
    assert probe in s, probe
    print("ok", probe)
ast.parse(open("/root/video-factory/corrected_scenes.py").read())
print("ALL OK")
