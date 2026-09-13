# -*- coding: utf-8 -*-
"""piper_v3_tts.py — نطق مباشر لموديل v3 المصري المدرّب على صوت المدرّب.
موديل v3 مصري بالفعل، فالمعالجة خفيفة: تشكيل mishkal + تصحيحات سطحية + سرعة مضبوطة.
لا تحويل فونيمي مصري (_egy) ولا حقن IPA — دول كانوا للموديل الأردني.
    piper_v3_tts(text, dest, speed=1.0) -> [[word,t0,t1],...] | None
"""
import json, os, re, subprocess, wave
from pathlib import Path
import numpy as np

ROOT = Path('/root/video-factory')
MODEL = os.environ.get('PIPER_MODEL', str(ROOT/'tts_models'/'piper_v3'/'opticsgate_v3.onnx'))
LEXDIR = ROOT/'pipeline'
_LS = float(os.environ.get('PIPER_LS', '1.30'))      # سرعة إلقاء مريحة
_NOISE = float(os.environ.get('PIPER_NOISE', '0.6'))
_NOISEW = float(os.environ.get('PIPER_NOISEW', '0.65'))
_GAP = float(os.environ.get('PIPER_GAP', '0.08'))
_AR = 'ء-ي'
_H = 'ً-ْٰ'
_voice = None; _diac = None

def _lx(name):
    try:
        d = json.loads((LEXDIR/name).read_text(encoding='utf-8'))
        return {k:v for k,v in d.items() if not str(k).startswith('_')} if isinstance(d,dict) else d
    except Exception:
        return {}

def _V():
    global _voice, _diac
    if _voice is None:
        from piper import PiperVoice
        _voice = PiperVoice.load(MODEL)
        _voice.use_tashkeel = False
        try:
            import mishkal.tashkeel as mt
            _diac = mt.TashkeelClass()
        except Exception:
            _diac = False
    return _voice, _diac

def _bare(w):
    return re.sub('['+_H+'ـ]', '', w).strip('.،!؟:؛"\'()')

def _deiraab(t):
    t = re.sub(r'([%s])[%s](?=[\s.،!؟:؛]|$)' % (_AR,'ًٌٍ'), r'\1', t)
    t = re.sub(r'([%s])[%s](?=[\s.،!؟:؛]|$)' % (_AR,'َُِ'), r'\1', t)
    return re.sub('ـ','',t)

def _prep(t, diac, surface):
    if diac:
        try: t = diac.tashkeel(t)
        except Exception: pass
    t = _deiraab(t)
    def repl(m):
        b = _bare(m.group(0))
        if b in surface: return surface[b]
        for pfx in ('وال','فال','بال','كال','لل','ال','و','ف','ب','ك','ل'):
            if b.startswith(pfx) and b[len(pfx):] in surface:
                return pfx + surface[b[len(pfx):]]
        return m.group(0)
    return re.sub(r'[%s]+[%s]*(?:[%s][%s]*)*' % (_AR,_H,_AR,_H), repl, t)

# قواعد صوتية للاختصارات الإنجليزية الشائعة في البصريات
_ACR = {
 'OCT':'أُو سِي تِي','IOL':'آي أُو إِل','RGP':'آر جِي بِي','PRK':'بِي آر كِيه',
 'UV':'يُو فِي','LED':'إِل إِي دِي','MR':'إِم آر','AB':'إِيه بِي','DK':'دِي كِيه',
 'ISO':'آيْزُو','LASIK':'لِيزِك','SMILE':'سْمايْل','PD':'بِي دِي',
}
def _acronyms(t):
    import re as _re
    def r(m):
        return _ACR.get(m.group(0).upper(), m.group(0))
    return _re.sub(r'[A-Za-z]{2,6}', r, t)


def piper_v3_tts(text, dest_path, speed=1.0):
    from piper.config import SynthesisConfig
    v, diac = _V()
    surface = _lx('pron_surface.json')
    surface.update(_lx('pron_optics.json'))  # مصطلحات البصريات لها الأولوية
    t = _acronyms(re.sub(r'\s+',' ', str(text)).strip())
    sents = [x.strip() for x in re.split(r'(?<=[.!؟])\s+', t) if x.strip()]
    ls = max(0.85, min(1.9, _LS/max(0.7,speed)))
    scfg = SynthesisConfig(length_scale=ls, noise_scale=_NOISE, noise_w_scale=_NOISEW)
    sr = v.config.sample_rate
    audio_all=[]; word_times=[]; cur=0.0
    for s in sents:
        raw_words=[w for w in s.split(' ') if w.strip()]
        d = _prep(s, diac, surface)
        chunks=[]
        for c in v.synthesize(d, scfg):
            chunks.append(np.frombuffer(c.audio_int16_bytes, dtype='<i2'))
        if not chunks: continue
        au = np.concatenate(chunks).astype('float32')/32768.0
        dur = len(au)/sr
        lens=[max(1,len(_bare(w))) for w in raw_words]; tot=sum(lens) or 1
        acc=cur
        for w,L in zip(raw_words,lens):
            wl=dur*L/tot
            word_times.append([re.sub(r'[^%s]'%_AR,'',_bare(w)) or w, round(acc,3), round(acc+wl,3)])
            acc+=wl
        audio_all.append(au); audio_all.append(np.zeros(int(_GAP*sr),dtype='float32'))
        cur += dur + _GAP
    if not audio_all: return None
    i16=(np.clip(np.concatenate(audio_all),-1,1)*32767).astype('<i2')
    dest_path=Path(dest_path); raw=dest_path.with_suffix('.raw.wav')
    with wave.open(str(raw),'wb') as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr); wf.writeframes(i16.tobytes())
    subprocess.run(['ffmpeg','-y','-loglevel','error','-i',str(raw),'-af',
        'highpass=f=70,equalizer=f=180:t=q:w=1:g=-1,equalizer=f=3000:t=q:w=2:g=1.2,'
        'acompressor=threshold=-20dB:ratio=2.2:attack=8:release=140,'
        'loudnorm=I=-16:TP=-1.5:LRA=11','-ar','44100','-b:a','160k',str(dest_path)],check=True)
    raw.unlink(missing_ok=True)
    if not dest_path.exists() or dest_path.stat().st_size<1200:
        raise RuntimeError('piper_v3: صوت فارغ')
    return word_times or None

if __name__=='__main__':
    import sys, time
    t=sys.argv[1] if len(sys.argv)>1 else 'النهارده هنتكلم عن القرنية، وسمكها نص مليمتر، والأكسجين مهم للفسيولوجيا.'
    d=sys.argv[2] if len(sys.argv)>2 else '/var/www/opticsgate.online/html/ttslab/v3_light_test.mp3'
    t0=time.time(); w=piper_v3_tts(t,d,1.0)
    import subprocess as sp
    dur=float(sp.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',d],capture_output=True,text=True).stdout.strip())
    print('OK %.1fs صوت | %.0f wpm' % (dur, len(t.split())/dur*60))
