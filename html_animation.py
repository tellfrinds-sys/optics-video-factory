# -*- coding: utf-8 -*-
"""html_animation.py — يسجّل صفحة HTML/CSS/JS متحركة كفيديو حقيقي (مش لقطة ثابتة)
عبر متصفح آلي (Chromium via Playwright)، لاستخدامها كمشهد كامل داخل خط الإنتاج.

مسار دائم في الخط (2026-09-18، بطلب صريح من المسؤول بدءًا من درس 100029 فصاعدًا):
أي مشهد "diagram" == "html_animation" مع حقل "animation_html_path" بيتسجل فيديو
حقيقي (مش صورة ثابتة) ويُستخدم كمشهد كامل بدل الرسم البرمجي/الصورة المولَّدة.

الاعتماد: Playwright + Chromium (مُثبَّتين على السيرفر فعليًا)، وffmpeg (موجود
مسبقًا في المشروع) لتحويل webm الناتج من Playwright إلى mp4 متوافق مع بقية الخط.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

W, H = 1920, 1080


def record_html_as_video(html_path: Path, out_path: Path, record_seconds: float = 15.0,
                          width: int = W, height: int = H) -> Path:
    """يفتح صفحة HTML في Chromium آلي، يسجّلها فيديو (webm) لمدة record_seconds،
    يحوّلها mp4 (H.264) عبر ffmpeg، ويرجع مسار الفيديو النهائي. بيرفع استثناء عادي
    عند أي فشل -- المتصل (narrated_render.py) مسؤول عن السقوط الآمن لصورة ثابتة."""
    from playwright.sync_api import sync_playwright  # استيراد داخلي: تجنّب تكلفة التحميل لو مش مستخدَم

    html_path = Path(html_path).resolve()
    out_path = Path(out_path)
    tmp_dir = out_path.parent / f"_html_rec_{out_path.stem}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": width, "height": height},
            record_video_dir=str(tmp_dir),
            record_video_size={"width": width, "height": height},
        )
        page = context.new_page()
        page.goto(html_path.as_uri())
        page.wait_for_timeout(int(record_seconds * 1000))
        context.close()  # يحفظ ملف الفيديو فور إغلاق الـcontext
        browser.close()

    webm_files = sorted(tmp_dir.glob("*.webm"))
    if not webm_files:
        raise RuntimeError("Playwright: مفيش فيديو اتسجّل من الصفحة")
    webm = webm_files[0]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(webm), "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-r", "30", "-an", str(out_path)],
        check=True, capture_output=True, timeout=120,
    )
    webm.unlink(missing_ok=True)
    try:
        tmp_dir.rmdir()
    except OSError:
        pass
    return out_path


def match_duration(video_path: Path, target_seconds: float, out_path: Path) -> Path:
    """يضبط مدة الفيديو المُسجَّل بالظبط على مدة السرد الصوتي المطلوبة: تقصير
    (trim) لو الأنيميشن أطول، أو تجميد آخر فريم (freeze) لو أقصر -- بنفس أسلوب
    الحماية المستخدَم بالفعل في narrated_render.py لباقي المشاهد."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True, check=True,
    )
    cur = float(probe.stdout.strip() or 0)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if cur <= 0:
        raise RuntimeError("html_animation: مدة الفيديو المُسجَّل صفر")
    if cur >= target_seconds:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_path), "-t", f"{target_seconds:.3f}",
             "-c", "copy", str(out_path)],
            check=True, capture_output=True, timeout=60,
        )
    else:
        pad = target_seconds - cur
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_path), "-vf",
             f"tpad=stop_mode=clone:stop_duration={pad:.3f}",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out_path)],
            check=True, capture_output=True, timeout=120,
        )
    return out_path


def render_animation_scene(html_path: Path, target_seconds: float, out_path: Path,
                            record_seconds: float | None = None) -> Path:
    """الواجهة المستخدَمة من narrated_render.py: تسجّل الأنيميشن وتظبط مدته على
    مدة السرد بالظبط في خطوة واحدة."""
    rec_seconds = record_seconds or max(target_seconds + 2.0, 15.0)
    raw = out_path.parent / f"{out_path.stem}_raw.mp4"
    record_html_as_video(html_path, raw, record_seconds=rec_seconds)
    match_duration(raw, target_seconds, out_path)
    raw.unlink(missing_ok=True)
    return out_path


if __name__ == "__main__":
    import sys
    html = Path(sys.argv[1] if len(sys.argv) > 1 else "assets/animations/lesson_100029_gc.html")
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/test_animation.mp4")
    dur = float(sys.argv[3]) if len(sys.argv) > 3 else 14.0
    render_animation_scene(html, dur, out)
    print("saved:", out)
