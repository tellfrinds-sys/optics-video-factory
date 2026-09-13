# -*- coding: utf-8 -*-
"""يطبّق سيناريو المستخدم المعدَّل يدويًا لدرس 100001 حرفيًا (بدون تغيير أي حرف/كلمة)،
   يضيف تشكيل فقط على الكلمات الخالية تمامًا من أي تشكيل، يحفظه كـ SCRIPT_FINAL معتمد، وينتج الفيديو."""
import os, sys, json, re, urllib.request

sys.path.insert(0, "/root/video-factory/pipeline")
sys.path.insert(0, "/root/video-factory")


def _env():
    f = "/root/video-factory/pipeline/.env"
    for ln in open(f, encoding="utf-8"):
        if "=" in ln and not ln.strip().startswith("#"):
            k, v = ln.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_env()
import agents

TASH = "ؗ-ًؚ-ْٰـ"  # نطاق حركات التشكيل + الشدة + الألف الخنجرية + التطويل
_TASH_RE = re.compile("[" + TASH + "]")
_AR_WORD = re.compile(r"[ء-ي]+")

_diac = None
try:
    import mishkal.tashkeel as _mt
    _diac = _mt.TashkeelClass()
except Exception as e:
    print("mishkal load failed:", e)


def _fill_word_tashkeel(word):
    """يشكّل الكلمة بس لو خالية تمامًا من أي تشكيل حاليًا، ويشيل نهايات الإعراب الفصيحة."""
    if _TASH_RE.search(word):
        return word  # فيها تشكيل جزئي/كامل بالفعل من المستخدم -- ماتتلمسش خالص
    if not _diac:
        return word
    try:
        out = _diac.tashkeel(word)
    except Exception:
        return word
    # جرّد تنوين/حركة إعرابية أخيرة (نطق وقفي مصري) وتطويل
    out = re.sub(r"[ًٌٍ]$", "", out)
    out = re.sub(r"[َُِ](?=$)", "", out)
    out = out.replace("ـ", "")
    return out


def add_tashkeel_preserving(text):
    def repl(m):
        return _fill_word_tashkeel(m.group(0))
    return _AR_WORD.sub(repl, text)


def bare(t):
    return _AR_WORD.sub(lambda m: m.group(0), _TASH_RE.sub("", t))


# 1) نص المستخدم كما هو حرفيًا
raw = open("/root/video-factory/user_script_100001.txt", encoding="utf-8").read()

# 2) السيناريو الأساسي الحالي (لأخذ diagram/labels/term_en/visual_focus عند عدم التحديد)
KEY = os.environ["SUPABASE_SERVICE_KEY"]; URL = os.environ["SUPABASE_URL"]
req = urllib.request.Request(
    URL + "/rest/v1/content_outputs?lesson_uid=eq.100001&stage_code=eq.SCRIPT_FINAL&order=created_at.desc&limit=1&select=output_text",
    headers={"apikey": KEY, "Authorization": "Bearer " + KEY})
rows = json.loads(urllib.request.urlopen(req, timeout=30).read())
base = {}
if rows:
    prev = json.loads(rows[0]["output_text"]).get("final_script") or {}
    base = {"scenes": prev.get("scenes") or []}

L = {"lesson_code": "B01-U01-C01-L01", "video_uid": 500128, "title_ar": None}
base["lesson_code"] = L["lesson_code"]
base["video_uid"] = L["video_uid"]

fs = agents.parse_script_text(raw, base)

# 3) إضافة تشكيل فقط للكلمات الخالية منه تمامًا في narration -- بدون لمس أي كلمة عندها تشكيل بالفعل
for sc in fs["scenes"]:
    original = sc.get("narration", "")
    filled = add_tashkeel_preserving(original)
    # تحقق أمان: نفس الحروف بالظبط بعد تجريد أي تشكيل من الاتنين
    if bare(filled) != bare(original):
        print("!!! SAFETY CHECK FAILED on scene", sc.get("scene_no"), "-- reverting to original text")
        filled = original
    sc["narration"] = filled

fs["title"] = "تتكون العين من ثلاثة أغلفة: الغلاف الليفي والوعائي والعصبي"
fs["video_uid"] = 500128
fs["lesson_code"] = "B01-U01-C01-L01"

out_path = "/root/video-factory/outputs/_status/script_100001_final_human.json"
json.dump(fs, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("wrote", out_path, "-- scenes:", len(fs["scenes"]))
for sc in fs["scenes"]:
    print(" scene", sc["scene_no"], "diagram=", sc.get("diagram"), "words=", len(sc["narration"].split()))

# 4) حفظ SCRIPT_FINAL معتمد جديد (human_edited)
lint = agents.dialect_lint(fs["scenes"]) if hasattr(agents, "dialect_lint") else {}
ot = json.dumps({"final_script": fs, "status": "PASS", "source": "human_edited", "dialect_lint": lint}, ensure_ascii=False)
body = json.dumps({
    "lesson_uid": 100001, "stage_code": "SCRIPT_FINAL", "prompt_binding_uid": "820006",
    "revision_no": 99, "output_text": ot, "output_hash": "", "model_used": "human_edited",
    "approval_status": "approved", "approved_by": "user_telegram",
}).encode()
req2 = urllib.request.Request(URL + "/rest/v1/content_outputs", data=body, method="POST",
    headers={"apikey": KEY, "Authorization": "Bearer " + KEY, "Content-Type": "application/json", "Prefer": "return=representation"})
try:
    r = urllib.request.urlopen(req2, timeout=30)
    print("SCRIPT_FINAL saved:", r.status)
except urllib.error.HTTPError as e:
    print("save ERROR", e.code, e.read().decode()[:400])
