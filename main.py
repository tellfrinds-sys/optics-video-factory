#!/usr/bin/env python3
"""مصنع فيديوهات منصة بوابة البصريات - نسخة خاصة أحادية المستخدم.

المسار المحكوم:
درس -> سكريبت -> SCRIPT_SCIENTIFIC -> مشاهد -> معاينة MP4 -> FINAL_VIDEO.
لا أفاتار متحرك، لا موسيقى، ولا نشر آلي.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


ROOT = Path(os.environ.get("OPTICSGATE_FACTORY_ROOT", Path(__file__).resolve().parent)).resolve()
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
LESSONS_DIR = DATA_DIR / "lessons"
DEMO_DIR = DATA_DIR / "demo_payloads"
OUTPUTS_DIR = ROOT / "outputs"
ASSETS_DIR = ROOT / "assets"
BRAND_DIR = ASSETS_DIR / "brand"
DB_PATH = DATA_DIR / "factory.sqlite3"
INDEX_PATH = ROOT / "index.html"
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("MODEL_NAME", "qwen2.5:7b-instruct")
# كان محدودًا بـ512KB بلا توضيح؛ هذا هو سبب رسائل 413 السابقة. رُفع الحد الآن
# لأن السيناريوهات التشريحية لم تعد تُرسل صورًا مضمّنة (تُرسم على السيرفر)، وما تبقى صغير.
MAX_BODY = 2 * 1024 * 1024


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def ensure_dirs() -> None:
    for path in (CONFIG_DIR, DATA_DIR, LESSONS_DIR, DEMO_DIR, OUTPUTS_DIR, ASSETS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def config() -> dict[str, Any]:
    return {
        "factory": load_json(CONFIG_DIR / "factory.json"),
        "content": load_json(CONFIG_DIR / "content_rules.json"),
        "visual": load_json(CONFIG_DIR / "visual_identity.json"),
    }


class FactoryError(RuntimeError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class FactoryDB:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def _init(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS lessons (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    audience TEXT NOT NULL,
                    target_duration_minutes INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    lesson_id TEXT NOT NULL REFERENCES lessons(id),
                    status TEXT NOT NULL,
                    model TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    script_json TEXT,
                    scene_plan_json TEXT,
                    preview_path TEXT,
                    publication_blocked INTEGER NOT NULL DEFAULT 1,
                    auto_publish INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL REFERENCES jobs(id),
                    gate TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    decision TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(job_id, gate, version)
                );
                CREATE TABLE IF NOT EXISTS revisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL REFERENCES jobs(id),
                    kind TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT,
                    event TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        for key in ("payload", "script_json", "scene_plan_json"):
            if key in item and item[key]:
                item[key] = json.loads(item[key])
        for key in ("publication_blocked", "auto_publish"):
            if key in item:
                item[key] = bool(item[key])
        return item

    def audit(self, event: str, job_id: str | None = None, payload: Any = None) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO audit_events(job_id,event,payload,created_at) VALUES(?,?,?,?)",
                (job_id, event, dump_json(payload or {}), now()),
            )

    def import_lesson(self, payload: dict[str, Any]) -> dict[str, Any]:
        required = ("id", "title", "audience", "target_duration_minutes", "topic_1", "topic_2", "topic_3")
        missing = [key for key in required if payload.get(key) in (None, "")]
        if missing:
            raise FactoryError(f"حقول الدرس الناقصة: {', '.join(missing)}")
        stamp = now()
        with self.connect() as db:
            db.execute(
                """INSERT INTO lessons(id,title,audience,target_duration_minutes,payload,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET title=excluded.title,audience=excluded.audience,
                   target_duration_minutes=excluded.target_duration_minutes,payload=excluded.payload,updated_at=excluded.updated_at""",
                (payload["id"], payload["title"], payload["audience"], int(payload["target_duration_minutes"]), dump_json(payload), stamp, stamp),
            )
        self.audit("LESSON_IMPORTED", payload={"lesson_id": payload["id"]})
        return self.get_lesson(payload["id"])

    def import_bundled_lessons(self) -> int:
        count = 0
        for path in sorted(LESSONS_DIR.glob("*.json")):
            self.import_lesson(load_json(path))
            count += 1
        return count

    def list_lessons(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM lessons ORDER BY id").fetchall()
        return [self._decode(row) for row in rows]

    def get_lesson(self, lesson_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM lessons WHERE id=?", (lesson_id,)).fetchone()
        item = self._decode(row)
        if not item:
            raise FactoryError("الدرس غير موجود", 404)
        return item

    def create_job(self, lesson_id: str, model: str = DEFAULT_MODEL) -> dict[str, Any]:
        self.get_lesson(lesson_id)
        job_id = f"JOB-{lesson_id}-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:5]}"
        stamp = now()
        with self.connect() as db:
            db.execute(
                "INSERT INTO jobs(id,lesson_id,status,model,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (job_id, lesson_id, "DRAFT", model, stamp, stamp),
            )
        self.audit("JOB_CREATED", job_id, {"lesson_id": lesson_id, "model": model})
        return self.get_job(job_id)

    def list_jobs(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT jobs.*,lessons.title lesson_title,lessons.audience audience
                   FROM jobs JOIN lessons ON lessons.id=jobs.lesson_id ORDER BY jobs.created_at DESC"""
            ).fetchall()
        return [self._decode(row) for row in rows]

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute(
                """SELECT jobs.*,lessons.title lesson_title,lessons.audience audience
                   FROM jobs JOIN lessons ON lessons.id=jobs.lesson_id WHERE jobs.id=?""",
                (job_id,),
            ).fetchone()
            approvals = db.execute(
                "SELECT gate,version,decision,notes,created_at FROM approvals WHERE job_id=? ORDER BY id", (job_id,)
            ).fetchall()
        item = self._decode(row)
        if not item:
            raise FactoryError("مهمة الفيديو غير موجودة", 404)
        item["approvals"] = [dict(row) for row in approvals]
        return item

    def _update_job(self, job_id: str, **fields: Any) -> dict[str, Any]:
        if not fields:
            return self.get_job(job_id)
        fields["updated_at"] = now()
        values = [dump_json(value) if key in {"script_json", "scene_plan_json"} and value is not None else value for key, value in fields.items()]
        sql = ",".join(f"{key}=?" for key in fields)
        with self.connect() as db:
            cursor = db.execute(f"UPDATE jobs SET {sql} WHERE id=?", (*values, job_id))
        if cursor.rowcount != 1:
            raise FactoryError("مهمة الفيديو غير موجودة", 404)
        return self.get_job(job_id)

    def _revision(self, job_id: str, kind: str, version: int, payload: Any) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO revisions(job_id,kind,version,payload,created_at) VALUES(?,?,?,?,?)",
                (job_id, kind, version, dump_json(payload), now()),
            )

    def set_script(self, job_id: str, script: dict[str, Any], replace: bool = False) -> dict[str, Any]:
        job = self.get_job(job_id)
        if job["status"] == "FINAL_APPROVED":
            raise FactoryError("النسخة النهائية غير قابلة للكتابة فوقها", 409)
        version = job["version"]
        if job.get("script_json"):
            if not replace or job["status"] not in {"CHANGES_REQUESTED", "DRAFT"}:
                raise FactoryError("السكريبت موجود؛ أنشئ مراجعة جديدة بدل الكتابة فوقه", 409)
            version += 1
        self._revision(job_id, "SCRIPT", version, script)
        self.audit("SCRIPT_GENERATED", job_id, {"version": version})
        return self._update_job(
            job_id, version=version, script_json=script, scene_plan_json=None, preview_path=None,
            status="AWAITING_SCRIPT_SCIENTIFIC", publication_blocked=1,
        )

    def approve(self, job_id: str, gate: str, decision: str = "APPROVED", notes: str = "") -> dict[str, Any]:
        if gate not in {"SCRIPT_SCIENTIFIC", "FINAL_VIDEO"}:
            raise FactoryError("بوابة اعتماد غير صحيحة")
        if decision not in {"APPROVED", "CHANGES_REQUESTED"}:
            raise FactoryError("قرار الاعتماد غير صحيح")
        job = self.get_job(job_id)
        expected = "AWAITING_SCRIPT_SCIENTIFIC" if gate == "SCRIPT_SCIENTIFIC" else "AWAITING_FINAL_VIDEO"
        if job["status"] != expected:
            raise FactoryError(f"لا يمكن اعتماد {gate} عندما تكون الحالة {job['status']}", 409)
        with self.connect() as db:
            try:
                db.execute(
                    "INSERT INTO approvals(job_id,gate,version,decision,notes,created_at) VALUES(?,?,?,?,?,?)",
                    (job_id, gate, job["version"], decision, notes, now()),
                )
            except sqlite3.IntegrityError as exc:
                raise FactoryError("قرار هذه النسخة محفوظ بالفعل ولا يمكن تغييره", 409) from exc
        if decision == "CHANGES_REQUESTED":
            status, blocked = "CHANGES_REQUESTED", 1
        elif gate == "SCRIPT_SCIENTIFIC":
            status, blocked = "SCRIPT_APPROVED", 1
        else:
            status, blocked = "FINAL_APPROVED", 0
        self.audit("HUMAN_GATE_DECISION", job_id, {"gate": gate, "decision": decision, "version": job["version"]})
        return self._update_job(job_id, status=status, publication_blocked=blocked)

    def script_approved(self, job_id: str, version: int) -> bool:
        with self.connect() as db:
            row = db.execute(
                "SELECT 1 FROM approvals WHERE job_id=? AND gate='SCRIPT_SCIENTIFIC' AND version=? AND decision='APPROVED'",
                (job_id, version),
            ).fetchone()
        return bool(row)

    def set_scenes(self, job_id: str, scene_plan: dict[str, Any]) -> dict[str, Any]:
        job = self.get_job(job_id)
        if not self.script_approved(job_id, job["version"]):
            raise FactoryError("لا يمكن بناء المشاهد قبل اعتماد SCRIPT_SCIENTIFIC", 409)
        if job["status"] not in {"SCRIPT_APPROVED", "SCENES_READY"}:
            raise FactoryError(f"حالة المهمة لا تسمح ببناء المشاهد: {job['status']}", 409)
        validate_scene_plan(scene_plan)
        self._revision(job_id, "SCENE_PLAN", job["version"], scene_plan)
        self.audit("SCENE_PLAN_READY", job_id, {"version": job["version"], "scenes": len(scene_plan["scenes"])})
        return self._update_job(job_id, scene_plan_json=scene_plan, status="SCENES_READY", publication_blocked=1)

    def mark_preview(self, job_id: str, path: str) -> dict[str, Any]:
        job = self.get_job(job_id)
        if job["status"] not in {"SCENES_READY", "AWAITING_FINAL_VIDEO"}:
            raise FactoryError(f"لا يمكن إنشاء المعاينة في الحالة {job['status']}", 409)
        if any(a["gate"] == "FINAL_VIDEO" and a["version"] == job["version"] for a in job["approvals"]):
            raise FactoryError("قرار النسخة النهائية محفوظ؛ أنشئ مراجعة جديدة", 409)
        self.audit("PREVIEW_RENDERED", job_id, {"path": path, "version": job["version"]})
        return self._update_job(job_id, preview_path=path, status="AWAITING_FINAL_VIDEO", publication_blocked=1)

    def stats(self) -> dict[str, int]:
        with self.connect() as db:
            lessons = db.execute("SELECT COUNT(*) FROM lessons").fetchone()[0]
            jobs = db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            waiting = db.execute("SELECT COUNT(*) FROM jobs WHERE status LIKE 'AWAITING_%'").fetchone()[0]
            approved = db.execute("SELECT COUNT(*) FROM jobs WHERE status='FINAL_APPROVED'").fetchone()[0]
        return {"lessons_loaded": lessons, "jobs": jobs, "waiting_review": waiting, "final_approved": approved}


