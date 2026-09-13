"""
eye_diagrams.py — رسوم تشريحية متجهية مبرمَجة لمقطع العين.
تُنتج صور PNG نظيفة ودقيقة ومتّسقة بألوان هوية "بوابة البصريات".
الدالة العامة: render_scene(scene_no, on_screen_text, source_codes, size) -> PIL.Image (RGB)
"""
from __future__ import annotations

import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ---------- ألوان الهوية ----------
NAVY = (22, 34, 53)
NAVY2 = (33, 47, 66)
TEAL = (78, 132, 133)
SKY = (214, 232, 233)
IVORY = (246, 243, 238)
WHITE = (255, 255, 255)
GOLD = (203, 162, 108)
HL = (124, 214, 220)          # إبراز
DIML = (120, 134, 152)        # بُنى غير مُبرزة
SCLERA = (222, 227, 234)
CHOROID = (176, 108, 112)
RETINA = (130, 162, 190)
CORNEA = (150, 214, 218)

# Noto Sans Arabic أولاً: تغطية كاملة للعربية + اللاتينية + علامات الترقيم والرموز.
_ARABIC_FONTS_B = [
    "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
    "/root/video-factory/assets/fonts/NotoSansArabic-Bold.ttf",
    "/usr/share/fonts/truetype/optics/Cairo-Bold.ttf",
]
_ARABIC_FONTS_R = [
    "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
    "/root/video-factory/assets/fonts/NotoSansArabic-Regular.ttf",
    "/usr/share/fonts/truetype/optics/Cairo-Regular.ttf",
]
_LATIN_FONTS_B = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
_LATIN_FONTS_R = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def _pick(paths, size):
    for p in paths:
        try:
            if Path(p).exists():
                return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def af(size, bold=True):
    return _pick(_ARABIC_FONTS_B if bold else _ARABIC_FONTS_R, size)


def lf(size, bold=True):
    return _pick(_LATIN_FONTS_B if bold else _LATIN_FONTS_R, size)


def _ar(draw, xy, text, font, fill, anchor="ra"):
    draw.text(xy, text, font=font, fill=fill, anchor=anchor, direction="rtl", language="ar")


def _lat(draw, xy, text, font, fill, anchor="la"):
    draw.text(xy, text, font=font, fill=fill, anchor=anchor)


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


# ---------- خلفية نظيفة (تدرّج فقط) ----------
def _background(W, H):
    img = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(img)
    for y in range(H):
        d.line([(0, y), (W, y)], fill=_lerp(NAVY2, NAVY, y / H))
    # توهّج بيضاوي خفيف جداً خلف الرسم
    glow = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(glow)
    gd.ellipse((W * 0.22, H * 0.06, W * 0.80, H * 0.74), fill=26)
    try:
        from PIL import ImageFilter
        glow = glow.filter(ImageFilter.GaussianBlur(120))
    except Exception:
        pass
    tint = Image.new("RGB", (W, H), TEAL)
    img = Image.composite(tint, img, glow)
    return img


BAND_FRAC = 0.155   # شريط رفيع: مساحة سفلية للترجمة المحروقة


# ---------- مقطع العين ----------
_MUTE = {"sclera": (150, 158, 170), "choroid": (128, 96, 100), "retina": (96, 116, 140),
         "cornea": (110, 150, 154), "ciliary": (150, 128, 96), "iris": (108, 120, 138),
         "lens": (110, 128, 140), "optic": (120, 138, 158)}
_BRIGHT = {"sclera": (238, 242, 248), "choroid": (214, 128, 132), "retina": (150, 200, 236),
           "cornea": (150, 224, 228), "ciliary": (240, 196, 120), "iris": (176, 200, 140),
           "lens": (168, 224, 232), "optic": (220, 236, 180)}


_NORMAL = {"sclera": (206, 212, 222), "choroid": (180, 116, 120), "retina": (128, 158, 188),
           "cornea": (138, 194, 198), "ciliary": (200, 166, 108), "iris": (140, 156, 176),
           "lens": (150, 172, 186), "optic": (160, 178, 198)}


