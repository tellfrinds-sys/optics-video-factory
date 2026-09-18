# -*- coding: utf-8 -*-
"""optics_diagrams.py -- رسم مخططات بصريات تقنية (عدسات/أشعة/منشور/أخطاء انكسارية/قياسات
إطار/المسافة بين الحدقتين) برمجيًا بالكامل عبر PIL، بلا أي استدعاء API مدفوع أو محدود
الحصة. بديل مجاني ودقيق لـ gemini_custom لمحتوى «بوابة البصريات» في مسار البصريات
الهندسي والتوصيف (مسار B02 فصاعدًا) -- محتوى هندسي بطبيعته، فالرسم البرمجي أدق من أي
صورة مولَّدة بالذكاء الاصطناعي (لا مجال لخطأ تشريحي/هندسي).

الواجهة: render_optics_diagram(scene: dict) -> PIL.Image | None
يرجع None لو diagram_type غير معروف (فيسقط render_scene في eye_scene2.py للرسم الافتراضي).
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

from eye_scene2 import (
    _bg, _header, _footer, _f, _plain, _pill, _draw_mixed,
    GOLD, INK, DIM, GLOW, W, H, AR_BOLD, AR_REG, LAT, LAT_B,
)

LINE = (120, 160, 210, 200)
AXIS = (255, 255, 255, 60)
RAY = (255, 209, 122, 230)


def _draw_convex_lens(d, cx, cy, half_h, thickness=26, color=(180, 210, 235, 90)):
    bulge = thickness
    d.ellipse([cx - bulge, cy - half_h, cx + bulge, cy + half_h], fill=color, outline=GOLD, width=3)


def _draw_concave_lens(d, cx, cy, half_h, thickness=22, color=(180, 210, 235, 90)):
    w = 18
    d.rectangle([cx - w, cy - half_h, cx + w, cy + half_h], fill=color, outline=GOLD, width=3)
    d.ellipse([cx - w - thickness, cy - half_h - 14, cx + w - thickness, cy + half_h + 14], fill=(6, 13, 26, 255))
    d.ellipse([cx - w + thickness, cy - half_h - 14, cx + w + thickness, cy + half_h + 14], fill=(6, 13, 26, 255))
    d.line([(cx, cy - half_h), (cx, cy + half_h)], fill=GOLD, width=3)


def _arrow(d, p0, p1, color=RAY, width=4, head=12):
    d.line([p0, p1], fill=color, width=width)
    ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    for da in (2.5, -2.5):
        a = ang + math.pi - da * 0.4
        d.line([p1, (p1[0] + head * math.cos(a), p1[1] + head * math.sin(a))], fill=color, width=width)


def _lens_ray_diagram(scene) -> Image.Image:
    spec = scene.get("diagram_spec") or {}
    lens_type = spec.get("lens_type", "convex")
    img = _bg()
    _header(img, scene.get("heading") or "", scene.get("term_en") or "")
    d = ImageDraw.Draw(img, "RGBA")
    cx, cy = W // 2, H // 2 + 30
    half_h = 260
    d.line([(cx - 560, cy), (cx + 560, cy)], fill=AXIS, width=2)

    if lens_type == "convex":
        _draw_convex_lens(d, cx, cy, half_h)
        f = 300
        for dy in (-140, -70, 0, 70, 140):
            _arrow(d, (cx - 520, cy + dy), (cx - 6, cy + dy))
            _arrow(d, (cx + 6, cy + dy), (cx + f, cy))
        d.ellipse([cx + f - 7, cy - 7, cx + f + 7, cy + 7], fill=GLOW, outline=INK, width=2)
        d.text((cx + f, cy + 26), "F", font=_f(LAT_B, 30), fill=GOLD, anchor="mm")
        d.text((cx, cy + half_h + 50), "عَدَسَة مُحَدَّبَة تَجْمِيعِيَّة", font=_f(AR_BOLD, 34), fill=INK, anchor="mm", language="ar")
    else:
        _draw_concave_lens(d, cx, cy, half_h)
        f = 260
        for dy in (-140, -70, 0, 70, 140):
            _arrow(d, (cx - 520, cy + dy), (cx - 20, cy + dy))
            if dy != 0:
                ext_dy = dy * (1 + (260 / f))
                d.line([(cx + 20, cy + dy * 0.15), (cx + 480, cy + ext_dy)], fill=RAY, width=4)
                d.line([(cx - f, cy), (cx + 20, cy + dy * 0.15)], fill=(255, 209, 122, 90), width=2)
            else:
                _arrow(d, (cx + 20, cy), (cx + 480, cy))
        d.ellipse([cx - f - 7, cy - 7, cx - f + 7, cy + 7], fill=GLOW, outline=INK, width=2)
        d.text((cx - f, cy + 26), "F", font=_f(LAT_B, 30), fill=GOLD, anchor="mm")
        d.text((cx, cy + half_h + 50), "عَدَسَة مُقَعَّرَة مُفَرِّقَة", font=_f(AR_BOLD, 34), fill=INK, anchor="mm", language="ar")

    _footer(img, scene.get("source_codes") or "")
    return img


def _prism_diagram(scene) -> Image.Image:
    img = _bg()
    _header(img, scene.get("heading") or "", scene.get("term_en") or "")
    d = ImageDraw.Draw(img, "RGBA")
    cx, cy = W // 2, H // 2 + 60
    apex = (cx, cy - 220)
    base_l = (cx - 220, cy + 140)
    base_r = (cx + 220, cy + 140)
    d.polygon([apex, base_l, base_r], fill=(180, 210, 235, 80), outline=GOLD, width=4)
    d.text((cx, cy + 180), "القاعِدَة", font=_f(AR_BOLD, 28), fill=DIM, anchor="mm", language="ar")
    d.text((apex[0], apex[1] - 30), "القِمَّة", font=_f(AR_BOLD, 28), fill=DIM, anchor="mm", language="ar")

    hit = (cx - 60, cy - 20)
    _arrow(d, (cx - 480, cy - 220), hit)
    out_dir = (cx + 520, cy + 60)
    _arrow(d, hit, out_dir)
    d.line([(hit[0] - 90, hit[1] + 40), (hit[0] + 90, hit[1] - 40)], fill=(255, 255, 255, 60), width=2)
    d.arc([hit[0] - 60, hit[1] - 60, hit[0] + 60, hit[1] + 60], start=-20, end=35, fill=GOLD, width=3)
    d.text((hit[0] + 70, hit[1] - 55), "زَاوِيَة الاِنْحِرَاف", font=_f(AR_BOLD, 26), fill=GOLD, anchor="lm", language="ar")
    d.text((cx, H - 150), "الشُّعَاع بِيِنْحَرِف نَاحِيَة القَاعِدَة", font=_f(AR_BOLD, 32), fill=INK, anchor="mm", language="ar")

    _footer(img, scene.get("source_codes") or "")
    return img


def _refractive_error_diagram(scene) -> Image.Image:
    spec = scene.get("diagram_spec") or {}
    err = spec.get("error_type", "myopia")
    img = _bg()
    _header(img, scene.get("heading") or "", scene.get("term_en") or "")
    d = ImageDraw.Draw(img, "RGBA")
    cx, cy = W // 2 - 60, H // 2 + 20
    eye_w, eye_h = 420, 260
    d.ellipse([cx - eye_w // 2, cy - eye_h // 2, cx + eye_w // 2, cy + eye_h // 2], outline=GOLD, width=4)
    lens_x = cx - 40
    d.ellipse([lens_x - 16, cy - 70, lens_x + 16, cy + 70], fill=(180, 210, 235, 100), outline=GOLD, width=3)
    retina_x = cx + eye_w // 2
    d.line([(retina_x, cy - eye_h // 2), (retina_x, cy + eye_h // 2)], fill=GOLD, width=5)
    d.text((retina_x + 14, cy), "الشَّبَكِيَّة", font=_f(AR_BOLD, 26), fill=DIM, anchor="lm", language="ar")

    if err == "myopia":
        focus_x = cx + 70
        label = "قَصَر النَّظَر: الصُّورَة بِتِتْكَوِّن قُدَّام الشَّبَكِيَّة"
    elif err == "hyperopia":
        focus_x = retina_x + 90
        label = "طُول النَّظَر: الصُّورَة بِتِتْكَوِّن وَرَا الشَّبَكِيَّة"
    else:
        focus_x = retina_x
        label = "عَيْن سَلِيمَة: الصُّورَة تَظْبُط عَلَى الشَّبَكِيَّة بِالظَّبْط"

    for dy in (-60, 0, 60):
        _arrow(d, (cx - 400, cy + dy), (lens_x - 15, cy + dy * 0.3))
        d.line([(lens_x + 15, cy + dy * 0.3), (focus_x, cy)], fill=RAY, width=3)
    d.ellipse([focus_x - 8, cy - 8, focus_x + 8, cy + 8], fill=GLOW, outline=INK, width=2)
    d.text((cx, H - 130), label, font=_f(AR_BOLD, 32), fill=INK, anchor="mm", language="ar")

    _footer(img, scene.get("source_codes") or "")
    return img


def _frame_measurement_diagram(scene) -> Image.Image:
    img = _bg()
    _header(img, scene.get("heading") or "", scene.get("term_en") or "")
    d = ImageDraw.Draw(img, "RGBA")
    cx, cy = W // 2, H // 2 + 10
    lw, lh = 300, 220
    l1 = (cx - 220, cy)
    l2 = (cx + 220, cy)
    for lx, ly in (l1, l2):
        d.rounded_rectangle([lx - lw // 2, ly - lh // 2, lx + lw // 2, ly + lh // 2],
                             radius=40, outline=GOLD, width=4)
    d.line([(l1[0] + lw // 2, l1[1]), (l2[0] - lw // 2, l2[1])], fill=(255, 255, 255, 90), width=3)
    d.text(((l1[0] + lw // 2 + l2[0] - lw // 2) / 2, l1[1] - 18), "DBL",
           font=_f(LAT_B, 26), fill=GOLD, anchor="mm")

    d.line([(l1[0] - lw // 2, l1[1] - lh // 2 - 26), (l1[0] + lw // 2, l1[1] - lh // 2 - 26)], fill=GOLD, width=2)
    d.text((l1[0], l1[1] - lh // 2 - 46), "A", font=_f(LAT_B, 28), fill=INK, anchor="mm")

    d.line([(l1[0] - lw // 2 - 26, l1[1] - lh // 2), (l1[0] - lw // 2 - 26, l1[1] + lh // 2)], fill=GOLD, width=2)
    d.text((l1[0] - lw // 2 - 50, l1[1]), "B", font=_f(LAT_B, 28), fill=INK, anchor="mm")

    ed_r = int(max(lw, lh) * 0.62)
    d.ellipse([l1[0] - ed_r, l1[1] - ed_r, l1[0] + ed_r, l1[1] + ed_r], outline=(214, 178, 92, 140), width=2)
    d.text((l1[0], l1[1] + ed_r + 24), "ED", font=_f(LAT, 24), fill=DIM, anchor="mm")

    d.text((cx, H - 120), "العَرْض، وَالاِرْتِفَاع، وَالمَسَافَة بَيْن العَدَسَتَيْن، وَالقُطْر الفَعَّال",
           font=_f(AR_BOLD, 28), fill=INK, anchor="mm", language="ar")
    _footer(img, scene.get("source_codes") or "")
    return img


def _pd_measurement_diagram(scene) -> Image.Image:
    img = _bg()
    _header(img, scene.get("heading") or "", scene.get("term_en") or "")
    d = ImageDraw.Draw(img, "RGBA")
    cx, cy = W // 2, H // 2
    ex = 170
    for sign in (-1, 1):
        d.ellipse([cx + sign * ex - 26, cy - 26, cx + sign * ex + 26, cy + 26], outline=GOLD, width=4)
        d.ellipse([cx + sign * ex - 8, cy - 8, cx + sign * ex + 8, cy + 8], fill=GLOW)
    d.line([(cx - 260, cy), (cx + 260, cy)], fill=(255, 255, 255, 40), width=2)
    d.line([(cx - ex, cy - 60), (cx - ex, cy + 60)], fill=(255, 255, 255, 90), width=2)
    d.line([(cx + ex, cy - 60), (cx + ex, cy + 60)], fill=(255, 255, 255, 90), width=2)
    d.line([(cx - ex, cy + 60), (cx + ex, cy + 60)], fill=GOLD, width=3)
    d.text((cx, cy + 90), "PD", font=_f(LAT_B, 30), fill=GOLD, anchor="mm")
    nose = (cx, cy)
    d.line([(nose[0], cy - 20), (nose[0], cy + 20)], fill=DIM, width=2)
    d.text((cx, H - 150), "المَسَافَة بَيْن الحَدَقَتَيْن",
           font=_f(AR_BOLD, 32), fill=INK, anchor="mm", language="ar")
    d.text((cx, H - 105), "Interpupillary Distance", font=_f(LAT, 24), fill=DIM, anchor="mm")
    _footer(img, scene.get("source_codes") or "")
    return img


def _labeled_slide(scene) -> Image.Image:
    img = _bg()
    _header(img, scene.get("heading") or "", scene.get("term_en") or "")
    d = ImageDraw.Draw(img, "RGBA")
    labels = scene.get("labels") or []
    if labels:
        y0 = H // 2 - (len(labels) * 74) // 2
        for i, (name, _key) in enumerate(labels[:6]):
            cy = y0 + i * 74
            d.ellipse([W // 2 - 480, cy - 8, W // 2 - 464, cy + 8], fill=GOLD)
            _draw_mixed(d, W // 2 - 440, cy, _plain(name), AR_BOLD, LAT_B, 40, INK, anchor="lm")
    _footer(img, scene.get("source_codes") or "")
    return img


def _frame_ruler_diagram(scene) -> Image.Image:
    """مسطرة قياس إطار برمجية بالكامل (بلا API) -- بديل حتمي عن توليد صورة
    بالذكاء الاصطناعي لأداة نادرة الموضوع طلّعت نتائج غير مطابقة فعليًا (صورة
    نظارة شبحية بدل مسطرة، لوحظ 2026-09-18 في درس 100029)."""
    img = _bg()
    _header(img, scene.get("heading") or "", scene.get("term_en") or "")
    d = ImageDraw.Draw(img, "RGBA")
    rx0, rx1 = 260, W - 260
    ry0, ry1 = 460, 560
    d.rounded_rectangle([rx0, ry0, rx1, ry1], radius=14, fill=(235, 240, 246, 255),
                         outline=GOLD, width=3)
    mm_total = 80
    px_per_mm = (rx1 - rx0 - 40) / mm_total
    base_x = rx0 + 20
    for mm in range(0, mm_total + 1, 1):
        x = base_x + mm * px_per_mm
        if mm % 10 == 0:
            d.line([(x, ry0 + 10), (x, ry0 + 55)], fill=(20, 34, 58, 255), width=3)
            d.text((x, ry0 + 65), str(mm), font=_f(LAT_B, 22), fill=(20, 34, 58, 255), anchor="mm")
        elif mm % 5 == 0:
            d.line([(x, ry0 + 10), (x, ry0 + 42)], fill=(60, 74, 98, 255), width=2)
        else:
            d.line([(x, ry0 + 10), (x, ry0 + 30)], fill=(120, 134, 158, 255), width=1)
    d.text((W / 2, ry1 + 40), "mm", font=_f(LAT, 26), fill=DIM, anchor="mm")
    labels = scene.get("labels") or []
    if labels:
        y0 = ry1 + 110
        for i, (name, _key) in enumerate(labels[:3]):
            cy = y0 + i * 70
            d.ellipse([W // 2 - 380, cy - 8, W // 2 - 364, cy + 8], fill=GOLD)
            _draw_mixed(d, W // 2 - 340, cy, _plain(name), AR_BOLD, LAT_B, 34, INK, anchor="lm")
    _footer(img, scene.get("source_codes") or "")
    return img


_DISPATCH = {
    "lens_ray_diagram": _lens_ray_diagram,
    "prism_diagram": _prism_diagram,
    "refractive_error_diagram": _refractive_error_diagram,
    "frame_measurement_diagram": _frame_measurement_diagram,
    "pd_measurement_diagram": _pd_measurement_diagram,
    "labeled_slide": _labeled_slide,
    "frame_ruler_diagram": _frame_ruler_diagram,
}


def render_optics_diagram(scene: dict):
    fn = _DISPATCH.get(scene.get("diagram"))
    if not fn:
        return None
    try:
        return fn(scene)
    except Exception as e:
        print(f"[optics_diagrams] فشل رسم {scene.get('diagram')}: {e}", flush=True)
        return None
