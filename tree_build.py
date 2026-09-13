import json
d = json.load(open("curriculum_export2.json", encoding="utf-8"))
doors = {x["door_uid"]: x for x in d["doors"]}
units = d["units"]
chapters_by_unit = {}
for c in d["chapters"]:
    chapters_by_unit.setdefault(c["unit_uid"], []).append(c)
units_by_door = {}
for u in units:
    units_by_door.setdefault(u["door_uid"], []).append(u)
lessons_by_chapter = {}
for l in d["lessons"]:
    lessons_by_chapter.setdefault(l["chapter_uid"], []).append(l)

out = []
for du in sorted(doors, key=lambda k: doors[k].get("door_code") or ""):
    dd = doors[du]
    out.append("### باب %s: %s" % (dd.get("door_code"), dd["title_ar"]))
    for u in sorted(units_by_door.get(du, []), key=lambda x: x["unit_uid"]):
        out.append("  وحدة: %s" % u["title_ar"])
        for ch in sorted(chapters_by_unit.get(u["unit_uid"], []), key=lambda x: x["chapter_uid"]):
            out.append("    فصل: %s" % ch["title_ar"])
            for les in sorted(lessons_by_chapter.get(ch["chapter_uid"], []), key=lambda x: x["sort_order"] or 0):
                out.append("      - [%s] %s" % (les["lesson_uid"], les["title_ar"]))

open("curriculum_tree.txt", "w", encoding="utf-8").write("\n".join(out))
print("lines:", len(out))