def draw_eye(d: ImageDraw.ImageDraw, cx, cy, R, hl: set):
    def c(name):
        if name in hl:
            return _BRIGHT[name]
        return _MUTE[name] if hl else _NORMAL[name]

    def wd(name, base):
        return base + 5 if name in hl else base

    # التجويف الزجاجي
    d.ellipse((cx - R, cy - R, cx + R, cy + R), fill=(24, 38, 58))
    # محور بصري خفيف
    d.line((cx - R - 70, cy, cx + R + 20, cy), fill=(58, 76, 98), width=1)

    a0, a1 = 128, 360 + 52   # فتحة أمامية للقرنية
    # الصلبة
    d.arc((cx - R, cy - R, cx + R, cy + R), a0, a1, fill=c("sclera"), width=wd("sclera", 12))
    # المشيمية
    d.arc((cx - R + 20, cy - R + 20, cx + R - 20, cy + R - 20), 150, 360 + 30, fill=c("choroid"), width=wd("choroid", 8))
    # الشبكية
    d.arc((cx - R + 36, cy - R + 36, cx + R - 36, cy + R - 36), 150, 360 + 30, fill=c("retina"), width=wd("retina", 7))

    # القرنية (انتفاخ أمامي)
    cr = int(R * 0.52)
    ccx = cx - R + int(cr * 0.58)
    d.arc((ccx - cr, cy - cr, ccx + cr, cy + cr), 120, 240, fill=c("cornea"), width=wd("cornea", 11))

    # الجسم الهدبي
    for s in (-1, 1):
        yy = cy + s * int(R * 0.42)
        xx = cx - R + int(R * 0.16)
        d.ellipse((xx - 16, yy - 12, xx + 16, yy + 12), fill=c("ciliary"))

    # العدسة
    lw, lh = int(R * 0.09), int(R * 0.24)
    lx = cx - int(R * 0.40)
    d.ellipse((lx - lw, cy - lh, lx + lw, cy + lh), outline=c("lens"), width=6)

    # القزحية (حجاب: قطعتان تتركان البؤبؤ)
    ix = cx - int(R * 0.50)
    pg = int(R * 0.10)
    d.line((ix, cy - int(R * 0.32), ix + 3, cy - pg), fill=c("iris"), width=wd("iris", 10))
    d.line((ix, cy + int(R * 0.32), ix + 3, cy + pg), fill=c("iris"), width=wd("iris", 10))

    # العصب البصري
    ox = cx + int(R * 0.90)
    d.polygon([(ox - 6, cy - int(R * 0.10)), (ox - 6, cy + int(R * 0.16)),
               (ox + 130, cy + int(R * 0.30)), (ox + 130, cy - int(R * 0.02))], fill=c("optic"))


def _leader(d, tx, ty, px, py, color):
    d.line((tx, ty, px, py), fill=color, width=2)
    d.ellipse((px - 4, py - 4, px + 4, py + 4), fill=color)


def _bullet(d, x, y, color, r=5):
    d.ellipse((x - r, y - r, x + r, y + r), fill=color)


def _arrow(d, x, y, color, w=26):
    d.line((x, y, x + w, y), fill=color, width=4)
    d.polygon([(x + w, y - 7), (x + w + 11, y), (x + w, y + 7)], fill=color)


# ---------- شريط سفلي رفيع (علامة + رمز المصدر فقط) ----------
def _caption_band(img, on_screen_text, source_codes):
    W, H = img.size
    d = ImageDraw.Draw(img, "RGBA")
    band = int(H * BAND_FRAC)
    d.rectangle((0, H - band, W, H), fill=(NAVY[0], NAVY[1], NAVY[2], 224))
    d.line((0, H - band, W, H - band), fill=(*TEAL, 255), width=2)
    _ar(d, (W - 44, H - band + 14), "منصة بوابة البصريات", af(20, False), SKY)
    _lat(d, (W - 44 - int(af(20, False).getlength("منصة بوابة البصريات")) - 130, H - band + 15), "OpticsGate", lf(19), SKY)
    if source_codes:
        s = source_codes if isinstance(source_codes, str) else " · ".join(source_codes)
        f = lf(17)
        _lat(d, (44, H - band + 16), s, f, SKY)


