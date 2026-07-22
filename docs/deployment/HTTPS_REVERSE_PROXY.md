# TASK-005 — HTTPS, WSS ve domain

Nexus'un internete açık tek giriş noktası Caddy reverse proxy'dir. Frontend, Core API ve Matrix
aynı public domain altında yayınlanır; PostgreSQL, AI Gateway ve Ollama public port açmaz.

```text
https://nexus.example.com/                         -> frontend:8080
https://nexus.example.com/api/*                    -> backend:8000 (/api silinir)
wss://nexus.example.com/api/channels/*/voice       -> backend:8000
https://nexus.example.com/_matrix/*                 -> matrix:8008
https://nexus.example.com/.well-known/matrix/*      -> Caddy discovery yanıtı
```

## 1. Domain ve DNS

Production'a geçmeden önce kalıcı bir domain/subdomain seçin. Aşağıdaki değerler aynı domain
olarak tutulmalıdır:

```dotenv
NEXUS_DOMAIN=nexus.example.com
MATRIX_SERVER_NAME=nexus.example.com
NEXUS_ACME_EMAIL=admin@example.com
NEXUS_HTTP_PORT=80
NEXUS_HTTPS_PORT=443
```

`NEXUS_ACME_EMAIL`, sertifika süresi/hesap sorunları için ulaşılabilir gerçek bir adres olmalıdır.
DNS A kaydı Nexus sunucusunun public IPv4 adresini göstermelidir. IPv6 gerçekten çalışıyorsa AAAA
kaydı eklenebilir; çalışmayan bir AAAA kaydı bırakılmamalıdır.

Matrix `server_name`, kullanıcı ve oda kimliklerinin kalıcı parçasıdır. Production veri üretildikten
sonra domain değişimi basit bir config düzenlemesi değildir; migration gerektirir.

## 2. Router ve firewall

Nexus sunucusuna yalnızca şu public yönlendirmeler gerekir:

