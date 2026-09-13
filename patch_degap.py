import ast, re
p = "/root/video-factory/narrated_render.py"
s = open(p, encoding="utf-8").read()

# 1) استبدل _spaced بالكامل بمنطق جديد: تنظيف نص TTS + إزالة صمت ما بين الكلمات
i0 = s.index("def _spaced(text: str) -> str:")
i1 = s.index('\n', s.index('return " ".join(out)', i0)) + 1
old = s[i0:i1]

new = '''DEGAP = os.environ.get("DEGAP", "1") == "1"
DEGAP_KEEP = float(os.environ.get("DEGAP_KEEP", "0.08"))   # أقصى صمت مسموح داخل الجملة (ث)
DEGAP_MIN = float(os.environ.get("DEGAP_MIN", "0.16"))     # لا يُقصّ إلا الصمت الأطول من هذا


def _tts_text(text: str) -> str:
    """نصّ يُرسَل لـ HeyGen: يُبقى التشكيل (لضبط مخارج الحروف) ويحذف الفواصل
    والنقطتين حتى لا يُدرج المُحرّك وقفة طويلة عند كل عنصر في القائمة."""
    t = _ud.normalize("NFC", str(text))
    t = t.replace("\\u060c", " ").replace("\\u061b", " ").replace(":", " ")
    t = _INVIS.sub("", t).replace("\\u06be", "\\u0647")
    return re.sub(r"\\s+", " ", t).strip()


def _degap(path: Path) -> None:
    """يقصّ أي صمت داخلي (بين الكلمات) أطول من DEGAP_MIN إلى DEGAP_KEEP —
    إصلاح جذري لظاهرة (التوقف بعد كل كلمة) في صوت HeyGen العربي."""
    if not DEGAP:
        return
    tmp = path.with_suffix(".degap.mp3")
    af = ("silenceremove=stop_periods=-1:stop_duration=%.2f:"
          "stop_threshold=-30dB:stop_silence=%.2f" % (DEGAP_MIN, DEGAP_KEEP))
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(path), "-af", af, "-ar", "48000", str(tmp)],
                       capture_output=True, text=True, timeout=120)
    if r.returncode == 0 and tmp.exists() and tmp.stat().st_size > 2000:
        tmp.replace(path)
'''

assert old in s
s = s.replace(old, new, 1)

# 2) نداء التوليد: نظّف النص ثم أزل الصمت
s = s.replace(
    "        else:\n            _heygen_tts(_spaced(narration), a_path, TTS_SPEED)\n"
    "        a_dur = _dur(a_path)",
    "        else:\n            _heygen_tts(_tts_text(narration), a_path, TTS_SPEED)\n"
    "            _degap(a_path)\n"
    "        a_dur = _dur(a_path)")

# 3) نظافة: احذف تعريفات WORD_GAP/COMMA_GAP/SENT_GAP القديمة إن بقيت بلا استخدام (غير ضارّ)
open(p, "w", encoding="utf-8").write(s)
ast.parse(s)
for probe in ["def _tts_text", "def _degap", "_heygen_tts(_tts_text(narration)", "_degap(a_path)"]:
    assert probe in s, probe
    print("ok", probe)
print("DONE")
