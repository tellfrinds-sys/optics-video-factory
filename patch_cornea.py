import ast
p = "/root/video-factory/eye_scene2.py"
s = open(p, encoding="utf-8").read()

if "_draw_cornea_layers" not in s:
    helper = '''

# ---------------- رسم مقطع القرنية وطبقاتها ----------------
_CORNEA_LAYERS = [
    ("tearfilm",   "الغشاء الدمعي",   "Tear Film",           0.05, (120, 170, 210)),
    ("epithelium", "الظهارة",          "Epithelium",          0.11, (150, 120, 200)),
    ("bowman",     "غشاء بومان",       "Bowman's Layer",      0.05, (210, 150, 120)),
    ("stroma",     "السدى",            "Stroma",              0.60, (225, 195, 150)),
    ("descemet",   "غشاء ديسيميه",     "Descemet's Membrane", 0.05, (150, 200, 170)),
    ("endothelium","البطانة",          "Endothelium",         0.09, (120, 190, 205)),
]


def _draw_cornea_layers(img, hl_keys):
    d = ImageDraw.Draw(img, "RGBA")
    hl = {k for k in hl_keys}
    px, py, pw, ph = 150, 210, 560, 690      # لوح القرنية
    d.rounded_rectangle([px - 14, py - 40, px + pw + 14, py + ph + 40], radius=22,
                        fill=(12, 22, 40, 180), outline=(255, 255, 255, 22), width=1)
    d.text((px + pw / 2, py - 66), "مقطع في القرنية (من الأمام للخلف)", font=_f(AR_BOLD, 30),
           fill=DIM, anchor="mm", language="ar")
    y = py
    for key, ar, en, frac, col in _CORNEA_LAYERS:
        h = max(26, ph * frac)
        on = key in hl or (not hl)
        a = 255 if on else 90
        d.rectangle([px, y, px + pw, y + h], fill=col + (a,),
                    outline=(255, 209, 122, 230) if key in hl else (255, 255, 255, 40),
                    width=3 if key in hl else 1)
        # مسمّى على اليمين
        cy = y + h / 2
        lx = px + pw + 70
        d.line([(px + pw, cy), (lx - 8, cy)], fill=(255, 209, 122, 200) if key in hl else (200, 210, 230, 90), width=2)
        d.text((lx, cy - 15), _plain(ar), font=_f(AR_BOLD, 30 if key in hl else 27),
               fill=GOLD if key in hl else INK, anchor="lm", language="ar")
        d.text((lx, cy + 16), en, font=_f(LAT, 22), fill=DIM, anchor="lm")
        y += h
    # أسهم الاتجاه
    d.text((px - 40, py + 10), "أمام", font=_f(AR_REG, 24), fill=DIM, anchor="mm", language="ar")
    d.text((px - 40, py + ph - 10), "خلف", font=_f(AR_REG, 24), fill=DIM, anchor="mm", language="ar")

'''
    s = s.replace("def render_scene(scene: dict, size=(W, H)) -> Image.Image:",
                  helper + "\ndef render_scene(scene: dict, size=(W, H)) -> Image.Image:", 1)

# فرع cornea_layers داخل render_scene — قبل "# صورة العين"
anchor = "    # صورة العين\n    eye = _eye_img()"
branch = '''    # رسم متخصّص: مقطع القرنية وطبقاتها
    if scene.get("diagram") == "cornea_layers" and sc != 1 and scene.get("kind") not in ("title", "outro"):
        _header(img, heading, scene.get("term_en") or "")
        keys = [k for (_n, k) in labels if k in {"tearfilm", "epithelium", "bowman", "stroma", "descemet", "endothelium"}]
        _draw_cornea_layers(img, keys)
        _footer(img, code)
        return img

    # صورة العين
    eye = _eye_img()'''
assert anchor in s
s = s.replace(anchor, branch, 1)

open(p, "w", encoding="utf-8").write(s)
ast.parse(s)
print("cornea_layers diagram added:", "_draw_cornea_layers" in s and 'diagram") == "cornea_layers"' in s)