| Protokol | Port | Amaç |
|---|---:|---|
| TCP | 80 | ACME doğrulama ve otomatik HTTPS yönlendirmesi |
| TCP | 443 | HTTPS ve WSS |
| UDP | 443 | HTTP/3 (opsiyonel ama Compose'ta hazır) |

Backend `8000`, Matrix `8008`, PostgreSQL `5432`, AI Gateway `8090` ve Ollama `11434` internete
açılmamalıdır. Arkadaş bilgisayarındaki backend, AI bilgisayarındaki gateway'e yalnızca Tailscale
üzerinden ulaşır.

CGNAT arkasındaki bir ev bağlantısında inbound 80/443 yönlendirmesi mümkün olmayabilir. Bu durumda
public HTTPS için VPS/tünel gibi ayrı bir ingress kararı gerekir; Tailscale tek başına public domain
ziyaretçilerine internetten erişim sağlamaz.

## 3. Caddy davranışı

`docker/reverse-proxy/Caddyfile` şunları uygular:

- Domain için public sertifikayı otomatik alır, yeniler ve HTTP isteklerini HTTPS'e yönlendirir.
- TLS sürümünü 1.2–1.3 aralığında tutar ve HSTS/güvenlik header'ları ekler.
- `/api/*` isteklerindeki `/api` önekini silerek Core API'ye gönderir.
- WebSocket Upgrade isteğini aynı reverse proxy tünelinden geçirir; frontend HTTPS sayfasında
  otomatik olarak `wss://` kullanır.
- Matrix client/federation endpoint'lerini ve `.well-known` discovery yanıtlarını yayınlar.
- `/_synapse/admin/*` yolunu internete açmaz.

Caddy sertifika ve ACME hesabı verisi `caddy_data` volume'unda kalıcıdır. Bu volume'u rastgele
silmeyin; silinmesi gereksiz sertifika yeniden üretimine ve CA rate limitlerine yol açabilir.

## 4. Başlatma

Gerçek değerler `.env` içine eklendikten ve DNS yayıldıktan sonra:

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose logs -f --tail 200 reverse-proxy
```

İlk sertifika alımı sırasında Caddy loglarında ACME sonucunu kontrol edin. Sertifika hazır olmadan
HTTPS/WSS dış doğrulamasına geçmeyin.

## 5. Dışarıdan doğrulama

DNS ve port erişimini sunucunun kendi LAN'ından değil, mümkünse başka bir internet bağlantısından
test edin:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-production-https.ps1 `
  -Domain nexus.example.com
```

Script DNS, HTTP→HTTPS, TLS, proxy health, Core API, Matrix ve discovery endpoint'lerini kontrol
eder. Gerçek bir WSS bağlantısını da doğrulamak için Nexus JWT'si ve erişilebilir ses kanalı ID'si
ortam değişkeni olarak verilebilir:

```powershell
$env:NEXUS_JWT = '<kısa-ömürlü-token>'
$env:NEXUS_VOICE_CHANNEL_ID = '1'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-production-https.ps1 `
  -Domain nexus.example.com
Remove-Item Env:NEXUS_JWT, Env:NEXUS_VOICE_CHANNEL_ID
```

Token'ı komut satırı argümanı olarak yazmak shell history/process listesinde görünmesine neden
olabilir; ortam değişkeni tercih edilmelidir. WSS testi yapılmazsa script bunu açıkça `SKIP` olarak
raporlar, başarılı sayılmış gibi göstermez.

## TURN / WebRTC relay

TURN trafiği Caddy üzerinden proxy edilmez. Coturn, `TURN_DOMAIN` üzerinde `3478/tcp+udp`
ve `TURN_MIN_PORT`–`TURN_MAX_PORT` relay aralığını doğrudan yayınlar. `TURN_EXTERNAL_IP`
sunucunun public IP'si olmalı; DNS ve firewall/NAT bu portları aynı hosta yönlendirmelidir.
Core API `/api/voice/ice-servers` üzerinden coturn REST formatında kısa ömürlü credential üretir.

### Yerel LAN testi (192.168.1.174)

`192.168.1.174` private bir LAN adresidir; aynı ağdaki cihazların testinde kullanılabilir, ancak
internet üzerinden erişilebilir public IP yerine geçmez. LAN-only test için `.env` değerleri şöyle
olabilir:

```dotenv
NEXUS_DOMAIN=192.168.1.174
TURN_DOMAIN=192.168.1.174
TURN_EXTERNAL_IP=192.168.1.174
```

Frontend geliştirme sunucusu `0.0.0.0:5173` üzerinde dinler; LAN cihazından
`http://192.168.1.174:5173` açılabilir. Windows firewall'da 5173 ve TURN portlarına izin verin.
Private IP için public ACME sertifikası üretilemeyeceğinden bu LAN senaryosunda Caddy HTTPS'i
beklemeyin; HTTPS/WSS production testinde public DNS adı kullanın.

Public deployment'ta `NEXUS_DOMAIN`/`TURN_DOMAIN` gerçek DNS adı olmalı ve `TURN_EXTERNAL_IP`
router/VPS'nin public IP'sine ayarlanmalıdır. Router arkasındaysa aşağıdaki portları
`192.168.1.174` adresine forward edin:

- `3478/tcp` ve `3478/udp` (TURN signaling)
- `49160-49200/tcp` ve `49160-49200/udp` (TURN relay)

## 6. Değişiklik ve sorun giderme

Caddyfile değişikliğinden önce sözdizimini çalışan container içinde doğrulayın:

```powershell
docker compose exec reverse-proxy caddy validate --config /etc/caddy/Caddyfile
docker compose exec reverse-proxy caddy reload --config /etc/caddy/Caddyfile
```

Sık görülen sorunlar:

- Sertifika alınamıyor: DNS yanlış, TCP 80/443 kapalı, CGNAT var veya CA rate limitine girilmiş.
- Tarayıcı mixed-content hatası: frontend dışındaki bir kod hâlâ `http://`/`ws://` URL üretiyor.
- WSS 401/403: TLS/proxy çalışıyor olabilir; JWT geçersiz ya da kullanıcı ses kanalına yetkili değil.
- WSS 502: reverse proxy backend container'ına ulaşamıyor veya backend sağlıksız.
- Matrix discovery yanlış: `NEXUS_DOMAIN` ile `MATRIX_SERVER_NAME` farklı girilmiş.
