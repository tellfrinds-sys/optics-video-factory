#!/usr/bin/env python3
"""ينشئ نموذج بوابة البصريات الاحترافي 30 ثانية.

من دون --voice ينشئ visual_master_silent.mp4 للمراجعة الداخلية فقط.
مع --voice ينشئ professional_preview_30s.mp4 بصوت واحد معتمد ومن دون موسيقى.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "data" / "demo_payloads" / "professional_preview_30s.json"
OUT = ROOT / "outputs" / "professional_preview_30s"
SLIDES = OUT / "slides"
FONT_REG = ROOT / "assets" / "fonts" / "NotoSansArabic-Regular.ttf"
FONT_BOLD = ROOT / "assets" / "fonts" / "NotoSansArabic-Bold.ttf"
FONT_LATIN_REG = ROOT / "assets" / "fonts" / "NotoSans-Regular.ttf"
FONT_LATIN_BOLD = ROOT / "assets" / "fonts" / "NotoSans-Bold.ttf"
LOGO_STATIC = ROOT / "assets" / "brand" / "optics_gate_logo_lashes_only.png"
W, H, FPS = 1920, 1080, 25
NAVY, NAVY_2, TEAL = "#162235", "#232E3E", "#467374"
SKY, TAUPE, IVORY = "#D4E6E7", "#8F7D6C", "#F6F3EE"
WHITE, INK, RED, GREEN = "#FFFFFF", "#2E2B28", "#8D4B43", "#34745D"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REG), size)


def font_latin(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_LATIN_BOLD if bold else FONT_LATIN_REG), size)


def gradient(top: str, bottom: str) -> Image.Image:
    a = tuple(int(top[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(bottom[i:i + 2], 16) for i in (1, 3, 5))
    image = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(image)
    for y in range(H):
        t = y / (H - 1)
        color = tuple(round(a[i] * (1 - t) + b[i] * t) for i in range(3))
        draw.line((0, y, W, y), fill=color)
    return image


def rtl(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, size: int,
        fill: str, bold: bool = False, anchor: str = "ra") -> None:
    draw.text(xy, text, font=font(size, bold), fill=fill, anchor=anchor,
              direction="rtl", language="ar", stroke_width=0)


def brand(image: Image.Image, draw: ImageDraw.ImageDraw, light: bool = True) -> None:
    color = SKY if light else TAUPE
    draw.rounded_rectangle((62, 38, 246, 222), radius=32, fill=WHITE)
    logo = Image.open(LOGO_STATIC).convert("RGBA")
    logo.thumbnail((166, 166), Image.Resampling.LANCZOS)
    image.paste(logo, (71 + (166 - logo.width) // 2, 47 + (166 - logo.height) // 2), logo)
    rtl(draw, (1810, 106), "منصة بوابة البصريات", 32, color, True)


def footer(draw: ImageDraw.ImageDraw, index: int, light: bool = True) -> None:
    color = SKY if light else TAUPE
    draw.rounded_rectangle((110, 1018, 1810, 1027), radius=4, fill=color)
    draw.rounded_rectangle((110, 1018, 110 + int(1700 * index / 7), 1027), radius=4, fill=TEAL)
    rtl(draw, (1810, 984), "المصادر العلمية أسفل الفيديو", 23, color)
    ar_index = str(index).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))
    rtl(draw, (110, 984), f"المشهد {ar_index} من ٧", 22, color, True, "la")


def pill(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str,
         fill: str, text_color: str, size: int = 30) -> None:
    draw.rounded_rectangle(box, radius=28, fill=fill)
    x = (box[0] + box[2]) // 2
    y = (box[1] + box[3]) // 2
    rtl(draw, (x, y + 2), text, size, text_color, True, "mm")


def title(draw: ImageDraw.ImageDraw, heading: str, sub: str, light: bool = True) -> None:
    primary = WHITE if light else NAVY
    secondary = SKY if light else TEAL
    heading_size = 60 if len(heading) > 24 else 70
    rtl(draw, (1765, 245), heading, heading_size, primary, True, "rt")
    draw.rounded_rectangle((1385, 365, 1765, 374), radius=4, fill=secondary)
    rtl(draw, (1765, 405), sub, 37, secondary, False, "rt")


def slide_intro(item: dict) -> Image.Image:
    image = gradient(NAVY, NAVY_2); draw = ImageDraw.Draw(image); brand(image, draw)
    draw.ellipse((105, 245, 735, 875), outline=SKY, width=11)
    draw.ellipse((240, 380, 870, 1010), outline=TAUPE, width=6)
    draw.ellipse((295, 435, 680, 820), fill="#233D52", outline=TEAL, width=7)
    rtl(draw, (1770, 345), item["title"], 86, WHITE, True)
    rtl(draw, (1770, 505), item["subtitle"], 42, SKY)
    pill(draw, (1170, 650, 1770, 735), "معًا لبصريات أفضل", TEAL, WHITE, 33)
    footer(draw, 1); return image


def slide_anatomy(item: dict) -> Image.Image:
    image = gradient(IVORY, "#EAF2F2"); draw = ImageDraw.Draw(image); brand(image, draw, False); title(draw, item["title"], item["subtitle"], False)
    # رسم وظيفي مبسط للقرنية والعدسة اللينة.
    cx, cy = 600, 590
    draw.ellipse((270, 300, 930, 880), fill="#FFFFFF", outline=TEAL, width=8)
    draw.arc((750, 355, 1030, 825), 88, 272, fill=NAVY, width=18)
    draw.arc((790, 375, 1085, 805), 88, 272, fill="#6FB8BE", width=10)
    draw.line((930, 570, 1090, 590), fill=TAUPE, width=4)
    pill(draw, (950, 545, 1310, 633), "العدسة اللينة", WHITE, NAVY, 31)
    draw.line((790, 690, 1130, 805), fill=TAUPE, width=4)
    pill(draw, (1000, 760, 1380, 848), "سطح القرنية", WHITE, NAVY, 31)
    draw.ellipse((cx - 70, cy - 70, cx + 70, cy + 70), fill=NAVY)
    draw.ellipse((cx - 30, cy - 30, cx + 30, cy + 30), fill="#95C8CB")
    footer(draw, 2, False); return image


def slide_parameters(item: dict) -> Image.Image:
    image = gradient(NAVY_2, TEAL); draw = ImageDraw.Draw(image); brand(image, draw); title(draw, item["title"], item["subtitle"], True)
    cards = [("BC", "انحناء العدسة", "8.6"), ("DIA", "قطر العدسة", "14.2"), ("PWR", "القوة البصرية", "−2.50")]
    for i, (code, label, value) in enumerate(cards):
        x = 240 + i * 540
        draw.rounded_rectangle((x, 550, x + 430, 865), radius=42, fill=IVORY)
        draw.text((x + 215, 635), code, font=font_latin(52, True), fill=TEAL, anchor="mm")
        draw.text((x + 215, 727), value, font=font_latin(62, True), fill=NAVY, anchor="mm")
        rtl(draw, (x + 215, 808), label, 28, INK, False, "mm")
    footer(draw, 3); return image


def slide_comparison(item: dict) -> Image.Image:
    image = gradient(IVORY, WHITE); draw = ImageDraw.Draw(image); brand(image, draw, False); title(draw, item["title"], item["subtitle"], False)
    boxes = [(160, 535, 825, 870), (1095, 535, 1760, 870)]
    draw.rounded_rectangle(boxes[0], radius=42, fill="#E4F0F0", outline=TEAL, width=4)
    draw.rounded_rectangle(boxes[1], radius=42, fill="#EEE8E2", outline=TAUPE, width=4)
    rtl(draw, (492, 630), "مادة العدسة", 50, NAVY, True, "mm")
    rtl(draw, (492, 735), "ممَّ تتكوّن؟", 34, TEAL, False, "mm")
    rtl(draw, (1427, 630), "جدول الاستبدال", 50, NAVY, True, "mm")
    rtl(draw, (1427, 735), "متى تتغيّر؟", 34, TAUPE, False, "mm")
    draw.ellipse((900, 655, 1020, 775), fill=NAVY)
    draw.text((960, 715), "≠", font=font_latin(58, True), fill=WHITE, anchor="mm")
    footer(draw, 4, False); return image


def _check(draw: ImageDraw.ImageDraw, center: tuple[int, int], allowed: bool) -> None:
    x, y = center; color = GREEN if allowed else RED
    draw.ellipse((x - 54, y - 54, x + 54, y + 54), fill=color)
    if allowed:
        draw.line((x - 24, y, x - 5, y + 22, x + 31, y - 25), fill=WHITE, width=10, joint="curve")
    else:
        draw.line((x - 27, y - 27, x + 27, y + 27), fill=WHITE, width=10)
        draw.line((x + 27, y - 27, x - 27, y + 27), fill=WHITE, width=10)


def slide_safety(item: dict) -> Image.Image:
    image = gradient(NAVY, "#1D4A53"); draw = ImageDraw.Draw(image); brand(image, draw); title(draw, item["title"], "ثلاث قواعد لا تتغيّر", True)
    labels = [("اغسل وجفف يديك", True), ("لا تستخدم ماء الصنبور", False), ("لا تنم بالعدسة غير المخصصة", False)]
    for i, (label, allowed) in enumerate(labels):
        x = 315 + i * 595
        draw.rounded_rectangle((x - 210, 535, x + 290, 870), radius=40, fill=WHITE)
        _check(draw, (x + 40, 655), allowed)
        rtl(draw, (x + 40, 795), label, 31, NAVY, True, "mm")
    footer(draw, 5); return image


def slide_sources(item: dict) -> Image.Image:
    image = gradient(IVORY, "#E8EEEE"); draw = ImageDraw.Draw(image); brand(image, draw, False); title(draw, item["title"], "لا معلومة علمية بلا مرجع", False)
    sources = [("FDA", "هيئة الغذاء والدواء الأمريكية"), ("CDC", "مراكز مكافحة الأمراض والوقاية منها")]
    for i, (abbr, label) in enumerate(sources):
        y = 550 + i * 175
        draw.rounded_rectangle((260, y, 1660, y + 125), radius=30, fill=WHITE)
        draw.rounded_rectangle((260, y, 540, y + 125), radius=30, fill=TEAL)
        draw.text((400, y + 64), abbr, font=font_latin(43, True), fill=WHITE, anchor="mm")
        rtl(draw, (1580, y + 65), label, 36, NAVY, True, "rm")
    footer(draw, 6, False); return image


def slide_outro(item: dict) -> Image.Image:
    image = gradient(NAVY_2, NAVY); draw = ImageDraw.Draw(image); brand(image, draw)
    for r, width, color in [(250, 9, SKY), (175, 5, TAUPE), (100, 3, TEAL)]:
        draw.ellipse((960 - r, 335 - r, 960 + r, 335 + r), outline=color, width=width)
    draw.ellipse((900, 275, 1020, 395), fill=TEAL)
    rtl(draw, (960, 650), item["title"], 82, WHITE, True, "mm")
    rtl(draw, (960, 765), item["subtitle"], 38, SKY, False, "mm")
    pill(draw, (630, 835, 1290, 920), "تابعوا منصة بوابة البصريات", TEAL, WHITE, 30)
    footer(draw, 7); return image


RENDERERS = {
    "brand_intro": slide_intro, "lens_anatomy": slide_anatomy,
    "parameters": slide_parameters, "comparison": slide_comparison,
    "safety": slide_safety, "sources": slide_sources, "brand_outro": slide_outro,
}


def render_slides(payload: dict) -> list[Path]:
    SLIDES.mkdir(parents=True, exist_ok=True)
    paths = []
    for item in payload["slides"]:
        path = SLIDES / f"{item['id']}.png"
        RENDERERS[item["type"]](item).save(path, "PNG", optimize=True)
        paths.append(path)
    return paths


def render_video(payload: dict, slides: list[Path], voice: Path | None) -> Path:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg غير مثبت")
    transition = 0.5
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for slide, item in zip(slides, payload["slides"]):
        args += ["-loop", "1", "-t", str(item["duration"]), "-i", str(slide)]
    if voice:
        args += ["-i", str(voice)]
    filters, labels = [], []
    for i, item in enumerate(payload["slides"]):
        frames = math.ceil(float(item["duration"]) * FPS)
        filters.append(
            f"[{i}:v]scale={W}:{H},zoompan=z='min(zoom+0.00012,1.018)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},"
            f"setsar=1,format=yuv420p[v{i}]"
        )
        labels.append(f"v{i}")
    current, elapsed = labels[0], float(payload["slides"][0]["duration"])
    for i in range(1, len(labels)):
        offset = elapsed - transition
        out = f"x{i}"
        filters.append(f"[{current}][{labels[i]}]xfade=transition=fade:duration={transition}:offset={offset:.3f}[{out}]")
        elapsed += float(payload["slides"][i]["duration"]) - transition
        current = out
    output = OUT / ("professional_preview_30s.mp4" if voice else "visual_master_silent.mp4")
    args += ["-filter_complex", ";".join(filters), "-map", f"[{current}]", "-t", "30", "-r", str(FPS)]
    if voice:
        audio_index = len(slides)
        args += ["-map", f"{audio_index}:a:0", "-af", "loudnorm=I=-16:LRA=7:TP=-1.5,apad", "-c:a", "aac", "-b:a", "160k"]
    args += ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-movflags", "+faststart", str(output)]
    subprocess.run(args, check=True, timeout=300)
    return output


def audio_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", str(path)],
        check=True, capture_output=True, text=True, timeout=30,
    )
    return float(result.stdout.strip())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice", type=Path, help="تسجيل صوتي معتمد للنص، 30 ثانية تقريبًا")
    args = parser.parse_args()
    if args.voice and not args.voice.is_file():
        parser.error("ملف الصوت غير موجود")
    if args.voice:
        duration = audio_duration(args.voice)
        if duration < 27:
            parser.error(f"التسجيل قصير ({duration:.2f} ثانية). المطلوب من 27 إلى 30.5 ثانية")
        if duration > 30.5:
            parser.error(f"التسجيل أطول من الحد ({duration:.2f} ثانية). لن يقص المحرك الكلام؛ أعد التسجيل في 30 ثانية")
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    if sum(float(x["duration"]) for x in payload["slides"]) - 3.0 != 30.0:
        raise RuntimeError("الخط الزمني لا يساوي 30 ثانية بعد الانتقالات")
    slides = render_slides(payload)
    video = render_video(payload, slides, args.voice)
    print(json.dumps({"video": str(video), "voice": bool(args.voice), "duration_seconds": 30,
                      "music": False, "font": "Noto Sans Arabic", "slides": len(slides)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
