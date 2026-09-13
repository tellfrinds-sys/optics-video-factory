import ast
p = "/root/video-factory/narrated_render.py"
s = open(p, encoding="utf-8").read()

i0 = s.index("def _spaced(text: str) -> str:")
i1 = s.index('\n', s.index('return " ".join(out)', i0)) + 1
old = s[i0:i1]

new = (
    'def _spaced(text: str) -> str:\n'
    '    """يُدرج توقفات <break> عند علامات الترقيم (وبين الكلمات إن طُلب WORD_GAP>0)\n'
    '    ليقترب إيقاع المتن من المقدمة/الخاتمة دون تغيير سرعة الصوت."""\n'
    '    toks = text.split()\n'
    '    out = []\n'
    '    for i, w in enumerate(toks):\n'
    '        out.append(w)\n'
    '        if i == len(toks) - 1:\n'
    '            break\n'
    '        if w.endswith((".", "!", "\\u061f", "?", ":")):\n'
    '            g = SENT_GAP\n'
    '        elif w.endswith(("\\u060c", "\\u061b")):\n'
    '            g = COMMA_GAP\n'
    '        elif WORD_GAP > 0:\n'
    '            g = WORD_GAP\n'
    '        else:\n'
    '            g = 0.0\n'
    '        if g > 0:\n'
    '            out.append(\'<break time="%.2fs"/>\' % g)\n'
    '    return " ".join(out)\n'
)

s = s.replace(old, new, 1)
s = s.replace('os.environ.get("WORD_GAP", "0.16")', 'os.environ.get("WORD_GAP", "0")')
s = s.replace('os.environ.get("COMMA_GAP", "0.30")', 'os.environ.get("COMMA_GAP", "0.38")')
s = s.replace('os.environ.get("SENT_GAP", "0.42")', 'os.environ.get("SENT_GAP", "0.60")')
open(p, "w", encoding="utf-8").write(s)
ast.parse(s)
print("OK — _spaced replaced")
print(new)
