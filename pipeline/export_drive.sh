#!/bin/bash
# يرفع الفيديو النهائي إلى Google Drive ثم يحذفه محليًا. يُستدعى بعد نجاح بوابة المراجعة.
# الاستخدام: export_drive.sh <video_uid>
set -e
UID_ARG="${1:?video_uid required}"
SRC="/root/video-factory/outputs/narrated_${UID_ARG}/final_narrated.mp4"
REMOTE="optics_drive:OpticsGate/Videos"
DATE="$(date +%Y%m%d-%H%M)"
NAME="lesson_${UID_ARG}_${DATE}.mp4"
[ -f "$SRC" ] || { echo "no file: $SRC" >&2; exit 2; }
rclone mkdir "$REMOTE"
rclone copyto "$SRC" "${REMOTE}/${NAME}" --drive-chunk-size 32M
LINK="$(rclone link "${REMOTE}/${NAME}")"
echo "{\"drive_name\":\"${NAME}\",\"drive_link\":\"${LINK}\"}"
# نظّف مخرجات السيرفر لتوفير المساحة (نُبقي الصوت المصدر للمراجعة اللاحقة اختياريًا)
rm -f "$SRC" "/root/video-factory/outputs/narrated_${UID_ARG}"/S0*.mp4 \
      "/root/video-factory/outputs/narrated_${UID_ARG}"/silent.mp4 \
      "/root/video-factory/outputs/narrated_${UID_ARG}"/body.mp4 \
      "/root/video-factory/outputs/narrated_${UID_ARG}"/intro_n.mp4 \
      "/root/video-factory/outputs/narrated_${UID_ARG}"/outro_n.mp4
