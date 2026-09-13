import os, sys, subprocess, pathlib
sys.path.insert(0, "/root/video-factory")
import narrated_render as nr


def dur(p):
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
        capture_output=True, text=True).stdout)


S1 = ("العين البشرية دي عضو تركيبها دقيق، ومتكوّن من كذا جزء بيكمّلوا بعض. "
      "في الفيديو ده هنتعرّف على أسامي الأجزاء دي بس، وهنفصّل كل جزء ووظيفته في الفيديوهات الجاية.")
S3 = ("الطبقة الوسطى اسمها العنبية، وفيها: القزحية الملوّنة، وفتحة البؤبؤ في نُصّها، "
      "وبعدين الجسم الهدبي، والمشيمية الغنيّة بالأوعية الدموية.")


def build(text, cg, sg):
    toks = text.split()
    out = []
    for i, w in enumerate(toks):
        out.append(w)
        if i == len(toks) - 1:
            break
        if w.endswith((".", "!", "؟", "?", ":")):
            g = sg
        elif w.endswith(("،", "؛")):
            g = cg
        else:
            g = 0.0
        if g > 0:
            out.append('<break time="%.2fs"/>' % g)
    return " ".join(out)


for tag, txt, nw in (("S1", S1, 29), ("S3", S3, 18)):
    for cg, sg in ((0.0, 0.0), (0.07, 0.16), (0.12, 0.25)):
        d = pathlib.Path("/tmp/p_%s_%s_%s.mp3" % (tag, cg, sg))
        nr._heygen_tts(build(txt, cg, sg), d, 1.0)
        x = dur(d)
        print("%s cg=%.2f sg=%.2f : %5.1fs  %.2f wps" % (tag, cg, sg, x, nw / x))
