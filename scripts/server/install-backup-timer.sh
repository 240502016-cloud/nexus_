#!/usr/bin/env bash
#
# Yedek timer'ını kurar veya günceller. Tekrar çalıştırmak güvenlidir.
# Kaldırmak için:  systemctl disable --now nexus-backup.timer
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_SCRIPT=/opt/nexus/scripts/server/backup-postgres.sh

# Depo zaten /opt/nexus'ta olduğunda kaynak ve hedef aynı dosyadır; yalnız izni ayarla.
if [ "$SRC_DIR/backup-postgres.sh" -ef "$TARGET_SCRIPT" ]; then
  chmod 0755 "$TARGET_SCRIPT"
else
  install -m 0755 "$SRC_DIR/backup-postgres.sh" "$TARGET_SCRIPT"
fi
install -m 0644 "$SRC_DIR/nexus-backup.service" /etc/systemd/system/nexus-backup.service
install -m 0644 "$SRC_DIR/nexus-backup.timer" /etc/systemd/system/nexus-backup.timer

systemctl daemon-reload
systemctl enable --now nexus-backup.timer

echo "--- timer durumu ---"
systemctl status nexus-backup.timer --no-pager | head -6
echo "--- sıradaki çalışma ---"
systemctl list-timers nexus-backup.timer --no-pager
