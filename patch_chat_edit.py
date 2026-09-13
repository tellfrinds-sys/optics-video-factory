# -*- coding: utf-8 -*-
"""agents.chat_edit — محادثة مباشرة مع وكيل المراجعة عبر تليجرام لضبط السيناريو."""
import io, ast

P = "/root/video-factory/pipeline/agents.py"
s = io.open(P, encoding="utf-8").read()
if "def chat_edit(" in s:
    print("already patched"); raise SystemExit

FN = '''

def chat_edit(fs: dict, lesson: dict, user_msg: str, history: list | None = None) -> dict:
    """محادثة تفاعلية: المستخدم يمرّر ملاحظاته للوكيل، والوكيل يرد ويعدّل السيناريو
    حتى يقول المستخدم «اعتمد/نفّذ». يعيد:
      {reply_ar, scene_patches:[{scene_no,field,new}], replace_all_scenes:[...]|None, ready_to_produce}
    """
    history = history or []
    scenes = fs.get("scenes") or []
    script_txt = "\\n".join("(%d) [%s] %s" % (s0.get("scene_no", i + 1),
                                              s0.get("heading", ""), s0.get("narration", ""))
                            for i, s0 in enumerate(scenes))
    hist_txt = "\\n".join("%s: %s" % ("المستخدم" if h.get("role") == "user" else "الوكيل",
                                      h.get("text", "")) for h in history[-8:])
    system = (
        "أنت «وكيل المراجعة» في أكاديمية بوابة البصريات، بتتكلم مع المسؤول مباشرة على تليجرام "
        "عشان تظبطوا سيناريو الدرس سوا. اللهجة مصرية عامية 100%. كن مختصرًا ومحترفًا.\\n"
        "قواعد:\\n"
        "- لو المستخدم طلب تعديل واضح (كلمة، جملة، مشهد، نطق، وقفة) — طبّقه فورًا وارجع scene_patches.\\n"
        "- لو لصق سيناريو كامل (فيه «〔مشهد») — رجّعه كامل في replace_all_scenes بنفس بنية المشاهد.\\n"
        "- لو المستخدم قال «اعتمد» أو «نفّذ» أو «يلا» أو «تمام ابدأ» — اضبط ready_to_produce=true.\\n"
        "- لو محتاج توضيح — اسأل سؤال واحد قصير في reply_ar وسيب ready_to_produce=false.\\n"
        "- طبّق دليل الأسلوب بصرامة (نطق القاف في المصطلحات العلمية، سُمك بالضم، تعطيش الجيم، لهجة مصرية).\\n"
        "أعد JSON فقط: {\\"reply_ar\\":\\"...\\",\\"scene_patches\\":[{\\"scene_no\\":n,\\"field\\":\\"narration|heading|caption\\",\\"new\\":\\"...\\"}],"
        "\\"replace_all_scenes\\":null,\\"ready_to_produce\\":false}\\n\\n" + style_guide()[:3000])
    user = ("السيناريو الحالي:\\n%s\\n\\nالمحادثة السابقة:\\n%s\\n\\nرسالة المستخدم الآن:\\n%s"
            % (script_txt, hist_txt or "(بداية)", user_msg))
    try:
        out = _gemini(system, user)
    except Exception as e:
        return {"reply_ar": "حصل خطأ عند الوكيل: %s. جرّب تاني." % e,
                "scene_patches": [], "replace_all_scenes": None, "ready_to_produce": False}
    if not isinstance(out, dict):
        return {"reply_ar": "ماقدرتش أفهم — ممكن توضّح؟", "scene_patches": [],
                "replace_all_scenes": None, "ready_to_produce": False}
    out.setdefault("reply_ar", "تمام.")
    out.setdefault("scene_patches", [])
    out.setdefault("replace_all_scenes", None)
    out.setdefault("ready_to_produce", False)
    return out
'''

anchor = "\ndef learn_from("
assert anchor in s
s = s.replace(anchor, FN + anchor, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8").write(s)
print("added agents.chat_edit")
