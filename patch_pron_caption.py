# -*- coding: utf-8 -*-
"""narrated_render.py:
   1) قاموس نطق للـ TTS (قرنية بالقاف، سُمك بالضم، تعطيش الجيم في الكلمات العلمية)
   2) تكبير الترجمة العربية المحروقة (50 -> 84)
"""
import io, ast

P = "/root/video-factory/narrated_render.py"
s = io.open(P, encoding="utf-8").read()
if "_PRON_FIXES" in s:
    print("already patched"); raise SystemExit

# ---------- 1) قاموس النطق ----------
DICT = '''

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
'''
s = s.replace("\ndef _tts_text_edge(text: str) -> str:", DICT + "\ndef _tts_text_edge(text: str) -> str:", 1)

OLD_TE = '''    t = _ud.normalize("NFC", str(text))
    t = _INVIS.sub("", t).replace("\\u06be", "\\u0647")
    return re.sub(r"\\s+", " ", t).strip()'''
NEW_TE = '''    t = _ud.normalize("NFC", str(text))
    t = _INVIS.sub("", t).replace("\\u06be", "\\u0647")
    t = _apply_pron(t)
    return re.sub(r"\\s+", " ", t).strip()'''
assert OLD_TE in s, "tts_text_edge body anchor missing"
s = s.replace(OLD_TE, NEW_TE, 1)

# ---------- 2) تكبير الترجمة ----------
OLD_ST = "Style: Cap, {SUB_FONT}, 50, &H00FFFFFF, &H00251A12, &H3C160E22, 1, 3, 12, 0, 2, 170, 170, 195, 1"
NEW_ST = "Style: Cap, {SUB_FONT}, 84, &H00FFFFFF, &H00251A12, &H3C160E22, 1, 3, 14, 0, 2, 150, 150, 165, 1"
assert OLD_ST in s, "ASS style anchor missing"
s = s.replace(OLD_ST, NEW_ST, 1)

ast.parse(s)
io.open(P, "w", encoding="utf-8").write(s)
print("narrated_render.py — pronunciation dict + bigger captions")
