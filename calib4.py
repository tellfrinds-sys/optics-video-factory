"""يقارن 3 مسارات لعلاج التقطيع مع الحفاظ على انسيابية الصوت."""
import subprocess, pathlib, sys, re, unicodedata
sys.path.insert(0, "/root/video-factory")
import narrated_render as nr

TASH = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭـ]")
TMP = pathlib.Path("/tmp/c4")
TMP.mkdir(exist_ok=True)


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
    t = t.replace("،", " ").replace("؛", " ").replace(":", " ")
    return re.sub(r"\s+", " ", t).strip()


S3 = ("الطبقة الوسطى اسمها العِنَبِيَّة، وفيها: القَزَحِيَّة الملوّنة، وفتحة البُؤْبُؤ في نُصّها، "
      "وبعدين الجسم الهُدْبِي، والمَشِيمِيَّة الغنيّة بالأوعية الدموية.")
NW = 18

# ---- المسار الأول: صوت واحد نظيف بدون معالجة ----
raw = TMP / "s3_raw.mp3"
nr._heygen_tts(clean(S3), raw, 1.0)
print("RAW           %.1fs  gaps=%s" % (dur(raw), gaps(raw)))

# ---- الثاني: silenceremove لطيف (عتبة منخفضة، إبقاء أكثر، في WAV ثم mp3 واحد) ----
for thr, sd, ss in (("-42dB", 0.28, 0.16), ("-45dB", 0.30, 0.18), ("-40dB", 0.24, 0.14)):
    w = TMP / ("s3_%s_%s.wav" % (thr, ss))
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw),
                    "-af", "silenceremove=stop_periods=-1:stop_duration=%s:stop_threshold=%s:stop_silence=%s,"
                           "aresample=48000" % (sd, thr, ss), str(w)], check=True)
    print("SR %s sd=%s ss=%s : %.1fs  gaps=%s  (%.2f wps)" % (thr, sd, ss, dur(w), gaps(w), NW / dur(w)))

# ---- الثالث: توليد لكل عبارة ثم دمج بـ acrossfade 25ms + صمت 0.10s ----
phrases = [p.strip() for p in re.split(r"[،:.]", S3) if p.strip()]
segs = []
for i, ph in enumerate(phrases):
    s = TMP / ("ph%d.wav" % i)
    m = TMP / ("ph%d.mp3" % i)
    nr._heygen_tts(clean(ph), m, 1.0)
    # قصّ صمت البداية/النهاية فقط + هامش 60ms
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(m), "-af",
                    "silenceremove=start_periods=1:start_silence=0.05:start_threshold=-45dB:"
                    "stop_periods=1:stop_silence=0.05:stop_threshold=-45dB,aresample=48000", str(s)], check=True)
    segs.append(s)
    print("  phrase %d: %r -> %.2fs" % (i, ph[:30], dur(s)))
# دمج بصمت 0.12s بين العبارات
concat = TMP / "s3_perphrase.wav"
parts = []
inp = []
for i, s in enumerate(segs):
    inp += ["-i", str(s)]
fc = ""
for i in range(len(segs)):
    fc += "[%d:a]" % i
    if i < len(segs) - 1:
        fc += "aevalsrc=0:d=0.12:s=48000[g%d];" % i
gg = "".join("[g%d]" % i for i in range(len(segs) - 1))
# تشابك: seg0 g0 seg1 g1 ...
order = ""
for i in range(len(segs)):
    order += "[%d:a]" % i
    if i < len(segs) - 1:
        order += "[g%d]" % i
fc2 = ";".join("aevalsrc=0:d=0.12:s=48000[g%d]" % i for i in range(len(segs) - 1))
full = fc2 + ";" + order + "concat=n=%d:v=0:a=1[out]" % (2 * len(segs) - 1)
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inp,
                "-filter_complex", full, "-map", "[out]", str(concat)], check=True)
print("PER-PHRASE    %.1fs  gaps=%s  (%.2f wps)" % (dur(concat), gaps(concat), NW / dur(concat)))
