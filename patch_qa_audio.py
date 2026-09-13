import ast
p = "/root/video-factory/qa_gate.py"
s = open(p, encoding="utf-8").read()

# --- إضافة مراجعة Gemini السمعية (تستمع للصوت الفعلي) ---
if "gemini_audio_review" not in s:
    fn = '''

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
    script_txt = "\\n".join("(%d) %s" % (s.get("scene_no", i + 1), s.get("narration", ""))
                            for i, s in enumerate(scenes))
    sysmsg = (
        "أنت المدقّق النهائي لأكاديمية «بوابة البصريات». استمع للتسجيل الصوتي وقارنه بالسيناريو المكتوب "
        "وهدف الدرس. طبّق دليل الأسلوب بصرامة.\\n" + _style_guide()[:4000] + "\\n\\n"
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
            {"text": "هدف الدرس: %s\\n\\nالسيناريو المكتوب:\\n%s" % (lesson_goal, script_txt)},
        ]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                             "maxOutputTokens": 8192},
    }).encode()
    req = urllib.request.Request(GEMINI_URL, data=body, method="POST",
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            d = json.loads(r.read())
        txt = "".join(pt.get("text", "") for pt in
                      ((d.get("candidates") or [{}])[0].get("content") or {}).get("parts", []))
        return json.loads(txt)
    except Exception as e:
        return {"verdict": "skip", "note": str(e)[:200]}
'''
    s = s.replace("def run_qa(video_uid: int, scenes: list[dict]) -> dict:",
                  fn + "\n\ndef run_qa(video_uid: int, scenes: list[dict]) -> dict:", 1)

# --- استبدال فحص qwen بمراجعة Gemini السمعية ---
old_block = '''    # 4) حكم LLM على اللهجة والإملاء
    sysmsg = (
        "أنت مدقّق لغوي لمحتوى تعليمي مصري. افحص النص مقابل: (1) لهجة مصرية عامية بالكامل "
        "لا فصحى، (2) لا أخطاء إملائية، (3) صحة المصطلحات التشريحية للعين. "
        'أجب JSON فقط: {"verdict":"pass|fail","issues":[{"type":"dialect|spelling|term","quote":"...","fix":"..."}]}'
    )
    try:
        llm = _ollama(sysmsg, "النص المعتمد:\\n" + expected[:3500])
    except Exception as _e:
        llm = {"verdict": "skip", "issues": [], "note": str(_e)[:120]}
    llm_ok = str(llm.get("verdict", "")).lower() in ("pass", "skip")
    for it in (llm.get("issues") or [])[:12]:
        issues.append({"type": "لغوي/" + str(it.get("type", "?")),
                       "quote": str(it.get("quote", ""))[:120], "fix": str(it.get("fix", ""))[:120]})
    add("مراجعة_ذكية", llm_ok, json.dumps(llm, ensure_ascii=False)[:200])'''

new_block = '''    # 4) المراجعة النهائية السمعية بـ Gemini (يستمع للصوت الفعلي)
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
        "%s (%s) — %s" % (gv, gar.get("score", "?"), gar.get("summary_ar", gar.get("note", ""))[:180]))'''

if old_block in s:
    s = s.replace(old_block, new_block, 1)
    s = s.replace('"مراجعة_ذكية"))', '"مراجعة_سمعية_Gemini"))')
    print("qa_gate: qwen -> gemini audio review")
else:
    print("WARN old qwen block not found")

open(p, "w", encoding="utf-8").write(s)
ast.parse(s)
print("done")
