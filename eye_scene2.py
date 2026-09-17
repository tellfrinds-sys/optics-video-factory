# -*- coding: utf-8 -*-
"""
eye_scene2.py — مُصيّر مشاهد فيديو «العين البشرية ومكوناتها».

يستخدم مقطعًا تشريحيًا واقعيًا للعين (Wikimedia، ملكية عامة) ويضيف فوقه:
- إطار وهوية «بوابة البصريات».
- عنوان المشهد.
- مسميات الأجزاء بخطوط إشارة (leader lines) إلى النقاط التشريحية الصحيحة،
  مع توهّج على كل نقطة يُبرزها عند ذِكرها.

الواجهة:  render_scene(scene: dict, size=(1920,1080)) -> PIL.Image
"""
from __future__ import annotations

import base64
import hashlib
import json as _json
import math
import os
import re
import unicodedata
import urllib.error as _urlerr
import urllib.request as _urlreq
from pathlib import Path

_TASHKEEL = re.compile("[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06DC\u06DF-\u06E8\u06EA-\u06ED\u0640]")


def _plain(s: str) -> str:
    """يزيل التشكيل والتطويل والأقواس — للعناوين والمسميات فقط (النطق يبقى مُشكَّلًا)."""
    s = unicodedata.normalize("NFC", str(s or ""))
    s = _TASHKEEL.sub("", s)
    return s.replace("(", "").replace(")", "").replace("  ", " ").strip()

from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(os.environ.get("OPTICSGATE_FACTORY_ROOT", Path(__file__).resolve().parent)).resolve()
ASSETS = ROOT / "assets"
EYE_PNG = ASSETS / "anatomy" / "eye_final.png"
LOGO_PNG = ASSETS / "brand" / "optics_gate_logo_transparent.png"  # نسخة بخلفية شفافة فعليًا (الأصلية كانت بيضاء صلبة رغم RGBA -- ظهرت كصندوق أبيض، لوحظ 2026-09-17)

# توليد صور Gemini (للمشاهد غير التشريحية الأساسية — ليس بديلًا عن رسم العين/القرنية المُعايَر)
GENERATED_DIR = ASSETS / "generated" / "gemini"
GEMINI_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

if not GEMINI_API_KEY:
    _envf = ROOT / "pipeline" / ".env"
    if _envf.exists():
        for _ln in _envf.read_text().splitlines():
            if _ln.strip().startswith("GEMINI_API_KEY="):
                GEMINI_API_KEY = _ln.split("=", 1)[1].strip()
                break

AR_BOLD = "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf"
AR_REG = "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"
LAT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
LAT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# ألوان الهوية
BG_TOP = (11, 22, 40)
BG_BOT = (6, 13, 26)
GOLD = (214, 178, 92)
INK = (243, 246, 250)
DIM = (150, 165, 185)
GLOW = (255, 209, 122)

W, H = 1920, 1080

# صندوق صورة العين — موسّط أفقيًا مع مِزراب يمين ويسار للمسميات
EYE_W, EYE_H = 740, 842
EYE_X, EYE_Y = (W - EYE_W) // 2, 156

# نقاط التوصيل التشريحية — كسور من صندوق صورة العين (fx, fy)
ANCHORS = {
    "eye_whole": (0.50, 0.50),
    "cornea":    (0.50, 0.05),
    "sclera":    (0.90, 0.34),
    "iris":      (0.40, 0.135),
    "pupil":     (0.50, 0.132),
    "ciliary":   (0.605, 0.115),
    "choroid":   (0.905, 0.46),
    "retina":    (0.875, 0.60),
    "fovea":     (0.55, 0.775),
    "disc":      (0.32, 0.745),
    "nerve":     (0.24, 0.90),
    "chamber":   (0.50, 0.088),
    "lens":      (0.50, 0.185),
    "zonules":   (0.63, 0.16),
    "vitreous":  (0.50, 0.55),
    "muscle":    (0.09, 0.26),
}

