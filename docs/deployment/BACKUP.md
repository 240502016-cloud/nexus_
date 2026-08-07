# Yedekleme ve geri yükleme

> Kurulum tarihi: 7 Ağustos 2026. Öncesinde **hiç otomatik yedek yoktu** — crontab boş,
> zamanlanmış görev yok, `postgres_backups` volume'u bomboştu.

## Neden bu kurulum

Sağlayıcı (Keyubu) paketinde snapshot yok, yani makine seviyesinde geri dönüş noktası
alınamıyor. Sunucu 4–6 Ağustos arasında üç kez sert sıfırlandı. Hesaplar, mesaj geçmişi ve
ekler geri getirilemez verilerdir. Bu yüzden veritabanı yedeği tek koruma katmanıdır.

## Nasıl çalışır

```text
sunucu                                        geliştirici makinesi
──────                                        ────────────────────
nexus-backup.timer  (günlük 03:30 UTC)
   └─ nexus-backup.service
        └─ scripts/server/backup-postgres.sh
             ├─ pg_dump  nexus    (custom)
             ├─ pg_dump  synapse  (custom)
             ├─ pg_dumpall --globals-only
             ├─ doğrulama: tablo verisi var mı
             ├─ /var/backups/nexus/ altına kopyala
             ├─ sha256 manifesti yaz
             └─ 30 günden eskiyi sil
                                              scripts/pull-server-backups.ps1
                                                 └─ eksikleri indir + sha256 doğrula
                                                    (60 gün sakla)
```

Yedek sunucuda **birincil**, geliştirici makinesinde **ikincil** kopyadır. Çekme yönü
bilinçlidir: Windows makinesinde SSH sunucusu yok, sunucu oraya push edemez; ayrıca makine
her zaman açık değildir.

`Persistent=true` ayarı önemlidir: sunucu kapalıyken kaçan çalışma açılışta telafi edilir.

## ⚠️ Veritabanı adı tuzağı

Postgres container'ında **üç** ilgili değişken vardır:

| Değişken | Değer | Ne işe yarar |
|---|---|---|
| `POSTGRES_DB` | `postgres` | Bootstrap/bakım veritabanı — **uygulama verisi burada değil** |
| `APP_POSTGRES_DB` | `nexus` | Uygulama verisi (kullanıcı, sunucu, kanal, oyun) |
| `SYNAPSE_POSTGRES_DB` | `synapse` | Matrix mesaj geçmişi |

Alışkanlıkla `POSTGRES_DB`'ye uzanmak **sessizce boş bir yedek** üretir; komut başarıyla
biter, dosya oluşur, içinde veri olmaz. 6 Ağustos 2026'da dağıtım öncesi elle alınan ilk
yedekte tam olarak bu oldu ve yalnız içerik kontrol edildiği için fark edildi.

Script bu yüzden dökümü kabul etmeden önce `pg_restore --list` çıktısında en az bir
`TABLE DATA` bloğu arar. Yanlış veritabanı 0 blok verir ve script hata ile durur
(ölçüldü: yanlış 0, doğru 74).

## Komutlar

Durumu görmek:

```bash
systemctl list-timers nexus-backup.timer
journalctl -u nexus-backup.service -n 30
ls -lh /var/backups/nexus/
```

Elle bir yedek almak:

```bash
systemctl start nexus-backup.service
```

Geliştirici makinesine çekmek:

```powershell
.\scripts\pull-server-backups.ps1
```

## Geri yükleme provası

Canlıya dokunmadan, yedeği ayrı bir veritabanına açıp karşılaştırır. 7 Ağustos 2026'da
yapıldı; alembic revizyonu, tablo sayısı ve satır sayıları canlıyla birebir eşleşti.

```bash
cd /opt/nexus
DUMP=$(ls -t /var/backups/nexus/nexus-*.dump | head -1)
docker compose cp "$DUMP" postgres:/tmp/restore-test.dump
docker compose exec -T postgres sh -c '
  psql -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE nexus_restore_prova"
  pg_restore -U "$POSTGRES_USER" -d nexus_restore_prova --no-owner --no-privileges /tmp/restore-test.dump
  psql -U "$POSTGRES_USER" -d nexus_restore_prova -Atc "select count(*) from users"
  psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE nexus_restore_prova"
  rm -f /tmp/restore-test.dump
'
```

## Gerçek felaket kurtarma

Uygulama veritabanını yedekten geri almak (**veri kaybettirir, dikkatli ol**):

```bash
cd /opt/nexus
docker compose stop backend ai-worker media-worker plugin-sandbox
docker compose cp /var/backups/nexus/nexus-<damga>.dump postgres:/tmp/r.dump
docker compose exec -T postgres sh -c '
  dropdb -U "$POSTGRES_USER" --force "$APP_POSTGRES_DB"
  createdb -U "$POSTGRES_USER" "$APP_POSTGRES_DB"
  pg_restore -U "$POSTGRES_USER" -d "$APP_POSTGRES_DB" --no-owner --no-privileges /tmp/r.dump
'
docker compose up -d
```

## Kapsamda olmayanlar

Bu yedek **yalnız PostgreSQL**'i kapsar. Kapsam dışındakiler:

- `avatar_data` ve `attachment_data` volume'ları (yüklenen dosyalar ve profil fotoğrafları)
- `matrix_data` volume'u (Synapse'in medya deposu ve imza anahtarları)
- `/opt/nexus/.env` (Cloudflare tokeni, TURN secret, JWT sırrı)

Bunların da yedeklenmesi ayrı bir iştir. `.env` kaybedilirse Matrix imza anahtarı
uyuşmazlığı ciddi sorun çıkarır; en azından elle güvenli bir yere kopyalanmalıdır.
