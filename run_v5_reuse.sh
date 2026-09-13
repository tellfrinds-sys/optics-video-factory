#!/bin/bash
cd /root/video-factory
while IFS= read -r line; do export "$line"; done < <(systemctl show videofactory -p Environment --value | tr " " "\n" | grep "=")
export TTS_SPEED=0.95 SCENE_GAP=0.42 USE_BOOKENDS=1 DEGAP=1 DEGAP_KEEP=0.17 DEGAP_MIN=0.30 REUSE_AUDIO=1
rm -f outputs/narrated_500128/*.mp4 outputs/narrated_500128/*.m4a
python3 test_render.py
echo "EXIT $?"