_FCACHE: dict = {}


def _f(path, size):
    key = (path, size)
    if key not in _FCACHE:
        _FCACHE[key] = ImageFont.truetype(path, size)
    return _FCACHE[key]

_LATIN_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_./+]*$")


def _draw_mixed(d, x, y, text, ar_path, lat_path, size, fill, anchor="rm"):
    """يرسم نص ممكن يحتوي على كلمات لاتينية مفردة (A، DBL، PDC...) وسط عربي --
    الخط العربي (Noto Naskh) مالوش حروف لاتينية فبتظهر كصندوق فارغ لو اتجاهلت (لوحظ
    فعليًا 2026-09-17 في عنوان مشهد وتسميات labels). بيرسم كل كلمة بالخط المناسب.
    anchor[0]: 'r' (يمين، الكلمات من اليمين لليسار بترتيب النص -- تقريب RTL) أو
    'l' (يسار، الكلمات من الشمال لليمين بنفس الترتيب) أو 'm' (وسط، معاملة كـ r).
    anchor[1]: محاذاة رأسية عادية (m/t/...). يرجع العرض الكلي بالبكسل.
    """
    tokens = str(text or "").split()
    if not tokens:
        return 0
    runs = []
    for tok in tokens:
        font = _f(lat_path, size) if _LATIN_TOKEN.match(tok) else _f(ar_path, size)
        is_lat = _LATIN_TOKEN.match(tok) is not None
        bbox = d.textbbox((0, 0), tok, font=font, anchor="lt",
                          **({} if is_lat else {"language": "ar"}))
        runs.append((tok, font, is_lat, bbox[2] - bbox[0]))
    gap = size * 0.28
    total_w = sum(w for *_r, w in runs) + gap * (len(runs) - 1)
    va = anchor[1] if len(anchor) > 1 else "m"
    if anchor[0] == "l":
        cursor = x
        for tok, font, is_lat, w in runs:
            d.text((cursor, y), tok, font=font, fill=fill, anchor="l" + va,
                   **({} if is_lat else {"language": "ar"}))
            cursor += w + gap
    else:
        start_right = x if anchor[0] == "r" else x + total_w / 2
        cursor = start_right
        for tok, font, is_lat, w in runs:
            d.text((cursor, y), tok, font=font, fill=fill, anchor="r" + va,
                   **({} if is_lat else {"language": "ar"}))
            cursor -= w + gap
    return total_w


def _pollinations_generate_image(prompt: str, cache_key: str) -> "Path | None":
    """يولّد صورة عبر Pollinations.ai — مجاني بالكامل، بلا مفتاح API وبلا فوترة
    (2026-09-17، بديل عن Gemini بعد نفاد الرصيد المدفوع مرارًا). حد الاستخدام المجهول:
    نداء كل 15 ثانية تقريبًا، وده متوافق تمامًا مع عدد صور الدرس الواحد. فيها علامة مائية
    صغيرة لحد ما يتسجَّل حساب مجاني على auth.pollinations.ai (خطوة يعملها المسؤول بنفسه)."""
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    dest = GENERATED_DIR / f"{cache_key}.png"
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    import urllib.parse as _uparse
    url = ("https://image.pollinations.ai/prompt/" + _uparse.quote(prompt) +
           "?width=1600&height=900&nologo=true&model=flux")
    try:
        with _urlreq.urlopen(url, timeout=60) as resp:
            raw = resp.read()
        dest.write_bytes(raw)
        if dest.stat().st_size < 1000:
            dest.unlink(missing_ok=True)
            return None
        return dest
    except Exception as e:
        print(f"[eye_scene2] Pollinations image generation failed: {e}", flush=True)
        return None