def http_json(url: str, payload: dict[str, Any] | None = None, timeout: float = 240) -> Any:
    data = None if payload is None else dump_json(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, method="GET" if payload is None else "POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise FactoryError(f"تعذر الوصول إلى Ollama على {OLLAMA_HOST}: {exc.reason}", 503) from exc


def ollama_status() -> dict[str, Any]:
    try:
        result = http_json(f"{OLLAMA_HOST}/api/tags", timeout=4)
        return {"reachable": True, "models": [x.get("name") or x.get("model") for x in result.get("models", [])]}
    except Exception as exc:
        return {"reachable": False, "models": [], "error": str(exc)}


def extract_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
        start = min(starts) if starts else -1
        end = max(text.rfind("}"), text.rfind("]"))
        if start < 0 or end <= start:
            raise FactoryError("لم يرجع النموذج JSON صالحًا", 502)
        return json.loads(text[start:end + 1])


def ollama_json(prompt: str, system: str, model: str) -> Any:
    result = http_json(
        f"{OLLAMA_HOST}/api/chat",
        {
            "model": model,
            "stream": False,
            "format": "json",
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "options": {"temperature": 0.2, "top_p": 0.9, "seed": 2026, "num_predict": 3000},
        },
    )
    return extract_json(result["message"]["content"])


def generate_script(db: FactoryDB, job_id: str) -> dict[str, Any]:
    job = db.get_job(job_id)
    lesson = db.get_lesson(job["lesson_id"])["payload"]
    rules = config()
    prompt = f"""حوّل الدرس التالي إلى بطاقة سكريبت كاملة لمنصة بوابة البصريات.
لا تضف معلومة علمية غير مرتبطة بالمصادر. اكتب JSON فقط بالحقول:
title, hook, learning_objectives, exclusions, opening, sections[], common_mistakes,
practical_summary, source_notice, closing_question, interactive_quiz, call_to_action,
signature, closing, scientific_review_flags.
كل section يحتوي heading,narration,on_screen,source_ids.

الدرس:
{json.dumps(lesson, ensure_ascii=False, indent=2)}

قواعد المحتوى:
{json.dumps(rules['content'], ensure_ascii=False, indent=2)}
"""
    script = ollama_json(prompt, "أنت محرر علمي مصري هادئ. الناتج مسودة تحتاج اعتمادًا بشريًا ولا يُنشر آليًا.", job["model"])
    if not isinstance(script, dict) or not script.get("sections"):
        raise FactoryError("بنية السكريبت الناتج غير صالحة", 502)
    return db.set_script(job_id, script)


def generate_scenes(db: FactoryDB, job_id: str, curated_demo: bool = False) -> dict[str, Any]:
    job = db.get_job(job_id)
    if curated_demo and job["lesson_id"] == "OG-PRACT-CL-001":
        plan = load_json(DEMO_DIR / "scene_plan.json")
    else:
        prompt = f"""حوّل السكريبت التالي إلى خطة مشاهد JSON لفيديو 1920x1080 بلا أفاتار وبلا موسيقى.
استخدم الهوية البصرية المرفقة نصيًا. الناتج: video_id,resolution,music,scenes[].
كل مشهد: id,type,title,narration,on_screen,visual_brief,duration_seconds,source_ids,medical_warning,sfx.
إجمالي النسخة النهائية 8-10 دقائق، والنص الظاهر قصير ومقروء.

السكريبت:
{json.dumps(job['script_json'], ensure_ascii=False, indent=2)}

الهوية:
{json.dumps(config()['visual'], ensure_ascii=False, indent=2)}
"""
        plan = ollama_json(prompt, "أنت مخرج فيديو تعليمي طبي دقيق. لا تحرك وجه المقدم ولا تستخدم موسيقى.", job["model"])
    return db.set_scenes(job_id, plan)


def validate_scene_plan(plan: dict[str, Any]) -> None:
    if not isinstance(plan, dict) or not isinstance(plan.get("scenes"), list) or not plan["scenes"]:
        raise FactoryError("خطة المشاهد فارغة أو غير صالحة")
    required = {"id", "type", "title", "narration", "on_screen", "visual_brief", "duration_seconds", "source_ids", "medical_warning", "sfx"}
    ids = set()
    for scene in plan["scenes"]:
        missing = required - set(scene)
        if missing:
            raise FactoryError(f"المشهد ينقصه: {', '.join(sorted(missing))}")
        if scene["id"] in ids:
            raise FactoryError(f"معرف مشهد مكرر: {scene['id']}")
        ids.add(scene["id"])
        if float(scene["duration_seconds"]) <= 0:
            raise FactoryError("مدة المشهد يجب أن تكون موجبة")
    if plan.get("music") not in (False, None):
        raise FactoryError("الموسيقى ممنوعة في هذا المصنع")


def _font(size: int, bold: bool = False):
    try:
        from PIL import ImageFont
    except ImportError as exc:
        raise FactoryError("Pillow غير مثبت؛ شغّل: pip install Pillow", 501) from exc
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    paths = [Path("/usr/share/fonts/truetype/dejavu") / name, Path("/usr/share/fonts/dejavu") / name]
    for path in paths:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.truetype(name, size)


def _wrap(draw, text: str, font, max_width: int) -> list[str]:
    words = str(text).split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        width = draw.textbbox((0, 0), candidate, font=font, direction="rtl")[2]
        if current and width > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _draw_rtl(draw, x: int, y: int, text: str, font, fill: str, max_width: int, spacing: int = 16) -> int:
    for line in _wrap(draw, text, font, max_width):
        draw.text((x, y), line, font=font, fill=fill, anchor="ra", direction="rtl", language="ar")
        y += font.size + spacing
    return y


def render_frame(scene: dict[str, Any], path: Path, index: int, total: int) -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise FactoryError("Pillow غير مثبت؛ شغّل: pip install Pillow", 501) from exc
    cfg = config()
    palette = cfg["visual"]["palette"]
    width, height = cfg["factory"]["render"]["width"], cfg["factory"]["render"]["height"]
    backgrounds = {
        "intro": palette["deep_navy"], "outro": palette["deep_navy"],
        "warning": palette["warning"], "scope": palette["charcoal"],
        "summary": palette["ivory"], "comparison": palette["navy"],
    }
    bg = backgrounds.get(scene["type"], palette["glass_teal"])
    light = scene["type"] == "summary"
    muted = palette["warm_taupe"] if light else palette["soft_sky"]
    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)
    logo_path = ROOT / cfg["visual"]["brand_logo"]["primary_static"]
    if not logo_path.is_file():
        raise FactoryError("ملف شعار بوابة البصريات المعتمد غير موجود", 500)
    draw.rounded_rectangle((95, 120, 425, 450), radius=46, fill=palette["white"])
    logo = Image.open(logo_path).convert("RGBA")
    logo.thumbnail((300, 300), Image.Resampling.LANCZOS)
    image.paste(logo, (110 + (300 - logo.width) // 2, 135 + (300 - logo.height) // 2), logo)
    draw.rounded_rectangle((910, 110, 1810, 970), radius=46, fill=palette["ivory"] if not light else palette["white"])
    draw.text((1810, 66), "منصة بوابة البصريات | OpticsGate", font=_font(34, True), fill=muted, anchor="ra", direction="rtl")
    draw.text((140, 110), f"{index:02d}/{total:02d}", font=_font(32, True), fill=muted)
    _draw_rtl(draw, 1740, 190, scene["title"], _font(64, True), palette["deep_navy"], 760, 20)
    _draw_rtl(draw, 1740, 390, scene["on_screen"], _font(46, True), palette["glass_teal"], 760, 18)
    _draw_rtl(draw, 1740, 650, scene["visual_brief"], _font(30), palette["charcoal"], 760, 12)
    warning = scene.get("medical_warning") or ""
    if warning:
        draw.rounded_rectangle((940, 820, 1760, 910), radius=18, fill="#F3E4E1")
        _draw_rtl(draw, 1720, 842, warning, _font(25, True), palette["warning"], 720, 8)
    sources = " · ".join(scene.get("source_ids") or []) or "المصادر العلمية أسفل الفيديو"
    draw.text((1810, 1010), sources, font=_font(24), fill=muted, anchor="ra", direction="rtl")
    image.save(path, "PNG", optimize=True)


def render_preview(db: FactoryDB, job_id: str, scene_ids: list[str] | None = None) -> dict[str, Any]:
    job = db.get_job(job_id)
    if job["status"] not in {"SCENES_READY", "AWAITING_FINAL_VIDEO"}:
        raise FactoryError(f"لا يمكن الرندر في الحالة {job['status']}", 409)
    if not shutil.which("ffmpeg"):
        raise FactoryError("FFmpeg غير مثبت", 501)
    plan = job["scene_plan_json"]
    validate_scene_plan(plan)
    render_cfg = config()["factory"]["render"]
    out_dir = OUTPUTS_DIR / job_id / f"v{job['version']}"
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    selected = set(scene_ids or [])
    for index, scene in enumerate(plan["scenes"], 1):
        frame = frames_dir / f"{scene['id']}.png"
        if not selected or scene["id"] in selected or not frame.exists():
            render_frame(scene, frame, index, len(plan["scenes"]))
    concat_path = out_dir / "frames.txt"
    lines = []
    for scene in plan["scenes"]:
        frame = frames_dir / f"{scene['id']}.png"
        duration = min(float(scene["duration_seconds"]), float(render_cfg["preview_max_seconds_per_scene"]))
        escaped = str(frame.resolve()).replace("'", "'\\''")
        lines.extend([f"file '{escaped}'", f"duration {duration:.3f}"])
    last = str((frames_dir / f"{plan['scenes'][-1]['id']}.png").resolve()).replace("'", "'\\''")
    lines.append(f"file '{last}'")
    concat_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {
        "job_id": job_id, "version": job["version"], "preview_only": True,
        "animated_avatar": False, "music": False, "resolution": "1920x1080",
        "scenes": plan["scenes"], "rendered_at": now(),
    }
    (out_dir / "render_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    video_path = out_dir / "storyboard_preview.mp4"
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_path), "-vf", f"fps={render_cfg['fps']},format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-movflags", "+faststart", str(video_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    if result.returncode != 0 or not video_path.exists():
        raise FactoryError(f"فشل FFmpeg: {result.stderr[-800:]}", 500)
    relative = "/" + video_path.relative_to(ROOT).as_posix()
    return db.mark_preview(job_id, relative)


def create_demo(db: FactoryDB) -> dict[str, Any]:
    lesson = db.import_lesson(load_json(LESSONS_DIR / "demo_soft_contact_lens.json"))
    job = db.create_job(lesson["id"], "curated-demo-no-ollama")
    return db.set_script(job["id"], load_json(DEMO_DIR / "script.json"))


def _pillow_available() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


def doctor(db: FactoryDB | None = None) -> dict[str, Any]:
    db = db or FactoryDB()
    db.import_bundled_lessons()
    cfg = config()
    refs = ASSETS_DIR / "visual_references"
    return {
        "factory": cfg["factory"]["factory_name"],
        "private_single_user": cfg["factory"]["private_single_user"],
        "animated_avatar": cfg["visual"]["avatar_policy"]["animated_avatar"],
        "music": cfg["content"]["music"],
        "auto_publish": cfg["content"]["auto_publish"],
        "resolution": cfg["visual"]["composition"]["resolution"],
        "reference_images": len(list(refs.glob("*.png"))),
        "approved_brand_logo": cfg["visual"]["brand_logo"]["primary_static"],
        "ffmpeg": shutil.which("ffmpeg"),
        "pillow": _pillow_available(),
        "ollama": ollama_status(),
        "database": db.stats(),
        "curriculum_baseline": cfg["factory"]["curriculum_baseline"],
    }


def _safe_path(base: Path, relative: str) -> Path | None:
    target = (base / unquote(relative).lstrip("/")).resolve()
    try:
        target.relative_to(base.resolve())
    except ValueError:
        return None
    return target if target.is_file() else None


HEYGEN_API_KEY = os.environ.get("HEYGEN_API_KEY", "")
HEYGEN_VOICE_ID = os.environ.get("HEYGEN_VOICE_ID", "b36a99c25d2f4a45a92ccc7f158ff7ae")
STABILITY_API_KEY = os.environ.get("STABILITY_API_KEY", "")


def stability_generate_image(prompt: str) -> bytes:
    if not STABILITY_API_KEY:
        raise FactoryError("STABILITY_API_KEY غير مضبوط في متغيرات البيئة", 500)
    boundary = uuid.uuid4().hex
    full_prompt = (
        "professional medical scientific illustration, " + prompt +
        ", clean flat vector art style, simple bold shapes, soft teal and navy blue color palette, "
        "minimalist, high quality medical textbook illustration"
    )
    negative_prompt = (
        "text, letters, numbers, words, writing, typography, labels, captions, watermark, logo, "
        "signature, blurry, distorted, photorealistic face, low quality, ugly, gibberish"
    )
    fields = {
        "prompt": full_prompt,
        "negative_prompt": negative_prompt,
        "output_format": "png",
        "aspect_ratio": "16:9",
    }
    parts = []
    for key, value in fields.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode("utf-8")
        )
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)
    req = urllib.request.Request(
        "https://api.stability.ai/v2beta/stable-image/generate/core",
        data=body,
        headers={
            "Authorization": f"Bearer {STABILITY_API_KEY}",
            "Accept": "image/*",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "OpticsGateVideoFactory/1.0 (+https://opticsgate.example)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise FactoryError(f"فشل توليد الصورة ({exc.code}): {exc.read().decode('utf-8', 'ignore')[:300]}", 502) from exc


def render_frame_ai(scene: dict[str, Any], path: Path, index: int, total: int) -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise FactoryError("Pillow غير مثبت", 501) from exc
    cfg = config()
    palette = cfg["visual"]["palette"]
    width, height = cfg["factory"]["render"]["width"], cfg["factory"]["render"]["height"]
    import io
    image_bytes = stability_generate_image(scene.get("visual_brief") or scene.get("title") or "")
    bg_image = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((width, height))
    image = bg_image
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rectangle((0, height - 320, width, height), fill=(*_hex_to_rgb(palette["deep_navy"]), 210))
    draw.text((width - 70, 40), "منصة بوابة البصريات | OpticsGate", font=_font(30, True), fill=palette["white"], anchor="ra", direction="rtl")
    draw.text((70, 40), f"{index:02d}/{total:02d}", font=_font(28, True), fill=palette["white"])
    _draw_rtl(draw, width - 70, height - 290, scene["title"], _font(48, True), palette["white"], width - 140, 14)
    _draw_rtl(draw, width - 70, height - 170, scene["on_screen"], _font(32, True), palette["soft_sky"], width - 140, 10)
    sources = " · ".join(scene.get("source_ids") or []) or "المصادر العلمية أسفل الفيديو"
    draw.text((width - 70, height - 40), sources, font=_font(20), fill=palette["soft_sky"], anchor="ra", direction="rtl")
    image.save(path, "PNG", optimize=True)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


# =============================================================================
# مخطط تشريح العين ثنائي اللغة مع إبراز متزامن مع الكلام (يعتمد على word_timestamps
# التي يرجعها HeyGen). أُضيف هذا القسم لحل ثلاث مشاكل أبلغ عنها المستخدم:
#   1) التسميات كانت إنجليزية فقط على صورة خارجية (Wikimedia) -> الآن نرسم
#      المخطط بأنفسنا بتسميات عربي+إنجليزي.
#   2) لا يوجد أي إبراز بصري متزامن مع الجزء المذكور -> الآن نبني "تايم لاين"
#      لكل مشهد ونبدّل بين نسخ مختلفة من نفس المخطط (كل نسخة تُبرز جزءًا مختلفًا).
#   3) صورة Wikimedia كانت تحتاج تنزيلًا خارجيًا هشًا (403) وتُثقل حجم الطلب ->
#      الآن نرسمها محليًا فلا حاجة لأي صورة خارجية للمشاهد التشريحية إطلاقًا.
# =============================================================================

AMIRI_BOLD_PATH = "/usr/share/fonts/opentype/fonts-hosny-amiri/Amiri-Bold.ttf"
AMIRI_REGULAR_PATH = "/usr/share/fonts/opentype/fonts-hosny-amiri/Amiri-Regular.ttf"

EYE_DIAGRAM_BG = "#EAF6F6"
EYE_DIAGRAM_CARD = "#FFFFFF"
EYE_DIAGRAM_NAVY = "#123B5E"
EYE_DIAGRAM_CHARCOAL = "#33414D"
EYE_DIAGRAM_HIGHLIGHT = "#FF7A45"

EYE_PARTS = {
    "sclera": {"ar": "الصلبة", "en": "Sclera"},
    "choroid": {"ar": "المشيمية", "en": "Choroid"},
    "retina": {"ar": "الشبكية", "en": "Retina"},
    "cornea": {"ar": "القرنية", "en": "Cornea"},
    "lens": {"ar": "العدسة", "en": "Lens"},
    "iris": {"ar": "القزحية", "en": "Iris"},
    "pupil": {"ar": "الحدقة", "en": "Pupil"},
    "optic_nerve": {"ar": "العصب البصري", "en": "Optic Nerve"},
}

# كل مصطلح وصيغه العربية المحتملة (بلا "ال" وبدونها) للمطابقة مع كلمات word_timestamps.
ANATOMY_TERMS = [
    {"key": "sclera", "variants": [["الصلبة"], ["صلبة"]]},
    {"key": "cornea", "variants": [["القرنية"], ["قرنية"]]},
    {"key": "choroid", "variants": [["المشيمية"], ["مشيمية"]]},
    {"key": "retina", "variants": [["الشبكية"], ["شبكية"]]},
    {"key": "lens", "variants": [["العدسة"], ["عدسة"]]},
    {"key": "iris", "variants": [["القزحية"], ["قزحية"]]},
    {"key": "pupil", "variants": [["الحدقة"], ["حدقة"], ["البؤبؤ"], ["بؤبؤ"]]},
    {"key": "optic_nerve", "variants": [["العصب", "البصري"], ["عصب", "بصري"]]},
]

_ARABIC_DIACRITICS_RE = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۨ-ۭـ]")


def _normalize_ar(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = _ARABIC_DIACRITICS_RE.sub("", text)
    for alef in "أإآٱ":
        text = text.replace(alef, "ا")
    text = text.replace("ى", "ي")
    text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
    return text.strip()


def _arabic_font(size: int, bold: bool = False):
    try:
        from PIL import ImageFont
    except ImportError as exc:
        raise FactoryError("Pillow غير مثبت؛ شغّل: pip install Pillow", 501) from exc
    path = AMIRI_BOLD_PATH if bold else AMIRI_REGULAR_PATH
    if not Path(path).is_file():
        raise FactoryError(
            "خط Amiri العربي غير مثبت على السيرفر. شغّل: apt-get install -y fonts-hosny-amiri "
            "(بدونه ستظهر التسميات العربية على المخطط كمربعات فارغة)",
            501,
        )
    return ImageFont.truetype(path, size)


def _draw_rtl_simple(draw, x: int, y: int, text: str, font, fill, anchor: str = "ra") -> None:
    draw.text((x, y), text, font=font, fill=fill, anchor=anchor, direction="rtl", language="ar")


def _wrap_rtl(draw, text: str, font, max_width: int) -> list[str]:
    words = str(text).split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        width = draw.textbbox((0, 0), candidate, font=font, direction="rtl")[2]
        if current and width > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def compute_highlight_timeline(
    word_timestamps: list[dict[str, Any]] | None,
    scene_duration: float,
    min_hold: float = 1.4,
) -> list[dict[str, Any]]:
    """يبني قائمة مقاطع {term, start, end} لمشهد واحد: أي جزء تشريحي يُبرز ومتى،
    بمطابقة كلمات النص التشريحي المعروفة مع توقيتات HeyGen الفعلية.
    عند غياب التوقيتات (أو عدم العثور على أي مصطلح معروف) تُرجع مقطعًا واحدًا
    بلا إبراز (term=None) يغطي كامل مدة المشهد -> سلوك آمن يرجع للصورة الأساسية.
    """
    if not word_timestamps:
        return [{"term": None, "start": 0.0, "end": scene_duration}]
    tokens = []
    for w in word_timestamps:
        word = w.get("word") or w.get("text") or ""
        start = float(w.get("start", 0.0))
        end = float(w.get("end", start))
        tokens.append({"norm": _normalize_ar(word), "start": start, "end": end})
    hits = []
    n = len(tokens)
    for term in ANATOMY_TERMS:
        for variant in term["variants"]:
            span = len(variant)
            i = 0
            while i <= n - span:
                if all(part in tokens[i + j]["norm"] for j, part in enumerate(variant)):
                    hits.append({"term": term["key"], "start": tokens[i]["start"], "end": tokens[i + span - 1]["end"]})
                    i += span
                else:
                    i += 1
    if not hits:
        return [{"term": None, "start": 0.0, "end": scene_duration}]
    # إزالة التكرار: صيغ المصطلح الواحد قد تتطابق كلها مع نفس الكلمة (مثال:
    # "صلبة" جزء من "الصلبة")، فينتج أكثر من hit لنفس الموضع.
    hits = list({(h["term"], h["start"], h["end"]): h for h in hits}.values())
    hits.sort(key=lambda h: h["start"])
    timeline: list[dict[str, Any]] = []
    cursor = 0.0
    for hit in hits:
        start = max(hit["start"], cursor)
        if start >= scene_duration:
            continue
        end = min(max(hit["end"], start + min_hold), scene_duration)
        if start > cursor:
            timeline.append({"term": None, "start": cursor, "end": start})
        timeline.append({"term": hit["term"], "start": start, "end": end})
        cursor = end
    if cursor < scene_duration:
        timeline.append({"term": None, "start": cursor, "end": scene_duration})
    return [seg for seg in timeline if seg["end"] > seg["start"]]


def draw_eye_diagram(highlight_key: str | None, on_screen_text: str = "", scene_label: str = "") -> "Any":
    """يرسم مخططًا تشريحيًا مبسّطًا للعين بتسميات عربي+إنجليزي، مع إبراز جزء واحد
    اختياريًا (لون مختلف + إطار حول تسميته + تعتيم بقية الأجزاء) لمزامنته مع الصوت.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise FactoryError("Pillow غير مثبت؛ شغّل: pip install Pillow", 501) from exc

    width, height = 1920, 1080
    img = Image.new("RGB", (width, height), EYE_DIAGRAM_BG)
    draw = ImageDraw.Draw(img, "RGBA")
    draw.rounded_rectangle((1180, 90, 1850, 990), radius=40, fill=EYE_DIAGRAM_CARD)
    draw.rounded_rectangle((70, 90, 1110, 990), radius=40, fill=EYE_DIAGRAM_CARD)

    cx, cy = 540, 520
    r0, r1, r2, r3 = 300, 274, 252, 230

    def alpha_of(key: str | None) -> int:
        if not highlight_key:
            return 255
        return 255 if key == highlight_key else 85

    for key, radius, rgb in [
        ("sclera", r0, (255, 255, 255)),
        ("choroid", r1, (123, 58, 63)),
        ("retina", r2, (200, 90, 90)),
        (None, r3, (214, 236, 236)),
    ]:
        a = alpha_of(key) if key else 255
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(*rgb, a))

    a = alpha_of("optic_nerve")
    draw.polygon(
        [(cx - r0 - 10, cy - 50), (cx - r0 - 120, cy - 36), (cx - r0 - 120, cy + 36), (cx - r0 - 10, cy + 50)],
        fill=(150, 150, 160, a),
    )

    a = alpha_of("lens")
    lens_cx = cx + r2 - 35
    draw.ellipse((lens_cx - 50, cy - 85, lens_cx + 50, cy + 85), fill=(255, 244, 200, a), outline=(200, 170, 90, 255), width=4)

    a = alpha_of("iris")
    ix0, ix1 = cx + r2 + 5, cx + r2 + 50
    draw.rectangle((ix0, cy - 120, ix1, cy - 20), fill=(90, 60, 40, a))
    draw.rectangle((ix0, cy + 20, ix1, cy + 120), fill=(90, 60, 40, a))

    a = alpha_of("pupil")
    draw.rectangle((ix0, cy - 20, ix1, cy + 20), fill=(15, 15, 20, a))

    a = alpha_of("cornea")
    bbox = (cx + r2 - 20, cy - 175, cx + r2 + 210, cy + 175)
    draw.arc(bbox, start=-55, end=55, fill=(30, 138, 138, a), width=10)

    f_ar_active = _arabic_font(28, bold=True)
    f_ar = _arabic_font(24)
    f_en = _font(18, bold=True)

    def label(key: str, lx: int, ly: int, leader_from: tuple[int, int] | None = None) -> None:
        active = key == highlight_key
        fill_ar = EYE_DIAGRAM_HIGHLIGHT if active else EYE_DIAGRAM_NAVY
        fill_en = EYE_DIAGRAM_HIGHLIGHT if active else EYE_DIAGRAM_CHARCOAL
        f1 = f_ar_active if active else f_ar
        _draw_rtl_simple(draw, lx, ly, EYE_PARTS[key]["ar"], f1, fill_ar, anchor="ma")
        draw.text((lx, ly + 32), EYE_PARTS[key]["en"], font=f_en, fill=fill_en, anchor="ma")
        if leader_from:
            draw.line([leader_from, (lx, ly + 15)], fill=(EYE_DIAGRAM_HIGHLIGHT if active else (150, 150, 150)), width=2)
        if active:
            box = draw.textbbox((lx, ly), EYE_PARTS[key]["ar"], font=f1, anchor="ma", direction="rtl", language="ar")
            pad = 10
            draw.rounded_rectangle((box[0] - pad, box[1] - pad, box[2] + pad, ly + 32 + 22), radius=10, outline=EYE_DIAGRAM_HIGHLIGHT, width=3)

    label("sclera", cx, cy - r0 - 20)
    label("choroid", cx - 130, cy - r1 - 25, leader_from=(cx - 90, cy - r1 + 10))
    label("retina", cx - 220, cy - r2 + 20, leader_from=(cx - 170, cy - r2 + 55))
    label("optic_nerve", cx - r0 - 75, cy - 100)
    label("lens", lens_cx, cy + 145)
    label("iris", cx + r2 + 175, cy - 90, leader_from=(ix1, cy - 70))
    label("pupil", cx + r2 + 175, cy + 10, leader_from=(ix1, cy))
    label("cornea", cx + r2 + 235, cy - 220, leader_from=(cx + r2 + 150, cy - 165))

    _draw_rtl_simple(draw, 1815, 50, "منصة بوابة البصريات | OpticsGate", _arabic_font(28, bold=True), EYE_DIAGRAM_NAVY)

    if highlight_key:
        _draw_rtl_simple(draw, 1810, 150, "الجزء الظاهر الآن:", _arabic_font(28), EYE_DIAGRAM_CHARCOAL)
        _draw_rtl_simple(draw, 1810, 200, EYE_PARTS[highlight_key]["ar"], _arabic_font(58, bold=True), EYE_DIAGRAM_HIGHLIGHT)
        draw.text((1810, 275), EYE_PARTS[highlight_key]["en"], font=_font(32, bold=True), fill=EYE_DIAGRAM_NAVY, anchor="ra")
    else:
        _draw_rtl_simple(draw, 1810, 190, scene_label or "تشريح العين البشرية", _arabic_font(46, bold=True), EYE_DIAGRAM_NAVY)

    if on_screen_text:
        draw.line([(1810, 360), (1215, 360)], fill=(220, 220, 220), width=2)
        f_caption = _arabic_font(30)
        y = 400
        for line in _wrap_rtl(draw, on_screen_text, f_caption, 600):
            draw.text((1810, y), line, font=f_caption, fill=EYE_DIAGRAM_CHARCOAL, anchor="ra", direction="rtl", language="ar")
            y += f_caption.size + 14

    return img


def render_highlighted_scene_clip(
    scene_no: int,
    narration: str,
    on_screen_text: str,
    word_timestamps: list[dict[str, Any]] | None,
    audio_path: Path,
    out_dir: Path,
    render_cfg: dict[str, Any],
) -> Path:
    """يبني كليب المشهد التشريحي الواحد: يرسم نسخ المخطط اللازمة فقط (مرة واحدة لكل
    جزء يظهر فعليًا)، يبني منها فيديو صامت بتوقيتات دقيقة عبر ffmpeg concat، ثم يدمج
    الصوت الأصلي للمشهد فوقه بدون إعادة ترميزه (copy) طالما الفيديو الصامت أطول أو
    يساوي الصوت (-shortest يقصّ الزائد فقط)."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(audio_path)],
        capture_output=True, text=True, timeout=20,
    )
    try:
        audio_duration = float(probe.stdout.strip())
    except (ValueError, AttributeError):
        audio_duration = 0.0
    scene_duration = max(audio_duration, 1.0)

    timeline = compute_highlight_timeline(word_timestamps, scene_duration)
    frame_cache: dict[str | None, Path] = {}
    concat_lines = []
    for seg in timeline:
        key = seg["term"]
        if key not in frame_cache:
            frame_path = out_dir / f"S{scene_no:02d}_{key or 'base'}.png"
            draw_eye_diagram(key, on_screen_text=on_screen_text if key is None else "", scene_label="").save(frame_path)
            frame_cache[key] = frame_path
        duration = seg["end"] - seg["start"]
        escaped = str(frame_cache[key].resolve()).replace("'", "'\\''")
        concat_lines.append(f"file '{escaped}'")
        concat_lines.append(f"duration {duration:.3f}")
    last_escaped = str(frame_cache[timeline[-1]["term"]].resolve()).replace("'", "'\\''")
    concat_lines.append(f"file '{last_escaped}'")
    concat_path = out_dir / f"S{scene_no:02d}_concat.txt"
    concat_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

    silent_path = out_dir / f"S{scene_no:02d}_silent.mp4"
    fps = render_cfg.get("fps", 30)
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
        "-i", str(concat_path), "-vf", f"fps={fps},format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", str(silent_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0 or not silent_path.exists():
        raise FactoryError(f"فشل بناء تايم لاين المشهد {scene_no}: {result.stderr[-500:]}", 500)

    clip_path = out_dir / f"S{scene_no:02d}.mp4"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(silent_path), "-i", str(audio_path),
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=7",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(clip_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0 or not clip_path.exists():
        raise FactoryError(f"فشل دمج صوت المشهد {scene_no}: {result.stderr[-500:]}", 500)
    return clip_path


def heygen_tts(text: str, voice_id: str | None = None) -> bytes:
    if not HEYGEN_API_KEY:
        raise FactoryError("HEYGEN_API_KEY غير مضبوط في متغيرات البيئة", 500)
    body = json.dumps({
        "text": text,
        "voice_id": voice_id or HEYGEN_VOICE_ID,
        "speed": 1.0,
        "language": "ar",
        "locale": "ar-EG",
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.heygen.com/v3/voices/speech",
        data=body,
        headers={"X-Api-Key": HEYGEN_API_KEY, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise FactoryError(f"فشل HeyGen TTS ({exc.code}): {exc.read().decode('utf-8', 'ignore')[:300]}", 502) from exc
    audio_url = (result.get("data") or {}).get("audio_url")
    if not audio_url:
        raise FactoryError(f"HeyGen لم يرجع رابط صوت: {json.dumps(result, ensure_ascii=False)[:300]}", 502)
    with urllib.request.urlopen(audio_url, timeout=60) as resp:
        return resp.read()


def render_narrated(payload: dict[str, Any]) -> dict[str, Any]:
    video_uid = payload.get("video_uid")
    scenes_in = payload.get("scenes") or []
    if not video_uid or not scenes_in:
        raise FactoryError("video_uid و scenes مطلوبين", 400)
    if not shutil.which("ffmpeg"):
        raise FactoryError("FFmpeg غير مثبت", 501)
    out_dir = OUTPUTS_DIR / f"narrated_{video_uid}"
    out_dir.mkdir(parents=True, exist_ok=True)
    clip_paths: list[Path] = []
    total = len(scenes_in)
    for i, raw in enumerate(scenes_in, 1):
        scene_no = raw.get("scene_no") or raw.get("scene no") or i
        narration = str(raw.get("narration", ""))
        on_screen = str(raw.get("on_screen_text") or raw.get("on screen text") or "")
        visual = str(raw.get("visual_direction") or raw.get("visual direction") or "")
        source_codes = raw.get("source_codes") or raw.get("source codes") or ""
        visual_en = raw.get("visual_prompt_en") or "human eye anatomy cross section diagram"
        scene = {
            "type": "content",
            "title": f"مشهد {scene_no}",
            "on_screen": on_screen,
            "visual_brief": visual_en,
            "source_ids": [source_codes] if source_codes else [],
        }
        audio_path = out_dir / f"S{int(scene_no):02d}.mp3"
        if raw.get("audio_url"):
            with urllib.request.urlopen(raw["audio_url"], timeout=60) as resp:
                audio_path.write_bytes(resp.read())
        elif raw.get("audio_base64"):
            import base64 as b64lib
            audio_path.write_bytes(b64lib.b64decode(raw["audio_base64"]))
        else:
            audio_path.write_bytes(heygen_tts(narration))

        if raw.get("use_custom_diagram"):
            # مشهد تشريحي: نرسم المخطط بأنفسنا ونبني تايم لاين إبراز متزامن مع
            # الكلام باستخدام word_timestamps بدلًا من صورة ثابتة واحدة.
            clip_path = render_highlighted_scene_clip(
                scene_no=int(scene_no),
                narration=narration,
                on_screen_text=on_screen,
                word_timestamps=raw.get("word_timestamps"),
                audio_path=audio_path,
                out_dir=out_dir,
                render_cfg=config()["factory"]["render"],
            )
            clip_paths.append(clip_path)
            continue

        frame_path = out_dir / f"S{int(scene_no):02d}.png"
        if raw.get("image_url"):
            with urllib.request.urlopen(raw["image_url"], timeout=60) as resp:
                frame_path.write_bytes(resp.read())
        elif raw.get("image_base64"):
            import base64 as b64lib
            frame_path.write_bytes(b64lib.b64decode(raw["image_base64"]))
        else:
            render_frame_ai(scene, frame_path, i, total)
        clip_path = out_dir / f"S{int(scene_no):02d}.mp4"
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-loop", "1", "-i", str(frame_path), "-i", str(audio_path),
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=7",
            "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p", "-shortest", str(clip_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0 or not clip_path.exists():
            raise FactoryError(f"فشل دمج المشهد {scene_no}: {result.stderr[-500:]}", 500)
        clip_paths.append(clip_path)
    concat_file = out_dir / "concat.txt"
    concat_file.write_text(
        "\n".join(f"file '{str(p.resolve()).replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'" for p in clip_paths),
        encoding="utf-8",
    )
    final_path = out_dir / "final_narrated.mp4"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c", "copy", str(final_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0 or not final_path.exists():
        raise FactoryError(f"فشل الدمج النهائي: {result.stderr[-500:]}", 500)
    relative = "/" + final_path.relative_to(ROOT).as_posix()
    return {"status": "ok", "video_path": relative, "scenes": total, "video_uid": video_uid}


class Handler(BaseHTTPRequestHandler):
    server_version = "OpticsGateVideoFactory/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        if os.environ.get("QUIET_HTTP") != "1":
            super().log_message(fmt, *args)

    def send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; media-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status: int, payload: Any) -> None:
        self.send_bytes(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > MAX_BODY:
            raise FactoryError("حجم الطلب غير صالح", 413)
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            db = FactoryDB()
            if path == "/":
                return self.send_bytes(200, INDEX_PATH.read_bytes(), "text/html; charset=utf-8")
            if path == "/health":
                return self.send_json(200, doctor(db))
            if path == "/api/config":
                return self.send_json(200, config())
            if path == "/api/lessons":
                return self.send_json(200, {"lessons": db.list_lessons()})
            if path == "/api/jobs":
                return self.send_json(200, {"jobs": db.list_jobs()})
            if path.startswith("/api/jobs/"):
                return self.send_json(200, db.get_job(path.split("/")[3]))
            if path.startswith("/assets/"):
                file = _safe_path(ASSETS_DIR, path[len("/assets/"):])
                if file:
                    return self.send_bytes(200, file.read_bytes(), "image/png")
            if path.startswith("/outputs/"):
                file = _safe_path(OUTPUTS_DIR, path[len("/outputs/"):])
                if file:
                    mime = "video/mp4" if file.suffix == ".mp4" else "application/json"
                    return self.send_bytes(200, file.read_bytes(), mime)
            return self.send_json(404, {"error": "المسار غير موجود"})
        except FactoryError as exc:
            return self.send_json(exc.status, {"error": str(exc)})
        except Exception as exc:
            return self.send_json(500, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            payload = self.body()
            db = FactoryDB()
            if path == "/api/lessons":
                result = db.import_lesson(payload)
            elif path == "/api/jobs":
                result = db.create_job(payload["lesson_id"], payload.get("model", DEFAULT_MODEL))
            elif path == "/api/demo":
                result = create_demo(db)
            elif path == "/api/render-narrated":
                result = render_narrated(payload)
            elif path.startswith("/api/jobs/"):
                parts = path.strip("/").split("/")
                if len(parts) != 4:
                    raise FactoryError("مسار المهمة غير صحيح", 404)
                job_id, action = parts[2], parts[3]
                if action == "generate-script":
                    result = generate_script(db, job_id)
                elif action == "approve-script":
                    result = db.approve(job_id, "SCRIPT_SCIENTIFIC", payload.get("decision", "APPROVED"), payload.get("notes", ""))
                elif action == "generate-scenes":
                    result = generate_scenes(db, job_id, bool(payload.get("curated_demo", False)))
                elif action == "render-preview":
                    result = render_preview(db, job_id, payload.get("scene_ids"))
                elif action == "approve-final":
                    result = db.approve(job_id, "FINAL_VIDEO", payload.get("decision", "APPROVED"), payload.get("notes", ""))
                else:
                    raise FactoryError("إجراء المهمة غير موجود", 404)
            else:
                raise FactoryError("المسار غير موجود", 404)
            return self.send_json(200, result)
        except FactoryError as exc:
            return self.send_json(exc.status, {"error": str(exc)})
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            return self.send_json(400, {"error": str(exc)})
        except Exception as exc:
            return self.send_json(500, {"error": str(exc)})


def serve(host: str, port: int) -> None:
    ensure_dirs()
    FactoryDB().import_bundled_lessons()
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"OpticsGate Video Factory: http://{host}:{port}")
    print("خاص بمستخدم واحد · لا أفاتار متحرك · لا موسيقى · لا نشر آلي")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    ensure_dirs()
    parser = argparse.ArgumentParser(description="مصنع فيديوهات منصة بوابة البصريات")
    sub = parser.add_subparsers(dest="command", required=True)
    p_serve = sub.add_parser("serve")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    sub.add_parser("doctor")
    p_demo = sub.add_parser("demo")
    p_demo.add_argument("--render", action="store_true")
    p_demo.add_argument("--approve-final", action="store_true")
    args = parser.parse_args(argv)
    db = FactoryDB()
    db.import_bundled_lessons()
    if args.command == "serve":
        serve(args.host, args.port)
    elif args.command == "doctor":
        print(json.dumps(doctor(db), ensure_ascii=False, indent=2))
    elif args.command == "demo":
        job = create_demo(db)
        job = db.approve(job["id"], "SCRIPT_SCIENTIFIC", notes="اعتماد اختباري صريح من CLI")
        job = generate_scenes(db, job["id"], curated_demo=True)
        if args.render:
            job = render_preview(db, job["id"])
        if args.approve_final:
            if not args.render:
                raise FactoryError("الاعتماد النهائي يتطلب --render")
            job = db.approve(job["id"], "FINAL_VIDEO", notes="اعتماد اختباري صريح من CLI")
        print(json.dumps(job, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
