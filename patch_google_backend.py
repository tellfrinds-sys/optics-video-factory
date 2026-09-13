p = "narrated_render.py"
s = open(p, encoding="utf-8").read()
old = '''def _tts(text: str, dest: Path, speed: float):
    if TTS_BACKEND in ("piper", "piper_v3"):
        import piper_v3_tts
        return piper_v3_tts.piper_v3_tts(text, dest, speed)
    if TTS_BACKEND == "azure":'''
new = '''def _tts(text: str, dest: Path, speed: float):
    if TTS_BACKEND == "google":
        import google_tts
        return google_tts.google_tts(text, dest, speed)
    if TTS_BACKEND in ("piper", "piper_v3"):
        import piper_v3_tts
        return piper_v3_tts.piper_v3_tts(text, dest, speed)
    if TTS_BACKEND == "azure":'''
assert old in s, "pattern not found"
s = s.replace(old, new)
open(p, "w", encoding="utf-8").write(s)
print("patched")
