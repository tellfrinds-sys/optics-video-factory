# -*- coding: utf-8 -*-
"""piper_tts.py — تركيب صوت مصري محلي (Piper) + طبقة نطق مصرية قابلة للضبط.

    piper_tts(text, dest, speed) -> [[word, t0, t1], ...] | None   (نفس واجهة _eleven_tts)

المبدأ (بعد اختبارات): فونمة الجملة **كاملة** (انسيابية) ثم تحويل مصري عام على التدفّق
ثم استبدال جراحي للمصطلحات المحميّة. التشكيل بـ mishkal على الجملة كاملة.
"""
import json, os, re, subprocess, wave
from pathlib import Path

ROOT = Path("/root/video-factory")
MODEL = os.environ.get("PIPER_MODEL", str(ROOT / "tts_models" / "piper_v3" / "opticsgate_v3.onnx"))
LEXDIR = ROOT / "pipeline"

_H = "ً-ْٰ"
_HFIN = "ًٌٍَُِ"
_AR = "ء-ي"
_PFX = [("وال", "wel"), ("فال", "fel"), ("بال", "bel"), ("كال", "kel"), ("لل", "lel"),
        ("ال", "el"), ("و", "we"), ("ف", "fa"), ("ب", "be"), ("ك", "ke"), ("ل", "le")]

_LS = float(os.environ.get("PIPER_LS", "0.74"))
_GAP = float(os.environ.get("PIPER_GAP", "0.06"))
_NOISE = float(os.environ.get("PIPER_NOISE", "0.5"))
_NOISEW = float(os.environ.get("PIPER_NOISEW", "0.6"))

_voice = None
_diac = None


def _lx(name, default):
    try:
        d = json.loads((LEXDIR / name).read_text(encoding="utf-8"))
        return {k: v for k, v in d.items() if not str(k).startswith("_")} if isinstance(d, dict) else d
    except Exception:
        return default


def _V():
    global _voice, _diac
    if _voice is None:
        from piper import PiperVoice
        _voice = PiperVoice.load(MODEL)
        _voice.use_tashkeel = False
        try:
            import mishkal.tashkeel as _mt
            _diac = _mt.TashkeelClass()
        except Exception:
            _diac = False
    return _voice, _diac


def _bare(w):
    return re.sub("[" + _H + "ـ]", "", w).strip(".،!؟:؛\"'()")


def _deiraab(t):
    # جرّد التنوين ونهاية الحركة القصيرة عند الوقف (نطق مصري)
    t = re.sub(r"([%s])[%s](?=[\s.،!؟:؛]|$)" % (_AR, "ًٌٍ"), r"\1", t)
    t = re.sub(r"([%s])[%s](?=[\s.،!؟:؛]|$)" % (_AR, "َُِ"), r"\1", t)
    return re.sub("ـ", "", t)


_EGY1 = {"q": "ʔ", "θ": "t", "ð": "d"}


def _egy(ph, keep_q=False):
    r, i = [], 0
    while i < len(ph):
        a, b = ph[i], (ph[i + 1] if i + 1 < len(ph) else "")
        if a == "d" and b == "ʒ":
            r.append("g"); i += 2; continue
        if a == "ð" and b == "ˤ":
            r += ["z", "ˤ"]; i += 2; continue
        if a == "q":
            r.append("q" if keep_q else "ʔ"); i += 1; continue
        r.append(_EGY1.get(a, a)); i += 1
    return r


def _phon(v, s):
    o = v.phonemize(s)
    return list(o[0]) if o and o[0] else []


def _find(hay, needle, start=0):
    if not needle or len(needle) > len(hay):
        return -1
    for i in range(start, len(hay) - len(needle) + 1):
        if hay[i:i + len(needle)] == needle:
            return i
    return -1


def _lex_ipa(b, phon_lex):
    if b in phon_lex:
        return list(phon_lex[b])
    for pfx, pph in _PFX:
        if b.startswith(pfx) and b[len(pfx):] in phon_lex:
            return list(pph) + list(phon_lex[b[len(pfx):]])
    return None


def _diacritize(t, diac, surface):
    if diac:
        try:
            t = diac.tashkeel(t)
        except Exception:
            pass
    t = _deiraab(t)
    # قاموس سطحي: استبدل الكلمة (بلا تشكيل) بشكلها الصحيح
    def repl(m):
        b = _bare(m.group(0))
        if b in surface:
            return surface[b]
        for pfx, _ in _PFX:
            if b.startswith(pfx) and b[len(pfx):] in surface:
                return pfx + surface[b[len(pfx):]]
        return m.group(0)
    return re.sub(r"[%s]+[%s]*(?:[%s][%s]*)*" % (_AR, _H, _AR, _H), repl, t)


