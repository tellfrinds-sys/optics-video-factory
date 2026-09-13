#!/bin/bash
# نسخ احتياطي يومي تلقائي لكود المصنع على GitHub
cd /root/video-factory || exit 1
git add -A > /dev/null 2>&1
if ! git diff --cached --quiet; then
  git -c user.email="bot@opticsgate.online" -c user.name="OpticsGate AutoBackup" \
      commit -m "نسخة احتياطية تلقائية يومية $(date +%Y-%m-%d_%H:%M)" > /dev/null 2>&1
  git push origin master >> /root/video-factory/outputs/_status/autobackup.log 2>&1
  echo "$(date): backed up" >> /root/video-factory/outputs/_status/autobackup.log
else
  echo "$(date): no changes" >> /root/video-factory/outputs/_status/autobackup.log
fi
