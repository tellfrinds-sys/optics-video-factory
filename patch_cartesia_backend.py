p = "narrated_render.py"
s = open(p, encoding="utf-8").read()
old = '''def _tts(text: str, dest: Path, speed: float):
    if TTS_BACKEND == "google":
        import google_tts
        return google_tts.google_tts(text, dest, speed)'''
new = '''def _tts(text: str, dest: Path, speed: float):
    if TTS_BACKEND == "cartesia":
        import cartesia_tts
        return cartesia_tts.cartesia_tts(text, dest, speed)
    if TTS_BACKEND == "google":
        import google_tts
        return google_tts.google_tts(text, dest, speed)'''
assert old in s, "pattern not found"
s = s.replace(old, new)
open(p, "w", encoding="utf-8").write(s)
print("patched")
