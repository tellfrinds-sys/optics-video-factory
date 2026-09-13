# -*- coding: utf-8 -*-
"""يبني صفحة فهرس الدروس والفيديوهات (lessons.html) من Supabase وينشرها على الموقع.
   يُستدعى تلقائيًا بعد كل إنتاج ناجح، أو يدويًا:  python3 build_lessons_page.py
"""
import json, os, re, html, subprocess, urllib.request
from pathlib import Path

ROOT = Path("/root/video-factory")
SITE = Path("/var/www/opticsgate.online/html")
OUT = SITE / "lessons.html"


def _env():
    f = ROOT / "pipeline" / ".env"
    if f.exists():
        for ln in f.read_text().splitlines():
            if "=" in ln and not ln.strip().startswith("#"):
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _get(path):
    key = os.environ["SUPABASE_SERVICE_KEY"]
    req = urllib.request.Request(os.environ["SUPABASE_URL"] + "/rest/v1/" + path,
                                 headers={"apikey": key, "Authorization": "Bearer " + key})
    return json.loads(urllib.request.urlopen(req, timeout=40).read())


def _fetch():
    return _get("lessons?select=lesson_uid,lesson_code,title_ar,chapter_uid,"
        "learning_goal,sort_order,duration_minutes,level,video_url,video_backup_url,video_status,"
        "video_duration_seconds,video_published_at,objectives_ar,question_bank_ar,scientific_refs_ar"
        "&order=sort_order")


def _drive_embed(link):
    if not link:
        return None
    m = re.search(r"(?:/d/|id=)([A-Za-z0-9_-]{20,})", link)
    return "https://drive.google.com/file/d/%s/preview" % m.group(1) if m else None


def _esc(s):
    return html.escape(str(s or ""))


