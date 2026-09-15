import json
import os
import urllib.request

import produce_lesson
produce_lesson._load_env()

url = os.environ["SUPABASE_URL"]
key = os.environ["SUPABASE_SERVICE_KEY"]
req = urllib.request.Request(
    f"{url}/rest/v1/lessons?lesson_uid=eq.100008&select=lesson_uid,video_url,video_status,video_published_at,objectives_ar,question_bank_ar,scientific_refs_ar",
    headers={"apikey": key, "Authorization": f"Bearer {key}"},
)
d = json.loads(urllib.request.urlopen(req, timeout=30).read())[0]
print("video_url:", d.get("video_url"))
print("video_status:", d.get("video_status"))
print("published_at:", d.get("video_published_at"))
print("objectives count:", len(d.get("objectives_ar") or []))
print("question_bank count:", len(d.get("question_bank_ar") or []))
refs = d.get("scientific_refs_ar") or []
print("refs count:", len(refs))
print("refs have urls:", all(isinstance(r, dict) and r.get("url") for r in refs))
