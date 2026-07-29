# Nexus Communication Platform — Kapsamlı Devir Özeti ve Ana Devir Belgesi

> Bu belge, yeni bir Codex/LLM sohbetine tek başına verilebilecek ana devir promptudur.
> Yeni sohbet önce bu dosyanın tamamını okumalı, ardından doğrudan güncel kaynak kodunu
> incelemelidir. Eski `yol haritası.md`, `ROADMAP.md` ve bazı mimari belgeler tarihsel bilgi
> içerebilir; güncel gerçeklik için öncelik sırası **kaynak kod → bu dosya → güncel deployment
> belgeleri → eski yol haritaları** olmalıdır.

Son güncelleme: **29 Temmuz 2026**

---

## 0. Yeni sohbete verilecek temel talimat

Bu repo üzerinde çalışmaya devam ederken:

1. Önce `DEVIR-OZETI.md` dosyasının tamamını oku.
2. Sonra `git status`, aktif branch, son commit ve ilgili kaynak dosyalarını doğrula.
3. Kullanıcının yeni isteğini mevcut mimariye uydur; çalışan özellikleri yeniden yazma.
4. İlgisiz kullanıcı değişikliklerini silme veya geri alma.
5. `.env`, API anahtarı, Cloudflare tokeni, parola, JWT sırrı ve veritabanı yedeği gibi
   gizli verileri ekrana veya Git'e çıkarma.
6. Kullanıcı özellikle istemedikçe ücretli servis ekleme. Projenin ana ilkesi:
   **kullanıcı da proje sahipleri de zorunlu abonelik veya kullanım ücreti ödemeyecek**.
7. Veritabanı volume'larını silen `docker compose down -v` komutunu çalıştırma veya önerme.
8. Mevcut Matrix kurulumunda `MATRIX_SERVER_NAME` değerini değiştirme; bu değer Matrix
   kullanıcı kimliklerini ve tokenlarını etkiler.
9. Kod değişikliğinden sonra en azından ilgili testleri, frontend TypeScript kontrolünü ve
   production build'i çalıştır.
10. Sunucu tarafındaki işlemlerde kişileri rolleriyle karıştırma:
    - **Mert:** ana Nexus sunucusunun sahibi ve operatörü.
    - **Furkan:** dışarıdan bağlanan misafir/test kullanıcısı.
    - **Mahfl / bu bilgisayarın sahibi:** AI/Ollama/AI Gateway makinesinin sahibi ve ana geliştirici.

---

## 1. Projenin amacı

Nexus; Discord benzeri sunucu, kanal, arkadaşlık, özel mesaj, sesli görüşme, kamera,
ekran paylaşımı, bot ve plugin özellikleri sunan; fakat Discord'un birebir kopyası olmayı
hedeflemeyen özel bir iletişim platformudur.

Temel tasarım kararları:

- Platforma özgü kullanıcı, arkadaşlık, sunucu, rol, kanal, davet, bot ve plugin verileri
  kendi FastAPI/PostgreSQL katmanında tutulur.
- Kalıcı metin mesajları ve birebir konuşma odaları Matrix Synapse üzerinden yürütülür.
- Ses, kamera ve ekran paylaşımı Matrix grup çağrı protokolü yerine özel WebSocket signaling
  ve WebRTC mesh ile çalışır.
- AI üretimi ücretli dış API yerine kullanıcının kendi bilgisayarındaki Ollama üzerinden yapılır.
- Web ve Windows masaüstü istemcisi aynı React özellik ağacını paylaşır.
- Dış erişim Hamachi gerektirmeden Cloudflare Tunnel ile sağlanacak şekilde tasarlanmıştır.

---

## 2. İnsanlar, makineler ve sorumluluklar

### Mert — sunucu sahibi

- Ana production Docker stack'i Mert'in bilgisayarında çalışır.
- Beklenen proje yolu:

```text
C:\Users\merte\Github\nexus-server
```

- PostgreSQL, Matrix, backend, frontend, Caddy, coturn, worker, plugin sandbox ve
  Cloudflare Tunnel connector'ı bu bilgisayarda çalışır.
- DNS, Cloudflare Tunnel Public Hostname, connector/replica ve production container
  sorunlarını Mert çözer.
- Rutin güncellemede repo kökündeki `Arkadas-Sunucuyu-Guncelle.cmd` dosyasını çalıştırır.

### Furkan — dış kullanıcı

- Furkan sunucu kurmaz, DNS değiştirmez, sertifika yüklemez ve Hamachi kullanmaz.
- Sistem düzgün çalıştığında yalnızca şu adresi açması gerekir:

```text
https://cekin.gen.tr
```

- Furkan'ın gördüğü sertifika, 502 veya erişim hataları istemci tarafında tarayıcı güvenliğini
  azaltarak çözülmemelidir; Mert'in sunucu/tünel tarafında düzeltilmelidir.

### AI bilgisayarı — bu çalışma alanının sahibi

- Ollama ve AI Gateway bu bilgisayarda çalışır.
- Ana sunucu AI üretimi için bu makinedeki Gateway'e bağlanır.
- Gerekli çalışma sırası:
  1. Ollama'yı başlat.
  2. `Nexus-Server-Manager.cmd` aç.
  3. **AI Gateway → Start AI Gateway** seç.
  4. Gateway penceresini açık bırak.
- AI bilgisayarı kapalı olsa bile Mert'in rutin Nexus güncellemesi ana uygulamayı
  durdurmamalıdır; yalnız AI cevapları geçici olarak çevrimdışı kalır.
- Açık bir `Validate` veya ilk kurulum işlemi AI Gateway adresi ve anahtarını zorunlu olarak
  doğrulamaya devam eder.

---

## 3. Git ve çalışma alanı durumu

### Yerel geliştirme yolu

```text
C:\Users\mahfl\source\repos\nexus-communication-platform
```

### Remote

```text
origin  https://github.com/240502016-cloud/nexus_.git
```

### Aktif branch

```text
cekingen
```

### Bu devir hazırlanırken doğrulanan HEAD

```text
72a1ff11de48d5eab67dfa3df5de1579961a867d
72a1ff1 fix auth retries and WebRTC negotiation
```

Bu özet dosyasının yenilenmesi doğal olarak çalışma ağacında yeni bir değişiklik oluşturur.
Koda devam etmeden önce yeniden `git status --short --branch` çalıştırılmalıdır.

### Yakın dönem önemli commitler

```text
72a1ff1 fix auth retries and WebRTC negotiation
5057922 Retry public checks during transient tunnel errors
52ad32e Add desktop client and resilient server joining
0391cf1 Redesign screen share stage without cropping
01d873c Fix secure voice access and add server invitations
df76733 Add free public Cloudflare tunnel access
e023498 Start Docker automatically during server updates
390caec Show only the focused media tile
830ca79 Allow updates while AI gateway is offline
cc2fd5b Add media focus and harden voice reconnects
290954c Polish media framing and bot settings
49eb2d0 Add rich messaging and dynamic voice stage
b11d7c5 Add social hub and repair realtime messaging
495817c Improve new message navigation
55462da Add adaptive media and persistent chat history
```

### Mert'in güncel kodu çekmesi

Önerilen ve güvenli yol:

```text
Arkadas-Sunucuyu-Guncelle.cmd
```

Bu script:

- `cekingen` branch'ini hedefler.
- Yerel tracked/untracked değişiklikleri zaman damgalı Git stash ile korur.
- `origin/cekingen` branch'ini fetch eder.
- Yalnız fast-forward güncelleme yapar.
- Docker Desktop kapalıysa otomatik başlatır ve hazır olmasını bekler.
- Image'ları build eder.
- PostgreSQL bootstrap kontrolünü yapar.
- Alembic migration'larını çalıştırır.
- Stack'i ve varsa `public-tunnel` profilini başlatır.
- Dış health kontrollerini gerçekleştirir.
- AI Gateway kapalıysa rutin güncellemeyi kesmez; uyarı verir.
- Otomatik stash'i kendiliğinden geri uygulamaz. Gerekirse daha sonra
  `git stash list` ve kontrollü `git stash apply` kullanılır.

Elle yalnız kod çekmek gerekirse:

```powershell
cd C:\Users\merte\Github\nexus-server
git fetch origin cekingen
git switch cekingen
git merge --ff-only origin/cekingen
```

Yerel değişiklik varsa doğrudan pull/merge yapılmamalı; önce `git status` incelenmelidir.

---

## 4. Teknoloji yığını

### Web frontend

- React `18.3`
- TypeScript `5.6`
- Vite `5.4`
- React DOM
- Düz CSS ve CSS custom property tabanlı tema sistemi
- React hook'ları ve localStorage tabanlı istemci durumu
- Redux veya başka global state framework'ü yok

### Backend

