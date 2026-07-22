# TASK-006 — PostgreSQL güvenliği, backup ve migration

Production Compose'ta PostgreSQL'in host `ports` tanımı yoktur. PostgreSQL yalnızca `data`
adlı `internal: true` Docker ağı üzerinde `backend` ve `matrix` servislerine açıktır. Dışarıdan
`5432` bağlantısı beklenmez ve firewall'da da açılmamalıdır.

## Migration akışı

`postgres-bootstrap` servisi PostgreSQL sağlıklı olduktan sonra idempotent init scriptini her
stack başlangıcında çalıştırır. Bu servis, kalıcı volume daha eski bir Compose sürümüyle
oluşturulmuş olsa bile eksik `nexus`/`synapse` rollerini ve veritabanlarını veri silmeden oluşturur,
parolaları `.env` ile eşitler ve veritabanı sahipliğini düzeltir. `migrate` ve `matrix`, bootstrap
başarıyla tamamlanmadan başlamaz.

Bootstrap yalnızca `postgres` ve `postgres-bootstrap` container'larının bağladığı yerel PostgreSQL
socket volume'ünü kullanır; PostgreSQL portu host'a açılmaz. Eski volume'de admin adı değişmişse
mevcut erişilebilir superuser (`POSTGRES_ADMIN_USER`, eski `POSTGRES_USER` veya `postgres`) yerel
bağlantı üzerinden tespit edilir.

Eski kurulumlarda PostgreSQL superuser'ı `POSTGRES_USER` ile oluşturulduğu için
`POSTGRES_ADMIN_USER` ve `POSTGRES_ADMIN_PASSWORD` tanımlı değilse Compose geriye dönük olarak
uygulama kullanıcısını kullanır. Yeni kurulumlarda `.env.example` dosyasındaki gibi ayrı ve güçlü
admin bilgileri tanımlanmalıdır. Var olan bir volume'de admin adı sonradan yalnızca `.env`
değiştirilerek değiştirilemez; değer volume ilk oluşturulurken kullanılan superuser ile aynı
olmalıdır.

Backend şeması artık uygulama startup'ında `create_all` ile sessizce değiştirilmez. `migrate`
servisi aynı backend image'ından çalışır ve PostgreSQL sağlıklı olduktan sonra:

```text
alembic upgrade head
```

komutunu bir kez çalıştırır. `backend` servisi, migration servisi başarıyla tamamlanmadan
başlamaz. İlk revision (`0001_initial_schema`) mevcut `create_all` kurulumlarıyla uyumludur:
tabloları zaten varsa korur, yoksa oluşturur ve `alembic_version` kaydını ekler. Bu revision
yalnızca Nexus `nexus` veritabanındaki uygulama tablolarını yönetir; Synapse şeması Alembic'e
dahil değildir.

İlk production geçişinden önce:

```powershell
docker compose build backend
docker compose up -d postgres
docker compose run --rm postgres-bootstrap
docker compose run --rm migrate
docker compose ps
```

Eski bir volume'de `role does not exist`, `database does not exist` veya Synapse parola hatası
görülürse volume'ü silmeden şu onarım akışını çalıştırın:

```powershell
docker compose up -d postgres
docker compose run --rm postgres-bootstrap
docker compose run --rm migrate
docker compose up -d
docker compose ps
```

`postgres-bootstrap` kimlik doğrulama hatası verirse `.env` içindeki `POSTGRES_ADMIN_USER` ve
`POSTGRES_ADMIN_PASSWORD`, volume ilk oluşturulurken kullanılan PostgreSQL superuser bilgileriyle
eşleştirilmelidir. Eski Nexus kurulumlarında bunlar çoğunlukla `POSTGRES_USER` ve
`POSTGRES_PASSWORD` değerleridir. `docker compose down -v` veri siler ve bu onarımın bir parçası
değildir.

Sonraki şema değişiklikleri için yeni, küçük ve geri alınabilir Alembic revision'ları ekleyin.
`0001_initial_schema` dosyasını değiştirmeyin. `alembic downgrade` veri kaybına yol açabileceği
için yalnızca doğrulanmış bir backup ve bakım penceresiyle çalıştırılmalıdır.

## PostgreSQL backup

`postgres_backups` adlı ayrı Docker volume'u database data volume'undan ayrıdır. Backup scripti
dump'ı önce bu iç volume'a üretir, sonra host üzerindeki `backups/postgres` klasörüne kopyalar:

```powershell
docker compose up -d postgres
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\backup-postgres.ps1
```

