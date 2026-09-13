# -*- coding: utf-8 -*-
import sys, time, subprocess as sp, os
sys.path.insert(0, "/root/video-factory")
import piper_tts as P

OUT = "/var/www/opticsgate.online/html/ttslab"
T = {
 "f_scene1": ("أهلاً بيكم في درس جديد من دروس أكاديمية بوابة البصريات. أخصائي البصريات الشاطر "
              "لازم يفهم كل أجزاء العين بدقة. النهاردة هنتكلم عن أول خط دفاع ونسيج شفاف قدام العين، "
              "وهو القرنية. المعلومة دي كلها محتوى تعليمي، ومش بديل عن الفحص الطبي في العيادة."),
 "f_scene5": ("الطبقة التالتة وهي الأكبر في جسم القرنية هي السدى. بتمثل تسعين في المية من السمك "
              "الكلي، يعني حوالي نص مليمتر. بتتكون من ألياف كولاجين. الأكسجين والتغذية بتوصل "
              "لها من السائل الدمعي عشان تفضل شفافة."),
}


def metrics(f, wc):
    dur = float(sp.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                        "csv=p=0", f], capture_output=True, text=True).stdout.strip())
    err = sp.run(["ffmpeg", "-i", f, "-af", "silencedetect=noise=-30dB:d=0.12", "-f", "null", "-"],
                 capture_output=True, text=True).stderr
    return dur, wc / dur * 60, err.count("silence_start")


for ls in ("0.70", "0.78"):
    os.environ["PIPER_LS"] = ls
    import importlib
    importlib.reload(P)
    for n, t in T.items():
        f = "%s/%s_ls%s.mp3" % (OUT, n, ls.replace(".", ""))
        t0 = time.time()
        P.piper_tts(t, f, 1.0)
        d, wpm, g = metrics(f, len(t.split()))
        print("%s ls=%s: %.1fs | %.0f wpm | %d gaps | synth %.1fs" % (n, ls, d, wpm, g, time.time() - t0))

page = ['<!doctype html><meta charset=utf-8><body dir=rtl style="font-family:sans-serif;background:#0b1220;color:#e9edf7;max-width:780px;margin:auto;padding:24px">',
        "<h2>Piper مصري — نسخة نهائية (جملة كاملة + سرعتين)</h2>",
        "<p>ls=0.70 أسرع · ls=0.78 أهدأ. القرنية بالقاف · نسيج/قدام مصري · أكسجين/فسيولوجيا جيم معطّشة · سُمك بالضم.</p>"]
for ls in ("070", "078"):
    page.append("<h3>سرعة %s</h3>" % ls)
    for n in T:
        page.append('<audio controls src="%s_ls%s.mp3" style="display:block;margin:6px 0"></audio>' % (n, ls))
open("%s/index.html" % OUT, "w", encoding="utf-8").write("\n".join(page) + "</body>")
print(">>> https://opticsgate.online/ttslab/")
