# -*- coding: utf-8 -*-
"""يجعل parse_script_text يدمج المشاهد الملصوقة فوق السيناريو الأصلي (لصق جزئي آمن)."""
import io, re, sys

P = "/root/video-factory/pipeline/agents.py"
src = io.open(P, encoding="utf-8").read()

OLD = """    if scenes:
        base["scenes"] = scenes
    return base"""

NEW = '''    if scenes:
        base_scenes = list(base.get("scenes") or [])
        if base_scenes:
            by_no = {}
            for i, s in enumerate(base_scenes):
                by_no[int(s.get("scene_no") or (i + 1))] = dict(s)
            for s in scenes:
                old = by_no.get(s["scene_no"], {})
                merged = dict(old)
                merged.update({k: v for k, v in s.items() if v not in (None, "", [])})
                if s.get("diagram") in ("", "eye") and old.get("diagram"):
                    merged["diagram"] = old["diagram"]
                if not s.get("term_en") and old.get("term_en"):
                    merged["term_en"] = old["term_en"]
                if old.get("labels"):
                    merged.setdefault("labels", old["labels"])
                if old.get("visual_focus"):
                    merged.setdefault("visual_focus", old["visual_focus"])
                by_no[s["scene_no"]] = merged
            base["scenes"] = [by_no[k] for k in sorted(by_no)]
        else:
            base["scenes"] = scenes
    return base'''

if NEW.split("\n")[1].strip() in src:
    print("already patched")
elif OLD in src:
    src = src.replace(OLD, NEW, 1)
    io.open(P, "w", encoding="utf-8").write(src)
    print("patched parse_script_text merge")
else:
    print("ANCHOR NOT FOUND", file=sys.stderr)
    sys.exit(1)
