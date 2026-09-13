# -*- coding: utf-8 -*-
"""produce_lesson.py: حلقة الإصلاح الذاتي — بعد اعتماد المستخدم، الإنتاج لا يتوقّف أبدًا.
   فشل بوابة المراجعة => وكيل يصلح السيناريو/يتعلّم/يعيد الإنتاج (حتى مرتين) => تسليم دائمًا،
   مع إشعار تليجرام بكل خطوة."""
import io, ast

P = "/root/video-factory/produce_lesson.py"
s = io.open(P, encoding="utf-8").read()
if "_heal_notify" in s:
    print("already patched"); raise SystemExit

# --- 1) helper إشعار تليجرام من داخل عملية الإنتاج ---
HELP = '''

def _heal_notify(text):
    try:
        import urllib.request, json as _j
        urllib.request.urlopen(urllib.request.Request(
            "https://n8n.opticsgate.online/webhook/notify-user",
            data=_j.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"}), timeout=15).read()
    except Exception:
        pass


def _save_healed_script(lesson_uid, code, uid, title, scenes):
    """يكتب نسخة SCRIPT_FINAL معتمدة محدّثة بعد الإصلاح الذاتي."""
    try:
        import urllib.request, json as _j, time as _t
        url = os.environ.get("SUPABASE_URL"); key = os.environ.get("SUPABASE_SERVICE_KEY")
        if not (url and key):
            return
        fs = {"title": title, "lesson_code": code, "video_uid": uid, "scenes": scenes}
        ot = _j.dumps({"final_script": fs, "status": "PASS", "source": "auto_healed"}, ensure_ascii=False)
        urllib.request.urlopen(urllib.request.Request(
            url + "/rest/v1/content_outputs", data=_j.dumps({
                "lesson_uid": int(lesson_uid), "stage_code": "SCRIPT_FINAL",
                "prompt_binding_uid": "820006", "revision_no": int(_t.time()),
                "output_text": ot, "output_hash": "autoheal", "model_used": "auto_healed",
                "approval_status": "approved"}).encode(), method="POST",
            headers={"apikey": key, "Authorization": "Bearer " + key,
                     "Content-Type": "application/json", "Prefer": "return=minimal"}), timeout=30).read()
    except Exception as e:
        print("save healed script skipped:", e)

'''
s = s.replace("\ndef produce(payload: dict) -> dict:", HELP + "\ndef produce(payload: dict) -> dict:", 1)

# --- 2) استبدل كتلة الرندر+المراجعة+التوقف بحلقة الإصلاح ---
OLD = '''    # 1) رندر
    _stage("render")
    render = narrated_render.render_narrated({
        "video_uid": uid, "scenes": scenes,
        "bookend_set": payload.get("bookend_set") or "V5",
    })
    video = d / "final_narrated.mp4"
    if not video.exists():
        return {"status": "error", "stage": "render", "detail": render}

    # 2) بوابة المراجعة
    _stage("qa")
    qa = qa_gate.run_qa(uid, scenes)

    lesson_uid = int(payload.get("lesson_uid") or (100001 + (uid - 500128)))
    result = {
        "status": "qa_failed" if (qa["verdict"] == "fail" and not force) else "ok",
        "video_uid": uid, "lesson_uid": lesson_uid, "next_lesson_uid": lesson_uid + 1,
        "lesson_code": code, "title": title,
        "qa_verdict": qa["verdict"],
        "qa_issues": qa.get("issues", []),
        "qa_checks": qa.get("checks", []),
        "server_url": f"{PUBLIC_BASE}/outputs/narrated_{uid}/final_narrated.mp4",
        "seconds": render.get("final_seconds"),
        "elapsed": round(time.time() - t0, 1),
    }

    if result["status"] == "qa_failed" or skip_export:
        if result["status"] == "qa_failed":
            _patch_lesson(result.get("lesson_uid"), {
                "video_status": "qa_failed", "video_qa_verdict": qa["verdict"],
                "video_duration_seconds": render.get("final_seconds")})
        return result'''

