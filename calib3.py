import subprocess, pathlib, sys, re, unicodedata
sys.path.insert(0, "/root/video-factory")
import narrated_render as nr

TASH = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭـ]")


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout)


def tts_text(t):
    t = unicodedata.normalize("NFC", t)
    t = TASH.sub("", t)
    t = t.replace("،", " ").replace("؛", " ").replace(":", " ")
    t = t.replace("ألصلبة", "الصَلبة")  # الصلبة -> الصَلبة
    return re.sub(r"\s+", " ", t).strip()


def sil(p):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(p), "-af",
                          "silenceremove=stop_periods=-1:stop_duration=0.20:stop_threshold=-32dB:stop_silence=0.10",
                          "-y", str(p) + ".sr.mp3"], capture_output=True, text=True)
    return p + ".sr.mp3"


def gaps(p, thr="-32dB", d="0.15"):
    o = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(p), "-af",
                        "silencedetect=n=%s:d=%s" % (thr, d), "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    return [float(x) for x in re.findall(r"silence_duration: ([\d.]+)", o)]


S3 = ("الطبقة الوسطى اسمها العِنَبِيَّة، وفيها: القَزَحِيَّة الملوّنة، وفتحة البُؤْبُؤ في نُصّها، "
      "وبعدين الجسم الهُدْبِي، والمَشِيمِيَّة الغنيّة بالأوعية الدموية.")
S1 = ("العين البشرية دي عضو تركيبها دقيق، ومتكوّن من كذا جزء بيكمّلوا بعض. "
      "في الفيديو ده هنتعرّف على أسامي الأجزاء دي بس، وهنفصّل كل جزء ووظيفته في الفيديوهات الجاية.")

for tag, txt, nw in (("S1", S1, 29), ("S3", S3, 18)):
    print("--", tag, "cleaned:", tts_text(txt))
    raw = pathlib.Path("/tmp/r_%s.mp3" % tag)
    nr._heygen_tts(tts_text(txt), raw, 1.0)
    d0 = dur(raw); g0 = gaps(raw)
    sr = sil(str(raw))
    d1 = dur(sr); g1 = gaps(sr)
    print("  raw : %.1fs  gaps>0.15: %s" % (d0, [round(x, 2) for x in g0]))
    print("  +SR : %.1fs  gaps>0.15: %s   (%.2f wps)" % (d1, [round(x, 2) for x in g1], nw / d1))
