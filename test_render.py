import json
import os
import sys

sys.path.insert(0, "/root/video-factory")
os.environ.setdefault("OPTICSGATE_FACTORY_ROOT", "/root/video-factory")

import narrated_render
from corrected_scenes import SCENES

payload = {"video_uid": int(os.environ.get("VUID", "500128")), "scenes": SCENES}
res = narrated_render.render_narrated(payload)
print(json.dumps(res, ensure_ascii=False, indent=1))