def _mmss(sec):
    try:
        sec = int(float(sec)); return "%d:%02d" % (sec // 60, sec % 60)
    except Exception:
        return ""


def _lesson_html(l):
    code = l["lesson_code"]
    embed = _drive_embed(l.get("video_url"))
    ready = bool(embed)
    badge = ('<span class="lx-badge lx-ok">فيديو متاح</span>' if ready else
             ('<span class="lx-badge lx-fail">قيد المراجعة</span>' if l.get("video_status") == "qa_failed"
              else '<span class="lx-badge lx-soon">قريبًا</span>'))
    dur = _mmss(l.get("video_duration_seconds")) or ("%g د" % l["duration_minutes"] if l.get("duration_minutes") else "")
    parts = ['<article class="lx-lesson" id="%s">' % _esc(code)]
    parts.append('<div class="lx-lhead"><span class="lx-num">%s</span>'
                 '<h3>%s</h3>%s</div>' % (_esc(code.split("-")[-1].replace("L", "")), _esc(l["title_ar"]), badge))
    if l.get("learning_goal"):
        parts.append('<p class="lx-goal">%s</p>' % _esc(l["learning_goal"]))
    if embed:
        parts.append('<div class="lx-video"><iframe src="%s" allow="autoplay; fullscreen" '
                     'allowfullscreen loading="lazy"></iframe></div>' % embed)
        if dur:
            parts.append('<div class="lx-meta">المدة: %s</div>' % _esc(dur))
    obj = l.get("objectives_ar") or []
    if obj:
        parts.append('<details class="lx-acc"><summary>أهداف الدرس</summary><ul>'
                     + "".join("<li>%s</li>" % _esc(x) for x in obj) + "</ul></details>")
    qs = l.get("question_bank_ar") or []
    if qs:
        items = []
        for q in qs:
            if isinstance(q, dict):
                ch = q.get("choices") or []
                items.append("<li><b>%s</b>%s%s</li>" % (
                    _esc(q.get("q") or q.get("question") or ""),
                    ("<ul>" + "".join("<li>%s</li>" % _esc(c) for c in ch) + "</ul>") if ch else "",
                    ("<div class='lx-ans'>الإجابة: %s</div>" % _esc(q.get("answer")) if q.get("answer") else "")))
            else:
                items.append("<li>%s</li>" % _esc(q))
        parts.append('<details class="lx-acc"><summary>بنك الأسئلة (%d)</summary><ol>%s</ol></details>'
                     % (len(qs), "".join(items)))
    refs = l.get("scientific_refs_ar") or []
    if refs:
        parts.append('<details class="lx-acc"><summary>المصادر العلمية</summary><ul>'
                     + "".join("<li>%s</li>" % _esc(r) for r in refs) + "</ul></details>")
    parts.append("</article>")
    return "\n".join(parts)


def build():
    _env()
    rows = _fetch()
    doors = _get("curriculum_doors?select=door_uid,door_code,title_ar&order=sort_order")
    units = _get("curriculum_units?select=unit_uid,door_uid,title_ar&order=sort_order")
    chaps = _get("curriculum_chapters?select=chapter_uid,unit_uid,title_ar&order=sort_order")
    total = len(rows)
    ready = sum(1 for l in rows if _drive_embed(l.get("video_url")))

    les_by_chap = {}
    for l in rows:
        les_by_chap.setdefault(l.get("chapter_uid"), []).append(l)
    for v in les_by_chap.values():
        v.sort(key=lambda l: l.get("sort_order") or 0)

    sections = []
    for d in doors:
        d_ready = d_total = 0
        d_inner = []
        for u in [u for u in units if u["door_uid"] == d["door_uid"]]:
            u_inner = []
            for c in [c for c in chaps if c["unit_uid"] == u["unit_uid"]]:
                ll = les_by_chap.get(c["chapter_uid"], [])
                if not ll:
                    continue
                d_total += len(ll)
                d_ready += sum(1 for l in ll if _drive_embed(l.get("video_url")))
                u_inner.append('<div class="lx-chap"><div class="lx-chap-h">%s</div>%s</div>' % (
                    _esc(c["title_ar"]), "\n".join(_lesson_html(l) for l in ll)))
            if u_inner:
                d_inner.append('<div class="lx-unit"><div class="lx-unit-h">%s</div>%s</div>' % (
                    _esc(u["title_ar"]), "\n".join(u_inner)))
        if not d_inner:
            continue
        sections.append(
            '<details class="lx-book"%s><summary><span>%s — %s</span>'
            '<span class="lx-count">%d/%d فيديو</span></summary>%s</details>' % (
                " open" if d["door_code"] == "B01" else "", _esc(d["door_code"]), _esc(d["title_ar"]),
                d_ready, d_total, "\n".join(d_inner)))

    page = TEMPLATE.replace("{{TOTAL}}", str(total)).replace("{{READY}}", str(ready)).replace(
        "{{SECTIONS}}", "\n".join(sections)).replace(
        "{{UPDATED}}", __import__("time").strftime("%Y-%m-%d %H:%M"))
    OUT.write_text(page, encoding="utf-8")
    print("wrote", OUT, len(page), "bytes;", ready, "/", total, "videos")
    # نشر على GitHub
    try:
        subprocess.run(["git", "-C", str(SITE), "add", "lessons.html"], check=False, timeout=30)
        subprocess.run(["git", "-C", str(SITE), "-c", "user.email=bot@opticsgate.online",
                        "-c", "user.name=OpticsGate Bot", "commit", "-m",
                        "تحديث فهرس الدروس (%d/%d فيديو)" % (ready, total)], check=False, timeout=30)
        subprocess.run(["git", "-C", str(SITE), "push"], check=False, timeout=60)
    except Exception as e:
        print("git publish skipped:", e)


TEMPLATE = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>فهرس الدروس والفيديوهات | بوابة البصريات</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;900&family=Cairo:wght@400;600;700;900&display=swap" rel="stylesheet">
<style>
 *{box-sizing:border-box} body{margin:0}
 body{font-family:'Tajawal','Cairo',system-ui,sans-serif;background:#060b18;color:#e9edf7;line-height:1.7}
 a{color:#2dd4bf;text-decoration:none}
 h1,h2,h3,summary{font-family:'Cairo','Tajawal',sans-serif}
 .lx-nav{position:sticky;top:0;z-index:20;background:rgba(6,11,24,.82);backdrop-filter:blur(12px);border-bottom:1px solid rgba(148,178,214,.12)}
 .lx-nav div{max-width:1100px;margin:0 auto;padding:14px 22px;display:flex;align-items:center;justify-content:space-between;gap:14px}
 .lx-nav img{width:64px;height:64px;object-fit:contain}
 .lx-wrap{max-width:1100px;margin:0 auto;padding:38px 22px 90px}
 .lx-hero h1{font-size:30px;margin:0 0 10px;color:#f7f9fc}
 .lx-hero p{color:#9db0cc;margin:0 0 18px;font-size:15px}
 .lx-stat{display:inline-flex;gap:8px;align-items:center;background:rgba(45,212,191,.1);border:1px solid rgba(45,212,191,.3);color:#5eead4;padding:6px 14px;border-radius:999px;font-size:13px;font-weight:700}
 .lx-book{margin:16px 0;border:1px solid rgba(148,178,214,.16);border-radius:16px;background:linear-gradient(160deg,#0c1428,#0a0f20);overflow:hidden}
 .lx-book>summary{cursor:pointer;list-style:none;padding:18px 20px;display:flex;justify-content:space-between;align-items:center;gap:12px;font-size:16px;font-weight:800;color:#f0f4fa}
 .lx-book>summary::-webkit-details-marker{display:none}
 .lx-book>summary:hover{background:rgba(45,212,191,.06)}
 .lx-count{font-size:12px;font-weight:700;color:#8fa0bc;background:rgba(148,178,214,.1);border:1px solid rgba(148,178,214,.2);padding:4px 10px;border-radius:999px;white-space:nowrap}
 .lx-unit{padding:2px 14px 6px}
 .lx-unit-h{color:#5eead4;font-size:14px;font-weight:800;margin:16px 0 4px;padding-inline-start:6px;border-inline-start:3px solid rgba(45,212,191,.5)}
 .lx-chap{padding:6px 18px 14px}
 .lx-chap-h{color:#a78bfa;font-size:12.5px;font-weight:800;margin:14px 0 8px}
 .lx-lesson{border:1px solid rgba(148,178,214,.12);border-radius:13px;background:#0a1122;padding:16px;margin:10px 0}
 .lx-lhead{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
 .lx-num{width:30px;height:30px;flex:0 0 30px;border-radius:8px;background:rgba(45,212,191,.12);border:1px solid rgba(45,212,191,.3);color:#5eead4;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:13px}
 .lx-lhead h3{margin:0;font-size:15px;color:#f0f4fa;flex:1;min-width:180px}
 .lx-badge{font-size:11px;font-weight:700;padding:3px 10px;border-radius:999px}
 .lx-ok{background:rgba(45,212,191,.14);border:1px solid rgba(45,212,191,.4);color:#8ff7e6}
 .lx-soon{background:rgba(148,178,214,.1);border:1px solid rgba(148,178,214,.28);color:#aebcd4}
 .lx-fail{background:rgba(245,196,81,.12);border:1px solid rgba(245,196,81,.4);color:#f5c451}
 .lx-goal{color:#93a3bf;font-size:13px;margin:9px 0 0}
 .lx-video{position:relative;margin:12px 0 0;border-radius:11px;overflow:hidden;border:1px solid rgba(148,178,214,.18);aspect-ratio:16/9;background:#000}
 .lx-video iframe{position:absolute;inset:0;width:100%;height:100%;border:0}
 .lx-meta{color:#7d93b3;font-size:12px;margin-top:6px}
 .lx-acc{margin:9px 0 0;border-top:1px solid rgba(148,178,214,.1);padding-top:8px}
 .lx-acc>summary{cursor:pointer;color:#5eead4;font-size:13px;font-weight:700;padding:4px 0}
 .lx-acc ul,.lx-acc ol{margin:6px 0;padding-inline-start:22px;color:#c6d3e8;font-size:13.5px}
 .lx-acc li{margin:4px 0}
 .lx-ans{color:#8ff7e6;font-size:12.5px;margin-top:3px}
 .lx-foot{text-align:center;color:#5c6f8c;font-size:12px;margin-top:40px}
 @media(max-width:560px){.lx-hero h1{font-size:24px}}
</style>
</head>
<body>
<div class="lx-nav"><div>
 <a href="/"><img src="assets/logo_nav.png" alt="بوابة البصريات"/></a>
 <a href="/" style="font-size:13px;font-weight:700">→ الصفحة الرئيسية</a>
</div></div>
<div class="lx-wrap">
 <div class="lx-hero">
  <h1>فهرس الدروس والفيديوهات</h1>
  <p>المنهج الكامل لأكاديمية بوابة البصريات — {{TOTAL}} درسًا عبر 20 بابًا. كل درس يظهر تحته الفيديو وأهدافه وبنك أسئلته ومصادره فور اعتماده.</p>
  <span class="lx-stat">● {{READY}} من {{TOTAL}} فيديو منشور</span>
 </div>
 {{SECTIONS}}
 <div class="lx-foot">آخر تحديث: {{UPDATED}} · يُحدَّث تلقائيًا بعد اعتماد كل فيديو</div>
</div>
</body>
</html>
"""

if __name__ == "__main__":
    build()
