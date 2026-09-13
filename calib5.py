"""قصّ الصمت الداخلي بلا نقر: detect -> atrim مقاطع الكلام -> concat مع acrossfade قصير."""
import subprocess, pathlib, sys, re, unicodedata
sys.path.insert(0, "/root/video-factory")
import narrated_render as nr

TMP = pathlib.Path("/tmp/c5"); TMP.mkdir(exist_ok=True)
TASH = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭـ]")


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout)


def gaps(p, thr="-38dB", d="0.14"):
    o = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(p), "-af",
                        "silencedetect=n=%s:d=%s" % (thr, d), "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    return [round(float(x), 2) for x in re.findall(r"silence_duration: ([\d.]+)", o)]


def clean(t):
    t = unicodedata.normalize("NFC", t)
    for c in "،؛:":
        t = t.replace(c, " ")
    return re.sub(r"\s+", " ", t).strip()


def degap_xfade(src, dst, keep=0.16, thr=-34.0, mind=0.30, xf=0.012):
    """يكتشف فترات الصمت، يبقي 'keep' ثانية من كلٍّ منها، ويصل المقاطع بـ crossfade 'xf'."""
    txt = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(src), "-af",
                          "silencedetect=n=%.0fdB:d=%.2f" % (thr, mind), "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", txt)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", txt)]
    total = dur(src)
    if not starts:
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
                        "-ar", "48000", str(dst)], check=True)
        return
    # ابنِ قائمة مقاطع "الاحتفاظ" = الكلام + هامش keep/2 حول كل فجوة
    segs = []
    cur = 0.0
    for s, e in zip(starts, ends):
        seg_end = max(cur, s + keep / 2)
        segs.append((cur, seg_end))
        cur = max(seg_end, e - keep / 2)
    segs.append((cur, total))
    segs = [(a, b) for a, b in segs if b - a > 0.03]
    parts = []
    inp = []
    for i, (a, b) in enumerate(segs):
        inp += ["-i", str(src)]
    fc = []
    for i, (a, b) in enumerate(segs):
        fc.append("[%d:a]atrim=start=%.3f:end=%.3f,asetpts=PTS-STARTPTS,aresample=48000[s%d]" % (i, a, b, i))
    # سلسلة acrossfade
    chain = "[s0]"
    label = "s0"
    for i in range(1, len(segs)):
        out = "x%d" % i
        fc.append("%s[s%d]acrossfade=d=%.3f:c1=tri:c2=tri[%s]" % ("[" + label + "]" if not label.startswith("[") else label, i, xf, out))
        label = out
    full = ";".join(fc)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inp,
                    "-filter_complex", full, "-map", "[%s]" % label, str(dst)], check=True)


S3 = ("الطبقة الوسطى اسمها العِنَبِيَّة، وفيها: القَزَحِيَّة الملوّنة، وفتحة البُؤْبُؤ في نُصّها، "
      "وبعدين الجسم الهُدْبِي، والمَشِيمِيَّة الغنيّة بالأوعية الدموية.")
NW = 18
raw = TMP / "raw.mp3"
nr._heygen_tts(clean(S3), raw, 1.0)
print("RAW  %.1fs  gaps=%s" % (dur(raw), gaps(raw)))

# silenceremove محافظ جدًا
for thr in (-50, -55):
    w = TMP / ("sr%d.wav" % -thr)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw), "-af",
                    "silenceremove=stop_periods=-1:stop_duration=0.30:stop_threshold=%ddB:stop_silence=0.16,aresample=48000" % thr,
                    str(w)], check=True)
    print("SR %ddB  %.1fs  gaps=%s  (%.2f wps)" % (thr, dur(w), gaps(w), NW / dur(w)))

# detect + atrim + crossfade
for keep in (0.14, 0.18):
    d = TMP / ("xf%02d.wav" % int(keep * 100))
    degap_xfade(raw, d, keep=keep)
    print("XFADE keep=%.2f  %.1fs  gaps=%s  (%.2f wps)" % (keep, dur(d), gaps(d), NW / dur(d)))
