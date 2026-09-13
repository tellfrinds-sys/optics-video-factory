# -*- coding: utf-8 -*-
"""يضيف agents.auto_remediate — وكيل الإصلاح الذاتي بعد فشل بوابة المراجعة."""
import io, ast

P = "/root/video-factory/pipeline/agents.py"
s = io.open(P, encoding="utf-8").read()
if "def auto_remediate" in s:
    print("already patched"); raise SystemExit

FN = '''

def auto_remediate(qa: dict, fs: dict, lesson: dict) -> dict:
    """وكيل الإصلاح الذاتي: يحلّل فشل بوابة المراجعة، يصلح ما يُصلَح في السيناريو،
    يقبل ما هو قيد صوتي بحت، ويستخلص قاعدة تعلُّم. يعيد JSON."""
    scenes = fs.get("scenes") or []
    issues = qa.get("issues") or []
    checks = qa.get("checks") or []
    script_txt = "\\n".join("(%d) %s" % (s0.get("scene_no", i + 1), s0.get("narration", ""))
                            for i, s0 in enumerate(scenes))
    iss_txt = "\\n".join("- [%s] %s" % (it.get("type", ""), it.get("note") or it.get("quote") or "")
                         for it in issues)
    system = (
        "أنت «الوكيل المراجع المُصلِح» في أكاديمية بوابة البصريات. بوابة المراجعة رصدت ملاحظات على "
        "الفيديو بعد إنتاجه. مهمتك: (1) صنّف كل ملاحظة: قابلة للإصلاح في نصّ السيناريو (كلمة خاطئة، "
        "رقم غلط، تعبير علمي غير دقيق، تسرّب فصحى) أم قيد صوتي بحت لا يُصلَح بالنص (مثل نطق القاف همزةً "
        "في اللهجة المصرية — هذا مقبول ولا يُصلَح). (2) للإصلاحات النصّية: أعطِ التعديل الدقيق "
        "(المشهد + النص القديم + النص الجديد) بالعامية المصرية فقط ومع الحفاظ على المعنى والطول. "
        "(3) استخلص قاعدة واحدة مختصرة تُضاف لدليل الأسلوب لمنع تكرار الخطأ. (4) قرّر action: "
        "\\"refix\\" لو فيه إصلاحات نصّية تستحق إعادة إنتاج، \\"accept\\" لو كل الملاحظات قيود صوتية "
        "مقبولة أو تافهة، \\"escalate\\" لو الخطأ جوهري ويحتاج تدخل بشري. "
        "أعد JSON فقط: {\\"diagnosis_ar\\":\\"جملة\\",\\"script_fixes\\":[{\\"scene_no\\":n,\\"field\\":\\"narration\\","
        "\\"old\\":\\"...\\",\\"new\\":\\"...\\"}],\\"accept_as_voice_limitation\\":[\\"...\\"],"
        "\\"learned_rule_ar\\":\\"...\\",\\"action\\":\\"refix|accept|escalate\\"}\\n\\n"
        + style_guide()[:3500])
    user = ("الدرس: %s\\nحكم البوابة: %s (score %s)\\n\\nالملاحظات:\\n%s\\n\\nالسيناريو الحالي:\\n%s" % (
        lesson.get("title_ar", ""), qa.get("verdict"),
        next((c.get("detail", "") for c in checks if "Gemini" in c.get("check", "")), ""),
        iss_txt, script_txt))
    try:
        out = _gemini(system, user)
    except Exception as e:
        return {"action": "escalate", "diagnosis_ar": "تعذّر استدعاء الوكيل: %s" % e,
                "script_fixes": [], "accept_as_voice_limitation": [], "learned_rule_ar": ""}
    if not isinstance(out, dict):
        return {"action": "escalate", "diagnosis_ar": "رد غير صالح من الوكيل",
                "script_fixes": [], "accept_as_voice_limitation": [], "learned_rule_ar": ""}
    out.setdefault("script_fixes", [])
    out.setdefault("accept_as_voice_limitation", [])
    out.setdefault("action", "escalate")
    out.setdefault("diagnosis_ar", "")
    out.setdefault("learned_rule_ar", "")
    return out
'''

# ألصقها قبل learn_from
anchor = "\ndef learn_from("
assert anchor in s
s = s.replace(anchor, FN + anchor, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8").write(s)
print("added agents.auto_remediate")