def _gemini_generate_image(prompt: str, cache_key: str) -> "Path | None":
    """احتياطي ثانوي فقط (مدفوع/محدود الحصة) — يُستخدم بس لو Pollinations فشل ولو مفتاح
    Gemini شغّال أصلًا. لا استثناء يُرفَع أبدًا هنا — الاحتياطي الآمن الأخير هو رسم العين
    الافتراضي في render_scene."""
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    dest = GENERATED_DIR / f"{cache_key}.png"
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    if not GEMINI_API_KEY:
        return None
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}")
    body = _json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
    req = _urlreq.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with _urlreq.urlopen(req, timeout=45) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
        parts = data["candidates"][0]["content"]["parts"]
        img_b64 = next(p["inlineData"]["data"] for p in parts if "inlineData" in p)
        raw = base64.b64decode(img_b64)
        dest.write_bytes(raw)
        return dest
    except Exception as e:
        print(f"[eye_scene2] Gemini image generation failed: {e}", flush=True)
        return None


def _generate_scene_image(prompt: str, cache_key: str) -> "Path | None":
    """نقطة الدخول الموحّدة لتوليد صورة مشهد: Pollinations (مجاني) أولًا، Gemini
    (مدفوع/احتياطي) لو فشل، وإلا None فيسقط render_scene لرسم العين الافتراضي الآمن."""
    return _pollinations_generate_image(prompt, cache_key) or _gemini_generate_image(prompt, cache_key)


def _bg() -> Image.Image:
    img = Image.new("RGB", (W, H), BG_BOT)
    top = Image.new("RGB", (W, H), BG_TOP)
    mask = Image.new("L", (1, H))
    for y in range(H):
        mask.putpixel((0, y), int(255 * (1 - y / H) ** 1.4))
    img.paste(top, (0, 0), mask.resize((W, H)))
    # لمسة توهّج خفيفة خلف العين
    d = ImageDraw.Draw(img, "RGBA")
    cx, cy = EYE_X + EYE_W // 2, EYE_Y + EYE_H // 2
    for r, a in ((520, 14), (380, 18), (240, 22)):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(90, 130, 190, a))
    return img


def _eye_img() -> Image.Image:
    im = Image.open(EYE_PNG).convert("RGBA")
    return im.resize((EYE_W, EYE_H), Image.LANCZOS)


def _anchor_xy(key):
    fx, fy = ANCHORS.get(key, (0.5, 0.5))
    return (EYE_X + fx * EYE_W, EYE_Y + fy * EYE_H)


def _ar(d, xy, text, font, fill, anchor="ra"):
    d.text(xy, text, font=font, fill=fill, anchor=anchor,
           language="ar", features=["-liga"] if False else None)


def _pill(d, cx, cy, text, font, fg=INK, bg=(17, 30, 52, 235), pad=(20, 12)):
    """font: كائن ImageFont (زي _f(AR_BOLD, 33)) -- بنستخرج المقاس منه ونرسم بخط
    مختلط عربي/لاتيني عبر _draw_mixed (بعض المسمّيات بتحتوي حروف لاتينية مفردة زي
    'القياس A' -- الخط العربي مالوش حروف لاتينية، لوحظ فعليًا 2026-09-17)."""
    size = getattr(font, "size", 33)
    l, t, r, b = d.textbbox((0, 0), text, font=font, anchor="lt", language="ar")
    th = b - t
    tokens = str(text or "").split() or [text]
    gap = size * 0.28
    widths = []
    for tok in tokens:
        is_lat = _LATIN_TOKEN.match(tok) is not None
        fnt2 = _f(LAT_B, size) if is_lat else font
        bb = d.textbbox((0, 0), tok, font=fnt2, anchor="lt", **({} if is_lat else {"language": "ar"}))
        widths.append(bb[2] - bb[0])
    tw = sum(widths) + gap * (len(widths) - 1)
    x0, y0 = cx - tw / 2 - pad[0], cy - th / 2 - pad[1]
    x1, y1 = cx + tw / 2 + pad[0], cy + th / 2 + pad[1]
    d.rounded_rectangle([x0, y0, x1, y1], radius=14, fill=bg, outline=GOLD, width=2)
    _draw_mixed(d, cx, cy, text, AR_BOLD, LAT_B, size, fg, anchor="mm")
    return (x0, y0, x1, y1)


