#!/usr/bin/env bash
#
# Nexus — günlük PostgreSQL yedeği (Linux VDS).
#
# scripts/backup-postgres.ps1 Windows/Docker Desktop kurulumu için yazılmıştır ve
# sunucuda çalışmaz. Bu script aynı işi sunucuda yapar ve systemd timer'ından çağrılır.
#
# ⚠️ Veritabanı adları: container içinde POSTGRES_DB=postgres'tir ve bu **bootstrap
# veritabanıdır**, uygulamanın verisi orada değildir. Uygulama verisi APP_POSTGRES_DB
# (nexus), Synapse verisi SYNAPSE_POSTGRES_DB (synapse) içindedir. POSTGRES_DB'ye
# uzanmak sessizce boş bir yedek üretir — 6 Ağustos 2026'da tam olarak bu yaşandı.
#
# Kullanım:  backup-postgres.sh [saklama_günü]
set -euo pipefail

PROJECT_DIR="${NEXUS_PROJECT_DIR:-/opt/nexus}"
DEST_DIR="${NEXUS_BACKUP_DIR:-/var/backups/nexus}"
RETENTION_DAYS="${1:-${NEXUS_BACKUP_RETENTION_DAYS:-30}}"

cd "$PROJECT_DIR"
mkdir -p "$DEST_DIR"
chmod 700 "$DEST_DIR"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
APP_FILE="nexus-$STAMP.dump"
SYNAPSE_FILE="synapse-$STAMP.dump"
GLOBALS_FILE="globals-$STAMP.sql.gz"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

in_postgres() { docker compose exec -T postgres sh -c "$1"; }

log "yedek başlıyor (saklama: ${RETENTION_DAYS} gün, hedef: ${DEST_DIR})"

# Şifreler komut satırına yazılmaz; kimlik doğrulama container içindeki local socket üzerinden.
in_postgres "pg_dump --format=custom --username=\"\$POSTGRES_USER\" --dbname=\"\$APP_POSTGRES_DB\" --file=/backups/$APP_FILE"
in_postgres "pg_dump --format=custom --username=\"\$POSTGRES_USER\" --dbname=\"\$SYNAPSE_POSTGRES_DB\" --file=/backups/$SYNAPSE_FILE"
in_postgres "pg_dumpall --globals-only --username=\"\$POSTGRES_USER\" | gzip > /backups/$GLOBALS_FILE"

# Boş yedek sessizce başarılı görünür. Uygulama dökümünde gerçekten tablo verisi olduğunu
# doğrula, yoksa yedeği kabul etme.
TABLE_DATA_COUNT="$(in_postgres "pg_restore --list /backups/$APP_FILE | grep -c 'TABLE DATA'" | tr -d '[:space:]')"
if [ "${TABLE_DATA_COUNT:-0}" -lt 1 ]; then
  log "HATA: $APP_FILE içinde tablo verisi yok (doğru veritabanı yedeklendi mi?)"
  exit 1
fi
log "doğrulama tamam: uygulama dökümünde $TABLE_DATA_COUNT tablo verisi bloğu var"

for f in "$APP_FILE" "$SYNAPSE_FILE" "$GLOBALS_FILE"; do
  docker compose cp "postgres:/backups/$f" "$DEST_DIR/$f" >/dev/null
  if [ ! -s "$DEST_DIR/$f" ]; then
    log "HATA: $f host'a kopyalanamadı veya boş"
    exit 1
  fi
  # Volume'da biriktirmeye gerek yok; kalıcı kopya host dizininde tutulur.
  in_postgres "rm -f /backups/$f"
done

( cd "$DEST_DIR" && sha256sum "$APP_FILE" "$SYNAPSE_FILE" "$GLOBALS_FILE" > "manifest-$STAMP.sha256" )
chmod 600 "$DEST_DIR"/*"$STAMP"* 2>/dev/null || true

log "yedek tamam: $(cd "$DEST_DIR" && du -ch "$APP_FILE" "$SYNAPSE_FILE" "$GLOBALS_FILE" | tail -1 | cut -f1)"

# Saklama süresi dolanları temizle. Yalnız bu script'in ürettiği desenler silinir.
DELETED="$(find "$DEST_DIR" -maxdepth 1 -type f \
  \( -name 'nexus-*.dump' -o -name 'synapse-*.dump' -o -name 'globals-*.sql.gz' -o -name 'manifest-*.sha256' \) \
  -mtime "+$RETENTION_DAYS" -print -delete | wc -l)"
log "eski dosya temizliği: $DELETED dosya silindi"

log "toplam yedek alanı: $(du -sh "$DEST_DIR" | cut -f1), kalan disk: $(df -h "$DEST_DIR" | tail -1 | awk '{print $4}')"
