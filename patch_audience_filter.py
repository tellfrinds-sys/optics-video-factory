p = "build_lessons_page.py"
s = open(p, encoding="utf-8").read()
old = (
    'def _fetch():\n'
    '    return _get("lessons?select=lesson_uid,lesson_code,title_ar,chapter_uid,"\n'
    '        "learning_goal,sort_order,duration_minutes,level,video_url,video_backup_url,video_status,"\n'
    '        "video_duration_seconds,video_published_at,objectives_ar,question_bank_ar,scientific_refs_ar"\n'
    '        "&order=sort_order")\n'
)
new = (
    'def _fetch():\n'
    '    # primary_audience_uid=3 = محتوى "للجمهور" (تثقيفي مبسّط) — يُستبعد من الفهرس المهني الرئيسي\n'
    '    return _get("lessons?select=lesson_uid,lesson_code,title_ar,chapter_uid,"\n'
    '        "learning_goal,sort_order,duration_minutes,level,video_url,video_backup_url,video_status,"\n'
    '        "video_duration_seconds,video_published_at,objectives_ar,question_bank_ar,scientific_refs_ar"\n'
    '        "&primary_audience_uid=neq.3&order=sort_order")\n'
)
assert old in s, "pattern not found"
s = s.replace(old, new)
open(p, "w", encoding="utf-8").write(s)
print("patched")