def piper_tts(text, dest_path, speed=1.0):
    from piper.config import SynthesisConfig
    import numpy as np

    v, diac = _V()
    surface = _lx("pron_surface.json", {})
    phon_lex = _lx("pron_phonemes.json", {})
    keepq = set(_lx("keep_qaf.json", []))

    t = re.sub(r"\s+", " ", str(text)).strip()
    sents = [x.strip() for x in re.split(r"(?<=[.!؟])\s+", t) if x.strip()]

    ls = max(0.62, min(1.15, _LS / max(0.7, speed)))
    scfg = SynthesisConfig(length_scale=ls, noise_scale=_NOISE, noise_w_scale=_NOISEW)
    sr = v.config.sample_rate

    audio_all, word_times, cursor = [], [], 0.0
    for s in sents:
        raw_words = [w for w in s.split(" ") if w.strip()]
        d = _diacritize(s, diac, surface)
        full = _phon(v, d)
        if not full:
            continue
        full = _egy(full)

        # استبدال جراحي: قاموس فونيمي + حماية القاف (بالترتيب من اليسار)
        search = 0
        for w in raw_words:
            b = _bare(w)
            if not b:
                continue
            want = _lex_ipa(b, phon_lex)
            kq = (b in keepq) or any(b.startswith(p) and b[len(p):] in keepq for p, _ in _PFX)
            if not want and not kq:
                continue
            # وقّع الكلمة كما تظهر في full (تشكيل ثم فونمة ثم تحويل عام)
            wd = _diacritize(w, diac, surface)
            sig = _egy(_phon(v, wd))
            pos = _find(full, sig, search)
            if pos < 0:
                pos = _find(full, sig)
            if pos < 0:
                continue
            if not want:
                want = _egy(_phon(v, wd), keep_q=True)
            full[pos:pos + len(sig)] = want
            search = pos + len(want)

        ids = v.phonemes_to_ids(full + ["."])
        au = v.phoneme_ids_to_audio(ids, scfg)
        au = np.asarray(au[0] if isinstance(au, tuple) else au, dtype="float32")
        dur = len(au) / sr

        # توقيت الكلمات بالتناسب مع أطوال فونيماتها
        lens = [max(1, len(_phon(v, _diacritize(w, diac, surface)))) for w in raw_words]
        tot = sum(lens) or 1
        acc = cursor
        for w, L in zip(raw_words, lens):
            wl = dur * L / tot
            word_times.append([re.sub(r"[^%s]" % _AR, "", _bare(w)) or w, round(acc, 3), round(acc + wl, 3)])
            acc += wl

        audio_all.append(au)
        audio_all.append(np.zeros(int(_GAP * sr), dtype="float32"))
        cursor += dur + _GAP

    if not audio_all:
        return None
    i16 = (np.clip(np.concatenate(audio_all), -1.0, 1.0) * 32767).astype("<i2")
    dest_path = Path(dest_path)
    raw = dest_path.with_suffix(".raw.wav")
    with wave.open(str(raw), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
        wf.writeframes(i16.tobytes())
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw),
                    "-af", ("highpass=f=80,equalizer=f=155:t=q:w=1:g=2,"
                            "equalizer=f=2900:t=q:w=2:g=-1.4,"
                            "acompressor=threshold=-20dB:ratio=2.4:attack=8:release=140,"
                            "loudnorm=I=-16:TP=-1.5:LRA=11"),
                    "-ar", "44100", "-b:a", "160k", str(dest_path)], check=True)
    raw.unlink(missing_ok=True)
    if not dest_path.exists() or dest_path.stat().st_size < 1200:
        raise RuntimeError("Piper: صوت فارغ")
    return word_times or None


if __name__ == "__main__":
    import sys, time, subprocess as sp
    t = sys.argv[1] if len(sys.argv) > 1 else (
        "النهاردة هنتكلم عن أول نسيج شفاف قدام العين، وهو القرنية. القرنية سمكها نص مليمتر، "
        "والأكسجين مهم جداً للفسيولوجيا بتاعتها.")
    d = sys.argv[2] if len(sys.argv) > 2 else "/var/www/opticsgate.online/html/ttslab/egy_test.mp3"
    t0 = time.time()
    w = piper_tts(t, d, 1.0)
    dur = float(sp.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", d],
                       capture_output=True, text=True).stdout.strip())
    print("OK synth %.1fs | %.1fs صوت | %.0f wpm | %d كلمة" % (
        time.time() - t0, dur, len(t.split()) / dur * 60, len(w or [])))
