import ast
p = "/root/video-factory/narrated_render.py"
s = open(p, encoding="utf-8").read()

# helper يختار زوج الماستر حسب المجموعة (V2..V5)
if "def _bookend_paths(" not in s:
    anchor = 'INTRO_PATH = os.environ.get("INTRO_MASTER", str(ASSETS / "avatar" / "_OPTICSGATE_INTRO_MASTER_V5.mp4"))'
    helper = '''BOOKEND_SET = os.environ.get("BOOKEND_SET", "V5").upper().lstrip("V")


def _bookend_paths(which=None):
    v = str(which or BOOKEND_SET).upper().lstrip("V") or "5"
    a = ASSETS / "avatar"
    intro = a / f"_OPTICSGATE_INTRO_MASTER_V{v}.mp4"
    outro = a / f"OPTICSGATE_END_MASTER_V{v}.mp4"
    if not intro.exists():
        intro = a / "_OPTICSGATE_INTRO_MASTER_V5.mp4"
        outro = a / "OPTICSGATE_END_MASTER_V5.mp4"
    return str(intro), str(outro)


'''
    s = s.replace(anchor, helper + anchor, 1)

# داخل render_narrated: اختر الماستر من payload["bookend_set"]
s = s.replace(
    "    out_dir = OUTPUTS_DIR / f\"narrated_{video_uid}\"\n    out_dir.mkdir(parents=True, exist_ok=True)",
    "    out_dir = OUTPUTS_DIR / f\"narrated_{video_uid}\"\n    out_dir.mkdir(parents=True, exist_ok=True)\n"
    "    intro_path, outro_path = _bookend_paths(payload.get(\"bookend_set\"))")

s = s.replace('if USE_BOOKENDS and Path(INTRO_PATH).exists():', 'if USE_BOOKENDS and Path(intro_path).exists():')
s = s.replace('"-i", INTRO_PATH,', '"-i", intro_path,')
s = s.replace('if USE_BOOKENDS and Path(OUTRO_PATH).exists():', 'if USE_BOOKENDS and Path(outro_path).exists():')
s = s.replace('"-i", OUTRO_PATH,', '"-i", outro_path,')
s = s.replace('"bookends": USE_BOOKENDS and Path(INTRO_PATH).exists(),',
              '"bookends": USE_BOOKENDS and Path(intro_path).exists(),\n        "bookend_set": os.path.basename(intro_path),')

open(p, "w", encoding="utf-8").write(s)
ast.parse(s)
for probe in ["def _bookend_paths(", "intro_path, outro_path = _bookend_paths", '"-i", intro_path,', '"-i", outro_path,']:
    assert probe in s, probe
    print("ok", probe)
print("bookend selection wired")
