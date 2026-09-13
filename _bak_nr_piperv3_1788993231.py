"""
narrated_render.py — محرّك بناء فيديو الدرس السردي (نسخة محسّنة).

يعالج:
- تزامن تام: مدة كل مشهد = مدة صوته الفعلي (لا اقتطاع في النهاية).
- صوت أبطأ وأوضح (TTS_SPEED، افتراضي 1.0 بدل 1.17).
- رسوم تشريحية متجهية (eye_diagrams) بدل صور الذكاء الاصطناعي.
- مؤثّر Ken Burns خفيف على كل مشهد.
- ترجمة (كابشن) ديناميكية عبارة-بعبارة، محروقة، مع تظليل المصطلحات.
- مقدمة/خاتمة ثابتة معتمدة (بوكمارك).
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

import eye_scene2

ROOT = Path(os.environ.get("OPTICSGATE_FACTORY_ROOT", Path(__file__).resolve().parent)).resolve()
OUTPUTS_DIR = ROOT / "outputs"
ASSETS = ROOT / "assets"

def _load_pipeline_env():
    f = ROOT / "pipeline" / ".env"
    if f.exists():
        for ln in f.read_text().splitlines():
            if "=" in ln and not ln.strip().startswith("#"):
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_pipeline_env()

TTS_SPEED = float(os.environ.get("TTS_SPEED", "1.0"))
TTS_BACKEND = os.environ.get("TTS_BACKEND", "eleven").lower()  # eleven | edge | heygen
ELEVEN_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVEN_VOICE_ID = os.environ.get("ELEVEN_VOICE_ID", "U14ZaLpYApoWmVvaKqQK")
ELEVEN_MODEL = os.environ.get("ELEVEN_MODEL", "eleven_multilingual_v2")
EDGE_VOICE = os.environ.get("EDGE_VOICE", "ar-EG-ShakirNeural")
EDGE_PY = os.environ.get("EDGE_PY", str(ROOT / "qaenv" / "bin" / "python"))
WORD_GAP = float(os.environ.get("WORD_GAP", "0"))    # توقف بين كل كلمة (ثوانٍ)
COMMA_GAP = float(os.environ.get("COMMA_GAP", "0.38"))  # توقف بعد فاصلة
SENT_GAP = float(os.environ.get("SENT_GAP", "0.60"))    # توقف بعد نهاية جملة


DEGAP = os.environ.get("DEGAP", "1") == "1"
DEGAP_KEEP = float(os.environ.get("DEGAP_KEEP", "0.17"))   # أقصى صمت مسموح داخل الجملة (ث)
DEGAP_MIN = float(os.environ.get("DEGAP_MIN", "0.30"))     # لا يُقصّ إلا الصمت الأطول من هذا
DEGAP_LONG = float(os.environ.get("DEGAP_LONG", "0.40"))   # ما يُبقى من وقفة نهاية الجملة
DEGAP_LONG_MIN = float(os.environ.get("DEGAP_LONG_MIN", "0.72"))  # فوقها = وقفة جملة مقصودة


def _tts_text(text: str) -> str:
    """نصّ يُرسَل لـ HeyGen: يُبقى التشكيل (لضبط مخارج الحروف) ويحذف الفواصل
    والنقطتين حتى لا يُدرج المُحرّك وقفة طويلة عند كل عنصر في القائمة."""
    t = _ud.normalize("NFC", str(text))
    t = t.replace("\u060c", " ").replace("\u061b", " ").replace(":", " ")
    t = _INVIS.sub("", t).replace("\u06be", "\u0647")
    # وقفة تنفّس بعد كل نهاية جملة
    t = re.sub(r"([.!\u061f])\s+", r'\1 <break time="0.35s"/> ', t)
    return re.sub(r"\s+", " ", t).strip()


def _degap(path: Path):
    """يقصّ الصمت الداخلي في صوت HeyGen (وقفاته ~0.6ث بين العبارات) بلا تقطيع:
    كشف فترات الصمت -> اقتطاع مقاطع الكلام مع إبقاء DEGAP_KEEP ثانية من كل فجوة
    -> وصلها بـ acrossfade قصير (12ms) يمنع النقر."""
    if not DEGAP:
        return None
    thr, mind, keep, xf = -34.0, DEGAP_MIN, DEGAP_KEEP, 0.012
    det = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af",
                          "silencedetect=n=%.0fdB:d=%.2f" % (thr, mind), "-f", "null", "-"],
                         capture_output=True, text=True, timeout=120).stderr
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", det)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", det)]
    if not starts or len(ends) < len(starts):
        return None
    total = _dur(path)
    segs, cur = [], 0.0
    for a, b in zip(starts, ends):
        k = DEGAP_LONG if (b - a) > DEGAP_LONG_MIN else keep
        seg_end = max(cur, a + k / 2)
        segs.append((cur, seg_end))
        cur = max(seg_end, b - k / 2)
    segs.append((cur, total))
    segs = [(a, b) for a, b in segs if b - a > 0.03]
    if len(segs) < 2:
        return None
    tmp = path.with_suffix(".degap.m4a")
    inp, fc = [], []
    for i, (a, b) in enumerate(segs):
        inp += ["-i", str(path)]
        fc.append("[%d:a]atrim=start=%.3f:end=%.3f,asetpts=PTS-STARTPTS,aresample=48000[s%d]" % (i, a, b, i))
    label = "s0"
    for i in range(1, len(segs)):
        fc.append("[%s][s%d]acrossfade=d=%.3f:c1=tri:c2=tri[x%d]" % (label, i, xf, i))
        label = "x%d" % i
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inp,
                        "-filter_complex", ";".join(fc), "-map", "[%s]" % label,
                        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(tmp)],
                       capture_output=True, text=True, timeout=180)
    if r.returncode == 0 and tmp.exists() and tmp.stat().st_size > 2000:
        final = path.with_suffix(".mp3")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(tmp),
                        "-c:a", "libmp3lame", "-q:a", "2", "-ar", "48000", str(final)],
                       capture_output=True, text=True, timeout=120)
        tmp.unlink(missing_ok=True)
        return segs
    return None
SCENE_GAP = float(os.environ.get("SCENE_GAP", "0.45"))          # فجوة صمت بين المشاهد
BOOKEND_SET = os.environ.get("BOOKEND_SET", "V5").upper().lstrip("V")


def _bookend_paths(which=None):
    v = str(which or BOOKEND_SET).upper().lstrip("V") or "5"
    a = ASSETS / "avatar"
    intro = a / f"_OPTICSGATE_INTRO_MASTER_V{v}.mp4"
    outro = a / f"OPTICSGATE_END_MASTER_V{v}.mp4"
    if not intro.exists():
        intro = a / "_OPTICSGATE_INTRO_MASTER_V5.mp4"
        outro = a / "OPTICSGATE_END_MASTER_V5.mp4"
    return str(intro), str(outro)


INTRO_PATH = os.environ.get("INTRO_MASTER", str(ASSETS / "avatar" / "_OPTICSGATE_INTRO_MASTER_V5.mp4"))
OUTRO_PATH = os.environ.get("OUTRO_MASTER", str(ASSETS / "avatar" / "OPTICSGATE_END_MASTER_V5.mp4"))
USE_BOOKENDS = os.environ.get("USE_BOOKENDS", "1") == "1"
LOUDNORM = os.environ.get("LOUDNORM", "I=-16:TP=-1.5:LRA=9")

HEYGEN_API_KEY = os.environ.get("HEYGEN_API_KEY", "")
HEYGEN_VOICE_ID = os.environ.get("HEYGEN_VOICE_ID", "e94bf61de2584daf96a6d82aa951caf5")

# Noto Naskh Arabic: تغطية كاملة وترابط سليم للأحرف في libass (على عكس Noto Sans Arabic)
SUB_FONT = os.environ.get("SUB_FONT", "Noto Naskh Arabic")
FONTS_DIR = "/usr/share/fonts/truetype/noto"


class FactoryError(RuntimeError):
    def __init__(self, message, status=500):
        super().__init__(message)
        self.status = status


# ---------------- أدوات ----------------
def _run(cmd, timeout=600):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise FactoryError("ffmpeg فشل: " + " ".join(str(c) for c in cmd[:6]) + " ... :: " + r.stderr[-700:], 500)
    return r


def _dur(path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True, timeout=60)
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise FactoryError(f"تعذّر قياس مدة {path}: {r.stderr[:200]}", 500)


def _download(url, dest, timeout=90):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        Path(dest).write_bytes(resp.read())


def _edge_tts(text: str, dest: Path, speed: float):
    """Microsoft Edge Neural TTS — مجاني بلا مفتاح (عبر venv qaenv)."""
    rate = "%+d%%" % int(round((speed - 1.0) * 100))
    r = subprocess.run([EDGE_PY, "-m", "edge_tts", "--voice", EDGE_VOICE,
                        "--rate=" + rate, "--text", text, "--write-media", str(dest)],
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 1200:
        raise FactoryError("edge-tts فشل: " + (r.stderr or r.stdout)[:300], 502)


def _eleven_tts(text: str, dest: Path, speed: float):
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
    return words


def _tts(text: str, dest: Path, speed: float):
    if TTS_BACKEND == "azure":
        import azure_tts
        return azure_tts.azure_tts(text, dest, speed)
    if TTS_BACKEND == "heygen":
        return _heygen_tts(_tts_text(text), dest, speed)
    if TTS_BACKEND == "edge":
        return _edge_tts(_tts_text_edge(text), dest, speed)
    return _eleven_tts(_tts_text_edge(text), dest, speed)



# قاموس تصحيح النطق لـ ElevenLabs — يُطبَّق على نصّ TTS فقط (الترجمة تُبنى من نفس النص لكن
# هذه التهجئات مقبولة/صحيحة بالعامية المصرية المكتوبة).
_PRON_FIXES = [
    # القرنية مصطلح علمي: القاف تُنطق قافًا لا همزة -> سكون صريح على القاف
    ("القرنية", "القَرنِيّة"),
    ("قرنية", "قَرنِيّة"),
    # سُمك (سماكة) بضم السين لا سَمك
    ("السمك", "السُمك"),
    ("سمك ", "سُمك "),
    # تعطيش الجيم في الكلمات العلمية/الأجنبية (چ = j الإنجليزية)
    ("الأكسجين", "الأكسِچين"),
    ("أكسجين", "أكسِچين"),
    ("فسيولوجيا", "فِسيولوچيا"),
    ("فسيولوجية", "فِسيولوچية"),
    ("بيولوجيا", "بايولوچيا"),
]


def _apply_pron(t: str) -> str:
    for a, b in _PRON_FIXES:
        t = t.replace(a, b)
    return t

def _tts_text_edge(text: str) -> str:
    """نصّ edge-tts: نبقي علامات الترقيم (اللازمة للنبرة)، ونزيل التشكيل الزائد
    الذي قد يربك المحرّك، ونحذف الحروف غير المرئية."""
    t = _ud.normalize("NFC", str(text))
    t = _INVIS.sub("", t).replace("\u06be", "\u0647")
    t = _apply_pron(t)
    return re.sub(r"\s+", " ", t).strip()


def _heygen_tts(text: str, dest: Path, speed: float):
    if not HEYGEN_API_KEY:
        raise FactoryError("HEYGEN_API_KEY غير مضبوط", 500)
    body = json.dumps({
        "text": text, "voice_id": HEYGEN_VOICE_ID, "input_type": "text",
        "speed": speed, "language": "ar", "locale": "ar-EG",
    }).encode("utf-8")
    req = urllib.request.Request("https://api.heygen.com/v3/voices/speech", data=body,
                                 headers={"X-Api-Key": HEYGEN_API_KEY, "Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    audio_url = (data.get("data") or {}).get("audio_url")
    if not audio_url:
        raise FactoryError(f"HeyGen بلا صوت: {json.dumps(data, ensure_ascii=False)[:300]}", 502)
    _download(audio_url, dest, timeout=90)


# ---------------- ترجمة (كابشن) ----------------
# مصطلحات جوهرية فقط: يُلوَّن السطر الذي يقدّم بنية تشريحية للمرة الأولى
_KEYWORDS = [
    "الصلبة", "القرنية", "المشيمية", "الجسم الهدبي", "القزحية",
    "الشبكية", "العصيات", "المخاريط", "العصب البصري",
]
_HL_COLOR = r"{\c&HDCD67C&}"   # HL بصيغة ASS (BGR): teal فاتح تقريبًا
_DEF_COLOR = r"{\c&HFFFFFF&}"
_RLE = "‫"
_PDF = "‬"

_SENT_SPLIT = re.compile(r"(?<=[\.\!\؟\?؛])\s+|،\s+|:\s+")
_TASHKEEL = re.compile("[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06DC\u06DF-\u06E8\u06EA-\u06ED\u0640]")
_INVIS = re.compile(r"[​-‏‪-‮⁦-⁩­]")

import unicodedata as _ud


def _clean(text: str) -> str:
    t = _ud.normalize("NFC", str(text))
    t = _TASHKEEL.sub("", t)
    t = _INVIS.sub("", t)
    t = t.replace("ھ", "ه")
    return t.strip()


def _phrases(text: str, max_words=9, min_words=4):
    # الفواصل تُدمج في مجرى الكلمات (لا تُقسّم سطر ترجمة مستقلًا)
    base = re.sub(r"\s+", " ", _clean(text).replace("\u060c", " ")).strip()
    out = []
    for chunk in re.split(r"(?<=[\.\!\u061f\?\u061b:])\s+", base):
        chunk = chunk.strip(" .!\u061f?\u061b:\n")
        if not chunk:
            continue
        words = chunk.split()
        parts = [words[i:i + max_words] for i in range(0, len(words), max_words)]
        if len(parts) > 1 and len(parts[-1]) < min_words:
            parts[-2] += parts[-1]
            parts.pop()
        out.extend(" ".join(p) for p in parts)
    # تمريرة نهائية: ادمج أي سطر قصير جدًا في جاره
    merged = []
    for c in out:
        if merged and len(c.split()) < min_words:
            merged[-1] = merged[-1] + " " + c
        else:
            merged.append(c)
    if len(merged) > 1 and len(merged[0].split()) < min_words:
        merged[1] = merged[0] + " " + merged[1]
        merged.pop(0)
    return merged or [_clean(text)]


def _remap_times(words, segs):
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


def _ass_escape(s: str) -> str:
    return s.replace("\\", "").replace("{", "(").replace("}", ")")


def _highlight(s: str, seen: set | None = None) -> str:
    # ترجمة بيضاء نظيفة؛ الإبراز البصري للمصطلحات يتم عبر الرسم التشريحي نفسه.
    return _ass_escape(_clean(s))


def _ass_time(t: float) -> str:
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _build_ass(events: list[tuple[float, float, str]], path: Path, offset: float = 0.0):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap, {SUB_FONT}, 84, &H00FFFFFF, &H00251A12, &H3C160E22, 1, 3, 14, 0, 2, 150, 150, 165, 1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [head]
    seen: set = set()
    for (st, en, txt) in events:
        st += offset; en += offset
        lines.append(f"Dialogue: 0,{_ass_time(st)},{_ass_time(en)},Cap,,0,0,0,,{_highlight(txt, seen)}")
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------- المحرّك ----------------
def render_narrated(payload: dict[str, Any]) -> dict[str, Any]:
    video_uid = payload.get("video_uid")
    scenes_in = payload.get("scenes") or []
    if not video_uid or not scenes_in:
        raise FactoryError("video_uid و scenes مطلوبين", 400)
    if not shutil.which("ffmpeg"):
        raise FactoryError("FFmpeg غير مثبت", 501)

    out_dir = OUTPUTS_DIR / f"narrated_{video_uid}"
    out_dir.mkdir(parents=True, exist_ok=True)
    intro_path, outro_path = _bookend_paths(payload.get("bookend_set"))
    keep_audio = os.environ.get("REUSE_AUDIO") == "1"
    for f in out_dir.glob("*"):
        if keep_audio and f.suffix == ".mp3":
            continue
        try:
            f.unlink()
        except OSError:
            pass

    clip_paths: list[Path] = []
    audio_parts: list[Path] = []
    sub_events: list[tuple[float, float, str]] = []
    t_cursor = 0.0
    W, H = 1920, 1080

    for idx, raw in enumerate(scenes_in, 1):
        sc = int(raw.get("scene_no") or raw.get("scene no") or idx)
        narration = str(raw.get("narration") or "").strip()
        on_screen = str(raw.get("on_screen_text") or raw.get("on screen text") or "")
        caption = str(raw.get("caption") or narration)
        src = raw.get("source_codes") or raw.get("source codes") or ""

        # 1) صوت المشهد
        a_path = out_dir / f"S{sc:02d}.mp3"
        if keep_audio and a_path.exists() and a_path.stat().st_size > 2000:
            pass
        elif raw.get("audio_url"):
            _download(raw["audio_url"], a_path)
        word_times = None
        if not (keep_audio and a_path.exists()) and not raw.get("audio_url"):
            word_times = _tts(narration, a_path, TTS_SPEED)
            segs = _degap(a_path)
            if word_times and segs:
                word_times = _remap_times(word_times, segs)
        a_dur = _dur(a_path)
        audio_parts.append(a_path)
        print(f"[scene {sc}] audio {a_dur:.1f}s", flush=True)

        # 2) الرسم
        frame = out_dir / f"S{sc:02d}.png"
        eye_scene2.render_scene(raw, size=(W, H)).save(frame)

        # 3) مقطع الفيديو: صورة ثابتة بمدة الصوت + الفجوة، مع fade خفيف عند الأطراف
        seg_dur = a_dur + SCENE_GAP
        fd = 0.4
        vf = (f"scale={W}:{H},setsar=1,fps=30,"
              f"fade=t=in:st=0:d={fd},fade=t=out:st={max(0.1, seg_dur - fd):.2f}:d={fd},format=yuv420p")
        clip = out_dir / f"S{sc:02d}.mp4"
        _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
              "-loop", "1", "-t", f"{seg_dur:.3f}", "-i", str(frame),
              "-vf", vf, "-r", "30", "-c:v", "libx264", "-tune", "stillimage",
              "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", str(clip)], timeout=120)
        clip_paths.append(clip)
        print(f"[scene {sc}] clip {seg_dur:.1f}s -> {clip.stat().st_size//1024}KB", flush=True)

        # 4) ترجمة المشهد — توقيت فعلي إن توفّر، وإلا توزيع نسبي
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
                cur = en

        t_cursor += seg_dur

    body_total = t_cursor

    # 5) دمج المقاطع -> فيديو صامت
    concat_txt = out_dir / "clips.txt"
    concat_txt.write_text("\n".join(f"file '{p.resolve()}'" for p in clip_paths), encoding="utf-8")
    silent = out_dir / "silent.mp4"
    _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
          "-i", str(concat_txt), "-c", "copy", str(silent)], timeout=300)

    # 6) بناء مسار الصوت: كل صوت مشهد + صمت SCENE_GAP، ثم loudnorm
    n = len(audio_parts)
    a_inputs = []
    for ap in audio_parts:
        a_inputs += ["-i", str(ap)]
    fc_a = []
    for i in range(n):
        fc_a.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,asetpts=N/SR/TB[a{i}]")
        fc_a.append(f"aevalsrc=0:d={SCENE_GAP}:s=48000:c=stereo[g{i}]")
    seq_labels = "".join(f"[a{i}][g{i}]" for i in range(n))
    full_filter = ";".join(fc_a) + f";{seq_labels}concat=n={2 * n}:v=0:a=1[cat];[cat]loudnorm={LOUDNORM}[out]"
    audio_mix = out_dir / "narration.m4a"
    _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *a_inputs,
          "-filter_complex", full_filter, "-map", "[out]", "-c:a", "aac", "-b:a", "192k",
          str(audio_mix)], timeout=300)

    # معايير ترميز موحّدة (تسمح بالدمج لاحقًا بلا إعادة ترميز)
    VENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-level", "4.0", "-x264-params", "keyint=60:min-keyint=60:scenecut=0",
            "-r", "30", "-video_track_timescale", "30000"]
    AENC = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]

    # 7) ترجمة ASS + حرقها + دمج الصوت -> جسم الفيديو (ترميز واحد)
    ass_path = out_dir / "captions.ass"
    _build_ass(sub_events, ass_path)
    body = out_dir / "body.mp4"
    subs_arg = f"subtitles={ass_path.as_posix()}:fontsdir={FONTS_DIR}"
    _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
          "-i", str(silent), "-i", str(audio_mix),
          "-vf", subs_arg + ",setsar=1,fps=30", "-map", "0:v", "-map", "1:a",
          *VENC, *AENC, "-shortest", str(body)], timeout=1200)

    final_path = out_dir / "final_narrated.mp4"

    # 8) مقدمة + جسم + خاتمة
    segs = [str(body)]
    if USE_BOOKENDS and Path(intro_path).exists():
        intro_n = out_dir / "intro_n.mp4"
        _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", intro_path,
              "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30",
              *VENC, *AENC, str(intro_n)], timeout=300)
        segs.insert(0, str(intro_n))
    if USE_BOOKENDS and Path(outro_path).exists():
        outro_n = out_dir / "outro_n.mp4"
        _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", outro_path,
              "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30",
              *VENC, *AENC, str(outro_n)], timeout=300)
        segs.append(str(outro_n))

    if len(segs) == 1:
        _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(body),
              "-c", "copy", "-movflags", "+faststart", str(final_path)], timeout=120)
    else:
        seglist = out_dir / "segs.txt"
        seglist.write_text("\n".join(f"file '{Path(s).resolve()}'" for s in segs), encoding="utf-8")
        try:
            _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
                  "-i", str(seglist), "-c", "copy", "-movflags", "+faststart", str(final_path)], timeout=300)
        except FactoryError:
            # احتياطي: إعادة ترميز الدمج
            inputs = []
            for s in segs:
                inputs += ["-i", s]
            fc = "".join(f"[{i}:v][{i}:a]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=1[v][a]"
            _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs,
                  "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
                  *VENC, *AENC, "-movflags", "+faststart", str(final_path)], timeout=1200)

    rel = "/outputs/" + final_path.relative_to(OUTPUTS_DIR).as_posix()
    return {
        "status": "ok",
        "video_path": rel,
        "scenes": len(scenes_in),
        "video_uid": video_uid,
        "body_seconds": round(body_total, 2),
        "final_seconds": round(_dur(final_path), 2),
        "tts_speed": TTS_SPEED,
        "tts_backend": TTS_BACKEND,
        "tts_voice": {"heygen": HEYGEN_VOICE_ID, "edge": EDGE_VOICE}.get(TTS_BACKEND, ELEVEN_VOICE_ID),
        "bookends": USE_BOOKENDS and Path(intro_path).exists(),
        "bookend_set": os.path.basename(intro_path),
        "image_source": "programmatic_vector_diagrams",
        "captions": "burned_ass_dynamic",
    }
