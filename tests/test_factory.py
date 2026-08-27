import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("opticsgate_factory", PROJECT / "main.py")
app = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(app)


class FactoryPolicyTests(unittest.TestCase):
    def test_private_avatar_free_music_free_and_manual_publish(self):
        cfg = app.config()
        self.assertTrue(cfg["factory"]["private_single_user"])
        self.assertFalse(cfg["visual"]["avatar_policy"]["animated_avatar"])
        self.assertFalse(cfg["visual"]["avatar_policy"]["face_animation"])
        self.assertFalse(cfg["content"]["music"])
        self.assertFalse(cfg["content"]["auto_publish"])

    def test_official_hybrid_path_reuses_master_avatar_segments(self):
        factory = app.load_json(PROJECT / "config" / "factory.json")
        hybrid = factory["hybrid_video_path"]
        self.assertTrue(hybrid["officially_approved"])
        self.assertEqual(hybrid["avatar_provider"], "HeyGen Digital Twin")
        self.assertEqual(hybrid["avatar_total_max_seconds_per_video"], 30)
        self.assertTrue(hybrid["master_segments"]["render_once"])
        self.assertTrue(hybrid["master_segments"]["reuse_across_all_videos"])
        self.assertFalse(hybrid["master_segments"]["dynamic_avatar_per_lesson"])
        self.assertEqual(hybrid["heygen_creator_reference"]["master_intro_outro_credits_avatar_iv_v"], 10)
        self.assertEqual(hybrid["approved_voice"]["engine"], "Cartesia")
        self.assertEqual(hybrid["approved_voice"]["voice_match_status"], "APPROVED")
        self.assertEqual(hybrid["approved_voice"]["dialect_match_status"], "APPROVED")
        self.assertFalse(hybrid["approved_voice"]["automatic_fallback_allowed"])

    def test_heygen_master_packages_are_complete_and_under_30_seconds(self):
        root = PROJECT / "outputs" / "heygen_master_segments"
        targets = [
            (root / "OPTICSGATE_INTRO_MASTER_HEYGEN.zip", "OPTICSGATE-INTRO-MASTER-V2"),
            (root / "OPTICSGATE_OUTRO_MASTER_HEYGEN.zip", "OPTICSGATE-OUTRO-MASTER-V1"),
        ]
        total_target = 0.0
        required = {
            "SCRIPT_AR.txt", "CAPTIONS_AR.srt", "HEYGEN_SETTINGS.json",
            "UPLOAD_INSTRUCTIONS_AR.md", "PRESENTER_REFERENCE.png", "VOICE_REFERENCE.wav",
        }
        for package, asset_id in targets:
            self.assertTrue(package.is_file())
            with zipfile.ZipFile(package) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()), required)
                settings = json.loads(archive.read("HEYGEN_SETTINGS.json"))
                script = archive.read("SCRIPT_AR.txt").decode("utf-8")
                self.assertEqual(settings["asset_id"], asset_id)
                self.assertEqual(settings["status"], "READY_FOR_HEYGEN_NOT_FINAL_APPROVED")
                self.assertEqual(settings["video"]["hard_max_duration_seconds"], 15.0)
                self.assertFalse(settings["video"]["music"])
                self.assertFalse(settings["avatar"]["automatic_fallback_allowed"])
                self.assertFalse(settings["voice"]["automatic_public_voice_allowed"])
                self.assertEqual(settings["voice"]["engine"], "Cartesia")
                self.assertTrue(settings["voice"]["approved_by_user"])
                self.assertFalse(settings["voice"]["automatic_engine_fallback_allowed"])
                self.assertIn("بوابة البصريات", script)
                if asset_id == "OPTICSGATE-INTRO-MASTER-V2":
                    self.assertEqual(settings["script_version"], 2)
                    self.assertIn("موثوقة علميًا وببساطة", script)
                total_target += settings["video"]["target_duration_seconds"]
        self.assertLessEqual(total_target, 30.0)

    def test_five_visual_references_exist(self):
        refs = list((PROJECT / "assets" / "visual_references").glob("*.png"))
        self.assertEqual(len(refs), 5)
        for path in refs:
            self.assertGreater(path.stat().st_size, 10_000)

    def test_permanent_approved_brand_logo_files_are_present(self):
        from PIL import Image

        visual = app.load_json(PROJECT / "config" / "visual_identity.json")
        factory = app.load_json(PROJECT / "config" / "factory.json")
        policy = visual["brand_logo"]
        self.assertEqual(policy["status"], "APPROVED_PERMANENT")
        self.assertTrue(policy["always_use"])
        self.assertTrue(policy["source_files_preserved_without_modification"])
        self.assertEqual(factory["brand_identity"]["status"], "APPROVED_PERMANENT")
        self.assertTrue(factory["brand_identity"]["replacement_requires_explicit_human_approval"])
        static_logo = PROJECT / policy["primary_static"]
        gif_logo = PROJECT / policy["gif_variant"]
        self.assertTrue(static_logo.is_file())
        self.assertTrue(gif_logo.is_file())
        with Image.open(static_logo) as image:
            self.assertEqual(image.size, (1920, 1920))
            self.assertIn("A", image.getbands())
        with Image.open(gif_logo) as image:
            self.assertEqual(image.size, (720, 720))
            self.assertEqual(getattr(image, "n_frames", 1), policy["gif_frame_count"])

    def test_one_html_dashboard(self):
        html = (PROJECT / "index.html").read_text(encoding="utf-8")
        self.assertIn("مصنع فيديوهات", html)
        self.assertIn("SCRIPT_SCIENTIFIC", html)
        self.assertIn("FINAL_VIDEO", html)
        self.assertIn("<style>", html)
        self.assertIn("<script>", html)
        self.assertNotIn("POST /chat", html)

    def test_professional_preview_contract(self):
        payload = app.load_json(PROJECT / "data" / "demo_payloads" / "professional_preview_30s.json")
        self.assertEqual(payload["duration_seconds"], 30)
        self.assertEqual(len(payload["slides"]), 7)
        self.assertFalse(payload["music"])
        self.assertFalse(payload["animated_avatar"])
        self.assertEqual(payload["font_family"], "Noto Sans Arabic")
        for name in ("NotoSansArabic-Regular.ttf", "NotoSansArabic-Bold.ttf", "NotoSans-Regular.ttf", "NotoSans-Bold.ttf"):
            self.assertTrue((PROJECT / "assets" / "fonts" / name).is_file())

    @unittest.skipUnless(shutil.which("ffprobe"), "FFprobe required")
    def test_professional_visual_master_is_real_full_hd_30_seconds(self):
        video = PROJECT / "outputs" / "professional_preview_30s" / "visual_master_silent.mp4"
        self.assertTrue(video.is_file())
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", str(video)],
            check=True, capture_output=True, text=True,
        )
        data = json.loads(probe.stdout)
        self.assertAlmostEqual(float(data["format"]["duration"]), 30.0, places=2)
        videos = [s for s in data["streams"] if s["codec_type"] == "video"]
        audios = [s for s in data["streams"] if s["codec_type"] == "audio"]
        self.assertEqual((videos[0]["width"], videos[0]["height"]), (1920, 1080))
        self.assertEqual(audios, [])
        self.assertFalse((video.parent / "professional_preview_30s.mp4").exists())

    @unittest.skipUnless(shutil.which("ffprobe"), "FFprobe required")
    def test_avatar_style_sample_has_real_voice_and_disclosure(self):
        sample_dir = PROJECT / "outputs" / "avatar_style_sample"
        video = sample_dir / "factory_avatar_style_30s.mp4"
        manifest = app.load_json(sample_dir / "manifest.json")
        self.assertTrue(video.is_file())
        self.assertFalse(manifest["music"])
        self.assertFalse(manifest["lip_sync"])
        self.assertIn("بدون مزامنة شفاه", manifest["disclosure"])
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", str(video)],
            check=True, capture_output=True, text=True,
        )
        data = json.loads(probe.stdout)
        self.assertAlmostEqual(float(data["format"]["duration"]), 30.0, places=2)
        videos = [s for s in data["streams"] if s["codec_type"] == "video"]
        audios = [s for s in data["streams"] if s["codec_type"] == "audio"]
        self.assertEqual((videos[0]["width"], videos[0]["height"]), (1920, 1080))
        self.assertEqual(len(audios), 1)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = app.FactoryDB(Path(self.temp.name) / "factory.sqlite3")
        self.lesson = self.db.import_lesson(app.load_json(PROJECT / "data" / "lessons" / "demo_soft_contact_lens.json"))
        self.job = self.db.create_job(self.lesson["id"], "unit-test")
        self.script = app.load_json(PROJECT / "data" / "demo_payloads" / "script.json")
        self.scenes = app.load_json(PROJECT / "data" / "demo_payloads" / "scene_plan.json")

    def tearDown(self):
        self.temp.cleanup()

    def test_scientific_gate_cannot_be_skipped(self):
        job = self.db.set_script(self.job["id"], self.script)
        self.assertEqual(job["status"], "AWAITING_SCRIPT_SCIENTIFIC")
        with self.assertRaises(app.FactoryError):
            self.db.set_scenes(job["id"], self.scenes)
        job = self.db.approve(job["id"], "SCRIPT_SCIENTIFIC", notes="reviewed")
        self.assertEqual(job["status"], "SCRIPT_APPROVED")
        job = self.db.set_scenes(job["id"], self.scenes)
        self.assertEqual(job["status"], "SCENES_READY")

    def test_approval_decision_is_immutable(self):
        job = self.db.set_script(self.job["id"], self.script)
        self.db.approve(job["id"], "SCRIPT_SCIENTIFIC")
        with self.assertRaises(app.FactoryError):
            self.db.approve(job["id"], "SCRIPT_SCIENTIFIC")

    @unittest.skipUnless(shutil.which("ffmpeg") and app._pillow_available(), "FFmpeg/Pillow required")
    def test_renders_real_silent_full_hd_mp4(self):
        job = self.db.set_script(self.job["id"], self.script)
        job = self.db.approve(job["id"], "SCRIPT_SCIENTIFIC")
        job = self.db.set_scenes(job["id"], self.scenes)
        job = app.render_preview(self.db, job["id"])
        self.assertEqual(job["status"], "AWAITING_FINAL_VIDEO")
        self.assertTrue(job["publication_blocked"])
        video = PROJECT / job["preview_path"].lstrip("/")
        self.assertTrue(video.exists())
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height", "-of", "json", str(video)],
            check=True, capture_output=True, text=True,
        )
        streams = json.loads(probe.stdout)["streams"]
        videos = [s for s in streams if s["codec_type"] == "video"]
        audios = [s for s in streams if s["codec_type"] == "audio"]
        self.assertEqual((videos[0]["width"], videos[0]["height"]), (1920, 1080))
        self.assertEqual(audios, [])
        final = self.db.approve(job["id"], "FINAL_VIDEO", notes="watched")
        self.assertEqual(final["status"], "FINAL_APPROVED")
        self.assertFalse(final["publication_blocked"])
        self.assertFalse(final["auto_publish"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
