import ast
p = "/root/video-factory/narrated_render.py"
s = open(p, encoding="utf-8").read()

if "import urllib.error" not in s:
    s = s.replace("import urllib.request", "import urllib.request\nimport urllib.error", 1)

# 1) حمّل pipeline/.env عند الاستيراد (مفاتيح ElevenLabs/HeyGen)
if "_load_pipeline_env" not in s:
    anchor = 'TTS_SPEED = float(os.environ.get("TTS_SPEED", "1.0"))'
    inj = ('def _load_pipeline_env():\n'
           '    f = ROOT / "pipeline" / ".env"\n'
           '    if f.exists():\n'
           '        for ln in f.read_text().splitlines():\n'
           '            if "=" in ln and not ln.strip().startswith("#"):\n'
           '                k, v = ln.split("=", 1)\n'
           '                os.environ.setdefault(k.strip(), v.strip())\n'
           '\n\n'
           '_load_pipeline_env()\n\n')
    s = s.replace(anchor, inj + anchor, 1)

# 2) إعدادات ElevenLabs + تحديث تعليق backend
s = s.replace(
    'TTS_BACKEND = os.environ.get("TTS_BACKEND", "edge").lower()   # edge (مجاني) | heygen',
    'TTS_BACKEND = os.environ.get("TTS_BACKEND", "eleven").lower()  # eleven | edge | heygen\n'
    'ELEVEN_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")\n'
    'ELEVEN_VOICE_ID = os.environ.get("ELEVEN_VOICE_ID", "U14ZaLpYApoWmVvaKqQK")\n'
    'ELEVEN_MODEL = os.environ.get("ELEVEN_MODEL", "eleven_multilingual_v2")')

# 3) دالة ElevenLabs TTS
if "def _eleven_tts(" not in s:
    anchor2 = "def _tts(text: str, dest: Path, speed: float):"
    fn = '''def _eleven_tts(text: str, dest: Path, speed: float):
    """ElevenLabs — استنساخ صوت المدرّب، عربي/مصري."""
    if not ELEVEN_API_KEY:
        raise FactoryError("ELEVENLABS_API_KEY غير مضبوط", 500)
    vs = {"stability": 0.5, "similarity_boost": 0.82, "style": 0.12,
          "use_speaker_boost": True, "speed": max(0.7, min(1.2, speed))}
    body = json.dumps({"text": text, "model_id": ELEVEN_MODEL, "voice_settings": vs}).encode("utf-8")
    url = ("https://api.elevenlabs.io/v1/text-to-speech/%s?output_format=mp3_44100_128"
           % ELEVEN_VOICE_ID)
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"xi-api-key": ELEVEN_API_KEY,
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            dest.write_bytes(resp.read())
    except urllib.error.HTTPError as e:
        raise FactoryError("ElevenLabs فشل %s: %s" % (e.code, e.read()[:300]), 502)
    if not dest.exists() or dest.stat().st_size < 1200:
        raise FactoryError("ElevenLabs: صوت فارغ", 502)


'''
    s = s.replace(anchor2, fn + anchor2, 1)

# 4) موزّع _tts
s = s.replace(
    '''def _tts(text: str, dest: Path, speed: float):
    if TTS_BACKEND == "heygen":
        return _heygen_tts(_tts_text(text), dest, speed)
    return _edge_tts(_tts_text_edge(text), dest, speed)''',
    '''def _tts(text: str, dest: Path, speed: float):
    if TTS_BACKEND == "heygen":
        return _heygen_tts(_tts_text(text), dest, speed)
    if TTS_BACKEND == "edge":
        return _edge_tts(_tts_text_edge(text), dest, speed)
    return _eleven_tts(_tts_text_edge(text), dest, speed)''')

# 5) وسم الصوت في الناتج
s = s.replace(
    '"tts_voice": (EDGE_VOICE if TTS_BACKEND != "heygen" else HEYGEN_VOICE_ID),',
    '"tts_voice": {"heygen": HEYGEN_VOICE_ID, "edge": EDGE_VOICE}.get(TTS_BACKEND, ELEVEN_VOICE_ID),')

open(p, "w", encoding="utf-8").write(s)
ast.parse(s)
for probe in ["_load_pipeline_env()", 'TTS_BACKEND", "eleven"', "def _eleven_tts(", "_eleven_tts(_tts_text_edge"]:
    assert probe in s, probe
    print("ok", probe)
print("ElevenLabs backend wired (default)")