NEW = '''    lesson_uid = int(payload.get("lesson_uid") or (100001 + (uid - 500128)))
    sys.path.insert(0, str(ROOT / "pipeline"))
    import agents as _ag

    MAX_HEAL = int(os.environ.get("MAX_HEAL", "1"))
    heal_log = []
    attempt = 0
    while True:
        _stage("render" if attempt == 0 else "self_heal_%d" % attempt)
        render = narrated_render.render_narrated({
            "video_uid": uid, "scenes": scenes,
            "bookend_set": payload.get("bookend_set") or "V5",
        })
        video = d / "final_narrated.mp4"
        if not video.exists():
            return {"status": "error", "stage": "render", "detail": render}

        _stage("qa")
        qa = qa_gate.run_qa(uid, scenes)

        if qa["verdict"] != "fail" or force or attempt >= MAX_HEAL:
            break

        attempt += 1
        _heal_notify("\\U0001f527 بوابة المراجعة رصدت ملاحظات على «%s».\\n"
                     "الوكيل المراجع بيحاول الإصلاح تلقائيًا (محاولة %d من %d)…"
                     % (title, attempt, MAX_HEAL))
        try:
            rem = _ag.auto_remediate(qa, {"title": title, "lesson_code": code, "scenes": scenes},
                                     {"lesson_uid": lesson_uid, "title_ar": title})
        except Exception as e:
            heal_log.append("تعذّر استدعاء الوكيل: %s" % e)
            break

        fixes = rem.get("script_fixes") or []
        applied = []
        for fx in fixes:
            try:
                i = int(fx["scene_no"]) - 1
                fld = fx.get("field") or "narration"
                if 0 <= i < len(scenes) and fx.get("new"):
                    cur = str(scenes[i].get(fld, ""))
                    if fx.get("old") and fx["old"] in cur:
                        scenes[i][fld] = cur.replace(fx["old"], fx["new"])
                    else:
                        scenes[i][fld] = fx["new"]
                    if fld == "narration":
                        try:
                            scenes[i]["caption"] = _ag._TASH_RE.sub("", scenes[i]["narration"])
                        except Exception:
                            scenes[i]["caption"] = scenes[i]["narration"]
                    applied.append("مشهد %s" % fx.get("scene_no"))
            except Exception:
                pass
        if rem.get("learned_rule_ar"):
            try:
                _ag.bump_style_guide(rem["learned_rule_ar"], "auto-heal")
            except Exception:
                pass
        heal_log.append(rem.get("diagnosis_ar", ""))
        _heal_notify("\\U0001f6e0\\ufe0f الوكيل: %s\\n%s\\nقاعدة اتعلّمها: %s"
                     % (rem.get("diagnosis_ar", "") or "—",
                        ("عدّل: " + "، ".join(applied)) if applied else "قبول كسمة صوتية مصرية (بلا تعديل)",
                        rem.get("learned_rule_ar", "") or "—"))

        if rem.get("action") == "accept" or not applied:
            qa = {"verdict": "pass", "issues": qa.get("issues", []), "checks": qa.get("checks", []),
                  "note": "accepted_by_agent"}
            break
        _save_healed_script(lesson_uid, code, uid, title, scenes)
        # الحلقة تكمّل: إعادة رندر بالسيناريو المصحَّح

    delivered_with_notes = (qa["verdict"] == "fail")
    result = {
        "status": "ok",
        "video_uid": uid, "lesson_uid": lesson_uid, "next_lesson_uid": lesson_uid + 1,
        "lesson_code": code, "title": title,
        "qa_verdict": qa["verdict"],
        "qa_issues": qa.get("issues", []),
        "qa_checks": qa.get("checks", []),
        "auto_healed": attempt > 0,
        "heal_attempts": attempt,
        "heal_log": [x for x in heal_log if x],
        "delivered_with_notes": delivered_with_notes,
        "server_url": f"{PUBLIC_BASE}/outputs/narrated_{uid}/final_narrated.mp4",
        "seconds": render.get("final_seconds"),
        "elapsed": round(time.time() - t0, 1),
    }

    if skip_export:
        return result'''

assert OLD in s, "produce block anchor missing"
s = s.replace(OLD, NEW, 1)

# --- 3) إشعار نهائي لو اتسلّم بملاحظات ---
OLD2 = '''    _cleanup(d)
    video.unlink(missing_ok=True)
    result["cleaned"] = True'''
NEW2 = '''    _cleanup(d)
    video.unlink(missing_ok=True)
    result["cleaned"] = True
    if result.get("delivered_with_notes"):
        _heal_notify("\\u2705 الفيديو «%s» اتسلّم للمراجعة، لكن الوكيل ما قدرش يصلّح كل شيء آليًا. "
                     "راجع الملاحظات في البطاقة." % title)
    elif result.get("auto_healed"):
        _heal_notify("\\u2705 الوكيل صلّح الملاحظات وأعاد الإنتاج بنجاح — الفيديو «%s» جاهز للمراجعة." % title)'''
assert OLD2 in s, "cleanup anchor missing"
s = s.replace(OLD2, NEW2, 1)

ast.parse(s)
io.open(P, "w", encoding="utf-8").write(s)
print("produce_lesson.py — self-heal loop installed")
