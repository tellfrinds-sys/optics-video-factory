import sys, json, os, urllib.request

sys.path.insert(0, "/root/video-factory/pipeline")
sys.path.insert(0, "/root/video-factory")

f = "/root/video-factory/pipeline/.env"
for ln in open(f, encoding="utf-8"):
    if "=" in ln and not ln.strip().startswith("#"):
        k, v = ln.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

import agents

URL = os.environ["SUPABASE_URL"]
KEY = os.environ["SUPABASE_SERVICE_KEY"]


def sb_get(path):
    req = urllib.request.Request(URL + path, headers={"apikey": KEY, "Authorization": "Bearer " + KEY})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def sb_patch(path, body):
    req = urllib.request.Request(URL + path, data=json.dumps(body).encode(), method="PATCH",
                                  headers={"apikey": KEY, "Authorization": "Bearer " + KEY,
                                           "Content-Type": "application/json", "Prefer": "return=minimal"})
    urllib.request.urlopen(req, timeout=30).read()


for LU in (100001, 100002, 100003, 100004):
    rows = sb_get(f"/rest/v1/content_outputs?lesson_uid=eq.{LU}&stage_code=eq.SCRIPT_FINAL"
                   f"&approval_status=eq.approved&select=output_text&order=created_at.desc&limit=1")
    if rows:
        fs = json.loads(rows[0]["output_text"]).get("final_script") or {}
        objectives = fs.get("objectives_ar")
        questions = fs.get("question_bank_ar")
        refs_raw = fs.get("scientific_refs_ar")
    else:
        objectives = questions = refs_raw = None

    if not refs_raw:
        # مفيش سكريبت معتمد أو بلا مراجع -- خد المراجع الموجودة بالفعل في lessons (لو نصوص خام)
        cur = sb_get(f"/rest/v1/lessons?lesson_uid=eq.{LU}&select=objectives_ar,question_bank_ar,scientific_refs_ar")
        if cur:
            objectives = objectives or cur[0].get("objectives_ar")
            questions = questions or cur[0].get("question_bank_ar")
            refs_raw = refs_raw or cur[0].get("scientific_refs_ar")

    refs_enriched = agents.enrich_refs(refs_raw)

    patch = {}
    if objectives:
        patch["objectives_ar"] = objectives
    if questions:
        patch["question_bank_ar"] = questions
    if refs_enriched:
        patch["scientific_refs_ar"] = refs_enriched

    if patch:
        sb_patch(f"/rest/v1/lessons?lesson_uid=eq.{LU}", patch)
        print(LU, "-- patched:", list(patch.keys()), "refs:", json.dumps(refs_enriched, ensure_ascii=False))
    else:
        print(LU, "-- nothing to patch")