_SCENE = {
    1: (set(), "الأغلفة الثلاثة للعين"),
    2: ({"sclera", "cornea"}, "الغلاف الليفي"),
    3: ({"choroid", "ciliary", "iris"}, "الغلاف الوعائي"),
    4: ({"retina", "optic"}, "الغلاف العصبي - الشبكية"),
    5: ({"sclera", "cornea", "choroid", "retina"}, "تكامل الأغلفة"),
    6: (set(), "أهمية الفهم للممارس"),
    7: (set(), ""),
}


def render_scene(scene_no, on_screen_text="", source_codes="", size=(1920, 1080)):
    W, H = size
    scene_no = int(scene_no)
    img = _background(W, H)
    d = ImageDraw.Draw(img)
    band = int(H * BAND_FRAC)
    cx = int(W * 0.50)
    cy = int((H - band) * 0.50)
    R = int(min(W, (H - band)) * 0.34)

    hl, heading = _SCENE.get(scene_no, (set(), ""))

    if scene_no == 7:
        _ar(d, (W // 2 + 120, int(H * 0.30)), "بوابة البصريات", af(90), SKY, anchor="ma")
        _lat(d, (W // 2, int(H * 0.44)), "OpticsGate", lf(44), TEAL, anchor="ma")
        _ar(d, (W // 2, int(H * 0.56)), "معًا لبصريات أفضل", af(38, False), SKY, anchor="ma")
        _caption_band(img, on_screen_text, source_codes)
        return img

    # شريط علوي: الشعار يسار، العنوان يمين
    try:
        logo = Image.open("/root/video-factory/assets/brand/optics_gate_logo_lashes_only.png").convert("RGBA")
        lh = 54
        logo = logo.resize((int(logo.width * lh / logo.height), lh))
        img.paste(logo, (36, 22), logo)
        _lat(d, (36 + logo.width + 14, 30), "OpticsGate", lf(22), SKY)
    except Exception:
        _ar(d, (330, 28), "بوابة البصريات", af(24, False), SKY, anchor="ra")
    if heading:
        _ar(d, (W - 60, 24), heading, af(44), _BRIGHT["cornea"] if hl else SKY)
        hw = int(af(44).getlength(heading))
        d.line((W - 60 - hw, 84, W - 60, 84), fill=TEAL, width=3)

    draw_eye(d, cx, cy, R, hl)

    fL = af(30)
    if scene_no == 1:
        # نقاط على الأقواس الثلاثة عند زوايا متباعدة
        rows = [("الغلاف الليفي", SCLERA, R, 55),
                ("الغلاف الوعائي", CHOROID, R - 20, 35),
                ("الغلاف العصبي", RETINA, R - 36, 18)]
        for i, (t, col, rr, deg) in enumerate(rows):
            ang = math.radians(deg)
            px = cx + int(rr * math.cos(ang))
            py = cy - int(rr * math.sin(ang))
            yy = int(H * 0.20) + i * 74
            _ar(d, (W - 60, yy), t, fL, col)
            _leader(d, W - 74 - int(fL.getlength(t)), yy + 16, px, py, col)
        _ar(d, (W // 2, H - band - 56), "تحذير: محتوى تعليمي، لا يُستخدم للتشخيص أو العلاج", af(28), GOLD, anchor="ma")
    elif scene_no == 2:
        a = math.radians(115)
        _ar(d, (210, int(H * 0.15)), "الصلبة", fL, _BRIGHT["sclera"], anchor="la")
        _leader(d, 210, int(H * 0.15) + 16, cx + int(R * math.cos(a)), cy - int(R * math.sin(a)), HL)
        _ar(d, (210, int(H * 0.28)), "القرنية", fL, _BRIGHT["cornea"], anchor="la")
        _leader(d, 210, int(H * 0.28) + 16, cx - int(R * 0.86), cy - int(R * 0.18), HL)
        _ar(d, (W - 60, int(H * 0.17)), "الصلبة: صلابة العين وشكلها الكروي وحمايتها", af(25, False), SKY)
        _ar(d, (W - 60, int(H * 0.24)), "القرنية: نافذة شفافة تُدخل الضوء وتكسره", af(25, False), SKY)
    elif scene_no == 3:
        a = math.radians(150)
        for i, (t, pt) in enumerate([
            ("المشيمية", (cx + int((R - 20) * math.cos(a)), cy - int((R - 20) * math.sin(a)))),
            ("الجسم الهدبي", (cx - R + int(R * 0.16), cy - int(R * 0.42))),
            ("القزحية", (cx - int(R * 0.50), cy - int(R * 0.20)))]):
            yy = int(H * 0.15) + i * 62
            _ar(d, (200, yy), t, fL, _BRIGHT["choroid"] if i == 0 else HL, anchor="la")
            _leader(d, 200, yy + 16, pt[0], pt[1], HL)
        _ar(d, (W - 60, int(H * 0.16)), "تغذية الأنسجة وضبط كمية الضوء الداخلة", af(26, False), SKY)
    elif scene_no == 4:
        _ar(d, (200, int(H * 0.14)), "الشبكية", fL, HL, anchor="la")
        _leader(d, 200, int(H * 0.14) + 16, cx + int(R * 0.30), cy - int(R * 0.52), HL)
        _ar(d, (200, int(H * 0.26)), "العصب البصري", fL, HL, anchor="la")
        _leader(d, 200, int(H * 0.26) + 16, cx + int(R * 1.02), cy + int(R * 0.16), HL)
        bx, by = W - 560, int(H * 0.10)
        d.rounded_rectangle((bx, by, bx + 500, by + 170), radius=16, outline=HL, width=3, fill=(24, 40, 60))
        _ar(d, (bx + 476, by + 16), "مستقبِلات الضوء", af(27), WHITE)
        _ar(d, (bx + 476, by + 60), "العصيّات: للرؤية في الإضاءة الخافتة", af(22, False), SKY)
        _ar(d, (bx + 476, by + 100), "المخاريط: للألوان والتفاصيل الدقيقة", af(22, False), SKY)
    elif scene_no == 5:
        _arrow(d, cx - R - 100, cy, GOLD, w=70)
        _ar(d, (W - 60, int(H * 0.13)), "ليفي: صلابة وحماية", af(28), SCLERA)
        _ar(d, (W - 60, int(H * 0.21)), "وعائي: تغذية وضبط الضوء", af(28), CHOROID)
        _ar(d, (W - 60, int(H * 0.29)), "عصبي: استقبال الضوء وإرسال الإشارة", af(28), RETINA)
    elif scene_no == 6:
        bx, by = int(W * 0.10), int(H * 0.10)
        d.rounded_rectangle((bx, by, W - bx, by + 190), radius=18, outline=GOLD, width=3, fill=(26, 42, 62))
        _ar(d, (W - bx - 26, by + 20), "للممارس:", af(30), GOLD)
        _ar(d, (W - bx - 26, by + 68), "فهم التشريح يعني تقييماً أدق لسلامة بنية العين", af(25, False), WHITE)
        _ar(d, (W - bx - 26, by + 108), "عند فقدان الرؤية المفاجئ أو الألم الشديد:", af(24, False), SKY)
        _ar(d, (W - bx - 26, by + 144), "توجيه المريض إلى طبيب عيون فوراً", af(24, False), SKY)

    _caption_band(img, on_screen_text, source_codes)
    return img


if __name__ == "__main__":
    out = Path(os.environ.get("DIAG_OUT", "/tmp/diag"))
    out.mkdir(parents=True, exist_ok=True)
    demo = {
        1: "الأغلفة الثلاثة للعين\nتحذير: لا تُستخدم للتشخيص أو العلاج",
        2: "الغلاف الليفي: الصلبة + القرنية\n-> صلابة وشكل كروي وحماية",
        3: "الغلاف الوعائي\n• المشيمية\n• الجسم الهدبي\n• القزحية\n-> تغذية وضبط الضوء",
        4: "الغلاف العصبي - الشبكية\n• العصيّات\n• المخاريط\n-> تحويل الضوء إلى إشارات",
        5: "تكامل الأغلفة\nليفي -> وعائي -> عصبي",
        6: "أهمية الفهم للممارس\n• تقييم سلامة العين\n• إرشاد المريض عند الطوارئ",
        7: "شكراً لمتابعتكم\nلأي استفسار تواصلوا مع المدرب",
    }
    for n in range(1, 8):
        render_scene(n, demo[n], "B01-U01-C01-L01").save(out / f"scene{n}.png")
    print("done ->", out)