- Python
- FastAPI `0.115+`
- Uvicorn
- SQLAlchemy `2.x`
- Pydantic `2.x`
- Alembic
- PostgreSQL sürücüsü: `psycopg2-binary`
- JWT: `PyJWT`
- Form/dosya yükleme: `python-multipart`
- Harici HTTP: `requests`
- Python WebRTC/müzik botu: `aiortc`

### Veritabanı ve mesajlaşma

- PostgreSQL `16.14-alpine`
- Matrix Synapse `1.153.0`
- Matrix uygulama mesajlarının kalıcı iletişim motorudur.
- Nexus'a özgü modeller PostgreSQL'deki Core şemasındadır.
- Synapse aynı PostgreSQL container'ında ayrı kullanıcı ve ayrı veritabanı kullanır.

### Gerçek zamanlı iletişim

- Global WebSocket: `/api/gateway`
- Ses signaling WebSocket'i: `/api/channels/{id}/voice`
- WebRTC mesh topoloji
- `RTCPeerConnection`, `getUserMedia`, `getDisplayMedia`
- STUN: Cloudflare ve Google yedekleri
- TURN: kendi coturn `4.6.3` servisi
- Web Audio API ile konuşma seviyesi algılama

### AI

- Ayrı Python/FastAPI AI Gateway
- Uzak/yerel Ollama
- `httpx`
- Bearer API key ve CIDR/güvenilir proxy kontrolü
- PostgreSQL kalıcı AI job kuyruğu
- Ayrı `ai-worker` process'i
- SSE streaming ve cooperative iptal

### Windows masaüstü istemcisi

- Electron `43`
- Electron Builder
- NSIS installer
- `electron-updater`
- Global giriş için `uiohook-napi`
- Electron `safeStorage` / Windows DPAPI

### Altyapı

- Docker ve Docker Compose
- Caddy `2.11.4`, Cloudflare DNS eklentili özel image
- Cloudflare Tunnel / `cloudflared 2026.5.2`
- Windows PowerShell ve `.cmd` yönetim araçları

---

## 5. Monorepo klasör yapısı

```text
nexus-communication-platform/
├── frontend/
│   ├── src/
│   │   ├── api/                 REST istemcisi ve retry davranışı
│   │   ├── components/          UI bileşenleri
│   │   ├── hooks/               Gateway, WebRTC, PTT, medya cihazları
│   │   ├── App.tsx              Ana uygulama orkestrasyonu
│   │   ├── App.css              Ana düzen ve bileşen stilleri
│   │   ├── index.css            Global tema ve reset
│   │   ├── settings.ts          Kalıcı kullanıcı ayarları
│   │   ├── notifications.ts     Tarayıcı/masaüstü bildirimleri
│   │   ├── messageContent.ts    Mesaj içerik işleme
│   │   ├── desktopBridge.ts     Web/Electron soyutlama katmanı
│   │   └── types.ts             İstemci veri tipleri
│   ├── Dockerfile
│   └── package.json
│
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   ├── routers/         REST ve WebSocket endpoint'leri
│   │   │   ├── models.py        Core SQLAlchemy modelleri
│   │   │   ├── schemas.py       Pydantic sözleşmeleri
│   │   │   ├── auth.py          JWT ve parola işlemleri
│   │   │   ├── authz.py         Üyelik/sahiplik yetkilendirmesi
│   │   │   ├── permissions.py   İzin altyapısı
│   │   │   ├── matrix_client.py Synapse istemcisi
│   │   │   └── matrix_rooms.py  Oda üyeliği/onarımı
│   │   ├── bot_engine/          Mesaj komut dispatcher'ı
│   │   ├── plugins_engine/      Plugin manifest/yükleme/sandbox
│   │   ├── plugins_sandbox/     İzole plugin çalıştırma servisi
│   │   ├── services/ollama/     AI client, worker, job ve token mantığı
│   │   ├── services/chance_games.py
│   │   ├── database.py
│   │   └── main.py
│   ├── alembic/
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
│
├── ai-gateway/
│   ├── gateway/
│   │   ├── main.py
│   │   ├── security.py
│   │   └── config.py
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
│
├── desktop/
│   ├── src/                     Electron main/preload/mini pencere
│   ├── assets/
│   ├── scripts/
│   └── package.json
│
├── plugins/
│   ├── ai_assistant/
│   ├── chance_games/
│   ├── game_status/
│   ├── moderation/
│   ├── music/
│   └── server_monitor/
│
├── matrix/                      Synapse image ve yapılandırma üretimi
├── docker/
│   ├── postgres/
│   ├── matrix/
│   └── reverse-proxy/
├── scripts/                     Sunucu, backup, restore, firewall araçları
├── docs/
│   ├── architecture/
│   ├── deployment/
│   └── desktop/
├── docker-compose.yml
├── Nexus-Server-Manager.cmd
├── Arkadas-Sunucuyu-Guncelle.cmd
├── Baslat-Nexus.cmd
├── Durdur-Nexus.cmd
└── Public-Tunnel-Ayarla.cmd
```

### Önemli frontend bileşenleri

- `ChatArea.tsx`: kanal mesajları, lazy loading, optimistic send, edit/delete, ekler.
- `VideoStage.tsx`: dinamik medya sahnesi, focus, grid ve fullscreen.
- `VoicePanel.tsx`: ses kanalı katılımcıları ve kontroller.
- `SettingsPanel.tsx`: durum, ses/video, kalite, bildirim, görünüm ve masaüstü ayarları.
- `ProfilePanel.tsx`: profil, arkadaşlar, istekler ve özel konuşmalar.
- `ServerSettingsPanel.tsx`: sunucu genel ayarları ve bot yönetimi.
- `ServerInvitesPanel.tsx`: hedefli davet kabul/ret/iptal.
- `JoinServerPanel.tsx`: paylaşılabilir kod/bağlantıyla katılım.
- `MembersPanel.tsx`: sunucudaki insan üyeler.
- `ServerRail.tsx`: sunucu geçiş şeridi ve davet sayaçları.
- `AttachmentCard.tsx`: görsel önizleme ve dosya indirme kartları.

### Önemli frontend hook'ları

- `useGateway.ts`: presence, mesajlar, çağrılar, sosyal olaylar ve reconnect.
- `useVoiceChannel.ts`: signaling, peer bağlantıları, medya track'leri ve ICE kurtarma.
- `useMediaDevices.ts`: mikrofon, kamera, hoparlör listeleme/önizleme/seçim.
- `usePushToTalk.ts`: tarayıcı içi PTT kombinasyonları.

---

## 6. Çalışma zamanı mimarisi

Basitleştirilmiş trafik akışı:

```text
Furkan / diğer kullanıcı
        │ HTTPS + WSS
        ▼
Cloudflare
        │ Cloudflare Tunnel
        ▼
public-tunnel container
        │ HTTP, Docker app ağı
        ▼
Caddy reverse-proxy:8081
        ├── /                 → frontend:8080
        ├── /api/*            → backend:8000
        ├── /_matrix/*        → matrix:8008
        ├── /healthz          → Caddy "ok"
        └── WebSocket Upgrade → backend

Backend
  ├── PostgreSQL             platform verileri, oyunlar, AI işleri
  ├── Matrix Synapse         kalıcı kanal/DM mesajları
  ├── plugin-sandbox         güvenilmeyen pluginler
  ├── ai-worker              kalıcı AI kuyruğu tüketicisi
  └── AI Gateway             Ollama bilgisayarına gider

Ses/kamera/ekran:
  İstemci ── WebSocket signaling ── Backend
  İstemci ═════ WebRTC medya ═════ Diğer istemci
                gerekirse coturn relay
```

Cloudflare Tunnel web/API/WebSocket trafiğini taşır; genel UDP tabanlı TURN relay değildir.
WebRTC doğrudan bağlantı kuramazsa coturn için Mert'in genel IPv4 ve port yönlendirmesi gerekir.

---

## 7. Docker Compose servisleri

### Kalıcı servisler

- `postgres`
  - Platform ve Synapse veritabanlarını barındırır.
  - Host'a PostgreSQL portu yayınlamaz.
  - `data` internal ağı kullanır.

- `plugin-sandbox`
  - Güvenilmeyen pluginleri sınırlı izinlerle çalıştırır.
  - Read-only root filesystem, capability drop, CPU/RAM/PID limitleri vardır.
  - Yalnız `sandbox` internal ağındadır.

- `turn`
  - coturn STUN/TURN servisi.
  - TCP/UDP `3478` ve yapılandırılmış relay port aralığını yayınlar.

- `ai-worker`
  - PostgreSQL'deki AI işlerini tüketir.
  - Backend image'ını ayrı process olarak kullanır.

- `matrix`
  - Matrix Synapse.
  - Ayrı PostgreSQL kullanıcısı/veritabanı.

- `backend`
  - FastAPI Core API.
  - App, data ve sandbox ağlarına bağlıdır.
  - Avatar ve attachment volume'larına yazabilir; root filesystem read-only'dir.

