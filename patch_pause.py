import ast
p = "/root/video-factory/narrated_render.py"
s = open(p, encoding="utf-8").read()

# 1) ثابت جديد: صمت طويل (نهاية جملة / <break>) يُبقى أطول من فجوات الكلمات
if "DEGAP_LONG" not in s:
    s = s.replace(
        'DEGAP_MIN = float(os.environ.get("DEGAP_MIN", "0.30"))     # لا يُقصّ إلا الصمت الأطول من هذا',
        'DEGAP_MIN = float(os.environ.get("DEGAP_MIN", "0.30"))     # لا يُقصّ إلا الصمت الأطول من هذا\n'
        'DEGAP_LONG = float(os.environ.get("DEGAP_LONG", "0.40"))   # ما يُبقى من وقفة نهاية الجملة\n'
        'DEGAP_LONG_MIN = float(os.environ.get("DEGAP_LONG_MIN", "0.72"))  # فوقها = وقفة جملة مقصودة')

# 2) _tts_text: أبقِ نهايات الجمل وأضف <break> بعدها (تنفّس بين الجُمَل)
old_tts = '''    t = _ud.normalize("NFC", str(text))
    t = t.replace("\\u060c", " ").replace("\\u061b", " ").replace(":", " ")
    t = _INVIS.sub("", t).replace("\\u06be", "\\u0647")
    return re.sub(r"\\s+", " ", t).strip()'''
new_tts = '''    t = _ud.normalize("NFC", str(text))
    t = t.replace("\\u060c", " ").replace("\\u061b", " ").replace(":", " ")
    t = _INVIS.sub("", t).replace("\\u06be", "\\u0647")
    # وقفة تنفّس بعد كل نهاية جملة
    t = re.sub(r"([.!\\u061f])\\s+", r'\\1 <break time="0.35s"/> ', t)
    return re.sub(r"\\s+", " ", t).strip()'''
assert old_tts in s
s = s.replace(old_tts, new_tts, 1)

# 3) _degap: keep متغيّر حسب طول الفجوة (وقفات الجمل تبقى أطول)
old_loop = '''    segs, cur = [], 0.0
    for a, b in zip(starts, ends):
        seg_end = max(cur, a + keep / 2)
        segs.append((cur, seg_end))
        cur = max(seg_end, b - keep / 2)'''
new_loop = '''    segs, cur = [], 0.0
    for a, b in zip(starts, ends):
        k = DEGAP_LONG if (b - a) > DEGAP_LONG_MIN else keep
        seg_end = max(cur, a + k / 2)
        segs.append((cur, seg_end))
        cur = max(seg_end, b - k / 2)'''
assert old_loop in s
s = s.replace(old_loop, new_loop, 1)

open(p, "w", encoding="utf-8").write(s)
ast.parse(s)
print("patched: DEGAP_LONG + sentence <break> + variable keep")

import importlib, sys
sys.path.insert(0, "/root/video-factory")
import narrated_render as nr
importlib.reload(nr)
print(repr(nr._tts_text("كلام أول. كلام تاني؟ وكلام تالت! خلاص.")))
