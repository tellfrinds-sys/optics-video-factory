import asyncio, subprocess, sys
import edge_tts
sys.path.insert(0, "/root/video-factory")
import corrected_scenes as cs


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", p], capture_output=True, text=True).stdout)


async def gen(text, voice, out, rate="+0%"):
    c = edge_tts.Communicate(text, voice, rate=rate)
    await c.save(out)


TEXTS = {
    "s2": cs.SCENES[1]["narration"],
    "s7": cs.SCENES[6]["narration"],
}
for tag, txt in TEXTS.items():
    nw = len(txt.split())
    for v, short in (("ar-EG-ShakirNeural", "shakir"), ("ar-EG-SalmaNeural", "salma")):
        out = f"/tmp/edge_{tag}_{short}.mp3"
        asyncio.run(gen(txt, v, out))
        d = dur(out)
        print(f"{tag} {short}: {d:.1f}s  {nw/d:.2f} wps  ({nw}w)")
