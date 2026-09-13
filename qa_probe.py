import json, urllib.request

SYS = (
    "أنت مدقّق لغوي محترف لمحتوى تعليمي مصري. مهمتك فحص نص تعليق صوتي مقابل ضوابط ثابتة.\n"
    "الضوابط:\n"
    "1) اللهجة: يجب أن تكون مصرية عامية بالكامل. أي جملة بالفصحى = مخالفة.\n"
    "2) الإملاء: لا أخطاء إملائية.\n"
    "3) المصطلحات التشريحية للعين يجب أن تكون صحيحة.\n"
    "أجب بـ JSON فقط بالشكل: "
    '{"verdict":"pass|fail","issues":[{"type":"dialect|spelling|term","quote":"...","fix":"..."}]}'
)

TESTS = [
    ("مصري سليم",
     "العين البشرية دي عضو تركيبها دقيق ومتكون من كذا جزء بيكملوا بعض وهنشرح كل جزء في الفيديوهات الجاية."),
    ("فصحى (يجب fail)",
     "إنّ العين البشرية عضوٌ دقيق التركيب، ويتكوّن من عدة أجزاء متكاملة سنشرحها لاحقاً."),
    ("خطأ إملائي + لفظ (يجب fail)",
     "الطبقه الوسطى اسمها العنبيه وفيها القزحيه الملونه وفتحة البؤبؤ والجسم الهدبى."),
]


def ask(model, text):
    body = json.dumps({
        "model": model, "system": SYS, "prompt": "النص:\n" + text,
        "stream": False, "format": "json", "options": {"temperature": 0},
    }).encode()
    r = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=body,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=300) as resp:
        return json.loads(resp.read())["response"]


for model in ("qwen2.5:7b-instruct", "aya-expanse:8b"):
    print("\n==================", model, "==================")
    for label, txt in TESTS:
        try:
            out = ask(model, txt)
        except Exception as e:
            out = "ERR %s" % e
        print("--", label)
        print("  ", out.strip()[:500])
