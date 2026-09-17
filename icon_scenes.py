# -*- coding: utf-8 -*-
"""icon_scenes.py — نظام تركيب مشاهد بالأيقونات (الطبقة الأولى/Tier 1 من حل التوصيف
البصري المجاني، 2026-09-17). يستخدم مكتبة Health Icons (MIT، مجانية للأبد، بلا مفتاح
API وبلا حصة استخدام) — بديل عام يغطي كل موضوعات المنهج (تشريح، أجهزة، تخصصات، حالات
سريرية)، مش بس الهندسة البصرية زي optics_diagrams.py.

الفكرة مطابقة لبصمة كارتيسيا الصوتية: تحميل مرة واحدة (تم فعلاً — 749 أيقونة SVG محليًا
تحت assets/icons/healthicons/outline)، ثم استخدام حر ومجاني للأبد بعد كده.

الواجهة: render_icon_scene(scene: dict) -> PIL.Image | None
scene["diagram"] == "icon_scene"
scene["icon_spec"] = {
    "items": [{"icon": "body/eye", "label": "العين"}, {"icon": "devices/eyeglasses", "label": "النظارة"}],
    "caption": "نص اختياري أسفل الأيقونات",
}
يرجع None لو أي أيقونة مش موجودة في القائمة المعتمدة ALLOWED_ICONS (فيسقط render_scene
في eye_scene2.py للرسم الاحتياطي الآمن) — منعًا لأي اسم أيقونة يتم اختراعه من الموديل.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from eye_scene2 import _bg, _header, _footer, _f, _plain, GOLD, INK, DIM, W, H, AR_BOLD

ICONS_ROOT = Path(__file__).parent / "assets" / "icons" / "healthicons" / "outline"

# قائمة معتمدة من الأيقونات ذات الصلة بمنهج البصريات/طب وعلوم العيون -- أي اسم مش هنا
# يترفض بأمان (مفيش اختراع أسماء ملفات من الموديل).
ALLOWED_ICONS = {
    "body/eye", "body/ear", "body/head", "body/skull", "body/nerve", "body/neurology",
    "devices/eyeglasses", "devices/contact-lenses", "devices/microscope",
    "devices/microscope-with_specimen", "devices/stethoscope", "devices/thermometer",
    "devices/thermometer-digital", "devices/medicine-bottle", "devices/medicine-mortar",
    "devices/syringe", "devices/ultrasound-scanner", "devices/xray", "devices/cane",
    "devices/wheelchair", "devices/hearing-aid", "devices/diabetes-measure",
    "conditions/dry-eyes", "conditions/low-vision", "conditions/headache",
    "conditions/allergies", "conditions/thyroid-cancer", "conditions/pain",
    "specialties/opthalmology", "specialties/ears-nose_and_throat", "specialties/pediatrics",
    "specialties/geriatrics", "specialties/pharmacy", "specialties/radiology",
    "symbols/magnifying-glass", "symbols/ui-zoom", "symbols/ui-zoom_in", "symbols/ui-zoom_out",
    "symbols/alert", "symbols/alert-circle", "symbols/alert-triangle", "symbols/info",
    "symbols/question", "symbols/question-circle", "symbols/yes", "symbols/no",
    "symbols/positive", "symbols/negative", "symbols/cancel", "symbols/health",
    "symbols/medical-advice", "symbols/medical-search", "symbols/lab-search", "symbols/rx",
    "symbols/pharmacy", "symbols/diabetes", "symbols/height", "symbols/guide-dog",
    "objects/book", "objects/calendar", "objects/prescription-document", "objects/laptop",
    "objects/phone",
    "people/doctor", "people/doctor-female", "people/doctor-male", "people/nurse",
    "people/old-man", "people/old-woman", "people/elderly", "people/regular-patient",
    "people/man", "people/woman", "people/person", "people/people",
    "emotions/eyeglasses", "emotions/happy", "emotions/sad", "emotions/confused",
    "emotions/calm", "emotions/dizzy",
}

_CACHE: dict[tuple[str, str, int], "Image.Image | None"] = {}


def _rasterize_icon(icon_id: str, color_hex: str = "#D6B25C", px: int = 480) -> "Image.Image | None":
    key = (icon_id, color_hex, px)
    if key in _CACHE:
        return _CACHE[key]
    svg_path = ICONS_ROOT / f"{icon_id}.svg"
    if not svg_path.exists():
        _CACHE[key] = None
        return None
    raw = svg_path.read_text(encoding="utf-8")
    raw = raw.replace("currentColor", color_hex)
    with tempfile.TemporaryDirectory() as td:
        tmp_svg = Path(td) / "icon.svg"
        tmp_png = Path(td) / "icon.png"
        tmp_svg.write_text(raw, encoding="utf-8")
        try:
            subprocess.run(
                ["rsvg-convert", "-w", str(px), "-h", str(px), "-o", str(tmp_png), str(tmp_svg)],
                check=True, capture_output=True, timeout=15,
            )
            img = Image.open(tmp_png).convert("RGBA")
            img.load()
        except Exception as e:
            print(f"[icon_scenes] فشل رسترة الأيقونة {icon_id}: {e}", flush=True)
            img = None
    _CACHE[key] = img
    return img


def _chip(d: "ImageDraw.ImageDraw", cx: int, cy: int, r: int):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(20, 34, 58, 235), outline=GOLD, width=4)


def render_icon_scene(scene: dict):
    spec = scene.get("icon_spec") or {}
    items = [it for it in (spec.get("items") or []) if it.get("icon") in ALLOWED_ICONS][:6]
    if not items:
        return None

    imgs = []
    for it in items:
        icon_img = _rasterize_icon(it["icon"])
        if icon_img is None:
            return None
        imgs.append((icon_img, it.get("label", "")))

    img = _bg()
    _header(img, scene.get("heading") or "", scene.get("term_en") or "")
    d = ImageDraw.Draw(img, "RGBA")

    n = len(imgs)
    r = 130 if n <= 3 else 105
    icon_px = int(r * 1.15)
    label_font = _f(AR_BOLD, 34 if n <= 3 else 28)

    if n <= 3:
        cols, rows = n, 1
    else:
        cols, rows = (3, 2) if n <= 6 else (n, 1)

    area_top, area_bot = 260, H - 190
    area_cy = (area_top + area_bot) // 2
    col_w = W // (cols + 1)
    row_h = (area_bot - area_top) // rows

    for i, (icon_img, label) in enumerate(imgs):
        col, row = i % cols, i // cols
        cx = col_w * (col + 1)
        cy = area_top + row_h * row + row_h // 2 if rows > 1 else area_cy
        _chip(d, cx, cy, r)
        ic = icon_img.resize((icon_px, icon_px), Image.LANCZOS)
        img.paste(ic, (cx - icon_px // 2, cy - icon_px // 2), ic)
        if label:
            d.text((cx, cy + r + 36), _plain(label), font=label_font, fill=INK, anchor="mm", language="ar")

    caption = spec.get("caption")
    if caption:
        d.text((W // 2, H - 130), _plain(caption), font=_f(AR_BOLD, 30), fill=DIM, anchor="mm", language="ar")

    _footer(img, scene.get("source_codes") or "")
    return img
