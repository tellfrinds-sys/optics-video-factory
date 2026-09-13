# -*- coding: utf-8 -*-
"""rvc_tts.py — Piper (نطق مصري) ثم RVC (نبرة صوت المستخدم) ثم إزالة صدى.
واجهة واحدة: rvc_tts(text, dest_path, speed=1.0) -> word_times | None  (نفس واجهة _eleven_tts)
"""
import os, subprocess, tempfile, wave
from pathlib import Path
import numpy as np

ROOT = Path('/root/video-factory')
RVC_REPO = ROOT / 'rvc_repo'
MODEL = 'mydataset.pth'
INDEX = str(ROOT / 'rvc_model' / 'mydataset.index')
PYBIN = '/root/xttsenv/bin/python'

INDEX_RATE = float(os.environ.get('RVC_INDEX_RATE', '0.5'))
PROTECT    = float(os.environ.get('RVC_PROTECT', '0.25'))
F0METHOD   = os.environ.get('RVC_F0', 'rmvpe')
ATEMPO     = float(os.environ.get('RVC_ATEMPO', '1.06'))


def _dereverb(src, dst):
    """WPE أحادي القناة + EQ خفيف + تسوية."""
    try:
        import soundfile as sf
        from nara_wpe.wpe import wpe
        from nara_wpe.utils import stft, istft
        sig, sr = sf.read(str(src))
        if sig.ndim > 1:
            sig = sig.mean(1)
        sig = sig.astype(np.float64)
        O = dict(size=512, shift=128)
        Y = stft(sig[None, :], **O).transpose(2, 0, 1)
        Z = wpe(Y, taps=10, delay=3, iterations=3).transpose(1, 2, 0)
        out = istft(Z, size=O['size'], shift=O['shift'])[0][:len(sig)]
        pk = np.max(np.abs(out)) or 1.0
        out = (out / pk * 0.95).astype(np.float32)
        tmp = str(Path(dst).with_suffix('.wpe.wav'))
        sf.write(tmp, out, sr)
        return tmp
    except Exception as e:
        print('WPE skip:', e)
        return str(src)


def rvc_tts(text, dest_path, speed=1.0):
    import piper_tts
    dest_path = Path(dest_path)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        piper_wav = td / 'piper.wav'
        wt = piper_tts.piper_tts(text, str(piper_wav.with_suffix('.mp3')), speed)
        # piper_tts يكتب mp3؛ حوّله wav للـ RVC
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i',
                        str(piper_wav.with_suffix('.mp3')), '-ar', '40000', '-ac', '1',
                        str(piper_wav)], check=True)
        rvc_wav = td / 'rvc.wav'
        env = dict(os.environ,
                   weight_root=str(RVC_REPO / 'assets' / 'weights'),
                   rmvpe_root=str(RVC_REPO / 'assets' / 'rmvpe'),
                   index_root=str(RVC_REPO / 'logs'))
        r = subprocess.run([PYBIN, '-m', 'infer.cli', '--model', MODEL,
                            '--input', str(piper_wav), '--output', str(rvc_wav),
                            '--index', INDEX, '--index-rate', str(INDEX_RATE),
                            '--f0-method', F0METHOD, '--protect', str(PROTECT)],
                           cwd=str(RVC_REPO), env=env, capture_output=True, text=True)
        if not rvc_wav.exists():
            raise RuntimeError('RVC فشل:\n' + r.stdout[-1500:] + r.stderr[-1500:])
        dry = _dereverb(rvc_wav, td / 'dry.wav')
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', dry, '-af',
                        (f'atempo={ATEMPO},highpass=f=85,'
                         'equalizer=f=200:t=q:w=1:g=-1.5,'
                         'equalizer=f=3200:t=q:w=2:g=1.2,'
                         'acompressor=threshold=-18dB:ratio=2.5:attack=6:release=120,'
                         'loudnorm=I=-16:TP=-1.5:LRA=11'),
                        '-ar', '44100', '-b:a', '160k', str(dest_path)], check=True)
    if not dest_path.exists() or dest_path.stat().st_size < 1200:
        raise RuntimeError('rvc_tts: ناتج فارغ')
    return wt or None


if __name__ == '__main__':
    import sys, time
    t = sys.argv[1] if len(sys.argv) > 1 else (
        'النهاردة هنتكلم عن أول نسيج شفاف قدام العين، وهو القرنية. '
        'سمك القرنية نص مليمتر تقريبا، والأكسجين مهم للفسيولوجيا بتاعتها. '
        'ده محتوى تعليمي مش بديل عن الفحص الطبي.')
    d = sys.argv[2] if len(sys.argv) > 2 else '/var/www/opticsgate.online/html/ttslab/rvc_v2.mp3'
    t0 = time.time()
    w = rvc_tts(t, d, 1.0)
    import subprocess as sp
    dur = float(sp.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0', d],
                       capture_output=True, text=True).stdout.strip())
    print('OK  %.0fs معالجة | %.1fs صوت | %.0f wpm' % (time.time()-t0, dur, len(t.split())/dur*60))
