import os
import json
import urllib.request
import urllib.error

# read key from .env (no SDK, no extra deps)
env = {}
with open(os.path.join(os.path.dirname(__file__), ".env"), encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line and "=" in line:
            k, v = line.split("=", 1)
            env[k] = v

CARTESIA_API_KEY = env.get("CARTESIA_API_KEY") or os.environ.get("CARTESIA_API_KEY")
if not CARTESIA_API_KEY:
    raise SystemExit("CARTESIA_API_KEY missing")

transcript = (
    ".ألسلام عليكم ورحمة الله وبركاته.\n"
    "أهلا بيكم.\n"
    "لو إنت مستخدم للبصريات او مهتم بالمجال ده ومحتاج تطور معرفتك للحفاظ على صحة عينيك.\n"
    "أو لو إنت شغّال في البصريات  سواء خريج جديد او ممارس وبتتعلّم بالخبرة والتخمين. \n"
    "أكاديمية بوابة البصريات هي بوابتك العربية الاولى في مجال البصريات.\n"
    "سواء كنت فني او مساعد بصريات, طالب يبحث عن تدريب؟؟، أخصائي مُرَخَّص؟، صاحب محل، حتى لو كنت مستهلك مهتم بتثقيف نفسه بصريا— كلٌ ليه  مساره التعليمي والتثقيفي.\n"
    "وده هيتم من خلال منهج منظم ومكون من أكثر من تلاتميه وخمسين فيديو تعليمي متفرعين تحت عشرين باب شاملين كل ما يخص مهنة البصريات الطبية.\n"
    "ومش بس كدة , ده منهج مهني وعلمي موثق بمصادر علمية هتلاقوها تحت كل فيديو., \n"
    "كن من اول المشتركين معنا لأن كل يوم بتأجله، ده عبارة عن معلومات ضايعه عليك و خبرة بتخسرها. \n"
    "نوعدك بتجربة مميزة وإن إقتراحاتك تكون محل إهتمامنا وتقديرنا ..\n"
    "ابدأ بتسجيل إهتمامك معانا وأكيد هاتكون من المبادرين إللي هايستفيدوا بخصم إطلاق المنصة قريبا إن شاء الله .  للإشتراك معنا؟ .\n"
    " تفضلوا بزيارة موقعنا الإلكتروني \n"
    "دبليودبليودبليو دوت\n"
    "Optics gate\n"
    "دوت كوم.\n"
    "الأان اصبح للبصرياتٌ بوابه."
)

body = json.dumps({
    "model_id": "sonic-3.6",
    "transcript": transcript,
    "voice": {"mode": "id", "id": "7010376c-87f3-49de-8dea-21e1fa048445"},
    "output_format": {"container": "wav", "encoding": "pcm_s16le", "sample_rate": 24000},
    "generation_config": {"speed": 1, "volume": 1},
}).encode("utf-8")

req = urllib.request.Request(
    "https://api.cartesia.ai/tts/bytes",
    data=body,
    headers={
        "Content-Type": "application/json",
        "X-API-Key": CARTESIA_API_KEY,
        "Cartesia-Version": "2026-08-14",
    },
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
        ctype = resp.headers.get("Content-Type", "")
except urllib.error.HTTPError as e:
    print("HTTP ERROR", e.code, e.read().decode("utf-8", "ignore")[:800])
    raise SystemExit(1)

print("content-type:", ctype, "| bytes:", len(data))
out_path = os.path.join(os.path.dirname(__file__), "output.wav")
with open(out_path, "wb") as f:
    f.write(data)
print("saved:", out_path)
