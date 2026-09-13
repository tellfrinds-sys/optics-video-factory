import ast, re
p = "/root/video-factory/narrated_render.py"
s = open(p, encoding="utf-8").read()

# ============ 1) ElevenLabs with-timestamps ============
old_el = '''def _eleven_tts(text: str, dest: Path, speed: float):
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
        raise FactoryError("ElevenLabs: صوت فارغ", 502)'''

new_el = '''def _eleven_tts(text: str, dest: Path, speed: float):
    """ElevenLabs مع طوابع زمنية للحروف — يعيد قائمة (كلمة, بداية, نهاية) أو None."""
    if not ELEVEN_API_KEY:
        raise FactoryError("ELEVENLABS_API_KEY غير مضبوط", 500)
    vs = {"stability": 0.5, "similarity_boost": 0.82, "style": 0.12,
          "use_speaker_boost": True, "speed": max(0.7, min(1.2, speed))}
    body = json.dumps({"text": text, "model_id": ELEVEN_MODEL, "voice_settings": vs}).encode("utf-8")
    url = ("https://api.elevenlabs.io/v1/text-to-speech/%s/with-timestamps?output_format=mp3_44100_128"
           % ELEVEN_VOICE_ID)
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"xi-api-key": ELEVEN_API_KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise FactoryError("ElevenLabs فشل %s: %s" % (e.code, e.read()[:300]), 502)
    import base64 as _b64
    dest.write_bytes(_b64.b64decode(data["audio_base64"]))
    if not dest.exists() or dest.stat().st_size < 1200:
        raise FactoryError("ElevenLabs: صوت فارغ", 502)
    al = data.get("alignment") or {}
    chars = al.get("characters") or []
    st = al.get("character_start_times_seconds") or []
    en = al.get("character_end_times_seconds") or []
    if not (chars and len(chars) == len(st) == len(en)):
        return None
    words, cur, w0 = [], "", None
    for c, a, b in zip(chars, st, en):
        if c.isspace():
            if cur:
                words.append([cur, w0, prev_b])
                cur, w0 = "", None
            continue
        if w0 is None:
            w0 = a
        cur += c
        prev_b = b
    if cur:
        words.append([cur, w0, prev_b])
    return words'''

assert old_el in s
s = s.replace(old_el, new_el, 1)

# ============ 2) _degap يعيد segs ============
s = s.replace(
    "def _degap(path: Path) -> None:",
    "def _degap(path: Path):")
s = s.replace(
    '''    if not DEGAP:
        return
    thr, mind, keep, xf = -34.0, DEGAP_MIN, DEGAP_KEEP, 0.012''',
    '''    if not DEGAP:
        return None
    thr, mind, keep, xf = -34.0, DEGAP_MIN, DEGAP_KEEP, 0.012''')
s = s.replace(
    '''    starts = [float(x) for x in re.findall(r"silence_start: (-?[\\d.]+)", det)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\\d.]+)", det)]
    if not starts or len(ends) < len(starts):
        return
    total = _dur(path)''',
    '''    starts = [float(x) for x in re.findall(r"silence_start: (-?[\\d.]+)", det)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\\d.]+)", det)]
    if not starts or len(ends) < len(starts):
        return None
    total = _dur(path)''')
s = s.replace(
    '''    segs = [(a, b) for a, b in segs if b - a > 0.03]
    if len(segs) < 2:
        return''',
    '''    segs = [(a, b) for a, b in segs if b - a > 0.03]
    if len(segs) < 2:
        return None''')
# في نهاية _degap: أعِد segs
s = s.replace(
    '''        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(tmp),
                        "-c:a", "libmp3lame", "-q:a", "2", "-ar", "48000", str(final)],
                       capture_output=True, text=True, timeout=120)
        tmp.unlink(missing_ok=True)''',
    '''        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(tmp),
                        "-c:a", "libmp3lame", "-q:a", "2", "-ar", "48000", str(final)],
                       capture_output=True, text=True, timeout=120)
        tmp.unlink(missing_ok=True)
        return segs
    return None''')