def _header(img, heading, term_en=""):
    d = ImageDraw.Draw(img, "RGBA")
    try:
        logo = Image.open(LOGO_PNG).convert("RGBA")
        lh = 84
        logo = logo.resize((int(logo.width * lh / logo.height), lh), Image.LANCZOS)
        img.paste(logo, (54, 40), logo)
        lx = 54 + logo.width + 16
    except Exception:
        lx = 60
    d.text((lx, 82), "بوابة البصريات", font=_f(AR_BOLD, 34), fill=GOLD, anchor="lm", language="ar")
    heading = _plain(heading)
    if heading:
        hw = _draw_mixed(d, W - 60, 70, heading, AR_BOLD, LAT_B, 40, INK, anchor="rm")
        d.line([(W - 60 - hw, 70 + 27), (W - 60, 70 + 27)], fill=GOLD, width=3)
        if term_en:
            d.text((W - 60, 70 + 50), str(term_en), font=_f(LAT, 24), fill=GOLD, anchor="rm")
    d.line([(54, 150), (W - 54, 150)], fill=(255, 255, 255, 26), width=1)


def _footer(img, code):
    d = ImageDraw.Draw(img, "RGBA")
    d.line([(54, H - 70), (W - 54, H - 70)], fill=(255, 255, 255, 26), width=2)
    d.text((60, H - 44), "أكاديمية بوابة البصريات",
           font=_f(AR_REG, 24), fill=DIM, anchor="lm", language="ar")
    if code:
        d.text((W - 60, H - 44), code, font=_f(LAT, 22), fill=DIM, anchor="rm")


def _glow_dot(img, x, y, on=True):
    d = ImageDraw.Draw(img, "RGBA")
    if on:
        g = Image.new("RGBA", (140, 140), (0, 0, 0, 0))
        gd = ImageDraw.Draw(g)
        gd.ellipse([20, 20, 120, 120], fill=(255, 209, 122, 120))
        g = g.filter(ImageFilter.GaussianBlur(14))
        img.paste(g, (int(x - 70), int(y - 70)), g)
        d.ellipse([x - 9, y - 9, x + 9, y + 9], fill=GLOW, outline=(255, 255, 255, 230), width=2)
    else:
        d.ellipse([x - 6, y - 6, x + 6, y + 6], fill=(210, 220, 235, 120))


def _place_labels(labels):
    """يحسب موضع كل بطاقة مسمّى بدفعها بعيدًا عن مركز العين ثم فضّ التداخل الرأسي."""
    cx, cy = EYE_X + EYE_W / 2, EYE_Y + EYE_H / 2
    out = []
    for name, key in labels:
        ax, ay = _anchor_xy(key)
        dx, dy = ax - cx, ay - cy
        n = math.hypot(dx, dy) or 1.0
        ux, uy = dx / n, dy / n
        ly = ay + uy * 150
        # ادفع البطاقات إلى المِزراب الجانبي (يمين/يسار الإطار، خارج صورة العين)
        lx = W - 250 if ax >= cx else 250
        ly = max(230, min(H - 190, ly))
        out.append([name, key, ax, ay, lx, ly])
    # فضّ التداخل الرأسي داخل كل عمود
    for side in (0, 1):
        col = [o for o in out if (o[4] > W / 2) == side]
        col.sort(key=lambda o: o[5])
        gap = 92 if len(col) <= 3 else 78
        for i in range(1, len(col)):
            if col[i][5] - col[i - 1][5] < gap:
                col[i][5] = col[i - 1][5] + gap
        # لو تجاوز العمود الحدّ السفلي، ارفع الكل لأعلى
        if col and col[-1][5] > H - 190:
            shift = col[-1][5] - (H - 190)
            for o in col:
                o[5] -= shift
    return out




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


