import ast
p = "/root/video-factory/narrated_render.py"
s = open(p, encoding="utf-8").read()

# 1) ثوابت TTS
if "TTS_BACKEND" not in s:
    s = s.replace(
        'TTS_SPEED = float(os.environ.get("TTS_SPEED", "1.0"))',
        'TTS_SPEED = float(os.environ.get("TTS_SPEED", "1.0"))\n'
        'TTS_BACKEND = os.environ.get("TTS_BACKEND", "edge").lower()   # edge (مجاني) | heygen\n'
        'EDGE_VOICE = os.environ.get("EDGE_VOICE", "ar-EG-ShakirNeural")\n'
        'EDGE_PY = os.environ.get("EDGE_PY", str(ROOT / "qaenv" / "bin" / "python"))')

# 2) دالة edge-tts + موزّع _tts  (تُدرج قبل _heygen_tts)
if "def _edge_tts(" not in s:
    anchor = "def _heygen_tts(text: str, dest: Path, speed: float):"
    inject = '''def _edge_tts(text: str, dest: Path, speed: float):
    """Microsoft Edge Neural TTS — مجاني بلا مفتاح (عبر venv qaenv)."""
    rate = "%+d%%" % int(round((speed - 1.0) * 100))
    r = subprocess.run([EDGE_PY, "-m", "edge_tts", "--voice", EDGE_VOICE,
                        "--rate=" + rate, "--text", text, "--write-media", str(dest)],
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 1200:
        raise FactoryError("edge-tts فشل: " + (r.stderr or r.stdout)[:300], 502)


def _tts(text: str, dest: Path, speed: float):
    if TTS_BACKEND == "heygen":
        return _heygen_tts(_tts_text(text), dest, speed)
    return _edge_tts(_tts_text_edge(text), dest, speed)


def _tts_text_edge(text: str) -> str:
    """نصّ edge-tts: نبقي علامات الترقيم (اللازمة للنبرة)، ونزيل التشكيل الزائد
    الذي قد يربك المحرّك، ونحذف الحروف غير المرئية."""
    t = _ud.normalize("NFC", str(text))
    t = _INVIS.sub("", t).replace("\\u06be", "\\u0647")
    return re.sub(r"\\s+", " ", t).strip()


'''
    s = s.replace(anchor, inject + anchor, 1)

# 3) نداء التوليد في حلقة المشاهد
s = s.replace(
    "            _heygen_tts(_tts_text(narration), a_path, TTS_SPEED)\n"
    "            _degap(a_path)",
    "            _tts(narration, a_path, TTS_SPEED)\n"
    "            _degap(a_path)")

# 4) وسم المصدر في الناتج
s = s.replace('"tts_speed": TTS_SPEED,', '"tts_speed": TTS_SPEED,\n        "tts_backend": TTS_BACKEND,\n        "tts_voice": (EDGE_VOICE if TTS_BACKEND != "heygen" else HEYGEN_VOICE_ID),')

open(p, "w", encoding="utf-8").write(s)
ast.parse(s)
for probe in ["TTS_BACKEND", "def _edge_tts(", "def _tts(", "_tts(narration, a_path", "def _tts_text_edge("]:
    assert probe in s, probe
    print("ok", probe)
print("edge-tts wired")