# ============ 3) أدوات إعادة التوقيت + كيوهات مضبوطة ============
anchor3 = "def _ass_escape(s: str) -> str:"
tools = '''def _remap_times(words, segs):
    """يحوّل توقيتات الكلمات من الصوت الأصلي إلى الصوت بعد قصّ الصمت (segs = مقاطع محتفَظ بها)."""
    if not segs or not words:
        return words
    bounds, acc = [], 0.0
    for (a, b) in segs:
        bounds.append((a, b, acc))
        acc += (b - a)
    def m(t):
        for (a, b, base) in bounds:
            if t < a:
                return base
            if t <= b:
                return base + (t - a)
        a, b, base = bounds[-1]
        return base + (b - a)
    return [[w, m(t0), m(t1)] for (w, t0, t1) in words]


def _timed_cues(words, max_words=8, min_dur=0.7):
    """يجمع الكلمات في أسطر ترجمة؛ بداية/نهاية كل سطر = التوقيت الفعلي للنطق."""
    cues, i, n = [], 0, len(words)
    while i < n:
        grp = words[i:i + max_words]
        # لا تكسر بعد حرف عطف/أداة قصيرة في نهاية السطر
        while len(grp) > 3 and _clean(grp[-1][0]).strip(".،!؟:") in ("و", "أو", "او", "الـ", "في", "من", "على"):
            grp = grp[:-1]
        txt = " ".join(_ass_escape(_clean(w)) for (w, _a, _b) in grp).strip()
        st = grp[0][1]
        en = max(grp[-1][2], st + min_dur)
        cues.append((round(st, 2), round(en, 2), txt))
        i += len(grp)
    return cues


'''
s = s.replace(anchor3, tools + anchor3, 1)

# ============ 4) لا تُجرّد اللاتيني من الترجمة ============
# _highlight يستدعي _clean الذي يُبقي اللاتيني بالفعل — لا تغيير مطلوب.

# ============ 5) حلقة المشاهد: استخدم التوقيت الفعلي عند توفره ============
old_loop = '''        else:
            _tts(narration, a_path, TTS_SPEED)
            _degap(a_path)
        a_dur = _dur(a_path)'''
new_loop = '''        word_times = None
        if not (keep_audio and a_path.exists()) and not raw.get("audio_url"):
            word_times = _tts(narration, a_path, TTS_SPEED)
            segs = _degap(a_path)
            if word_times and segs:
                word_times = _remap_times(word_times, segs)
        a_dur = _dur(a_path)'''
assert old_loop in s
s = s.replace(old_loop, new_loop, 1)

old_sub = '''        # 4) ترجمة المشهد: عبارات متتابعة (بلا تداخل) موزّعة على مدة صوت المشهد
        phr = _phrases(caption)
        total_chars = sum(len(p) for p in phr) or 1
        cur = t_cursor
        end_limit = t_cursor + a_dur
        for j, p in enumerate(phr):
            dur = (len(p) / total_chars) * a_dur
            st = cur
            en = min(cur + dur, end_limit) if j < len(phr) - 1 else end_limit
            en = max(en, st + 0.7)
            sub_events.append((round(st, 2), round(en, 2), p))
            cur = en'''
new_sub = '''        # 4) ترجمة المشهد — توقيت فعلي إن توفّر، وإلا توزيع نسبي
        if word_times:
            for (st, en, tx) in _timed_cues(word_times):
                st2 = t_cursor + st
                en2 = min(t_cursor + en, t_cursor + a_dur)
                sub_events.append((round(st2, 2), round(max(en2, st2 + 0.7), 2), tx))
        else:
            phr = _phrases(caption)
            total_chars = sum(len(p) for p in phr) or 1
            cur = t_cursor
            end_limit = t_cursor + a_dur
            for j, p in enumerate(phr):
                dur = (len(p) / total_chars) * a_dur
                st = cur
                en = min(cur + dur, end_limit) if j < len(phr) - 1 else end_limit
                en = max(en, st + 0.7)
                sub_events.append((round(st, 2), round(en, 2), p))
                cur = en'''
assert old_sub in s
s = s.replace(old_sub, new_sub, 1)

open(p, "w", encoding="utf-8").write(s)
ast.parse(s)
for probe in ["with-timestamps", "def _remap_times(", "def _timed_cues(", "word_times = _tts(narration", "_timed_cues(word_times)"]:
    assert probe in s, probe
    print("ok", probe)
print("synced captions wired")
