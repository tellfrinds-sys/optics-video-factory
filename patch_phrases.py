import ast
p = "/root/video-factory/narrated_render.py"
s = open(p, encoding="utf-8").read()

i0 = s.index("def _phrases(text: str, max_words=9, min_words=4):")
i1 = s.index("return out or [_clean(text)]", i0) + len("return out or [_clean(text)]") + 1
old = s[i0:i1]

new = '''def _phrases(text: str, max_words=9, min_words=4):
    # الفواصل تُدمج في مجرى الكلمات (لا تُقسّم سطر ترجمة مستقلًا)
    base = re.sub(r"\\s+", " ", _clean(text).replace("\\u060c", " ")).strip()
    out = []
    for chunk in re.split(r"(?<=[\\.\\!\\u061f\\?\\u061b:])\\s+", base):
        chunk = chunk.strip(" .!\\u061f?\\u061b:\\n")
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
'''

assert old in s
s = s.replace(old, new, 1)
open(p, "w", encoding="utf-8").write(s)
ast.parse(s)
print("patched _phrases")

# اختبار سريع
import importlib, sys
sys.path.insert(0, "/root/video-factory")
import narrated_render as nr
importlib.reload(nr)
for t in ["نكمل رحلتنا ونوصل للستارة الملونة دي.. القزحية، أو آيرِس. دي اللي بتدي للعين لونها، سواء بني، أو أزرق، أو أخضر. لكن وظيفتها البصرية أهم بكتير من شكلها.",
          "شفنا إزاي كل جزء في العين. كأخصائيين، فهمنا العميق للتشريح والفيزيولوجيا هو الأساس."]:
    for ph in nr._phrases(t):
        print("  |", ph)
    print("---")