Her backup şunları içerir:

- Nexus uygulama veritabanı: `nexus-<timestamp>.dump`
- Synapse veritabanı: `synapse-<timestamp>.dump`
- PostgreSQL roller/şifre hash'leri ve global yetkiler: `globals-<timestamp>.sql`
- Dosya boyutu ve SHA-256 değerleri: `manifest-<timestamp>.json`

14 günden eski dosyaları isteğe bağlı temizlemek için:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\backup-postgres.ps1 `
  -RetentionDays 14 -Prune
```

Backup klasörü `.gitignore` içindedir; yine de üretim ortamında bu klasörü şifreli ve ayrı bir
diskte/off-site saklayın. `globals` dosyası rol password hash'leri içerir. Backup'ı yalnızca
PostgreSQL yöneticisi ve yetkili operasyon hesabı okuyabilmelidir. En az bir backup'ın başka bir
makinede geri yüklenmesi periyodik olarak denenmelidir.

PostgreSQL dump'ları Matrix'in `matrix_data` volume'undaki signing key, `homeserver.yaml` ve medya
dosyalarını içermez. Bu volume ayrıca snapshot/tar ile yedeklenmelidir; yalnızca database dump'ı
ile Matrix kurulumu eksik kalır.

Örnek Docker volume yedeği (Compose proje adı `nexus` ise):

```powershell
New-Item -ItemType Directory -Force .\backups\matrix | Out-Null
docker run --rm `
  -v nexus_matrix_data:/data:ro `
  -v "${PWD}\backups\matrix:/backup" `
  alpine:3.20 tar -czf /backup/matrix-data-$(Get-Date -Format yyyyMMdd-HHmmss).tar.gz -C /data .
```

## Restore

Restore yıkıcıdır; script varsayılan olarak açık onay ister ve SHA-256 manifestini doğrulamadan
servisleri durdurmaz:

```powershell
docker compose up -d postgres
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\restore-postgres.ps1 `
  -BackupDirectory .\backups\postgres `
  -ConfirmRestore
```

Script backend, Matrix ve reverse proxy'yi durdurur; global rolleri, Nexus dump'ını ve Synapse
dump'ını geri yükler. Servisleri başarıyla restore sonrasında otomatik başlatmak için ayrıca
`-StartServices` verilebilir. Aynı cluster'da mevcut roller için `CREATE ROLE` hataları beklenir;
dump'ın devamındaki `ALTER ROLE` ifadeleri yine uygulanır.

Restore sonrasında kontrol:

```powershell
docker compose up -d matrix backend reverse-proxy
docker compose logs --tail 200 migrate backend matrix
```

`postgres_data`, `postgres_backups` veya `matrix_data` volume'larını silmek backup/restore
işleminin parçası değildir; veri migration doğrulanmadan bu volume'lara `down -v` uygulamayın.

## Eski Synapse veritabanında locale/collation onarımı

Synapse `Database has incorrect collation ... Should be 'C'` hatası verirse mevcut database eski
bir PostgreSQL kurulumu tarafından `en_US.utf8` gibi desteklenmeyen bir locale ile oluşturulmuştur.
`allow_unsafe_locale` kontrolünü kapatmayın. Aşağıdaki script önce custom-format dump alır ve hosta
kopyalar, eski database'i geri dönüş için yeniden adlandırır, aynı adla UTF8 + `C/C` database
oluşturur ve dump'ı geri yükler:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\repair-synapse-collation.ps1 `
  -ConfirmRepair -StartServices
```

Dump `backups/postgres-locale-repair` altında, eski database ise PostgreSQL içinde
`synapse_locale_backup_<timestamp>` adıyla korunur. Yeni Matrix kurulumu ve uygulama verileri
doğrulanmadan bu geri dönüş kopyalarını silmeyin.

## Güvenlik kontrol listesi

- `docker compose config` çıktısında `postgres` altında `ports:` bulunmadığını doğrulayın.
- TCP/UDP 5432'yi router ve host firewall'da kapalı tutun.
- Uygulama bağlantısı `postgres:5432`, Synapse bağlantısı aynı internal ağ üzerinden yapılır.
- `POSTGRES_ADMIN_PASSWORD`, uygulama ve Synapse parola değerlerini birbirinden farklı tutun.
- `.env`, dump ve globals dosyalarını loglara, issue'lara veya chat'e koymayın.
- Backup alımını ve restore denemesini izleyip başarısız job'larda alarm üretin.
