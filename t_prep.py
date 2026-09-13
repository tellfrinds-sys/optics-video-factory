import sys, json
sys.path.insert(0, "/root/video-factory/pipeline")
import agents, prepare_lesson

L = prepare_lesson._fetch_lesson(100002)
print("lesson:", L["title_ar"])
fs = agents.write_script(L)
wc = sum(len(s["narration"].split()) for s in fs["scenes"])
print("scenes:", len(fs["scenes"]), "| words:", wc, "| ~min:", round(wc / 150, 1))
print("title:", fs["title"])
for s in fs["scenes"]:
    print("  S%s [%s] %s | term_en=%r | %dw" % (
        s["scene_no"], s.get("diagram"), s["heading"], s.get("term_en"),
        len(s["narration"].split())))
print("\nنموذج مشهد 4:\n", fs["scenes"][3]["narration"][:500])
print("\n--- review ---")
rv = agents.review_script(fs, L)
print(json.dumps(rv, ensure_ascii=False, indent=1)[:2500])
open("/tmp/fs_100002.json", "w", encoding="utf-8").write(json.dumps(fs, ensure_ascii=False, indent=1))
