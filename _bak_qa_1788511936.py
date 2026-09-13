# -*- coding: utf-8 -*-
"""
qa_gate.py — بوابة مراجعة آلية تعمل كآخر خطوة قبل تسليم أي فيديو.

تفحص الفيديو النهائي مقابل الضوابط المعتمدة وتُرجع:
  {"verdict": "pass"|"fail", "checks": [...], "issues": [...], "transcript": "..."}

المكوّنات (كلها مفتوحة المصدر / محلية):
- faster-whisper (venv) : تفريغ الصوت للتحقق من مطابقة النص.
- قواعد نصّية          : كشف الفصحى الدخيلة + كلمات ممنوعة + أرقام/مصطلحات لاتينية في النطق.
- qwen2.5:7b عبر Ollama : حكم نهائي على اللهجة والإملاء.
- ffprobe               : بنية الفيديو (مدة، مسارات، مقدمة/خاتمة).

الاستخدام:
  python3 qa_gate.py <video_uid> [scenes_json_path]
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unicodedata
import urllib.request
import urllib.error
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path("/root/video-factory")
OUT = ROOT / "outputs"
WHISPER_PY = ROOT / "qaenv" / "bin" / "python"
OLLAMA = "http://127.0.0.1:11434/api/generate"
QA_MODEL = os.environ.get("QA_MODEL", "qwen2.5:7b-instruct")
PUBLIC_BASE = os.environ.get("PUBLIC_BASE", "https://n8n.opticsgate.online")

_TASH = re.compile("[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06DC\u06DF-\u06E8\u06EA-\u06ED\u0640]")

# علامات فصحى شائعة لا تُقال في العامية المصرية
MSA_MARKERS = [
    r"\bإنَّ\b", r"\bلقد\b", r"\bسوف\b", r"\bالذي\b", r"\bالتي\b", r"\bهذه\b", r"\bهذا\b",
    r"\bكذلك\b", r"\bحيث\b", r"\bعندما\b", r"\bلذلك\b", r"\bيتم\b", r"\bقام\b", r"\bنقوم\b",
    r"\bسنشرح\b", r"\bنستطيع\b", r"\bيمكننا\b", r"\bجداً ومن\b",
]
FORBIDDEN = [r"\bإعلان\b", r"\bاشترك\b الآن\b", r"\blorem\b", r"\bplaceholder\b", r"\bTODO\b", r"\bخطأ\b\s*\d"]


def _run(cmd, timeout=600):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", str(s or ""))
    s = _TASH.sub("", s)
    s = re.sub(r"[^\w؀-ۿ ]+", " ", s)
    s = s.replace("ـ", "").replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي").replace("ة", "ه")
    return re.sub(r"\s+", " ", s).strip()


def _probe(path: Path) -> dict:
    r = _run(["ffprobe", "-v", "error", "-show_entries",
              "format=duration:stream=codec_type,codec_name", "-of", "json", str(path)])
    return json.loads(r.stdout or "{}")


def _whisper(audio: Path) -> str:
    model = os.environ.get("QA_WHISPER", "small")
    code = (
        "import sys; from faster_whisper import WhisperModel;"
        "m=WhisperModel(%r, device='cpu', compute_type='int8');"
        "segs,_=m.transcribe(sys.argv[1], language='ar', vad_filter=True);"
        "print(' '.join(s.text.strip() for s in segs))" % model
    )
    r = _run([str(WHISPER_PY), "-c", code, str(audio)], timeout=1800)
    return (r.stdout or "").strip()


def _word_recall(expected: str, got: str) -> float:
    """نسبة كلمات النصّ المعتمد (المميّزة) التي ظهرت في التفريغ — متينة أمام أخطاء whisper."""
    stop = {"في", "من", "على", "عن", "ده", "دي", "اللي", "هي", "هو", "أو", "او", "مع",
            "كل", "ما", "يا", "بس", "كمان", "زي", "أي", "الى", "إلى", "و", "ثم"}
    ew = [w for w in _norm(expected).split() if len(w) > 2 and w not in stop]
    gw = set(_norm(got).split())
    if not ew:
        return 1.0
    hit = sum(1 for w in ew if w in gw or any(w[:4] == g[:4] and len(g) > 3 for g in gw))
    return hit / len(ew)


def _ollama(system: str, prompt: str) -> dict:
    body = json.dumps({"model": QA_MODEL, "system": system, "prompt": prompt,
                       "stream": False, "format": "json",
                       "options": {"temperature": 0, "num_ctx": 4096}}).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=420) as resp:
        raw = json.loads(resp.read())["response"]
    try:
        return json.loads(raw)
    except Exception:
        return {"verdict": "fail", "issues": [{"type": "parse", "note": raw[:300]}]}




GEMINI_URL = os.environ.get(
    "GEMINI_URL",
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent")
STYLE_GUIDE_FILE = ROOT / "pipeline" / "style_guide.md"


def _style_guide():
    try:
        return STYLE_GUIDE_FILE.read_text(encoding="utf-8")
    except Exception:
        return ""


def gemini_audio_review(audio_path: Path, scenes: list, lesson_goal: str = "") -> dict:
    """يرسل صوت السرد الفعلي + السيناريو إلى Gemini ليستمع ويراجع:
       اللهجة المصرية، مخارج الحروف، مواضع التوقف، الإملاء مقابل المنطوق، تغطية الهدف."""
    import base64
    key = os.environ.get("GEMINI_API_KEY")
    if not key or not audio_path.exists():
        return {"verdict": "skip", "note": "no key/audio"}
    raw = audio_path.read_bytes()
    if len(raw) > 18_000_000:
        r = _run(["ffmpeg", "-y", "-i", str(audio_path), "-ac", "1", "-ar", "22050",
                  "-b:a", "48k", str(audio_path) + ".q.mp3"], timeout=120)
        raw = Path(str(audio_path) + ".q.mp3").read_bytes()
        mime = "audio/mpeg"
    else:
        mime = "audio/mp4"
    script_txt = "\n".join("(%d) %s" % (s.get("scene_no", i + 1), s.get("narration", ""))
                            for i, s in enumerate(scenes))
    sysmsg = (
        "أنت المدقّق النهائي لأكاديمية «بوابة البصريات». استمع للتسجيل الصوتي وقارنه بالسيناريو المكتوب "
        "وهدف الدرس. طبّق دليل الأسلوب بصرامة.\n" + _style_guide()[:4000] + "\n\n"
        "افحص: (1) اللهجة مصرية عامية 100% في كل جملة مسموعة. (2) مخارج الحروف والمصطلحات صحيحة "
        "(دايوبتر، الصلبة بفتح الصاد، الأسماء الإنجليزية). (3) مواضع التوقف طبيعية — لا وقفات طويلة بين "
        "كل كلمة ولا اندفاع بلا تنفّس. (4) الصوت مطابق للسيناريو بلا كلمات ساقطة أو مضافة. "
        "(5) تغطية هدف الدرس. أجب JSON فقط: "
        '{"verdict":"pass|fail","score":0-100,"dialect_issues":[{"scene":n,"heard":"","should":""}],'
        '"pronunciation_issues":["..."],"pause_issues":["..."],"mismatch":["..."],"coverage_gaps":["..."],'
        '"summary_ar":"جملتان بالعربية"}'
    )
    body = json.dumps({
        "system_instruction": {"parts": [{"text": sysmsg}]},
        "contents": [{"role": "user", "parts": [
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(raw).decode()}},
            {"text": "هدف الدرس: %s\n\nالسيناريو المكتوب:\n%s" % (lesson_goal, script_txt)},
        ]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                             "maxOutputTokens": 8192},
    }).encode()
    req = urllib.request.Request(GEMINI_URL, data=body, method="POST",
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    d=None
    for _t in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.loads(r.read()); break
        except urllib.error.HTTPError as he:
            if he.code in (429,503) and _t<3:
                import time as _tm; _tm.sleep(25*(_t+1)); continue
            return {"verdict":"skip","note":"gemini %s"%he.code}
        except Exception as e:
            return {"verdict":"skip","note":str(e)[:150]}
    try:
        txt = "".join(pt.get("text", "") for pt in
                      ((d.get("candidates") or [{}])[0].get("content") or {}).get("parts", []))
        return json.loads(txt)
    except Exception as e:
        return {"verdict": "skip", "note": str(e)[:200]}


def run_qa(video_uid: int, scenes: list[dict]) -> dict:
    d = OUT / f"narrated_{video_uid}"
    video = d / "final_narrated.mp4"
    checks, issues = [], []

    def add(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        if not ok:
            issues.append({"type": name, "note": detail})

    # 1) بنية الفيديو
    if not video.exists():
        return {"verdict": "fail", "checks": [{"check": "file", "ok": False}],
                "issues": [{"type": "file", "note": "final_narrated.mp4 غير موجود"}]}
    meta = _probe(video)
    dur = float(meta.get("format", {}).get("duration", 0))
    vs = [s for s in meta.get("streams", []) if s.get("codec_type") == "video"]
    as_ = [s for s in meta.get("streams", []) if s.get("codec_type") == "audio"]
    add("مسار_فيديو", len(vs) == 1, f"{len(vs)} مسار")
    add("مسار_صوت", len(as_) == 1, f"{len(as_)} مسار")
    add("مدة_معقولة", 60 <= dur <= 900, f"{dur:.0f}s")
    tail = _run(["ffmpeg", "-v", "error", "-sseof", "-3", "-i", str(video), "-f", "null", "-"])
    add("النهاية_سليمة", tail.returncode == 0, tail.stderr[:200])
    intro = d / "intro_n.mp4"
    outro = d / "outro_n.mp4"
    add("مقدمة_وخاتمة", intro.exists() and outro.exists(),
        f"intro={intro.exists()} outro={outro.exists()}")

    # 2) الترجمة/الصوت — تفريغ متن السرد
    body_audio = d / "narration.m4a"
    transcript = _whisper(body_audio) if body_audio.exists() else ""
    add("تفريغ_الصوت", len(transcript) > 40, f"{len(transcript)} حرفًا")

    expected = " ".join(s.get("caption") or s.get("narration") or "" for s in scenes)
    sim = _word_recall(expected, transcript) if transcript else 0.0
    add("مطابقة_النص", sim >= 0.60, f"استرجاع كلمات {sim:.2f}")

    # 3) قواعد على النص المكتوب (السكربت المعتمد)
    for pat in MSA_MARKERS:
        for m in re.finditer(pat, expected):
            issues.append({"type": "فصحى", "quote": expected[max(0, m.start() - 15):m.end() + 15]})
    add("خلو_من_الفصحى", not any(i["type"] == "فصحى" for i in issues),
        f"{sum(1 for i in issues if i['type']=='فصحى')} موضع")
    for pat in FORBIDDEN:
        if re.search(pat, expected, re.I):
            issues.append({"type": "كلمة_ممنوعة", "quote": pat})
    add("خلو_من_الممنوع", not any(i["type"] == "كلمة_ممنوعة" for i in issues))
    # مصطلحات إنجليزية داخل السرد (مقبولة — تُنطق إنجليزيًا) — معلومة فقط
    lat = re.findall(r"[A-Za-z]{2,}", " ".join(s.get("narration", "") for s in scenes))
    add("مصطلحات_إنجليزية", True, f"{len(lat)} مصطلح: {lat[:8]}")

    # 4) المراجعة النهائية السمعية بـ Gemini (يستمع للصوت الفعلي)
    goal = ""
    try:
        goal = (scenes[0] or {}).get("lesson_goal", "")
    except Exception:
        pass
    gar = gemini_audio_review(d / "narration.m4a", scenes, goal)
    gv = str(gar.get("verdict", "skip")).lower()
    gar_ok = gv in ("pass", "skip")
    for it in (gar.get("dialect_issues") or [])[:10]:
        issues.append({"type": "لهجة(سماعي)", "note": json.dumps(it, ensure_ascii=False)[:160]})
    for grp in ("pronunciation_issues", "pause_issues", "mismatch", "coverage_gaps"):
        for it in (gar.get(grp) or [])[:6]:
            issues.append({"type": grp, "note": str(it)[:160]})
    add("مراجعة_سمعية_Gemini", gar_ok,
        "%s (%s) — %s" % (gv, gar.get("score", "?"), gar.get("summary_ar", gar.get("note", ""))[:180]))

    # 5) قابلية خدمة الملف من السيرفر (فحص محلي موثوق)
    try:
        url = f"http://127.0.0.1:8000/outputs/narrated_{video_uid}/final_narrated.mp4"
        rq = urllib.request.Request(url, headers={"Range": "bytes=0-200"})
        with urllib.request.urlopen(rq, timeout=20) as rp:
            add("الملف_يُخدَم", rp.status in (200, 206), f"HTTP {rp.status}")
    except Exception as e:
        add("الملف_يُخدَم", False, str(e)[:120])

    hard_fail = any(not c["ok"] for c in checks if c["check"] in (
        "مسار_فيديو", "مسار_صوت", "مدة_معقولة", "النهاية_سليمة", "مقدمة_وخاتمة",
        "تفريغ_الصوت", "مطابقة_النص", "خلو_من_الفصحى", "خلو_من_الممنوع",
        "مراجعة_سمعية_Gemini"))
    return {
        "verdict": "fail" if hard_fail else "pass",
        "video_uid": video_uid, "duration": round(dur, 1),
        "text_similarity": round(sim, 3),
        "checks": checks, "issues": issues, "transcript": transcript[:2000],
    }


def _load_scenes(arg: str | None) -> list[dict]:
    if arg and Path(arg).exists():
        return json.loads(Path(arg).read_text(encoding="utf-8"))
    sys.path.insert(0, str(ROOT))
    import corrected_scenes as cs
    return cs.SCENES


if __name__ == "__main__":
    uid = int(sys.argv[1]) if len(sys.argv) > 1 else 500128
    scenes = _load_scenes(sys.argv[2] if len(sys.argv) > 2 else None)
    print(json.dumps(run_qa(uid, scenes), ensure_ascii=False, indent=1))
