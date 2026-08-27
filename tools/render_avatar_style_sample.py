#!/usr/bin/env python3
"""عينة 30 ثانية بالصوت الحقيقي والصورة الثابتة مع حركة بصرية هادئة.

هذه ليست مزامنة شفاه ولا Digital Twin؛ الإفصاح مثبت داخل الفيديو والملف الناتج.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
PHOTO = ROOT / "assets" / "visual_references" / "presenter_navy_neutral.png"
AUDIO = ROOT / "data" / "audio_samples" / "speaker_reference.wav"
FONT_REG = ROOT / "assets" / "fonts" / "NotoSansArabic-Regular.ttf"
FONT_BOLD = ROOT / "assets" / "fonts" / "NotoSansArabic-Bold.ttf"
LOGO_STATIC = ROOT / "assets" / "brand" / "optics_gate_logo_lashes_only.png"
OUT = ROOT / "outputs" / "avatar_style_sample"
POSTER = OUT / "factory_avatar_style_poster.png"
VIDEO = OUT / "factory_avatar_style_30s.mp4"
W, H = 1920, 1080
NAVY, NAVY2, TEAL, SKY = "#162235", "#232E3E", "#467374", "#D4E6E7"
TAUPE, IVORY, WHITE = "#8F7D6C", "#F6F3EE", "#FFFFFF"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REG), size)


def rtl(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, size: int,
        fill: str, bold: bool = False, anchor: str = "ra") -> None:
    draw.text(xy, text, font=font(size, bold), fill=fill, anchor=anchor,
              direction="rtl", language="ar")


def gradient() -> Image.Image:
    top = (22, 34, 53); bottom = (43, 65, 75)
    image = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(image)
    for y in range(H):
        t = y / (H - 1)
        color = tuple(round(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        draw.line((0, y, W, y), fill=color)
    return image


def rounded_photo() -> Image.Image:
    source = Image.open(PHOTO).convert("RGB")
    target_w, target_h = 980, 700
    ratio = max(target_w / source.width, target_h / source.height)
    source = source.resize((round(source.width * ratio), round(source.height * ratio)), Image.Resampling.LANCZOS)
    left = (source.width - target_w) // 2; top = (source.height - target_h) // 2
    source = source.crop((left, top, left + target_w, top + target_h))
    mask = Image.new("L", (target_w, target_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, target_w, target_h), radius=48, fill=255)
    rgba = source.convert("RGBA"); rgba.putalpha(mask)
    return rgba


def make_poster() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    image = gradient().convert("RGBA"); draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((80, 58, 280, 258), radius=34, fill=WHITE)
    logo = Image.open(LOGO_STATIC).convert("RGBA")
    logo.thumbnail((180, 180), Image.Resampling.LANCZOS)
    image.alpha_composite(logo, (90 + (180 - logo.width) // 2, 68 + (180 - logo.height) // 2))
    photo = rounded_photo()
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0)); sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((817, 187, 1827, 917), radius=58, fill=(0, 0, 0, 82))
    image = Image.alpha_composite(image, shadow)
    image.alpha_composite(photo, (800, 170)); draw = ImageDraw.Draw(image)
    rtl(draw, (1780, 105), "منصة بوابة البصريات", 34, SKY, True)
    rtl(draw, (750, 260), "صوتك الحقيقي", 62, WHITE, True)
    rtl(draw, (750, 365), "وصورتك داخل المصنع", 52, SKY, True)
    draw.rounded_rectangle((125, 530, 690, 625), radius=28, fill=TEAL)
    rtl(draw, (408, 580), "مدرب البصريات محمد سعيد", 32, WHITE, True, "mm")
    draw.rounded_rectangle((125, 680, 690, 815), radius=28, fill="#17333E", outline=TEAL, width=3)
    rtl(draw, (750, 885), "تحريك بصري للصورة، بدون مزامنة شفاه", 25, SKY)
    draw.rounded_rectangle((125, 1005, 1795, 1015), radius=5, fill=SKY)
    draw.rounded_rectangle((125, 1005, 760, 1015), radius=5, fill=TEAL)
    image.convert("RGB").save(POSTER, "PNG", optimize=True)


def render() -> None:
    make_poster()
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-i", str(POSTER), "-i", str(AUDIO),
        "-filter_complex",
        "[0:v]zoompan=z='min(zoom+0.00008,1.025)':x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':d=750:s=1920x1080:fps=25,format=yuv420p[base];"
        "[1:a]asplit=2[voice][waveaudio];"
        "[voice]loudnorm=I=-16:LRA=7:TP=-1.5[aout];"
        "[waveaudio]showwaves=s=540x105:mode=p2p:rate=25:colors=0xD4E6E7:scale=sqrt,format=rgba[wave];"
        "[base][wave]overlay=x=150:y=700:shortest=1[v]",
        "-map", "[v]", "-map", "[aout]", "-t", "30",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "1",
        "-movflags", "+faststart", str(VIDEO),
    ]
    subprocess.run(command, check=True, timeout=300)
    manifest = {
        "duration_seconds": 30, "resolution": "1920x1080", "fps": 25,
        "voice": "speaker_reference.wav — first 30 seconds", "music": False,
        "image": "presenter_navy_neutral.png", "lip_sync": False,
        "disclosure": "تحريك بصري للصورة، بدون مزامنة شفاه",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"video": str(VIDEO), **manifest}, ensure_ascii=False))


if __name__ == "__main__":
    render()
