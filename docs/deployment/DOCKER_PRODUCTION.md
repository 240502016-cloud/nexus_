# TASK-004 — Production Docker düzeni

Production Compose beş ana servis ve üç yardımcı servisten (migration + AI worker + plugin sandbox) oluşur:

```text
Internet
   │ 80/443 TCP, 443 UDP (HTTP/3)
   ▼
reverse-proxy (Caddy, otomatik HTTPS)
   ├── /                 -> frontend:8080
   ├── /api/*            -> backend:8000 (prefix silinir, WebSocket dahil)
   └── /_matrix/*        -> matrix:8008

backend ────── postgres/nexus
   │   └────── matrix (internal HTTP)
   └────────── AI Gateway (Tailscale:8090)

matrix ─────── postgres/synapse

migrate ────── postgres/nexus (tek-seferlik Alembic)
ai-worker ──── postgres/nexus + AI Gateway + Matrix
plugin-sandbox ── yalnızca internal sandbox ağı (Core API çağrıları için)
```

Frontend, backend, Matrix ve PostgreSQL host portu yayınlamaz. Dış dünyaya açık tek servis
`reverse-proxy`dir. `/_synapse/admin/*` proxy edilmez; Core API Matrix admin kayıt işlemlerini
Docker ağı üzerinden yapar.

## 1. Önemli veri/migration uyarısı

Bu düzen eski geliştirme kurulumunun yerinde güncellemesi değildir:

- Eski `matrix/synapse/homeserver.db` SQLite verisi otomatik olarak PostgreSQL'e taşınmaz.
- Yeni Matrix servisi `matrix_data` volume'u ve ayrı `synapse` PostgreSQL veritabanı kullanır.
- Compose proje adı artık `nexus` olduğu için volume adları `nexus_*` olur.
- PostgreSQL init scripti yalnızca boş `postgres_data` volume'unun ilk açılışında çalışır.
- Matrix `server_name` ilk üretimden sonra değiştirilemez; kullanıcı kimliklerinin domain
  parçasıdır.

Mevcut kullanıcı/oda/mesaj verisi korunacaksa önce eski PostgreSQL ve `matrix/synapse/`
dizininin yedeğini alın, ardından ayrı bir migration planı uygulayın. Bu doğrulanmadan eski
volume veya dosyaları silmeyin.

## 2. Production ortam değişkenleri

Var olan `.env` dosyasını ezmeyin. Yeni kurulumda `.env.example` kopyalanabilir; mevcut
kurulumda yeni alanları elle birleştirin.

En az şu placeholder değerleri gerçek ve birbirinden farklı rastgele secret'larla değiştirin:

```dotenv
POSTGRES_ADMIN_PASSWORD=...
POSTGRES_PASSWORD=...
SYNAPSE_POSTGRES_PASSWORD=...
CORE_API_SECRET_KEY=...
MATRIX_REGISTRATION_SHARED_SECRET=...
MATRIX_MACAROON_SECRET_KEY=...
MATRIX_FORM_SECRET=...
OLLAMA_API_KEY=...
```

Rastgele değer üretme örneği:

```powershell
py -c "import secrets; print(secrets.token_urlsafe(48))"
```

Domain ayarları:

```dotenv
NEXUS_DOMAIN=nexus.example.com
NEXUS_ACME_EMAIL=admin@example.com
MATRIX_SERVER_NAME=nexus.example.com
NEXUS_HTTP_PORT=80
NEXUS_HTTPS_PORT=443
```

`NEXUS_DOMAIN` için DNS A/AAAA kaydı arkadaş bilgisayarının public adresini göstermelidir.
Caddy'nin public TLS sertifikası alabilmesi için TCP 80 ve 443 erişilebilir olmalıdır. HTTP/3
için UDP 443 de açılır. AI Gateway `8090` ve Ollama `11434` internete açılmaz; onlar TASK-002
Tailscale bağlantısında kalır.

HTTPS, WSS, Matrix discovery ve internet üzerinden doğrulama ayrıntıları için
[HTTPS_REVERSE_PROXY.md](./HTTPS_REVERSE_PROXY.md) dosyasına bakın.

## 3. Yapılandırmayı doğrulama

Secret değerlerini ekledikten sonra:

```powershell
docker compose config --quiet
```

Bu komut eksik zorunlu değişkenleri ve Compose sözdizimini container başlatmadan kontrol eder.
Çözülmüş config çıktısını paylaşmayın; secret değerleri içerebilir.

## 4. Image build ve ilk başlatma

```powershell
docker compose build --pull
docker compose up -d
docker compose ps
```

`migrate` servisi backend image'ı içindeki Alembic migration'larını PostgreSQL sağlıklı olduktan
sonra çalıştırır. Database backup/restore prosedürü için
[DATABASE_SECURITY.md](./DATABASE_SECURITY.md) dosyasına bakın.

Başlatma sırası healthcheck'lerle kontrol edilir:

1. PostgreSQL hazır olur ve ilk açılışta `nexus`/`synapse` kullanıcı-veritabanlarını oluşturur.
2. Alembic `migrate` servisi Nexus uygulama şemasını uygular.
3. Matrix config/signing key üretir; backend migration tamamlandıktan sonra Matrix'e bağlanır.
4. `ai-worker` servisi kuyruğa alınan AI üretimlerini API process'inden ayrı işler.
4. Frontend build'i Nginx üzerinde açılır.
5. Hepsi sağlıklı olunca reverse proxy devreye girer.

Loglar:

```powershell
docker compose logs -f --tail 200 postgres migrate plugin-sandbox matrix backend frontend reverse-proxy
```

## 5. Health kontrolleri

```text
https://<NEXUS_DOMAIN>/healthz                  reverse proxy
https://<NEXUS_DOMAIN>/api/health              Core API
https://<NEXUS_DOMAIN>/_matrix/client/versions Matrix
```

AI health kullanıcı JWT'si gerektirir:

```text
GET https://<NEXUS_DOMAIN>/api/ai/health
Authorization: Bearer <NEXUS_JWT>
```

## 6. Ağ ve güvenlik özellikleri

- `data` ağı `internal: true`; PostgreSQL yalnızca backend ve Matrix tarafından görülür.
- Backend, Matrix ve frontend için host `ports` tanımı yoktur.
- Backend tek worker çalışır; voice manager, plugin registry ve rate limitler process belleğindedir.
- Backend filesystem'i read-only, yalnızca `/tmp` tmpfs olarak yazılabilirdir.
- Caddy aynı origin altında frontend, REST, WebSocket ve Matrix yönlendirmesi yapar.
- Caddy sertifika verisini `caddy_data` volume'unda saklar.
- Matrix genel kullanıcı kaydı kapalıdır; kayıt yalnızca Core API shared-secret akışından yapılır.

## 7. Operasyon notları

- `.env` veya image değişince: `docker compose up -d --build`.
- Sadece proxy config değişince: `docker compose restart reverse-proxy`.
- Veritabanı şifrelerini `.env` içinde sonradan değiştirmek PostgreSQL rollerini otomatik
  değiştirmez; kontrollü SQL migration gerekir.
- PostgreSQL ve `matrix_data` için düzenli, geri yüklemesi test edilmiş yedek alınmalıdır.
- Synapse image sürümünü yükseltmeden önce release notları ve PostgreSQL uyumluluğu okunmalıdır.
- Docker hostunun Tailscale `100.64.0.0/10` rotasına container içinden erişebildiği ayrıca
  doğrulanmalıdır; aksi halde backend AI Gateway'e ulaşamaz.
