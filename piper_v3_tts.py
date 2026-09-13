# -*- coding: utf-8 -*-
"""piper_v3_tts.py — نطق مباشر لموديل v3/v4 المصري المدرّب على صوت المدرّب.
موديل مصري بالفعل، فالمعالجة خفيفة: تشكيل mishkal + تصحيحات سطحية + سرعة مضبوطة.
لا تحويل فونيمي مصري (_egy) ولا حقن IPA — دول كانوا للموديل الأردني.
    piper_v3_tts(text, dest, speed=1.0) -> [[word,t0,t1],...] | None

نسخة "السلاسة": توليف النص كامل في نداء واحد، دمج مقاطع Piper بمزج قصير (crossfade)
وسكتات طبيعية عند الترقيم بدل الفواصل الرقمية الحادة، ومعالجة ffmpeg أخف.
"""
import json, os, re, subprocess, wave
from pathlib import Path
import numpy as np

ROOT = Path('/root/video-factory')
MODEL = os.environ.get('PIPER_MODEL', str(ROOT/'tts_models'/'piper_v3'/'opticsgate_v5.onnx'))
LEXDIR = ROOT/'pipeline'
_LS = float(os.environ.get('PIPER_LS', '1.23'))       # أبطأ 10% عن 1.12 (طلب المستخدم) — يساعد نهايات الكلمات
_NOISE = float(os.environ.get('PIPER_NOISE', '0.667'))   # القيمة الأصلية للموديل
_NOISEW = float(os.environ.get('PIPER_NOISEW', '0.8'))   # القيمة الأصلية — أقل من كده بيبقى آلي ومتقطّع
_XFADE = float(os.environ.get('PIPER_XFADE', '0.018'))   # مزج 18ms عند وصلات المقاطع (يمنع الطقطقة)
_PAUSE_DOT = float(os.environ.get('PIPER_PAUSE_DOT', '0.22'))    # سكتة بعد . ! ؟
_PAUSE_COM = float(os.environ.get('PIPER_PAUSE_COM', '0.11'))    # سكتة بعد ،
_EDGE_SIL = float(os.environ.get('PIPER_EDGE_SIL', '0.065'))     # سكوت حواف أوسع = مايقصّش آخر حرف
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
    def r(m):
        return _ACR.get(m.group(0).upper(), m.group(0))
    return re.sub(r'[A-Za-z]{2,6}', r, t)


def _trim_edges(au, sr, keep=_EDGE_SIL, thr=0.006):
    """يقصّ السكوت الزائد من أول وآخر المقطع ويسيب هامش صغير ثابت."""
    if len(au) == 0: return au
    idx = np.where(np.abs(au) > thr)[0]
    if len(idx) == 0: return au
    k = int(keep*sr)
    a = max(0, idx[0]-k); b = min(len(au), idx[-1]+1+k)
    return au[a:b]

def _xfade_join(parts, sr, xf=_XFADE):
    """يدمج قائمة مقاطع بمزج متساوي القدرة قصير عند الوصلات."""
    n = int(xf*sr)
    out = parts[0].astype('float32')
    for p in parts[1:]:
        p = p.astype('float32')
        if n > 0 and len(out) >= n and len(p) >= n:
            r = np.linspace(0, np.pi/2, n, dtype='float32')
            fo = np.cos(r); fi = np.sin(r)
            out[-n:] = out[-n:]*fo + p[:n]*fi
            out = np.concatenate([out, p[n:]])
        else:
            out = np.concatenate([out, p])
    return out


