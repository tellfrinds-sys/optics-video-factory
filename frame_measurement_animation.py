# -*- coding: utf-8 -*-
"""frame_measurement_animation.py — أنيميشن HTML/SVG احترافي (GSAP محلي، بلا اعتماد
على شبكة خارجية وقت الإنتاج) لمشاهد قياسات إطار النظارة (A/B/DBL/E) ومعادلة المركز
الهندسي (GC) — الجيل الثاني بعد نسخة CSS-transitions اليدوية الأولى (2026-09-18، درس
100029)، بعد ملاحظات حقيقية: تداخل تسميات (A وE كانوا فوق بعض) وتوقيت ثابت بمعزل عن
مدة السرد الفعلية (سبب تزامن فاشل -- مشهد مدته 43 ثانية كان الأنيميشن بيجمد بعد 13
ثانية بس). الحل هنا: توقيت الظهور بيتحسب ديناميكيًا من seg_dur الفعلي لكل مشهد،
وإحداثيات تسميات مُعاد ترتيبها بلا أي تداخل.

هذا حجر الأساس (بطلب صريح من المسؤول) لتحويل بقية مشاهد الجزء الأوسط لأنيميشن
تدريجيًا مستقبلًا، مش بس قياسات الإطار.

الواجهة: build_html(stage, seg_dur, out_html_path) -> Path
stage: "A" | "B" | "DBL" | "E" | "GC"
كل مرحلة بترسم قياسات المراحل السابقة كلها ثابتة (بلا حركة)، وتُحرِّك قياس المرحلة
الحالية بس -- استمرارية بصرية عبر المشاهد المتتالية.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
GSAP_PATH = ROOT / "assets" / "vendor" / "gsap.min.js"

_STAGE_ORDER = ["A", "B", "DBL", "E"]

_COLORS = {"A": "#2f7dd6", "B": "#2fa85a", "DBL": "#1ea3ad", "E": "#8a3fb8", "GC": "#c0392b"}

# (خط، نقطة تسمية) لكل قياس -- إحداثيات مُعاد توزيعها بعناية لمنع أي تداخل نصوص
_GEOM = {
    "A": {"line": (105, 168, 340, 168), "label": (222, 195), "text": "A"},
    "B": {"line": (222.5, 78, 222.5, 242), "label": (170, 160), "text": "B"},
    "DBL": {"line": (340, 145, 460, 145), "label": (400, 118), "text": "DBL"},
    "E": {"line": (128, 225, 318, 92), "label": (300, 210), "text": "E"},
}


def _svg_measurement(key: str, revealed: bool) -> str:
    g = _GEOM[key]
    x1, y1, x2, y2 = g["line"]
    lx, ly = g["label"]
    color = _COLORS[key]
    cls = "dim-static" if revealed else "dim-anim"
    gid = f"dim{key.replace('DBL', 'DBL')}"
    return (
        f'<g id="{gid}" class="{cls}" data-color="{color}">'
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="5" '
        f'marker-end="url(#arrow-{key})" marker-start="url(#arrow-{key}-rev)"/>'
        f'<text x="{lx}" y="{ly}" class="dim-text" fill="{color}">{g["text"]}</text>'
        f'</g>'
    )


def _markers() -> str:
    parts = []
    for key, color in _COLORS.items():
        if key == "GC":
            continue
        parts.append(
            f'<marker id="arrow-{key}" markerWidth="10" markerHeight="10" refX="9" refY="3" '
            f'orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" fill="{color}"/></marker>'
            f'<marker id="arrow-{key}-rev" markerWidth="10" markerHeight="10" refX="1" refY="3" '
            f'orient="auto" markerUnits="strokeWidth"><path d="M9,0 L9,6 L0,3 z" fill="{color}"/></marker>'
        )
    return "".join(parts)


def build_html(stage: str, seg_dur: float, out_html_path: Path,
                values: dict | None = None) -> Path:
    """values: قيم اختيارية للعرض في صندوق المعادلة (مرحلة GC بس)، مثل {"A":52,"DBL":16}."""
    values = values or {"A": 52, "DBL": 16}
    out_html_path = Path(out_html_path)
    out_html_path.parent.mkdir(parents=True, exist_ok=True)

    if stage == "GC":
        revealed_keys = _STAGE_ORDER
        anim_key = None
    else:
        idx = _STAGE_ORDER.index(stage)
        revealed_keys = _STAGE_ORDER[:idx]
        anim_key = stage

    svg_groups = "".join(_svg_measurement(k, revealed=True) for k in revealed_keys)
    if anim_key:
        svg_groups += _svg_measurement(anim_key, revealed=False)

    gc_val = values.get("A", 52) + values.get("DBL", 16)
    eq_box = (
        '<div id="eqBox" class="equation-box">'
        '<div class="calc-header">المركز الهندسي للإطار (Geometrical Center)</div>'
        '<div class="result-equation">'
        f'GC = <span style="color:{_COLORS["A"]}">A</span> + '
        f'<span style="color:{_COLORS["DBL"]}">DBL</span><br>'
        f'GC = <span style="color:{_COLORS["A"]}">{values.get("A", 52)}</span> + '
        f'<span style="color:{_COLORS["DBL"]}">{values.get("DBL", 16)}</span> = '
        f'<span class="highlight">{gc_val} mm</span></div></div>'
    )

    # توقيت ديناميكي: بداية الحركة عند 12% من مدة المشهد (سياق كلامي قبلها)، ومدة
    # الحركة نفسها ~1.4 ثانية مهما كانت مدة المشهد -- الباقي تثبيت (hold) على الحالة
    # النهائية لحد ما الصوت يخلص (match_duration بيهتم بالتجميد لو الأنيميشن أقصر).
    reveal_at = max(0.8, min(seg_dur * 0.15, 6.0))
    anim_dur = 1.3
    eq_reveal_at = max(reveal_at, seg_dur * 0.18) if stage == "GC" else None

    gsap_calls = []
    if anim_key:
        gid = f"dim{anim_key}"
        x1, y1, x2, y2 = _GEOM[anim_key]["line"]
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        # ملاحظة: drawSVG بلجن مدفوع (GSAP Club) -- مش متاح في حزمة npm المجانية، وscaleX
        # وحدها بتفشل مع الخطوط الرأسية/القطرية (B وE). البديل المجاني الموحّد لكل
        # الاتجاهات: ظهور بـ fade + scale-pop من مركز الخط نفسه -- مظهر احترافي شائع
        # في الإنفوجرافيك المتحركة، وشغال بنفس الجودة لأي اتجاه خط.
        gsap_calls.append(
            f'gsap.set("#{gid}", {{transformOrigin:"{cx}px {cy}px", opacity:0, scale:0.6}});'
            f'gsap.set("#{gid} text", {{opacity:0}});'
            f'gsap.to("#{gid}", {{opacity:1, scale:1, duration:{anim_dur:.2f}, '
            f'delay:{reveal_at:.2f}, ease:"back.out(1.6)"}});'
            f'gsap.to("#{gid} text", {{opacity:1, duration:0.5, '
            f'delay:{reveal_at + anim_dur - 0.3:.2f}}});'
        )
    if stage == "GC":
        gsap_calls.append(
            f'gsap.fromTo("#eqBox", {{opacity:0, y:30}}, {{opacity:1, y:0, '
            f'duration:1.0, delay:{eq_reveal_at:.2f}, ease:"back.out(1.4)"}});'
        )

    html = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="UTF-8">
<title>Frame Measurement Animation</title>
<script src="{GSAP_PATH.resolve().as_uri()}"></script>
<style>
:root {{ --text-main:#2c3e50; }}
body {{ font-family:'Segoe UI',Tahoma,sans-serif; background:#f8fbfe; color:var(--text-main);
  margin:0; padding:0; display:flex; justify-content:center; align-items:flex-start;
  height:100vh; overflow:hidden; }}
/* المحتوى مثبَّت أعلى الشاشة (2026-09-18، ملاحظة بشرية: الترجمة كانت بتغطي على
   المخطط) -- كل العناصر لازم تفضل فوق منطقة الترجمة السفلية (تبدأ ~ي830px). */
.scene {{ width:100%; max-width:1200px; display:flex; flex-direction:column; align-items:center;
  gap:24px; padding-top:130px; box-sizing:border-box; }}
.svg-container {{ width:100%; height:360px; display:flex; justify-content:center; align-items:center; }}
svg {{ width:82%; height:auto; max-height:330px; overflow:visible; }}
.frame-path {{ fill:none; stroke:#1a4a76; stroke-width:8; stroke-linecap:round; stroke-linejoin:round; }}
.lens-path {{ fill:#e3f2fd; opacity:0.55; stroke:#bdc3c7; stroke-width:2; }}
.dim-text {{ font-size:30px; font-weight:bold; font-family:Arial,sans-serif; }}
.dim-static {{ opacity:1; }}
.dim-anim {{ opacity:0; }}
.equation-box {{ background:#fff; border:3px dashed #1a4a76; border-radius:18px; padding:18px 48px;
  box-shadow:0 10px 30px rgba(0,0,0,.12); opacity:0; }}
.calc-header {{ font-size:22px; font-weight:bold; color:#1a4a76; margin-bottom:10px; text-align:center; }}
.result-equation {{ font-size:32px; color:#333; direction:ltr; text-align:center; font-weight:bold; }}
.highlight {{ color:#d32f2f; font-size:38px; }}
</style></head>
<body>
<div class="scene">
  <div class="svg-container">
    <svg viewBox="0 0 800 300" xmlns="http://www.w3.org/2000/svg">
      <rect x="105" y="78" width="235" height="164" rx="70" ry="70" class="lens-path"/>
      <rect x="105" y="78" width="235" height="164" rx="70" ry="70" class="frame-path"/>
      <rect x="460" y="78" width="235" height="164" rx="70" ry="70" class="lens-path"/>
      <rect x="460" y="78" width="235" height="164" rx="70" ry="70" class="frame-path"/>
      <path class="frame-path" d="M 340 130 Q 400 110 460 130"/>
      <path class="frame-path" d="M 340 160 Q 400 140 460 160"/>
      <path class="frame-path" d="M 105 160 L 40 150"/>
      <path class="frame-path" d="M 695 160 L 760 150"/>
      <defs>{_markers()}</defs>
      {svg_groups}
    </svg>
  </div>
  {eq_box}
</div>
<script>
  {"".join(gsap_calls)}
</script>
</body></html>"""

    out_html_path.write_text(html, encoding="utf-8")
    return out_html_path