- `frontend`
  - Vite production çıktısını servis eder.

- `reverse-proxy`
  - Caddy.
  - Doğrudan domain için 80/443 ve Docker içi Tunnel origin'i için 8081 dinler.

- `public-tunnel`
  - İsteğe bağlı `public-tunnel` profili.
  - `.env` içinde `CLOUDFLARE_TUNNEL_TOKEN` varsa yönetim scriptleri profili otomatik ekler.

### Tek seferlik servisler

- `postgres-bootstrap`
  - Veritabanı kullanıcılarını ve veritabanlarını idempotent biçimde hazırlar.

- `migrate`
  - `alembic upgrade head` çalıştırır.

### Docker ağları

- `app`: frontend/backend/matrix/Caddy/tunnel iletişimi.
- `data`: internal PostgreSQL ağı.
- `sandbox`: internal plugin izolasyon ağı.

### Kalıcı volume'lar

```text
postgres_data
postgres_socket
postgres_backups
matrix_data
caddy_data
caddy_config
avatar_data
attachment_data
```

`postgres_data`, `matrix_data`, `avatar_data` ve `attachment_data` kullanıcı verisidir.
Bu volume'lar bilinçsizce silinmemelidir.

---

## 8. Veritabanı ve migration durumu

Güncel migration zinciri:

```text
0001_initial_schema
0002_ai_jobs
0003_ai_bot_jobs
0004_ai_stream_cancel
0005_chance_games
0006_social_graph
0007_server_invites
0008_server_join_codes
```

Güncel head:

```text
0008_server_join_codes
```

Başlıca Core modelleri:

- `User`
- `Friendship`
- `Server`
- `ServerMember`
- `ServerInvite`
- `ServerJoinCode`
- `Channel`
- `Role`
- `Plugin`
- `Bot`
- `BotServerLink`
- `BotPluginLink`
- `ChanceGameSession`
- `ChanceWheel`

AI tarafındaki modeller:

- `AiConversation`
- `AiMessage`
- `AiJob`
- `AiBotJob`
- `AiTokenUsage`

Mesaj gövdeleri esas olarak Matrix'te tutulur; sunucu/kanal ilişkileri ve Matrix oda kimlikleri
Core veritabanında tutulur.

---

## 9. Kimlik doğrulama, hesap ve güvenlik

### Uygulananlar

- JWT tabanlı login.
- Endpoint'lerde kullanıcı kimliği Bearer token'dan alınır.
- Sunucu sahipliği ve üyelik backend'de doğrulanır.
- Parolalar düz metin tutulmaz.
- Hash biçimi: PBKDF2-SHA256, salt ve yüksek iterasyon sayısı.
- Görünen ad değişikliği.
- Mevcut parola doğrulamalı parola değiştirme.
- Avatar yükleme:
  - magic-byte MIME kontrolü,
  - 2 MB sınırı,
  - rate limit,
  - path traversal koruması,
  - eski avatar temizliği,
  - istemcide kare kırpma ve 256px çıktı.
- Login rate limit'i yalnız IP'ye değil istemci adresi + kullanıcı adına ayrılmıştır.
  Aynı reverse proxy arkasındaki kullanıcılar birbirinin limitini tüketmez.
- Login ve register geçici `502/503/504`, timeout ve bağlantı kopmalarında sınırlı yeniden denenir.
- Register aynı username/e-posta/parola için idempotent davranır.

### Masaüstü token güvenliği

- Web sürümü mevcut localStorage davranışını korur.
- Electron sürümünde token localStorage'a yazılmaz.
- Token Windows DPAPI tabanlı Electron `safeStorage` ile şifrelenir.
- `nodeIntegration` kapalıdır.
- `contextIsolation` ve renderer sandbox açıktır.
- Preload IPC yüzeyi allowlist ile sınırlıdır.
- Paketli uygulama uzaktan web sayfasını privileged renderer olarak açmaz; `nexus://app`
  yerel origin'inden çalışır.

### Gizli veriler için kesin kurallar

- `.env` ve `ai-gateway/.env` Git'e gönderilmez.
- Cloudflare Tunnel tokeni, Cloudflare API tokeni ve AI Gateway API key paylaşılmaz.
- Hesapların düz metin parolaları sistemden “çıkarılamaz”; yalnız reset edilebilir.
- Eski `.env.bak.*`, dump ve backup dosyalarının Git tarafından yok sayıldığı push öncesi
  doğrulanmalıdır.
- Kullanıcı daha önce hesap giriş bilgilerini istemiş olsa bile parola veya secret devir
  belgesine yazılmamalıdır.

---

## 10. Sunucu, kanal, üye ve davet sistemi

### Sunucular

- Sunucu oluşturma.
- Sunucu adını ve açıklamasını düzenleme.
- Sunucudan ayrılma.
- Sunucuyu silme.
- Sahip dışındaki üyeyi çıkarma.
- Sunucu sahibi korunur.
- Sol sunucu şeridi standart olarak dar/kapalı başlar; fare veya klavye fokusu geldiğinde açılır.

### Kanallar

- Metin ve ses kanalı ayrımı vardır.
- Kanal oluşturma, yeniden adlandırma ve silme.
- Ses kanalları kendilerine özel mesaj odası değildir.
- Yeni ses kanalı için Matrix text room oluşturulmaz.
- Eski ses kanallarında mesaj gönderme veya geçmiş listeleme backend tarafından reddedilir.

### Üye görünümü

- Eski büyük/tekrarlı kullanıcı görünümü kaldırılmıştır.
- Sunucudaki insan üyeler, sunucu şeridi ile kanal listesi arasında solda açılıp kapanabilen
  kompakt panelde gösterilir.
- Botlar insan üye listesinden ayrıdır.
- Küçük sunucular hedeflenmiştir; çoğunlukla 7–8 insan kullanıcı beklenir.
- Durum noktaları çevrimiçi/boşta/rahatsız etmeyin/görünmez durumlarını gösterir.

### Hedefli sunucu davetleri

- Davet, serbest kullanıcı adı yazarak gönderilmez.
- Sunucu sahibi kabul edilmiş arkadaşlardan seçim yapar.
- Alıcıda **Kabul et / Reddet** görünür.
- Gönderende bekleyen daveti **İptal et** seçeneği vardır.
- Kabul anında:
  - `ServerMember` oluşturulur,
  - varsayılan rol atanır,
  - Matrix metin odası üyelikleri hazırlanır.
- Sol sunucu şeridinde bekleyen davet sayacı vardır.

### Paylaşılabilir katılım kodu

- Hedefli arkadaş davetinden ayrı olarak 16 karakterli kalıcı katılım kodu üretilebilir.
- Örnek bağlantı:

```text
https://cekin.gen.tr/?invite=<kod>
```

- Kullanıcı bağlantıyı açarak veya `JoinServerPanel` üzerinden kodu girerek katılır.
- Bu akış arkadaşlık gerektirmez.
- Katılım idempotenttir; ağ cevabı kaybolup tekrar denenirse çift üyelik oluşmaz.
- PostgreSQL üyeliği Matrix senkronundan önce yazılır.
- Matrix geçici kapalıysa kullanıcı yine sunucuyu ve ses kanallarını görebilir.
- Metin odası üyeliği gerektiğinde mesaj okuma/gönderme sırasında onarılır.
- Kod yalnız sunucu sahibi tarafından görüntülenebilir, yenilenebilir ve iptal edilebilir.
- Kod denemeleri kullanıcı başına dakikada 12 ile sınırlıdır.

---

## 11. Arkadaşlık, profil ve özel mesajlaşma

- Genel profil merkezi kullanıcının:
  - hesap özetini,
  - arkadaşlarını,
  - gelen arkadaşlık isteklerini,
  - giden arkadaşlık isteklerini,
  - birebir özel konuşmalarını gösterir.
- Kullanıcı arama ile arkadaşlık isteği gönderilebilir.
- Kabul, ret, gönderilen isteği iptal ve arkadaş çıkarma işlemleri vardır.
- Arkadaşlık isteklerinin süre sonu yoktur; kullanıcı işlem yapana kadar PostgreSQL'de kalır.
- İstek mutasyonları idempotenttir; ağda yanıt kaybolduğunda güvenli tekrar yapılabilir.
- Aynı arkadaşlık isteği çoğalmaz.
- Gateway canlı olayı kaçarsa panel 15 saniyelik uzlaştırma ile kalıcı API durumunu yeniden çeker.
- Birebir konuşmalar kalıcı Matrix odalarıdır.
- Özel mesajlar gerçek zamanlı gelir.
- Eski özel mesajlar cursor ile sayfalanır.
- Özel mesaj kutusu da Enter/Shift+Enter, dinamik büyüme, edit ve ek özelliklerini paylaşır.

---

## 12. Mesajlaşma sistemi