def render_scene(scene: dict, size=(W, H)) -> Image.Image:
    sc = int(scene.get("scene_no") or 1)
    heading = scene.get("heading") or ""
    labels = scene.get("labels") or []
    code = scene.get("source_codes") or ""

    img = _bg()

    # مشهد الشعار الختامي (يُطلب صراحةً عبر kind=="outro")
    if scene.get("kind") == "outro":
        d = ImageDraw.Draw(img, "RGBA")
        try:
            logo = Image.open(LOGO_PNG).convert("RGBA")
            lh = 360
            logo = logo.resize((int(logo.width * lh / logo.height), lh), Image.LANCZOS)
            img.paste(logo, ((W - logo.width) // 2, 210), logo)
        except Exception:
            pass
        d.text((W / 2, 640), "بوابة البصريات", font=_f(AR_BOLD, 78), fill=GOLD, anchor="mm", language="ar")
        d.text((W / 2, 740), "فتابِعونا", font=_f(AR_BOLD, 52), fill=INK, anchor="mm", language="ar")
        _footer(img, code)
        return img

    # رسم برمجي بالكامل (بلا API) لمخططات البصريات الهندسية -- عدسات/أشعة/منشور/أخطاء
    # انكسارية/قياسات إطار/PD -- بديل مجاني ودقيق هندسيًا عن gemini_custom لمحتوى مسار
    # التوصيف البصري (2026-09-17). راجع optics_diagrams.py.
    if sc != 1 and scene.get("kind") not in ("title", "outro"):
        import optics_diagrams
        _od_img = optics_diagrams.render_optics_diagram(scene)
        if _od_img is not None:
            return _od_img

    # مشاهد مركّبة بالأيقونات (Health Icons، MIT، مجانية للأبد) -- تغطي عمومًا كل
    # موضوعات المنهج (تشريح/أجهزة/تخصصات) مش بس الهندسة البصرية (2026-09-17).
    if scene.get("diagram") == "icon_scene" and sc != 1 and scene.get("kind") not in ("title", "outro"):
        import icon_scenes
        _is_img = icon_scenes.render_icon_scene(scene)
        if _is_img is not None:
            return _is_img

    # رسم متخصّص: مقطع القرنية وطبقاتها
    if scene.get("diagram") == "cornea_layers" and sc != 1 and scene.get("kind") not in ("title", "outro"):
        _header(img, heading, scene.get("term_en") or "")
        keys = [k for (_n, k) in labels if k in {"tearfilm", "epithelium", "bowman", "stroma", "descemet", "endothelium"}]
        _draw_cornea_layers(img, keys)
        _footer(img, code)
        return img

    # رسم عام مُولَّد عبر Gemini — لمشاهد غير تشريحية أساسية (لا تمسّ رسم العين/القرنية المُعايَر)
    if (scene.get("diagram") == "gemini_custom" and scene.get("visual_prompt")
            and sc != 1 and scene.get("kind") not in ("title", "outro")):
        prompt = (str(scene["visual_prompt"]).strip() +
                  ", simple flat educational illustration, clean plain background, "
                  "professional optics/medical textbook style, no text, no words, no letters, "
                  "no labels, no watermark, high detail")
        cache_key = hashlib.md5(prompt.encode("utf-8")).hexdigest()[:16]
        gen_path = _generate_scene_image(prompt, cache_key)
        if gen_path is not None:
            try:
                gi = Image.open(gen_path).convert("RGBA")
                _header(img, heading, scene.get("term_en") or "")
                box_w, box_h = 1500, 760
                gi.thumbnail((box_w, box_h), Image.LANCZOS)
                gx = (W - gi.width) // 2
                gy = 180 + (box_h - gi.height) // 2
                d = ImageDraw.Draw(img, "RGBA")
                pad = 18
                d.rounded_rectangle([gx - pad, gy - pad, gx + gi.width + pad, gy + gi.height + pad],
                                     radius=18, fill=(255, 255, 255, 235), outline=GOLD, width=3)
                img.paste(gi, (gx, gy), gi)
                if labels:
                    ly = gy + gi.height + pad + 46
                    names = [_plain(n) for (n, _k) in labels]
                    d.text((W / 2, ly), "،  ".join(names), font=_f(AR_BOLD, 28),
                           fill=INK, anchor="mm", language="ar")
                _footer(img, code)
                return img
            except Exception as e:
                print(f"[eye_scene2] failed to composite generated image: {e}", flush=True)
                # يسقط إلى الرسم الافتراضي أدناه (احتياطي آمن)

    # مشهد العنوان (المشهد الأول أو kind=="title") — يعرض العنوان الفعلي للحلقة.
    # ملحوظة (2026-09-17، مراجعة بشرية مباشرة): كان بيتعرض رسم العين التشريحي هنا
    # دايمًا بغض النظر عن موضوع الدرس -- غريب/بلا معنى لدروس مش عن تشريح العين (زي
    # قياسات الإطار)، وكمان ثابت فعليًا في كل عنوان بلا استثناء طول المشروع. استُبدل
    # بشعار العلامة (زي مشهد الختام) بدل رسم تشريحي مُقحَم على موضوع مش دايمًا مناسب له.
    if sc == 1 or scene.get("kind") == "title":
        d = ImageDraw.Draw(img, "RGBA")
        try:
            logo = Image.open(LOGO_PNG).convert("RGBA")
            lh = 300
            logo = logo.resize((int(logo.width * lh / logo.height), lh), Image.LANCZOS)
            img.paste(logo, ((W - logo.width) // 2, 150), logo)
        except Exception:
            pass
        words = _plain(heading).split()
        if len(words) >= 3:
            cut = (len(words) + 1) // 2
            l1, l2 = " ".join(words[:cut]), " ".join(words[cut:])
        else:
            l1, l2 = heading, ""
        d.text((W / 2, 560), l1, font=_f(AR_BOLD, 70), fill=INK, anchor="mm", language="ar")
        if l2:
            d.text((W / 2, 648), l2, font=_f(AR_BOLD, 70), fill=GOLD, anchor="mm", language="ar")
        d.line([(W / 2 - 420, 700), (W / 2 + 420, 700)], fill=GOLD, width=3)
        for i, ln in enumerate(scene.get("subtitle_lines") or []):
            d.text((W / 2, 750 + i * 52), ln, font=_f(AR_REG, 32), fill=DIM, anchor="mm", language="ar")
        _footer(img, code)
        return img

    # صورة العين -- للمشاهد التشريحية العامة بس (بعد استبعاد مشهد العنوان أعلاه)
    eye = _eye_img()
    img.paste(eye, (EYE_X, EYE_Y), eye)

    _header(img, heading, scene.get("term_en") or "")

    # المسميات + خطوط الإشارة
    placed = _place_labels(labels)
    d = ImageDraw.Draw(img, "RGBA")
    fnt = _f(AR_BOLD, 33)
    for name, key, ax, ay, lx, ly in placed:
        txt = _plain(name)
        tb = d.textbbox((0, 0), txt, font=fnt, anchor="lt", language="ar")
        half = (tb[2] - tb[0]) / 2 + 22
        edge = lx + half if lx < ax else lx - half
        d.line([(ax, ay), (edge, ly)], fill=(255, 209, 122, 210), width=3)
    for name, key, ax, ay, lx, ly in placed:
        _glow_dot(img, ax, ay, on=True)
    for name, key, ax, ay, lx, ly in placed:
        _pill(d, lx, ly, _plain(name), fnt)

    _footer(img, code)
    return img


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT))
    import corrected_scenes as cs
    for s in cs.SCENES:
        render_scene(s).save(f"/tmp/scene_{s['scene_no']}.png")
        print("scene", s["scene_no"], "ok")
