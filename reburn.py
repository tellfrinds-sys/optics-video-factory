"""إعادة توليد ASS + حرق الترجمة + دمج البوكمارك — بدون إعادة توليد الصوت/المشاهد."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/root/video-factory")
import narrated_render as nr
import corrected_scenes as cs

OUT = Path("/root/video-factory/outputs/narrated_500128")
W, H = 1920, 1080


def dur(p):
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
        capture_output=True, text=True).stdout)


# أعد بناء أحداث الترجمة بنفس منطق المحرّك
ev = []
t = 0.0
for i, sc in enumerate(cs.SCENES, 1):
    ad = dur(OUT / f"S{i:02d}.mp3")
    phr = nr._phrases(sc["narration"])
    tc = sum(len(p) for p in phr) or 1
    cur = t
    lim = t + ad
    for j, p in enumerate(phr):
        d = (len(p) / tc) * ad
        st = cur
        en = min(cur + d, lim) if j < len(phr) - 1 else lim
        en = max(en, st + 0.7)
        ev.append((round(st, 2), round(en, 2), p))
        cur = en
    t += ad + nr.SCENE_GAP

nr._build_ass(ev, OUT / "captions.ass")
print(f"ASS: {len(ev)} cues")

VENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
        "-profile:v", "high", "-level", "4.0",
        "-x264-params", "keyint=60:min-keyint=60:scenecut=0",
        "-r", "30", "-video_track_timescale", "30000"]
AENC = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]

body = OUT / "body.mp4"
subs = f"subtitles={(OUT / 'captions.ass').as_posix()}:fontsdir=/usr/share/fonts/truetype/noto,setsar=1,fps=30"
nr._run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", str(OUT / "silent.mp4"), "-i", str(OUT / "narration.m4a"),
         "-vf", subs, "-map", "0:v", "-map", "1:a", *VENC, *AENC, "-shortest", str(body)],
        timeout=1200)
print("body reburned")

segs = [OUT / "intro_n.mp4", body, OUT / "outro_n.mp4"]
sl = OUT / "segs.txt"
sl.write_text("\n".join(f"file '{s.resolve()}'" for s in segs), encoding="utf-8")
nr._run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", str(sl), "-c", "copy", "-movflags", "+faststart", str(OUT / "final_narrated.mp4")],
        timeout=300)
print("final:", dur(OUT / "final_narrated.mp4"), "s")