### Kalıcılık ve geçmiş

- Metin mesajları Matrix'te kalıcı tutulur.
- Mesajlar sayfa yenilendiğinde kaybolmamalıdır.
- Geçmiş cursor ile 50'şer yüklenir.
- Kullanıcı yukarı gittikçe lazy-load ile daha eski sayfa çekilir.
- Uzun DOM listelerinde `content-visibility` kullanılarak çizim maliyeti düşürülür.
- Kullanıcı Matrix odasında eksikse mesaj okuma/gönderme sırasında otomatik davet ve join ile
  oda üyeliği onarılır.
- Yeni metin kanalı oluşturulurken mevcut sunucu üyeleri odaya eklenir.

### Gerçek zamanlı teslim

- Normal mesajlar `channel-message` gateway payload'ı ile anında istemcilere gönderilir.
- Eski 4 saniyelik polling ana yol değildir.
- Gateway bağlıyken düşük frekanslı snapshot yalnız güvenlik ağıdır.
- Polling/snapshot aralıkları sekme durumu ve gateway bağlantısına göre seyrekleşir.
- Mesaj gönderildiğinde istemcide optimistic olarak hemen görünür.
- `client_id`, Matrix transaction ID olarak kullanılır.
- Timeout/retry durumunda duplicate mesaj önlenir.
- Gönderim başarısız olursa kullanıcı tekrar deneyebilir.

### Kaydırma davranışı

- Kullanıcı kendi mesajını gönderdiği anda sohbet kesin olarak en alta iner.
- Başka kullanıcı mesaj gönderdiğinde:
  - kullanıcı zaten aşağıdaysa yeni mesaja gider,
  - kullanıcı eski geçmişi okuyorsa konumu bozulmaz,
  - sağ altta küçük dairesel aşağı ok/yeni mesaj düğmesi görünür.
- Bu aşağı ok uygulama içi genel bildirim sayılmaz ve kaldırılmamalıdır.

### Mesaj düzenleme ve silme

- Kullanıcı kendi mesajını düzenleyebilir.
- Düzenleme Matrix `m.replace` ilişkisiyle saklanır.
- Edit event'i ayrı bir normal mesaj gibi gösterilmez; orijinal mesajla birleştirilir.
- Düzenleme gateway üzerinden diğer istemcilere anında yansır.
- Kullanıcı kendi mesajını silebilir.
- Matrix redaction uygulanır.
- Silinen mesaj normal geçmişten elenir/güncellenir.
- Düzenleme ve silme ikonları küçük, ortak modern SVG setindedir.

### Mesaja yanıt

- Kanal mesajları ve birebir özel mesajlar Discord/WhatsApp benzeri alıntılı yanıtı destekler.
- Kalıcı ilişki Matrix `m.in_reply_to` sözleşmesiyle saklanır.
- Kısa yanıt önizlemesi optimistic gönderimde, gateway canlı olayında ve F5 sonrası Matrix
  geçmişinde korunur.
- Kullanıcı yanıt önizlemesine tıklayarak hedef mesaj hâlâ yüklenen sayfadaysa ona kayabilir.

### Çok satırlı mesaj

- Enter mesajı gönderir.
- Shift+Enter aynı mesaj içinde yeni satır açar.
- Textarea içeriğe göre dinamik büyür.
- En fazla yaklaşık sekiz satır görünür; sonrasında textarea kendi içinde kaydırılır.

### Dosya ve fotoğraf

- Kanal ve birebir konuşmalarda dosya/görsel yükleme vardır.
- Üst sınır 25 MB'dir.
- Dosyalar `attachment_data` Docker volume'unda kalıcı tutulur.
- Resimler lazy-load önizlenir.
- Diğer dosyalar güvenli indirme kartı olarak gösterilir.

### Spam/rate limit

- Synapse normal mesaj limiti yaklaşık 5 mesaj/sn ve 50 mesaj burst olacak şekilde gevşetilmiştir.
- Bot komut limiti 10 saniyede 20 komuttur.
- Yaklaşık 10 mesajda hemen spam hatası verme sorunu giderilmiştir.

---

## 13. Bildirimler ve kullanıcı durumları

### Durumlar

- Çevrimiçi
- Boşta
- Rahatsız etmeyin
- Görünmez
- Özel durum metni

Durum ve özel durum ana araç çubuğundan kaldırılmış, Ayarlar'a taşınmıştır.

### Bildirim davranışı

- Eski uygulama içi sağ üst mesaj toast/kenar bildirimleri kaldırılmıştır.
- Yeni mesaj aşağı oku korunmuştur.
- Sekme arka plandaysa:
  - kısa mesaj sesi,
  - izin varsa işletim sistemi/tarayıcı bildirimi gösterilebilir.
- Gelen çağrı için zil ve masaüstü bildirimi vardır.
- Rahatsız Etmeyin durumunda mesaj ve çağrı bildirimlerinin tamamı bastırılır.
- Bildirim sesi Ayarlar'dan açılıp kapatılabilir.
- Electron sürümü native Windows bildirimi kullanabilir.

---

## 14. Sesli sohbet, WebRTC ve çağrı sistemi

### Temel topoloji

- Ses signaling endpoint'i:

```text
/api/channels/{channel_id}/voice
```

- Medya backend üzerinden aktarılmaz; peer'ler arasında WebRTC ile taşınır.
- Backend join/leave, offer/answer, ICE, mute, speaking ve roster olaylarını relay eder.
- Mesh olduğu için katılımcı sayısı arttıkça istemci CPU ve upload kullanımı artar.

### Sesli oturum yaşam döngüsü

- Metin kanalına geçmek sesli görüşmeden çıkarmaz.
- Başka sunucunun metin kanalına geçmek de çıkarmaz.
- Sesli oturum yalnız:
  - kullanıcı açıkça ayrılırsa,
  - başka bir ses kanalına geçerse,
  - sunucudan/kanaldan atılırsa,
  - tarayıcı/pencere kapanırsa biter.
- F5 ve hızlı reconnect sırasında eski WebSocket'in yeni oturumu roster'dan silmesine yol açan
  yarış koşulu giderilmiştir.
- Backend ses bağlantılarını session kimliğiyle ayırır.
- Kullanıcının kendi peer listesine girmesi engellenir.

### Mikrofon ve dinleme

- Mikrofon izni reddedilse bile yalnız dinleyici olarak kanala katılmak mümkündür.
- Mikrofon yoksa karşıdan ses alabilmek için `recvonly` audio transceiver oluşturulur.
- Mikrofon toggle ve deafen vardır.
- Deafen ve mute ikonları modern ve birbiriyle çakışmayacak biçimdedir.
- Mikrofon açık/kapalı durumu tüm peer'lere yansıtılır.
- Hoparlör seçimi `setSinkId` destekleyen Chrome/Edge'de çalışır.
- Gürültü bastırma, echo cancellation ve auto gain gerçek MediaTrackConstraints ile uygulanır.
- Görüşme sırasında mikrofon değişimi `replaceTrack` ile bağlantı kesmeden yapılır.
- Mikrofon seviye testi, kamera önizleme ve hoparlör test sesi vardır.

### Push-to-talk

- Web istemcisinde sekme odaktayken özelleştirilebilir PTT kombinasyonu vardır.
- Metin alanına yazarken PTT tetiklenmez ve yazmayı engellemez.
- Sekme blur olduğunda takılı mikrofon durumunu engellemek için PTT bırakılır.
- Tarayıcı güvenlik modeli nedeniyle oyun/başka uygulama ön plandayken global PTT mümkün değildir.
- Electron sürümü global key hook ile Mouse4/Mouse5, Ctrl/Alt/CapsLock ve kombinasyonları destekler.

### Çağrı daveti

- Global gateway üzerinden `call-invite`, accept, reject ve cancel olayları vardır.
- Üye listesinden kullanıcı çağrılabilir.
- Gelen çağrı modalı Kabul/Reddet sunar.
- Zil sesi ve arka plan bildirimi vardır.
- Rahatsız Etmeyin çağrı bildirimini bastırır.

### Reconnect ve hata dayanıklılığı

- Gateway ve voice WebSocket jitter'lı exponential backoff kullanır.
- ICE yapılandırması geçici erişilemezse Cloudflare/Google STUN yedeğiyle katılım devam eder.
- İlk retry yaklaşık 250 ms'den başlar.
- Kısa ICE kopmalarında otomatik ICE restart yapılır.
- Kapanan bağlantıların beklenen `connection aborted` hatası kullanıcıya ham hata olarak gösterilmez.
- SDP mesajları sırayla işlenir.
- Eş zamanlı offer glare/rollback sorunları giderilmiştir.
- İlk WebRTC teklifini yalnız kanala yeni katılan taraf üretir.
- Kamera/ekran aç-kapa renegotiation işlemleri kuyruklanır; kaybolmaz.
- Audio, camera ve screen transceiver/m-line sırası sabittir.
- Daha önce görülen şu hata hedeflenerek giderilmiştir:

```text
Failed to set remote offer sdp:
The order of m-lines in subsequent offer doesn't match order from previous offer/answer
```

---

## 15. Kamera, ekran paylaşımı ve medya sahnesi

### Aynı anda kamera ve ekran paylaşımı

- Kamera ve ekran paylaşımı ayrı, sırası sabit WebRTC transceiver'larıdır.
- İkisi aynı anda açık olabilir.
- Birini kapatmak diğerini kesmez.
- Kamera kapanınca son video karesi donmuş şekilde kalmaz.
- Kamera/ekran açık-kapalı durumu eşlere ayrıca `video-state` sinyaliyle iletilir; tarayıcı
  `replaceTrack(null)` sonrasında son kareyi tutsa bile uzak döşeme anında kaldırılır.
- Kamera/yayın yoksa profil fotoğrafı veya kullanıcı baş harfi görünür.

### Dinamik sahne

- Medya yokken ses kanalındaki katılımcıların profil kartları görünür.
- Katılımcı sayısına göre sahne:
  - tek kişi,
  - iki kişi,
  - 2×2,
  - üç sütun ve gerekli satırlar biçiminde dinamik düzenlenir.
- İki kişi sahneyi gereksiz boşluk bırakmadan paylaşır.
- Tek kişilik kamera görünümünde zorunlu 16:9 crop kaldırılmıştır.
- Kamera doğal oranı korunur ve `object-fit: contain` ile saç/çene dahil tamamı görünür.

### Ekran paylaşımı

- Aktif ekran paylaşımı yayın odası benzeri ana sahneye alınır.
- Kamera/profil önizlemeleri masaüstünde sağ şeritte, dar ekranda alt şeritte yer alır.
- Kamera kapalı ve yalnız yayın açıksa gereksiz profil döşemesi kaldırılır.
- Kaynak ekranın dört kenarı korunur.
- Genişlik/yükseklik zorlamasıyla kırpma yapılmaz.
- Video mutlak sahne sınırlarına oturur ve `object-fit: contain` kullanır.
- Kaynak en-boy oranı bozulmaz.
- Ekran paylaşan kullanıcının üstü/altı/yanları hiçbir sahne oranında kesilmemelidir.
- Normal sahnede tekrar eden üst yayın bilgi bloğu ve alt görüşme kontrol çubuğu yoktur.
- Sahneyi gizle ve tam ekran kontrolleri medya üzerinde soldaki kompakt çubuktadır; kaldırılan
  dikey alan sohbet ekranına geri verilirken gerçek medya görüntü alanı küçültülmez.

### Focus ve grid'e dönüş

- Kamera, ekran paylaşımı veya katılımcı kartına tıklanınca focus o karta geçer.
- Focus durumunda sahnede yalnız seçilen medya/kart görünür.
- Seçilen öğe kullanılabilir alanın tamamını kullanır.
- Aynı karta tekrar tıklamak normal ızgaraya döndürür.

### İzlemeyi kapatma ve bant tasarrufu

- Kullanıcı her uzak kamera veya ekran paylaşımını ayrı ayrı izlemeyi kapatabilir.
- Bu yalnız CSS ile gizleme değildir.
- WebRTC receiver yönü renegotiation ile kapatılır ve gereksiz video trafiği durdurulur.
- Yayını/kamerayı açan kendi yerel kaynağını bu yöntemle kapatmaz.
- Canlı sahne tamamen gizlenebilir; mesaj alanı tüm çalışma alanını kullanır.
- Arka plandaki video elemanları duraklatılır, ses ayrı audio elemanından devam eder.

### Tam ekran

- Gerçek fullscreen seçeneği vardır.
- Fullscreen sırasında şu kontrollere erişim korunur:
  - mikrofon,
  - deafen/gelen ses,
  - kamera,
  - ekran paylaşımı,
  - ses kanalından ayrılma,
  - grid/focus davranışı.

### Kalite seçenekleri

- Kalite ayarları ana araç çubuğunda değil, **Ayarlar → Ses ve Video** içindedir.
- Kullanıcı seçenekleri:
  - 480p
  - 720p
  - 1080p
  - 30 FPS
  - 60 FPS
- Güncel arayüzde maksimum 1080p'dir; 4K seçenek uygulanmış kabul edilmemelidir.
- Ekran paylaşımında kaynak crop edilmez; kalite düşürme WebRTC encoder
  `scaleResolutionDownBy` üzerinden orantılı yapılır.
- “Ne pahasına olursa olsun 4K/60” uygulanmaz; bağlantı ve cihaz kapasitesi dikkate alınmalıdır.

---

## 16. Arayüz ve tema

### Genel tasarım

- Discord benzeri çok panelli koyu modern arayüz.
- Glassmorphism etkileri ve mor vurgu rengi.
- Açık tema ve sistem teması da vardır.
- CSS değişkenleri üzerinden ortak renk sistemi kullanılır.
- `color-scheme` koyu/açık temayla uyumludur.
- Metin ve arka plan hiçbir kritik durumda benzer kontrastsız renkte bırakılmamalıdır.

### Yerleşim

- En solda hover/focus ile açılan sunucu şeridi.
- Yanında solda kompakt sunucu üye paneli.
- Kanal listesi.
- Ortada medya sahnesi ve metin sohbeti.
- Sağ/katman olarak ayarlar veya sunucu yönetimi gerektiğinde açılır.
- Kullanılmayan eski/tekrarlı paneller kaldırılmalıdır.

### Ayarlar

Sekmeler en az:

- Hesabım
- Durum
- Ses ve Video
- Bildirimler
- Görünüm
- Electron'da Kısayollar
- Electron'da Windows
- Gelişmiş

Kalite/FPS, durum ve özel durum yalnız ayarlarda tutulur.

### Sunucu ayarları

- Bot yönetimi ve sunucu genel yönetimi ortak temalı `Sunucu Ayarları` penceresindedir.
- Bot oluşturma formu temaya uyumludur.
- Select/input/devre dışı butonların kontrastı okunabilir olmalıdır.
- Platform pluginleri kart tabanlı, satıra saran açıklama ve komut listeleriyle gösterilir.
- Sunucu yeniden adlandırma, açıklama, ayrılma ve silme burada bulunur.

### İkonlar

- Emoji/karışık semboller yerine ortak modern SVG ikon seti kullanılır.
- Ayarlar dişli simgesiyle açılır.
- Çıkış profil alanının içindedir.
- Çıkıştan önce bir kez “emin misiniz?” onayı gösterilir.
- Düzenle/sil ikonları mesajın yanında küçük ve dikkat dağıtmayacak boyuttadır.

---

## 17. Bot ve plugin sistemi

### Genel mimari

- Plugin manifesti `plugins/<ad>/plugin.json` içindedir.
- Plugin kurulabilir, kaldırılabilir, etkinleştirilebilir ve bir bota bağlanabilir.
- Bot yalnız eklendiği sunucularda çalışır.
- Bot-plugin bağlantısı açıkça yapılır.
- Aynı sunucuda belirli pluginlerin uygunsuz ikinci bağlantısı engellenebilir.
- Core servisine güvenilir erişim gerektiren yerleşik pluginler yalnız tam ad allowlist ile
  local çalışır:
  - `music`
  - `ai_assistant`
  - `moderation`
- Diğer pluginler `plugin-sandbox` içinde çalışır.
- Sandbox doğrudan veritabanı anahtarı almaz; doğrulanmış eylem zarfı Core'a iletilir.

### Mevcut pluginler

#### `ai_assistant`

- `/sor <soru>` benzeri komutlar.
- AI işi ana API request'i içinde bloklanmaz; worker kuyruğuna bırakılır.
- Ollama/AI Gateway kullanır.

#### `chance_games`

Taş–Kağıt–Makas:

- `/takama @kullanıcı`
- Karşı tarafta Kabul/Reddet kartı.
- `/kabul <kod>` alternatifi.
- Kabul sonrası komut rehberi.
- `/taş`, `/kağıt`, `/makas` hamleleri ilk oyuncunun seçimini rakipten gizler.
- İlk hamle Matrix'e açık mesaj olarak yazılmaz.
- İki oyuncu tamamladıktan sonra sonuç aynı anda açıklanır.

Yazı–Tura:

- `/yazıtura`
- `/yazıtura @kullanıcı`

Çark:

- `/ekleçark elma`
- `ekleçark: elma`
- `/ekleçark elma | 3`
- `/çarkliste`
- `/çıkarçark`
- `/temizleçark`
- `/çark`

Dayanıklılık:

- Sunucu tarafı `secrets` rastgeleliği.
- Harici/ücretli API yok.
- Davet yaklaşık 2 dakika, aktif oyun yaklaşık 5 dakika timeout.
- Kullanıcı aynı anda tek açık oyunda olabilir.
- Kendine davet ve sunucu dışı etiket reddedilir.
- Oyunlar ve çarklar PostgreSQL'de kalıcıdır.
- Structured oyun kartı yalnız backend'in `is_bot` olarak doğruladığı mesajlarda açılır.

#### `music`

- Gerçek WebRTC ses akışı gönderir; yalnız “çalıyor” mesajı yazan sahte bot değildir.
- `aiortc` kullanır.
- Yerel `plugins/music/library/` klasöründeki dosyaları çalar.
- İnternetten şarkı indirmez.
- Örnek komutlar:
  - `/muzik-katil <sesli-kanal>`
  - `/muzik-ekle <parça>`
  - `/muzik-kuyruk`
  - `/muzik-sonraki`
  - `/muzik-ayril`
  - `/muzik-listele`
- Plugin açıkça bir bota bağlanmalıdır.
- Eski voice manager çağrı sözleşmesi ve double-offer glare hatası düzeltilmiştir.
- Production ortamında gerçek kullanıcıyla tekrar smoke test yapılması yine yararlıdır.

#### `moderation`

- Mesaj redaction/silme araçları.
- Yetki kontrolü backend/Core üzerinden yapılır.

#### `game_status`

- Minecraft Server List Ping protokolüyle sunucu durumunu sorgular.
- Ham socket kullanır.

#### `server_monitor`

- Sunucu/sistem durum bilgileri.

### Bilinen plugin yetki sınırı

- Tam platform-admin, detaylı RBAC ve plugin permission approval akışı tamamlanmış değildir.
- İzin modeli altyapısı olsa da birçok yönetim kararı hâlâ sahiplik seviyesindedir.

---

## 18. AI mimarisi

### Akış

```text
Kullanıcı mesajı
    │
    ▼
FastAPI Core
    │ kısa DB işlemi
    ▼
ai_jobs / ai_bot_jobs (queued)
    │
    ▼
ai-worker
    │ HTTP + Bearer key
    ▼
AI Gateway (AI bilgisayarı)
    │
    ▼
Ollama
```

### Özellikler

- AI job'ları PostgreSQL'de kalıcıdır.
- API process'i model üretirken bloklanmaz.
- Worker lease ve `SKIP LOCKED` kullanır.
- Worker kapanırsa lease süresi dolan iş tekrar alınabilir.
- Geçici Gateway hataları sınırlı exponential backoff ile denenir.
- Model/auth/config hataları kalıcı `failed` durumuna geçer.
- Aynı request için `Idempotency-Key` duplicate prompt'u önleyebilir.
- Kanal bot cevabında Matrix transaction ID job kimliğinden türetilerek duplicate sonuç önlenir.
- Context varsayılan yaklaşık token bütçesine sığan en yeni mesajlardan hazırlanır.
- Ollama gerçek prompt/output token sayılarını döndürdüğünde kullanım kaydedilir.
- SSE:

```text
GET  /api/ai/jobs/{job_id}/stream
POST /api/ai/jobs/{job_id}/cancel
```

- İptal cooperative'dir.
- Ücretli OpenAI/Anthropic API zorunluluğu yoktur.

### AI Gateway

- Ayrı FastAPI uygulamasıdır.
- `/ai/health`, `/api/tags`, `/api/chat` proxy uçları vardır.
- Bearer API key zorunludur.
- CIDR ve trusted proxy kontrolü vardır.
- Server `.env` içindeki `OLLAMA_API_KEY` ile AI bilgisayarındaki
  `AI_GATEWAY_API_KEY` aynı olmalıdır.
- Gerçek anahtar bu belgeye yazılmamalıdır.

---

## 19. Windows Electron istemcisi

- React/Vite web istemcisini özellikleri yeniden yazmadan paketler.
- Kendi yerel `nexus://app` origin'ini kullanır.
- API ve WSS sözleşmeleri web sürümüyle aynıdır.
- Global PTT ve kısayollar.
- Mikrofon, deafen ve focus kısayolları.
- Mouse4/Mouse5 desteği.
- System tray.
- X'e basınca tray'e küçült veya tamamen çık tercihi.
- Windows başlangıcında açılma.
- Native bildirim.
- Kompakt özel titlebar.
- Minimum pencere boyutu.
- Always-on-top mini ses penceresi:
  - kanal,
  - katılımcı,
  - konuşan,
  - mute/deafen durumu,
  - temel ses kontrolleri.
- Ekran/pencere seçimi Electron `desktopCapturer` ile mevcut WebRTC akışına bağlanır.
- Giriş gain'i `%0–200`, çıkış seviyesi `%0–100`.
- NSIS installer, Start Menu, masaüstü kısayolu, uninstall ve update metadata üretir.
- Auto-update ilk kurulumda kapalıdır.
- Production dağıtımı öncesi Authenticode kod imzası gerekir.
- İmzasız installer sıkı Windows Application Control/SmartScreen politikalarında engellenebilir.

Bilinen artifact notu:

```text
desktop/release-delivery2/NexusSetup-1.0.0-x64.exe
```

Bu dosya geliştirme artifact'ıdır; imzalı production release kabul edilmemelidir.

---

## 20. Yönetim scriptleri

### Ana grafik arayüz

```text
Nexus-Server-Manager.cmd
```

Sunulan ana işlemler:

- Configure
- Initialize
- Validate
- Deploy
- Update
- Start
- Stop
- Restart
- Status
- Diagnose
- Backup
- RepairDatabase
- AI Gateway start/stop/status
- Firewall işlemleri
- Config editörü

### Kolay başlatma

```text
Baslat-Nexus.cmd
```

- Docker Desktop gerekirse başlatılır.
- Stack başlatılır.
- Token varsa Cloudflare Tunnel profili de çalışır.

### Güvenli durdurma

```text
Durdur-Nexus.cmd
```

- Container'ları durdurur.
- Volume silmez.

### Tunnel token kurulumu

```text
Public-Tunnel-Ayarla.cmd
```

- `eyJ...` biçimindeki gerçek tunnel tokenini görünmeyen girişle `.env` içine kaydeder.
- Replica/Connector ID tunnel tokeni değildir.

### PowerShell CLI

```powershell
.\scripts\nexus-server.ps1 -Action Status
.\scripts\nexus-server.ps1 -Action Diagnose
.\scripts\nexus-server.ps1 -Action Start
.\scripts\nexus-server.ps1 -Action Stop
.\scripts\nexus-server.ps1 -Action Restart
.\scripts\nexus-server.ps1 -Action Deploy
.\scripts\nexus-server.ps1 -Action Update -GitBranch cekingen
.\scripts\nexus-server.ps1 -Action Backup
```

---

## 21. Normal deploy ve doğrulama

### Migration içeren değişiklik

```powershell
docker compose build matrix backend frontend
docker compose run --rm migrate
docker compose --profile public-tunnel up -d
```

Yönetim scriptini kullanmak tercih edilir; bootstrap, migration ve health sırasını güvenli
biçimde uygular.

### Yalnız backend/frontend değişikliği

```powershell
docker compose build backend frontend
docker compose --profile public-tunnel up -d backend ai-worker plugin-sandbox frontend reverse-proxy public-tunnel
```

### Durum

```powershell
docker compose --profile public-tunnel ps
docker compose --profile public-tunnel logs --tail 120
```

### Yerel origin kontrolü

```powershell
docker compose exec -T reverse-proxy wget -qO- http://127.0.0.1:8081/healthz
```

Beklenen çıktı:

```text
ok
```

### Public kontrol

```powershell
curl.exe https://cekin.gen.tr/healthz
```

Beklenen çıktı:

```text
ok
```

---

## 22. 29 Temmuz 2026 itibarıyla canlı dış erişim sorunu

### Gözlenen ekran

Cloudflare:

```text
Bad gateway
Error code 502
Browser Working
Cloudflare Working
Host Error
```

### Yapılan canlı doğrulama

- `cekin.gen.tr` artık genel DNS'te Cloudflare IP'lerine çözülüyor:
  - `172.67.221.25`
  - `104.21.70.73`
- Eski `25.49.22.166` Hamachi A kaydı artık istemciye dönmüyor.
- TLS/HTTPS sertifikası geçerli.
- Tarayıcı → Cloudflare bağlantısı çalışıyor.
- Arka arkaya 10 public health isteğinin 10'u da HTTP `502` döndürdü.
- Bu nedenle önceki DNS/sertifika problemi çözülmüş, sorun
  **Cloudflare Tunnel → Mert'in origin servisi** arasına daralmıştır.
- Cloudflare'ın bu hata türündeki anlamı: tunnel Cloudflare'a bağlı olabilir fakat
  `cloudflared` yapılandırılmış origin'e ulaşamaz.

### Doğru Cloudflare Public Hostname

Cloudflare Zero Trust:

```text
Networks → Tunnels → nexus → Public Hostnames
```

Değerler:

```text
Hostname: cekin.gen.tr
Type:     HTTP
URL:      reverse-proxy:8081
```

Şunlar yanlış olur:

- `HTTPS`
- `localhost`
- `127.0.0.1`
- `cekin.gen.tr`
- host portu
- eski Windows servisinin erişemeyeceği Docker service adıyla Docker dışı connector

### Mert'in çalıştıracağı tanı

```powershell
cd C:\Users\merte\Github\nexus-server

docker compose --profile public-tunnel ps
docker compose --profile public-tunnel logs --tail 120 reverse-proxy public-tunnel
docker compose exec -T reverse-proxy wget -qO- http://127.0.0.1:8081/healthz
```

Sonra:

```powershell
docker compose --profile public-tunnel up -d --build
```

veya güvenli tam akış:

```text
Arkadas-Sunucuyu-Guncelle.cmd
```

### Log yorumlama

- `lookup reverse-proxy ... no such host`
  - Connector Docker `app` ağı dışında.
  - Eski Windows cloudflared servisi trafiği alıyor olabilir.
  - Yanlış/eski connector aktiftir.

- `connect: connection refused`
  - `reverse-proxy` kapalı/restarting.
  - Caddy 8081'i dinlemiyor.
  - Public Hostname portu yanlış.

- TLS/protocol hatası
  - Public Hostname Type yanlışlıkla HTTPS seçilmiş olabilir.
  - Origin plain HTTP olmalıdır.

- Yerel `wget ...8081/healthz` `ok`, public hâlâ 502
  - Cloudflare Tunnel connector listesi incelenmelidir.
  - Eski bilgisayar, eski Docker projesi veya Windows servisine ait connector kaldırılmalıdır.
  - Tek connector satırında dört Cloudflare bağlantısı görünmesi normaldir.
  - Farklı **Connector ID** satırları farklı replica/connector'lardır.

### Sorumluluk

- Bu sorun Mert'in sunucu/tünel tarafındadır.
- Furkan'ın yapacağı ayar yoktur.
- Tarayıcı güvenliğini azaltmak veya sertifika uyarısını geçmek çözüm değildir.
- AI Gateway bu 502'nin temel nedeni değildir; AI kapalı olsa bile Caddy health endpoint'i
  `ok` dönebilmelidir.

---

## 23. Test ve doğrulama durumu

Bu belge hazırlanırken yerelde yeniden çalıştırılan kontroller:

### Backend

```text
33 passed
```

### AI Gateway

```text
9 passed
```

Bir testte `PytestReturnNotNoneWarning` vardır:

```text
tests/test_gateway.py::test_settings
```

Test başarılıdır fakat fonksiyon `return` yerine `assert` kullanacak şekilde ileride
temizlenebilir.

### Frontend TypeScript

```text
npm.cmd run lint
tsc --noEmit
başarılı
```

### Frontend production build

```text
npm.cmd run build
Vite production build başarılı
60 module transformed
```

Bu doğrulamalar live server deploy'u değildir; Mert'in production Docker stack'i ayrıca
health ve iki gerçek kullanıcıyla smoke test edilmelidir.

### Mevcut backend test kapsamı

- Auth retry/idempotency
- Şans oyunları
- Matrix pagination
- Müzik botu WebRTC
- Ollama client ve error mapping
- Plugin loader
- Sosyal sistem
- Voice connection/session davranışı

### Eksik test katmanları

- Tam browser E2E paketi yok.
- Çok kullanıcılı gerçek medya testi büyük ölçüde manuel.
- Farklı NAT/CGNAT ağlarında WebRTC/TURN matrisi otomatik değil.
- Electron installer'ın imzalı production doğrulaması yapılmış değil.
- Cloudflare Tunnel end-to-end testi Mert'in canlı makinesine bağlı.

---

## 24. Performans ve kaynak tasarrufu

- Gerçek zamanlı mesaj payload'ı geldiğinde son 50 mesaj tekrar indirilmez.
- Gateway bağlıyken snapshot daha seyrek yapılır.
- Sekme arka plandaysa polling dakikalar düzeyinde seyrekleşebilir.
- Konuşma algılama yaklaşık 60 Hz yerine yaklaşık 13 Hz çalışır.
- Arka plan sekmesinde analyser durur.
- Arka plan video render'ı duraklatılır.
- İzlenmeyen uzak video track'i receiver yönünden kapatılır.
- Matrix HTTP client keep-alive session ve connect/read timeout kullanır.
- Mesaj geçmişi sayfalıdır; bütün tarih tek seferde DOM'a basılmaz.
- `content-visibility` uzun sohbetlerin render maliyetini azaltır.
- AI model üretimi API process'inden ayrı worker'a taşınmıştır.
- Docker servislerinde CPU/RAM sınırları vardır.

---

## 25. Bilinen mimari sınırlar

### WebRTC mesh

- 4–5 ve üzeri aktif video kullanıcısında CPU/upload maliyeti hızla artar.
- Büyük odalar hedeflenecekse SFU gerekir.
- Ücretsiz/self-hosted seçenekler araştırılabilir; fakat bu büyük bir mimari değişikliktir.

### TURN

- Cloudflare Tunnel genel UDP TURN taşımaz.
- Kendi coturn servisi ücretsizdir fakat Mert'in:
  - genel IPv4'e,
  - modem port yönlendirmesine,
  - firewall iznine ihtiyacı olabilir.
- CGNAT arkasında genel IPv4 olmadan garantili relay mümkün değildir.

### Gateway state

- Presence/gateway state'i büyük ölçüde process belleğindedir.
- Birden çok backend worker/replica'ya geçilirse Redis benzeri ortak pub/sub ve presence store gerekir.

### Tarayıcı kısıtları

- Global PTT tarayıcıda mümkün değildir.
- `setSinkId` tüm tarayıcılarda desteklenmez.
- Sistem bildirimi kullanıcı iznine bağlıdır.
- Kamera/mikrofon yalnız güvenli context'te çalışır.

### Yetki sistemi

- Tam RBAC, audit log, kanal bazlı detaylı izin ve platform-admin akışı tamamlanmış değildir.

### Dil

- Arayüz metinleri büyük ölçüde bileşenlerde sabit Türkçedir.
- i18n altyapısı yoktur.

### Hesap güvenliği

- 2FA yoktur.
- Aktif oturum listesi ve diğer cihazlardan çıkış yoktur.
- Kullanıcı engelleme/raporlama/gelişmiş DM gizlilik tercihleri tamamlanmamıştır.

---

## 26. Mantıklı sonraki geliştirmeler

Öncelik sırası önerisi:

### P0 — production erişimi

1. Mert'in `502 Host Error` sorununu çöz.
2. Public `/healthz`, login, gateway WSS, Matrix ve ses signaling endpoint'lerini doğrula.
3. Furkan ile sıkı güvenlikli tarayıcıdan giriş testi yap.
4. İki farklı ağdan ses, kamera ve ekran paylaşımını doğrula.
5. TURN gerçekten gerekiyorsa Mert'in genel IPv4/port yönlendirmesini test et.

### P1 — otomatik uçtan uca testler

1. Playwright ile iki kullanıcı oturumu.
2. Login/register retry ve duplicate önleme.
3. Arkadaşlık/davet kabul akışı.
4. Mesaj optimistic send, F5 sonrası kalıcılık ve lazy history.
5. Shift+Enter, edit, delete ve attachment.
6. Voice roster reconnect.
7. Kamera + ekran aynı anda.
8. Focus/grid ve video `contain` görsel regresyon testi.

### P1 — gözlemlenebilirlik

- Caddy/tunnel/backend/Matrix health durumlarını tek admin ekranında göster.
- WebRTC `getStats()` ile:
  - bitrate,
  - packet loss,
  - RTT,
  - selected candidate type,
  - çözünürlük/FPS göster.
- Kullanıcıya teknik ham hata yerine eyleme dönük durum mesajı sun.

### P2 — mesajlaşma

- Emoji tepkileri.
- Yanıtlama/thread.
- Mesaj arama.
- Sabitlenmiş mesajlar.
- Yazıyor göstergesi.
- Okunmamış kanal sayaçları ve mention.

### P2 — güvenlik/yönetim

- Tam RBAC.
- Audit log.
- Ban/unban.
- Kanal bazlı izin.
- 2FA.
- Oturum yönetimi.
- Engelleme/raporlama.

### P3 — medya ölçekleme

- Katılımcı sayısı büyürse self-hosted SFU değerlendirmesi.
- Adaptif simulcast/SVC.
- Otomatik kalite düşürme/yükseltme.
- Kullanıcı başına yerel ses seviyesi ve susturma.

---

## 27. Hızlı sorun giderme rehberi

### Site hiç açılmıyor

Mert:

```powershell
docker compose --profile public-tunnel ps
docker compose --profile public-tunnel logs --tail 120 reverse-proxy public-tunnel
```

### Cloudflare 502

```powershell
docker compose exec -T reverse-proxy wget -qO- http://127.0.0.1:8081/healthz
```

- Yerel başarısız: Caddy/upstream/container sorunu.
- Yerel başarılı, public başarısız: Tunnel hostname/connector sorunu.

### Mesaj 403 “user not in room”

- Kullanıcının Core `ServerMember` kaydı var mı kontrol et.
- Kanal gerçekten metin kanalı mı kontrol et.
- Matrix room üyeliği onarım akışının loglarını incele.
- `messages.py`, `matrix_rooms.py`, `matrix_client.py` kaynaklarını kontrol et.
- Ham Matrix hatasını kullanıcıya göstermeden yeniden join onarımı uygulanmalıdır.

### Mesaj F5 sonrası kayboluyor

- Mesaj optimistic listede görünüp Matrix send başarısız olmuş olabilir.
- Gateway payload tek kaynak değildir; Matrix history kalıcı kaynak olmalıdır.
- `client_id`/transaction ID duplicate önlemeyi korumalıdır.
- Kanal üyeliği ve Matrix event ID doğrulanmalıdır.

### Ses “Bağlanıyor” durumunda kalıyor

- Sayfa HTTPS secure context mi?
- Mikrofon izni sonucu nedir?
- `/api/channels/{id}/voice` WSS açılıyor mu?
- `/api/voice/ice-servers` erişilebilir mi?
- ICE server endpoint başarısızsa fallback STUN devreye girmeli.
- Bağlantı sonsuza kadar spinner göstermemeli; timeout kullanıcıya anlaşılır hata vermeli.

### SDP m-line hatası

- Audio/camera/screen transceiver sırasını değiştirme.
- Her toggle'da yeni rastgele transceiver ekleme.
- Renegotiation kuyruğunu koru.
- Offer glare politikasını ve polite/initiator rolünü bozma.

### Kamera kapanınca donmuş kare

- Uzak track ended/mute durumunda video element stream'i temizlenmeli.
- Profil avatarı/baş harf fallback'i gösterilmeli.

### Yayın kırpılıyor

- `object-fit: cover` kullanılmamalı.
- Screen-share video `object-fit: contain` olmalı.
- Sabit 16:9 crop ve zorunlu capture width/height uygulanmamalı.
- Parent container `min-height: 0`, overflow ve absolute inset düzeni kontrol edilmeli.

### AI cevap vermiyor

AI bilgisayarı:

1. Ollama çalışıyor mu?
2. AI Gateway çalışıyor mu?
3. Gateway penceresi açık mı?
4. `/ai/health` doğru Bearer key ile cevaplıyor mu?

Mert:

```powershell
docker compose ps ai-worker
docker compose logs --tail 120 ai-worker backend
```

AI kapalıysa mesajlaşma/ses/web uygulaması yine çalışmalıdır.

### Müzik botu çalışmıyor

- `music` plugin kurulu mu?
- Açıkça bir bota bağlı mı?
- Bot ilgili sunucuya ekli mi?
- Parça `plugins/music/library/` içinde mi?
- Sesli kanal adı/kimliği doğru mu?
- Backend loglarında `aiortc`/PyAV yükleme hatası var mı?
- Botun voice peer olarak roster'a girdiği doğrulanmalı.

---

## 28. Kritik dosya rehberi

### Başlangıç noktaları

- `frontend/src/App.tsx`
- `backend/app/main.py`
- `docker-compose.yml`
- `docker/reverse-proxy/Caddyfile`

### Mesajlaşma

- `frontend/src/components/ChatArea.tsx`
- `frontend/src/api/client.ts`
- `backend/app/core/routers/messages.py`
- `backend/app/core/matrix_client.py`
- `backend/app/core/matrix_rooms.py`
- `backend/app/core/routers/gateway.py`

### Arkadaşlık/DM/davet

- `frontend/src/components/ProfilePanel.tsx`
- `frontend/src/components/ServerInvitesPanel.tsx`
- `frontend/src/components/JoinServerPanel.tsx`
- `backend/app/core/routers/friends.py`
- `backend/app/core/routers/direct.py`
- `backend/app/core/routers/server_invites.py`
- `backend/app/core/routers/join_codes.py`

### Ses ve medya

- `frontend/src/hooks/useVoiceChannel.ts`
- `frontend/src/hooks/useMediaDevices.ts`
- `frontend/src/hooks/usePushToTalk.ts`
- `frontend/src/components/VoicePanel.tsx`
- `frontend/src/components/VideoStage.tsx`
- `backend/app/core/routers/voice.py`

### Ayarlar ve tema

- `frontend/src/settings.ts`
- `frontend/src/components/SettingsPanel.tsx`
- `frontend/src/components/ServerSettingsPanel.tsx`
- `frontend/src/App.css`
- `frontend/src/index.css`

### Botlar ve AI

- `backend/app/bot_engine/dispatcher.py`
- `backend/app/plugins_engine/`
- `backend/app/plugins_sandbox/`
- `backend/app/services/chance_games.py`
- `backend/app/services/ollama/`
- `plugins/`
- `ai-gateway/gateway/`

### Desktop

- `frontend/src/desktopBridge.ts`
- `desktop/src/`
- `desktop/package.json`
- `docs/desktop/DESKTOP_MIGRATION_PLAN.md`

### Deployment

- `scripts/nexus-server.ps1`
- `Arkadas-Sunucuyu-Guncelle.cmd`
- `Public-Tunnel-Ayarla.cmd`
- `docs/deployment/SERVER_QUICKSTART.md`
- `docs/deployment/PUBLIC_CLOUDFLARE_TUNNEL.md`
- `docs/deployment/DOCKER_PRODUCTION.md`
- `docs/deployment/AI_WORKER.md`

---

## 29. Yeni bir görev geldiğinde önerilen çalışma sırası

1. Kullanıcı isteğini bu belgedeki uygulanmış özelliklerle karşılaştır.
2. İlgili dosyalarda `rg` ile gerçek implementasyonu bul.
3. Git çalışma ağacında kullanıcıya ait değişiklik olup olmadığını kontrol et.
4. Sorun tanı isteğiyse önce kök nedeni kanıtla; kullanıcı düzeltme istemeden kapsam dışı
   değişiklik yapma.
5. Değişiklik isteğiyse minimum ama uçtan uca çalışan değişikliği yap.
6. Backend API sözleşmesi değişiyorsa frontend tiplerini aynı turda güncelle.
7. Veritabanı modeli değişiyorsa yeni Alembic migration ekle; eski migration'ı değiştirme.
8. WebSocket/WebRTC değişikliğinde reconnect, F5, duplicate event ve iki eşzamanlı kullanıcı
   senaryolarını düşün.
9. Medya UI değişikliğinde:
   - tek kişi,
   - iki kişi,
   - dört kişi,
   - yalnız profil,
   - yalnız kamera,
   - yalnız yayın,
   - kamera+yayın,
   - focus,
   - fullscreen,
   - dar ekran senaryolarını kontrol et.
10. Mesaj UI değişikliğinde:
    - optimistic send,
    - kendi mesajında aşağı kaydırma,
    - başkasının mesajında konum koruma,
    - yeni mesaj oku,
    - F5,
    - lazy history,
    - Shift+Enter,
    - edit/delete,
    - attachment senaryolarını kontrol et.
11. Testleri çalıştır.
12. Kullanıcı açıkça isterse commit/push yap; aksi halde yerel değişikliği ve doğrulamayı raporla.
13. Yapılan önemli değişiklikleri bu devir dosyasının üst düzey güncel durumuna ekle; eski,
    çelişkili kayıtları biriktirme.

---

## 30. Son durumun kısa özeti

- Kod tabanı işlevsel bir React + FastAPI + PostgreSQL + Matrix + WebRTC iletişim platformudur.
- Mesaj, sosyal sistem, DM, attachment, bot/plugin, ses, kamera, ekran paylaşımı, kalite ayarı,
  dinamik sahne ve Electron istemcisi uygulanmıştır.
- Yerel testler güncel HEAD'de başarılıdır:
  - backend 33/33,
  - AI Gateway 9/9,
  - frontend type-check başarılı,
  - frontend production build başarılı.
- Şu anki en önemli engel uygulama kodu değil, Mert'in production Cloudflare Tunnel origin
  bağlantısındaki sürekli `502 Host Error` durumudur.
- DNS ve TLS artık doğrudur; düzeltilmesi gereken bağlantı:

```text
public-tunnel → http://reverse-proxy:8081
```

- Furkan'ın istemci tarafında yapacağı ayar yoktur.
- Yeni geliştirme başlamadan önce production erişimi ve iki kullanıcılı gerçek smoke test
  tamamlanmalıdır.