def piper_v3_tts(text, dest_path, speed=1.0):
    from piper.config import SynthesisConfig
    v, diac = _V()
    surface = _lx('pron_surface.json')
    surface.update(_lx('pron_optics.json'))  # مصطلحات البصريات لها الأولوية
    t = _acronyms(re.sub(r'\s+',' ', str(text)).strip())
    # تقسيم إلى جُمل مع الاحتفاظ بعلامة الترقيم المنهية لكل جملة
    sents = re.findall(r'[^.!؟]*[.!؟]|[^.!؟]+$', t)
    sents = [s.strip() for s in sents if s.strip()]
    ls = max(0.85, min(1.9, _LS/max(0.7, speed)))
    scfg = SynthesisConfig(length_scale=ls, noise_scale=_NOISE, noise_w_scale=_NOISEW)
    sr = v.config.sample_rate

    seg_audio = []          # مقطع صوتي لكل جملة (بعد قصّ الحواف)
    seg_words = []           # كلمات كل جملة
    pauses = []              # السكتة اللي تسبق الجملة التالية
    for s in sents:
        raw_words = [w for w in s.split(' ') if w.strip()]
        d = _prep(s, diac, surface)
        if d and d[-1] not in '.!؟،':   # علامة نهاية = إطلاق أوضح لآخر حرف (مثل التدريب)
            d = d + ' .'
        chunks = []
        for c in v.synthesize(d, scfg):
            chunks.append(np.frombuffer(c.audio_int16_bytes, dtype='<i2'))
        if not chunks:
            continue
        au = np.concatenate(chunks).astype('float32')/32768.0
        au = _trim_edges(au, sr)
        # تطبيع ذروة لكل جملة → مفيش جملة تطلع واطية
        pk = float(np.max(np.abs(au))) if len(au) else 0.0
        if pk > 1e-4:
            au = au * (0.95/pk)
        # fade خفيف جدًا على الحواف (يمنع الطقطقة بدون بلع آخر حرف)
        fi = int(0.006*sr); fo = int(0.004*sr)
        if len(au) > fi+fo:
            au[:fi] *= np.linspace(0,1,fi,dtype='float32')
            au[-fo:] *= np.linspace(1,0,fo,dtype='float32')
        seg_audio.append(au)
        seg_words.append(raw_words)
        last = s.strip()[-1:]
        pauses.append(_PAUSE_DOT if last in '.!؟' else (_PAUSE_COM if last == '،' else 0.06))

    if not seg_audio:
        return None

    # تجميع: مقطع + سكتة طبيعية + مزج قصير
    parts = []
    word_times = []
    cur = 0.0
    for i, (au, words, pz) in enumerate(zip(seg_audio, seg_words, pauses)):
        dur = len(au)/sr
        lens = [max(1, len(_bare(w))) for w in words]; tot = sum(lens) or 1
        acc = cur
        for w, L in zip(words, lens):
            wl = dur*L/tot
            word_times.append([re.sub(r'[^%s]'%_AR,'',_bare(w)) or w, round(acc,3), round(acc+wl,3)])
            acc += wl
        parts.append(au)
        cur += dur
        if i < len(seg_audio)-1:
            gap = np.zeros(int(pz*sr), dtype='float32')
            parts.append(gap)
            cur += pz

    full = _xfade_join(parts, sr)
    # سكتة نهاية قصيرة عشان آخر كلمة ماتتقصّش بنهاية الملف
    full = np.concatenate([full.astype('float32'), np.zeros(int(0.12*sr), dtype='float32')])
    i16 = (np.clip(full, -1, 1)*32767).astype('<i2')
    dest_path = Path(dest_path); raw = dest_path.with_suffix('.raw.wav')
    with wave.open(str(raw),'wb') as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr); wf.writeframes(i16.tobytes())
    # معالجة: EQ حضور + وضوح النهايات + ضاغط لطيف + تطبيع بمستوى أعلى (أعلى وأقوى)
    subprocess.run(['ffmpeg','-y','-loglevel','error','-i',str(raw),'-af',
        'highpass=f=65,'
        'equalizer=f=190:t=q:w=1.2:g=-1.0,'          # تقليل طنين منخفض
        'equalizer=f=2600:t=q:w=2.0:g=1.6,'          # حضور الصوت
        'treble=g=3.2:f=4800,'                       # وضوح نهايات الكلمات (احتكاكيات/انفجاريات)
        'acompressor=threshold=-19dB:ratio=3:attack=6:release=110:makeup=3,'
        'loudnorm=I=-13:TP=-1.0:LRA=10,'             # أعلى بـ 3dB من قبل
        'alimiter=limit=0.94,'
        'volume=1.0dB',
        '-ar','44100','-b:a','176k',str(dest_path)],check=True)
    raw.unlink(missing_ok=True)
    if not dest_path.exists() or dest_path.stat().st_size < 1200:
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
