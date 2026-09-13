import ast
p = "/root/video-factory/narrated_render.py"
s = open(p, encoding="utf-8").read()

i0 = s.index("def _degap(path: Path) -> None:")
i1 = s.index("tmp.replace(path)", i0) + len("tmp.replace(path)") + 1
old = s[i0:i1]

new = '''def _degap(path: Path) -> None:
    """يقصّ الصمت الداخلي في صوت HeyGen (وقفاته ~0.6ث بين العبارات) بلا تقطيع:
    كشف فترات الصمت -> اقتطاع مقاطع الكلام مع إبقاء DEGAP_KEEP ثانية من كل فجوة
    -> وصلها بـ acrossfade قصير (12ms) يمنع النقر."""
    if not DEGAP:
        return
    thr, mind, keep, xf = -34.0, DEGAP_MIN, DEGAP_KEEP, 0.012
    det = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af",
                          "silencedetect=n=%.0fdB:d=%.2f" % (thr, mind), "-f", "null", "-"],
                         capture_output=True, text=True, timeout=120).stderr
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\\d.]+)", det)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\\d.]+)", det)]
    if not starts or len(ends) < len(starts):
        return
    total = _dur(path)
    segs, cur = [], 0.0
    for a, b in zip(starts, ends):
        seg_end = max(cur, a + keep / 2)
        segs.append((cur, seg_end))
        cur = max(seg_end, b - keep / 2)
    segs.append((cur, total))
    segs = [(a, b) for a, b in segs if b - a > 0.03]
    if len(segs) < 2:
        return
    tmp = path.with_suffix(".degap.m4a")
    inp, fc = [], []
    for i, (a, b) in enumerate(segs):
        inp += ["-i", str(path)]
        fc.append("[%d:a]atrim=start=%.3f:end=%.3f,asetpts=PTS-STARTPTS,aresample=48000[s%d]" % (i, a, b, i))
    label = "s0"
    for i in range(1, len(segs)):
        fc.append("[%s][s%d]acrossfade=d=%.3f:c1=tri:c2=tri[x%d]" % (label, i, xf, i))
        label = "x%d" % i
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inp,
                        "-filter_complex", ";".join(fc), "-map", "[%s]" % label,
                        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(tmp)],
                       capture_output=True, text=True, timeout=180)
    if r.returncode == 0 and tmp.exists() and tmp.stat().st_size > 2000:
        final = path.with_suffix(".mp3")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(tmp),
                        "-c:a", "libmp3lame", "-q:a", "2", "-ar", "48000", str(final)],
                       capture_output=True, text=True, timeout=120)
        tmp.unlink(missing_ok=True)
'''

assert old in s
s = s.replace(old, new, 1)
s = s.replace('os.environ.get("DEGAP_KEEP", "0.08")', 'os.environ.get("DEGAP_KEEP", "0.17")')
s = s.replace('os.environ.get("DEGAP_MIN", "0.16")', 'os.environ.get("DEGAP_MIN", "0.30")')
open(p, "w", encoding="utf-8").write(s)
ast.parse(s)
print("patched _degap -> crossfade method; DEGAP_KEEP=0.17 DEGAP_MIN=0.30")
