import subprocess, pathlib, sys, re
sys.path.insert(0, "/root/video-factory")
import narrated_render as nr


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout)


S3 = ("الطبقة الوسطى اسمها العنبية، وفيها: القزحية الملوّنة، وفتحة البؤبؤ في نُصّها، "
      "وبعدين الجسم الهدبي، والمشيمية الغنيّة بالأوعية الدموية.")
S5 = ("جوّه العين فيه أوساط شفّافة بيعدّي منها الضوء: الخَلْط المائي اللي في الغُرْفة الأمامية، "
      "والعَدَسَة المعلّقة بأربطة رفيعة، والجسم الزُّجاجي الهُلامي اللي بيملا مؤخّرة العين.")


def soft(t):
    t = t.replace("،", "").replace(":", "").replace("؛", "")
    return re.sub(r"\s+", " ", t).strip()


for tag, txt, nw in (("S3", S3, 18), ("S5", S5, 25)):
    for label, x in (("orig", txt), ("soft", soft(txt))):
        d = pathlib.Path("/tmp/q_%s_%s.mp3" % (tag, label))
        nr._heygen_tts(x, d, 1.0)
        s = dur(d)
        print("%s %s: %5.1fs  %.2f wps" % (tag, label, s, nw / s))
