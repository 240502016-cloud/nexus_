# Nexus — Devir Özeti ve Ana Devir Belgesi

> Bu belge yeni bir LLM sohbetine tek başına verilebilecek ana devir promptudur.
> Önce bu dosyanın tamamını oku, sonra doğrudan kaynak kodu ve canlı sunucuyu doğrula.
> Öncelik sırası: **canlı sistem → kaynak kod → bu dosya → `docs/` → eski yol haritaları**.

Son güncelleme: **5 Ağustos 2026** (VDS taşıması + kaynak bazlı ses miksi, kalite presetleri,
Nexus Lab ve görsel cila)

---

## 0. Yeni sohbete temel talimat

1. Bu dosyanın tamamını oku.
2. `git status --short --branch` ve `git log -1 --oneline` çalıştır. **Çıktıyı `head`/`tail` ile kesme** —
   bu repoda 40+ commit'lenmemiş dosya var, kesilen çıktı yanlış sonuca götürür.
3. Kullanıcının isteğini mevcut mimariye uydur; çalışan özellikleri yeniden yazma.
4. İlgisiz kullanıcı değişikliklerini silme veya geri alma.
5. `.env`, API anahtarı, Cloudflare tokeni, parola, JWT sırrı ve veritabanı yedeğini ekrana
   veya Git'e çıkarma. Bu belgeye de yazma.
6. Kullanıcı özellikle istemedikçe ücretli servis ekleme. Ana ilke:
   **kullanıcı da proje sahipleri de zorunlu abonelik veya kullanım ücreti ödemeyecek**.
7. `docker compose down -v` çalıştırma veya önerme — veri volume'larını siler.
8. **`MATRIX_SERVER_NAME` değerini asla değiştirme.** Şu an `nexus.cekin.gen.tr`. Değiştirmek tüm
   Matrix kullanıcı kimliklerini, tokenlarını ve odalarını geçersiz kılar.
9. Kod değişikliğinden sonra ilgili testleri, frontend TypeScript kontrolünü ve production build'i çalıştır.
10. Canlı sunucuda değişiklik yapmadan önce ne yapacağını söyle. Geri dönüşü zor işlemlerde onay al.

---

## 1. Projenin amacı

Nexus; Discord benzeri sunucu, kanal, arkadaşlık, özel mesaj, sesli görüşme, kamera,
ekran paylaşımı, bot, plugin ve AI deneyimleri sunan özel bir iletişim platformudur.
Discord'un birebir kopyası olmayı hedeflemez.

Temel tasarım kararları:

- Platforma özgü veriler (kullanıcı, arkadaşlık, sunucu, rol, kanal, davet, bot, plugin,
  AI deneyimleri) kendi FastAPI/PostgreSQL katmanında tutulur.
- Kalıcı metin mesajları ve birebir konuşma odaları Matrix Synapse üzerinden yürütülür.
- Ses, kamera ve ekran paylaşımı özel WebSocket signaling + WebRTC mesh ile çalışır
  (Matrix grup çağrı protokolü kullanılmaz).
- AI üretimi ücretli dış API yerine geliştiricinin kendi bilgisayarındaki Ollama üzerinden yapılır.
- Web ve Windows masaüstü istemcisi aynı React özellik ağacını paylaşır.

---

## 2. Altyapı — güncel gerçeklik

> ⚠️ Eskiden sistem iki ayrı ev bilgisayarına dağıtılmıştı ve Hamachi + Cloudflare Tunnel
> kullanıyordu. **Bunların hepsi kaldırıldı.** Eski belgelerde geçen `merte`/`nexus-server`
> yolları, Hamachi IP'leri (`25.x.x.x`), tunnel token/connector kavramları ve `502 Host Error`
> bölümü artık geçersizdir.

### Production sunucusu (VDS)

```text
IP        : 45.155.124.254
OS        : Ubuntu 24.04 LTS
Donanım   : 4 vCPU / 5.8 GB RAM (+3.1 GB swap) / 50 GB disk
Proje yolu: /opt/nexus
Erişim    : root@45.155.124.254
SSH key   : ~/.ssh/nexus_vds_migration_ed25519   (geliştirici makinesinde)
Docker    : 29.1.3 + Compose 2.40.3
```

Örnek bağlantı:

```bash
ssh -i ~/.ssh/nexus_vds_migration_ed25519 root@45.155.124.254
```

### Geliştirici / AI makinesi

```text
Yerel repo : C:\Users\mahfl\source\repos\nexus-communication-platform
Rol        : geliştirme + Ollama + AI Gateway
```

Sunucu ve bu makine **Tailscale** ile bağlıdır:

| Cihaz | Tailscale IP | Rol |
|---|---|---|
| `muter` (Windows) | `100.104.192.122` | Ollama + AI Gateway |
| `nexus-vds` (Ubuntu) | `100.125.7.124` | Production stack |

### Domain ve DNS

DNS **Cloudflare**'de yönetilir (domain kaydı inetmar'da olsa da kayıtlar Cloudflare panelinde).

```text
Zone       : cekin.gen.tr
Zone ID    : 32cd5cfb3a0548f6fcdd55e4f521ee89
Nameserver : fiona.ns.cloudflare.com / marty.ns.cloudflare.com
```

| Kayıt | Hedef | Proxy | Durum |
|---|---|---|---|
| `nexus.cekin.gen.tr` | A → 45.155.124.254 | DNS only (gri) | ✅ Canlı |
| `turn.cekin.gen.tr` | A → 45.155.124.254 | DNS only (gri) | ✅ Canlı |
| `cekin.gen.tr` (kök) | CNAME → `*.cfargotunnel.com` | proxied | ⚠️ Ölü kayıt — portal için silinecek |

> **Eski kurulumun akıbeti — KARAR VERİLDİ (5 Ağustos 2026).**
>
> Eski Nexus, ev bilgisayarında Cloudflare Tunnel üzerinden `cekin.gen.tr` kökünde çalışıyordu
> ve taşıma sırasında hâlâ canlıydı. Kullanıcı şu kararı verdi:
>
> - Aktif kullanan **yok**.
> - Oradaki hesaplar / mesaj geçmişi **önemli değil**, yedek alınmasına gerek yok.
> - Eski kurulum **tamamen kapatılacak**.
>
> Docker durduruldu; kök domain artık Cloudflare `530` (tünel origin'ine ulaşılamıyor) döner.
> Yeni sunucu bundan etkilenmez.
>
> **Not:** Docker'ı durdurmak volume'ları silmez — eski veri hâlâ ev bilgisayarının diskindedir.
> Fikir değişirse `docker compose down -v` çalıştırılmadığı sürece kurtarılabilir.
> Ayrıca dikkat: Git ve yerel kopya **kodu** içerir, çalışma zamanı verisini (PostgreSQL,
> Matrix odaları, attachment/avatar volume'ları) içermez.

Kök domain portal için ayrılmıştır. Portal hazır olduğunda `cfargotunnel` CNAME'i silinip A kaydına
çevrilecektir (apex'te CNAME ile A birlikte olamaz). Eski kurulum zaten kapalı olduğu için bu işlem
artık kimseyi etkilemez.

Hedeflenen son yapı:

```text
cekin.gen.tr         → Hub / portal (ana projelerin listesi)
nexus.cekin.gen.tr   → Nexus (ana proje, hep açık)
turn.cekin.gen.tr    → coturn
<proje>.cekin.gen.tr → diğer projeler (yalnız açıldığında çalışır)
```

Bu yapı mevcut kurulumla uyumludur: Nexus baştan alt alan adına kurulduğu için `MATRIX_SERVER_NAME`
değiştirmeye gerek kalmaz.

**Proxy neden gri olmalı:** turuncu bulut TURN'ün UDP trafiğini taşımaz ve TLS akışını karıştırır.
İleride web için turuncuya alınırsa `turn` alt alanı gri kalmalıdır.

### TLS

Caddy, **Cloudflare DNS-01** ile Let's Encrypt sertifikası alır. `docker/reverse-proxy/Dockerfile`
Caddy'ye `caddy-dns/cloudflare` eklentisini gömer. Bu yüzden `.env` içinde `CLOUDFLARE_API_TOKEN`
**zorunludur** (Zone:DNS:Edit yetkisi, yalnız `cekin.gen.tr` zone'u için kapsamlı).

DNS-01 seçimi ileride **wildcard sertifika** (`*.cekin.gen.tr`) almayı mümkün kılar — portalın
"her projeye bir subdomain" tasarımı bunu gerektirir.

### Açık portlar (UFW aktif)

```text
22/tcp                  SSH
80/tcp, 443/tcp+udp     HTTP / HTTPS / HTTP3
3478/tcp+udp            TURN
50000-50040/tcp+udp     TURN relay aralığı
```

Cloudflare Tunnel olmadığı için **TURN artık gerçekten UDP taşır** — eski kurulumda hiç
sahip olunmayan bir yetenek.

### Boot dayanıklılığı

- Tüm container'lar `restart: unless-stopped`
- `docker.service` boot'ta enabled
- Ek güvenlik ağı: `/etc/systemd/system/nexus.service` (enabled), `docker compose up -d` çalıştırır

---

## 3. Git durumu — dağıtılan vs. devam eden

### Remote ve branch

```text
origin  https://github.com/240502016-cloud/nexus_.git
branch  cekingen
```

### Sunucuda çalışan sürüm

```text
0034708  Add per-listener audio mixing, higher media quality and Nexus Lab
DB revizyonu: 0015_user_auth_version   (değişmedi — bu commit şemaya dokunmaz)
```

Bu commit **yalnız** kaynak bazlı ses miksi, kalite presetleri, Nexus Lab ve görsel cilayı
içerir. Dört AI oyun modülü, `0016`–`0019` migration'ları ve yerel test ortamı bilinçli olarak
dışarıda bırakıldı (bkz. aşağıdaki bölüm). Geri alma noktası: `2aa6ce3`.

### ⚠️ Yerelde commit'lenmemiş, DAĞITILMAMIŞ çalışma

Geliştirici bu modüller üzerinde **hâlâ çalışıyor**; kullanıcı açıkça istemedikçe bunları
commit etme, push etme veya sunucuya dağıtma.

Yeni modüller (untracked):

```text
backend/app/modules/ai_board_game/
backend/app/modules/ai_escape_room/
backend/app/modules/hidden_role_game/
backend/app/modules/shared_story/
backend/alembic/versions/0016_ai_board_game.py
backend/alembic/versions/0017_hidden_role_game.py
backend/alembic/versions/0018_shared_story.py
backend/alembic/versions/0019_ai_escape_room.py
frontend/src/components/{BoardGame,EscapeRoom,HiddenRoleGame,PartyLore,RoastBattle,SharedStory}Panel.tsx
backend/app/platform/crypto.py
backend/tests/test_{ai_board_game,ai_escape_room,hidden_role_game,shared_story}.py
docker-compose.local.yml, Yerel-Test-*.cmd, scripts/*local-dev*, docs/LOCAL_HUMAN_TEST.md
```

Değişmiş (modified) dosyalar arasında: `backend/app/main.py`, `backend/app/config.py`,
`backend/app/platform/worker.py`, `backend/app/modules/ai_roast_battle/{router,service}.py`,
`backend/app/modules/party_lore/service.py`, `frontend/src/{App.tsx,App.css,types.ts,api/client.ts}`.

> **5 Ağustos 2026 çalışması dağıtıldı** (`0034708`): kaynak bazlı ses miksi, kalite presetleri,
> Nexus Lab ve görsel cila. Şemaya dokunmadığı için migration çalıştırılmadı.

**Sonuç:** Yerelde migration zinciri `0019`'a kadar gider, sunucuda `0015`'te durur. Bu bir hata
değil, bilinçli durumdur.

### Nexus Lab'in dağıtılmamış modüllerle ilişkisi

Lab dokuz modülü de **kod olarak** içerir, ancak `LabApp.tsx` içindeki `released` bayrağı
backend'i sunucuda çalışmayanları production build'de gizler:

| Modül | `released` | Neden |
|---|---|---|
| Highlight, Meme, AI Yorumcu | `true` | Backend'leri `0015`'te mevcut ve değişmedi |
| Party Lore, Roast Battle | `false` | Backend modülü sunucuda var ama servisi **ve** paneli yerelde birlikte değişti; ikisi birden dağıtılmalı |
| Son Portal, Üç Mühür, Ortak Hikâye, Escape Room | `false` | Backend modülü ve `0016`–`0019` migration'ları hiç dağıtılmadı |

Geliştirmede (`import.meta.env.DEV`) hepsi görünür — `docs/LOCAL_HUMAN_TEST.md` ortamı tam da
bunun için var. Production'da geçici olarak açmak gerekirse `VITE_LAB_UNRELEASED=1` ile build alınır.

**Bir modülün backend'i dağıtıldığında yapılacak tek şey:** `LabApp.tsx` içinde o modülün
`released` değerini `true` yapmak. Başka değişiklik gerekmez.

> ⚠️ `backend/app/main.py` yereldeki dört modülün router'ını **koşulsuz** import eder. Yani
> backend'i olduğu gibi dağıtmak dört modülü ve `0016`–`0019` migration'larını da zorunlu olarak
> canlıya taşır. Kısmi dağıtım isteniyorsa `main.py` staged edilmemelidir.

---

## 4. Teknoloji yığını

### Web frontend
React `18.3` · TypeScript `5.6` · Vite `5.4` · düz CSS + CSS custom property tema sistemi ·
React hook'ları ve localStorage tabanlı istemci durumu · **global state framework yok**

### Backend
Python · FastAPI `0.115+` · Uvicorn · SQLAlchemy `2.x` · Pydantic `2.x` · Alembic ·
`psycopg2-binary` · `PyJWT` · `python-multipart` · `requests` · `aiortc` (müzik botu WebRTC)

### Veritabanı ve mesajlaşma
PostgreSQL `16.14-alpine` · Matrix Synapse `1.153.0`
Synapse aynı PostgreSQL container'ında ayrı kullanıcı ve ayrı veritabanı kullanır.

### Gerçek zamanlı
Global WebSocket `/api/gateway` · ses signaling `/api/channels/{id}/voice` · WebRTC mesh ·
`RTCPeerConnection`/`getUserMedia`/`getDisplayMedia` · STUN (Cloudflare + Google yedek) ·
kendi coturn `4.6.3` servisi · Web Audio API ile konuşma seviyesi algılama

### AI
Ayrı Python/FastAPI AI Gateway · uzak Ollama (Tailscale üzerinden) · `httpx` ·
Bearer API key + CIDR kontrolü · PostgreSQL kalıcı AI job kuyruğu · ayrı `ai-worker` ve
`media-worker` process'leri · SSE streaming ve cooperative iptal

### Masaüstü
Electron `43` · Electron Builder · NSIS · `electron-updater` · `uiohook-napi` (global PTT) ·
Electron `safeStorage` / Windows DPAPI

### Altyapı
Docker + Compose · Caddy `2.11.4` (Cloudflare DNS eklentili özel image) · ffmpeg/ffprobe
(highlight render) · PowerShell ve `.cmd` yönetim araçları

---

## 5. Monorepo yapısı

```text
nexus-communication-platform/
├── frontend/
│   ├── index.html      Ana istemci giriş belgesi
│   ├── lab.html        Nexus Lab giriş belgesi (ayrı pencere, ayrı chunk)
│   ├── nginx.conf      Statik servis + /lab yönlendirmesi
│   └── src/
│   ├── api/            REST istemcisi ve retry davranışı
│   ├── components/     UI bileşenleri
│   ├── hooks/          Gateway, WebRTC, PTT, medya cihazları
│   ├── lab/            Nexus Lab kabuğu (main.tsx, LabApp.tsx, lab.css)
│   ├── App.tsx         Ana uygulama orkestrasyonu
│   ├── App.css         Ana düzen, bileşen stilleri ve sondaki görsel cila katmanı
│   ├── index.css       Global tema ve reset
│   ├── settings.ts     Kalıcı kullanıcı ayarları
│   ├── notifications.ts
│   ├── messageContent.ts
│   ├── desktopBridge.ts  Web/Electron soyutlama katmanı
│   └── types.ts
│
├── backend/app/
│   ├── core/
│   │   ├── routers/    auth, users, servers, channels, members, messages,
│   │   │               friends, direct, attachments, plugins, bots,
│   │   │               server_invites, join_codes, voice, gateway
│   │   ├── models.py, schemas.py, auth.py, authz.py, permissions.py
│   │   ├── matrix_client.py, matrix_rooms.py
│   ├── modules/        AI deneyim modülleri (bkz. §9)
│   ├── platform/       Paylaşılan deneyim/olay/job/medya altyapısı
│   │                   (crypto, events, jobs, models, router, schemas, sessions, worker)
│   ├── bot_engine/     Mesaj komut dispatcher'ı
│   ├── plugins_engine/ Plugin manifest/yükleme/sandbox
│   ├── plugins_sandbox/ İzole plugin çalıştırma servisi
│   ├── services/ollama/ AI client, worker, job ve token mantığı
│   ├── services/chance_games.py
│   ├── database.py, config.py, main.py
│
├── ai-gateway/gateway/{main,security,config}.py
├── desktop/            Electron main/preload/mini pencere
├── plugins/            ai_assistant, chance_games, game_status, moderation, music, server_monitor
├── matrix/             Synapse image ve yapılandırma üretimi
├── docker/{postgres,matrix,reverse-proxy}/
├── scripts/            Sunucu, backup, restore, firewall, AI gateway araçları
├── docs/{architecture,deployment,desktop}/
└── docker-compose.yml
```

### Önemli frontend bileşenleri

`ChatArea.tsx` (kanal mesajları, lazy loading, optimistic send, edit/delete, ekler) ·
`VideoStage.tsx` (dinamik medya sahnesi, focus, grid, fullscreen) · `VoicePanel.tsx` ·
`SettingsPanel.tsx` · `ProfilePanel.tsx` · `ServerSettingsPanel.tsx` · `ServerInvitesPanel.tsx` ·
`JoinServerPanel.tsx` · `MembersPanel.tsx` · `ServerRail.tsx` · `AttachmentCard.tsx`

### Önemli frontend hook'ları

`useGateway.ts` (presence, mesajlar, çağrılar, sosyal olaylar, reconnect) ·
`useVoiceChannel.ts` (signaling, peer bağlantıları, medya track'leri, ICE kurtarma) ·
`useMediaDevices.ts` · `usePushToTalk.ts`

---

## 6. Çalışma zamanı mimarisi

```text
Kullanıcı
    │ HTTPS + WSS
    ▼
Cloudflare DNS (gri bulut — sadece isim çözümleme)
    │
    ▼
45.155.124.254 : 443
    │
    ▼
Caddy reverse-proxy
    ├── /                 → frontend:8080
    ├── /api/*            → backend:8000
    ├── /_matrix/*        → matrix:8008
    ├── /healthz          → "ok"
    └── WebSocket Upgrade → backend

Backend
  ├── PostgreSQL      platform verileri, oyunlar, AI işleri
  ├── Matrix Synapse  kalıcı kanal/DM mesajları
  ├── plugin-sandbox  güvenilmeyen pluginler
  ├── ai-worker       kalıcı AI kuyruğu tüketicisi
  ├── media-worker    highlight/medya render kuyruğu
  └── AI Gateway      Tailscale → geliştirici makinesi → Ollama

Ses/kamera/ekran:
  İstemci ── WebSocket signaling ── Backend
  İstemci ═════ WebRTC medya ═════ Diğer istemci
                gerekirse coturn relay (turn.cekin.gen.tr:3478)
```

---

## 7. Docker Compose servisleri

### Kalıcı servisler

| Servis | Görev | Notlar |
|---|---|---|
| `postgres` | Platform + Synapse veritabanları | Host'a port yayınlamaz, `data` internal ağı |
| `matrix` | Matrix Synapse | Ayrı PostgreSQL kullanıcı/DB |
| `backend` | FastAPI Core API | app/data/sandbox ağları, root FS read-only |
| `frontend` | Vite production çıktısı | |
| `reverse-proxy` | Caddy | 80/443 + Docker içi 8081 |
| `turn` | coturn STUN/TURN | 3478 + relay aralığı |
| `plugin-sandbox` | İzole plugin çalıştırma | read-only FS, capability drop, CPU/RAM/PID limitleri, yalnız `sandbox` ağı |
| `ai-worker` | AI job tüketicisi | backend image'ı, ayrı process |
| `media-worker` | Medya/highlight render kuyruğu | ffmpeg kullanır |

### Tek seferlik servisler

- `postgres-bootstrap` — DB kullanıcı/veritabanlarını idempotent hazırlar
- `migrate` — `alembic upgrade head`
- `media-storage-init` — avatar/attachment volume sahipliğini veri silmeden düzeltir

### Kullanılmayan servis

- `public-tunnel` — Cloudflare Tunnel connector'ı. **Artık kullanılmıyor.** `public-tunnel`
  profili altında olduğu için normal `docker compose up -d` ile başlamaz. İleride
  compose'dan tamamen kaldırılabilir.

### Ağlar

`app` (frontend/backend/matrix/Caddy) · `data` (internal PostgreSQL) · `sandbox` (internal plugin izolasyonu)

### Kalıcı volume'lar

```text
postgres_data      ← kullanıcı verisi
matrix_data        ← kullanıcı verisi
avatar_data        ← kullanıcı verisi
attachment_data    ← kullanıcı verisi
postgres_socket, postgres_backups, caddy_data, caddy_config
```

İlk dört volume bilinçsizce silinmemelidir.

---

## 8. Veritabanı ve migration

Sunucudaki güncel head: **`0015_user_auth_version`**

```text
0001_initial_schema        0009_platform_foundation
0002_ai_jobs               0010_party_lore
0003_ai_bot_jobs           0011_ai_commentator
0004_ai_stream_cancel      0012_meme_generator
0005_chance_games          0013_highlight_generator
0006_social_graph          0014_ai_roast_battle
0007_server_invites        0015_user_auth_version
0008_server_join_codes
```

Yerelde ek olarak (dağıtılmamış): `0016_ai_board_game`, `0017_hidden_role_game`,
`0018_shared_story`, `0019_ai_escape_room`.

Başlıca Core modelleri: `User`, `Friendship`, `Server`, `ServerMember`, `ServerInvite`,
`ServerJoinCode`, `Channel`, `Role`, `Plugin`, `Bot`, `BotServerLink`, `BotPluginLink`,
`ChanceGameSession`, `ChanceWheel`

AI modelleri: `AiConversation`, `AiMessage`, `AiJob`, `AiBotJob`, `AiTokenUsage`

Mesaj gövdeleri Matrix'te; sunucu/kanal ilişkileri ve Matrix oda kimlikleri Core veritabanındadır.

**Kural:** Veritabanı modeli değişiyorsa yeni migration ekle, eskisini değiştirme.

---

## 9. AI mimarisi ve deneyim modülleri

### Akış

```text
Kullanıcı mesajı → FastAPI Core → ai_jobs/ai_bot_jobs (queued)
    → ai-worker → HTTP + Bearer → AI Gateway (Tailscale) → Ollama
```

### Özellikler

- AI job'ları PostgreSQL'de kalıcıdır; API process'i model üretirken bloklanmaz.
- Worker lease + `SKIP LOCKED` kullanır; lease süresi dolan iş tekrar alınabilir.
- Geçici Gateway hataları sınırlı exponential backoff ile denenir; model/auth/config
  hataları kalıcı `failed` olur.
- `Idempotency-Key` duplicate prompt'u önler. Bot cevaplarında Matrix transaction ID
  job kimliğinden türetilir.
- SSE: `GET /api/ai/jobs/{job_id}/stream`, `POST /api/ai/jobs/{job_id}/cancel` (cooperative iptal).
- Ücretli OpenAI/Anthropic API zorunluluğu yoktur.
- **AI Gateway kapalıysa yalnız AI özellikleri pasifleşir**; mesaj, ses ve medya etkilenmez.

### AI Gateway

Geliştirici makinesinde çalışan ayrı FastAPI uygulamasıdır.

```text
Adres      : http://100.104.192.122:8090   (Tailscale)
Uçlar      : /ai/health, /api/tags, /api/chat
Config     : ai-gateway/.env               ← ASIL DOSYA
```

> ⚠️ **Tuzak:** `ai-gateway/` klasöründe hem `.env` hem `ai-gateway.env` vardır.
> `gateway/config.py` `env_file=".env"` kullanır — yani **`.env` okunur**, `ai-gateway.env` değil.
> Yalnız `ai-gateway.env`'i düzenlemek hiçbir işe yaramaz.

Anahtarlar (değerleri buraya yazma):

| ai-gateway/.env | sunucu /opt/nexus/.env | İlişki |
|---|---|---|
| `AI_GATEWAY_API_KEY` | `OLLAMA_API_KEY` | **Aynı olmalı** (64 karakter) |
| `AI_GATEWAY_ALLOWED_NETWORKS` | — | `100.125.7.124/32` içermeli (sunucunun Tailscale IP'si) |
| `OLLAMA_BASE_URL=http://127.0.0.1:11434` | `OLLAMA_BASE_URL=http://100.104.192.122:8090` | |

Gateway en az 32 karakterlik API key ve en az bir CIDR ağı ister (`validate_runtime`).

Başlatma:

```powershell
.\ai-gateway\start-gateway.ps1 -HostAddress 100.104.192.122 -Port 8090
```

Yüklü Ollama modelleri: `qwen3-coder:30b`, `gpt-oss:20b`, `qwen2.5:7b`
(`.env` varsayılanı `qwen2.5:7b`).

> **Bilinen eksik:** Gateway şu an Windows'ta kalıcı servis/scheduled task olarak
> kayıtlı değildir; bilgisayar yeniden başlayınca elle açılması gerekir.

### Dağıtılan deneyim modülleri (`backend/app/modules/`)

`main.py` içinde router'ları kayıtlı olanlar:

- `party_lore` — onay öncelikli (consent-first) parti anısı çıkarımı
- `ai_commentator` — canlı yorumcu
- `meme_generator` — meme metni/görsel üretimi
- `highlight_generator` — ffmpeg tabanlı kayıt/render pipeline'ı
- `ai_roast_battle` — onay öncelikli roast battle

Ortak altyapı `backend/app/platform/` içindedir (deneyim/olay/job/medya/oturum).

Her modülün tasarım notu ve promptları `docs/architecture/<modül-adı>/` altındadır.

### Dağıtılmamış modüller

`ai_board_game`, `hidden_role_game`, `shared_story`, `ai_escape_room` — kod ve migration'ları
yerelde mevcut, sunucuda yok. Geliştirme devam ediyor.

---

## 10. Kimlik doğrulama, hesap ve güvenlik

- JWT tabanlı login; endpoint'lerde kimlik Bearer token'dan alınır.
- Sunucu sahipliği ve üyelik backend'de doğrulanır.
- Parola hash'i: PBKDF2-SHA256, salt + yüksek iterasyon. Düz metin tutulmaz ve
  **sistemden çıkarılamaz**, yalnız reset edilebilir.
- Parola değişince eski access token'lar geçersizleşir (`0015_user_auth_version`).
- Avatar yükleme: magic-byte MIME kontrolü, 2 MB sınırı, rate limit, path traversal koruması,
  eski avatar temizliği, istemcide kare kırpma ve 256px çıktı.
- Login rate limit'i istemci adresi **+ kullanıcı adı** ayrımı yapar; aynı reverse proxy
  arkasındaki kullanıcılar birbirinin limitini tüketmez.
- Login/register geçici `502/503/504`, timeout ve bağlantı kopmalarında sınırlı yeniden denenir.
- Register aynı username/e-posta/parola için idempotenttir.

### Masaüstü token güvenliği

Web sürümü localStorage kullanır. Electron'da token localStorage'a yazılmaz; Windows DPAPI
tabanlı `safeStorage` ile şifrelenir. `nodeIntegration` kapalı, `contextIsolation` ve renderer
sandbox açık, preload IPC yüzeyi allowlist ile sınırlı. Paketli uygulama uzak sayfayı privileged
renderer olarak açmaz; `nexus://app` yerel origin'inden çalışır.

### Gizli veri kuralları

- `.env` ve `ai-gateway/.env` Git'e gönderilmez.
- Cloudflare API tokeni, AI Gateway API key ve TURN auth secret paylaşılmaz.
- `.env.bak.*`, dump ve backup dosyalarının gitignore'da olduğu push öncesi doğrulanmalıdır.
- Kullanıcı istese bile parola/secret devir belgesine yazılmaz.

---

## 11. Sunucu, kanal, üye ve davet sistemi

**Sunucular:** oluşturma, ad/açıklama düzenleme, ayrılma, silme, üye çıkarma. Sahip korunur.
Sol sunucu şeridi dar/kapalı başlar; fare veya klavye fokusuyla açılır.

**Kanallar:** metin/ses ayrımı var. Oluşturma, yeniden adlandırma, silme.
Ses kanalları mesaj odası değildir — yeni ses kanalı için Matrix text room oluşturulmaz ve
eski ses kanallarında mesaj gönderme/listeleme backend tarafından reddedilir.

**Üye görünümü:** insan üyeler geniş masaüstünde sağdaki sabit grid kolonunda; dar ekranda
sağdan overlay olarak açılır ve sol rail/kanal paneli/toolbar/sahne/chat koordinatlarını
değiştirmez. Botlar insan listesinden ayrıdır. Küçük sunucular hedeflenir (~7–8 kullanıcı).
Durum noktaları çevrimiçi/boşta/rahatsız etmeyin/görünmez gösterir.

**Hedefli davetler:** serbest kullanıcı adı yazılarak gönderilmez; sahip kabul edilmiş
arkadaşlardan seçer. Alıcıda Kabul/Reddet, gönderende İptal vardır. Kabulde `ServerMember`
oluşur, varsayılan rol atanır, Matrix oda üyelikleri hazırlanır. Sol şeritte bekleyen davet sayacı vardır.

**Paylaşılabilir katılım kodu:** 16 karakterli kalıcı kod, `https://nexus.cekin.gen.tr/?invite=<kod>`.
Arkadaşlık gerektirmez. Katılım idempotenttir. PostgreSQL üyeliği Matrix senkronundan **önce**
yazılır; Matrix geçici kapalıysa kullanıcı yine sunucuyu ve ses kanallarını görür, metin odası
üyeliği sonradan onarılır. Kod yalnız sahip tarafından görüntülenir/yenilenir/iptal edilir.
Deneme limiti: kullanıcı başına dakikada 12.

---

## 12. Arkadaşlık, profil ve özel mesajlaşma

- Profil merkezi: hesap özeti, arkadaşlar, gelen/giden istekler, birebir konuşmalar.
- Kullanıcı arama ile istek gönderme; kabul, ret, iptal, arkadaş çıkarma.
- İsteklerin süre sonu yoktur; kullanıcı işlem yapana kadar PostgreSQL'de kalır.
- İstek mutasyonları idempotenttir; aynı istek çoğalmaz.
- Gateway canlı olayı kaçarsa panel 15 saniyelik uzlaştırma ile kalıcı API durumunu yeniden çeker.
- Birebir konuşmalar kalıcı Matrix odalarıdır; eski mesajlar cursor ile sayfalanır.
- DM kutusu da Enter/Shift+Enter, dinamik büyüme, edit ve ek özelliklerini paylaşır.

---

## 13. Mesajlaşma sistemi

### Kalıcılık ve geçmiş

Metin mesajları Matrix'te kalıcıdır ve sayfa yenilendiğinde kaybolmamalıdır. Geçmiş cursor ile
50'şer yüklenir; yukarı gidildikçe lazy-load ile daha eski sayfa çekilir. Uzun listelerde
`content-visibility` çizim maliyetini düşürür. Kullanıcı odada eksikse mesaj okuma/gönderme
sırasında otomatik davet+join ile üyelik onarılır. Yeni metin kanalında mevcut üyeler odaya eklenir.

### Gerçek zamanlı teslim

`channel-message` gateway payload'ı ile anında iletilir; eski 4 saniyelik polling ana yol değildir
(gateway bağlıyken düşük frekanslı snapshot yalnız güvenlik ağıdır, sekme durumuna göre seyrekleşir).
Gönderim istemcide optimistic görünür; `client_id` Matrix transaction ID olarak kullanılır, böylece
timeout/retry'de duplicate önlenir.

### Kaydırma davranışı

- Kullanıcı kendi mesajını gönderince sohbet kesin olarak en alta iner.
- Başkası gönderdiğinde: kullanıcı aşağıdaysa yeni mesaja gider, eski geçmişi okuyorsa konumu bozulmaz
  ve sağ altta dairesel aşağı ok görünür.
- **Bu aşağı ok uygulama içi genel bildirim sayılmaz ve kaldırılmamalıdır.**

### Düzenleme, silme, yanıt

Düzenleme Matrix `m.replace` ile saklanır ve orijinalle birleştirilir (ayrı mesaj gibi gösterilmez).
Silme Matrix redaction uygular. İkonlar küçük, ortak modern SVG setindedir.
Alıntılı yanıt `m.in_reply_to` ile kalıcıdır; önizleme optimistic gönderimde, gateway olayında ve
F5 sonrası korunur. Önizlemeye tıklayınca hedef mesaj yüklü sayfadaysa ona kayılır.

### Reaksiyon, mention, unread, typing, arama, pin

- Reaksiyonlar `m.reaction`/`m.annotation` ile kalıcı; aynı emojiye tekrar basmak redaction ile kaldırır.
  UI optimistic güncellenir, sonra Matrix özeti ve `channel-message-meta` olayıyla uzlaştırılır.
- `@kullanıcı` yazarken üyeler önerilir; `m.mentions` F5 sonrası korunur. Mention vurgulanır,
  bildirimi ayarlardan kapatılabilir.
- Unread sayaçları kullanıcı kimliğiyle localStorage'da; kanala girince temizlenir, F5 sonrası korunur.
  **Eksik:** uygulama tamamen kapalıyken kaçan mesajlar için Matrix receipt tabanlı server-side unread yok.
- Typing yalnız gateway belleğinde (DB'ye yazılmaz), 750 ms throttle, istemcide 4,5 sn otomatik süre sonu.
- Arama Matrix `/search` üzerinden; ayrı arama servisi yok.
- Pin'ler `m.room.pinned_events` state'inde, en fazla 50 gösterilir, `MANAGE_MESSAGES` izniyle denetlenir.

### Çok satırlı mesaj

Enter gönderir, Shift+Enter yeni satır açar. Textarea içeriğe göre dinamik büyür (~8 satıra kadar),
sonra kendi içinde kaydırılır. Manuel resize kapalıdır; içerik boşalınca uzun placeholder'dan
etkilenmeden tek satırlık minimum yüksekliğe döner.

### Görsel gruplama

Kanal adı birleşik üst barda olduğu için mesaj listesi üzerindeki ikinci `Chat` başlığı kaldırılmıştır.
Aynı gönderenin 5 dakika içinde, aynı takvim gününde gönderdiği ardışık düz metin mesajları
**yalnız görsel olarak** gruplanır; ad ve saat yalnız ilk mesajda görünür. Gönderen/gün değişimi,
5 dakikayı aşan süre, bot/oyun mesajı, reply ve attachment yeni grup başlatır. Matrix event kimlikleri
ve ayrı reaction/edit/delete/pin aksiyonları birleştirilmez.

### Dosya ve fotoğraf

Kanal ve DM'lerde yükleme var, üst sınır 25 MB, `attachment_data` volume'unda kalıcı.
Resimler lazy-load önizlenir, diğerleri güvenli indirme kartı olur. Backend image `/srv/avatars`
ve `/srv/attachments` dizinlerini `nexus` kullanıcısına ait oluşturur; `media-storage-init`
mevcut root sahipli dizinleri veri silmeden düzeltir. File input'lar seçimden sonra temizlenir
(aynı dosya yeniden seçilebilir); kanal yüklemesi başarısız olursa açıklama, yanıt hedefi ve
seçili dosya composer'a geri yüklenir.

### Spam/rate limit

Synapse normal mesaj limiti ~5 mesaj/sn ve 50 burst olacak şekilde gevşetilmiştir.
Bot komut limiti 10 saniyede 20 komuttur.

---

## 14. Bildirimler ve durumlar

Durumlar: çevrimiçi, boşta, rahatsız etmeyin, görünmez, özel durum metni.
Durum ve özel durum **ana araç çubuğunda değil, Ayarlar'dadır**.

- Eski sağ üst mesaj toast/kenar bildirimleri kaldırılmıştır; yeni mesaj aşağı oku korunmuştur.
- Sekme arka plandaysa kısa mesaj sesi ve izin varsa OS/tarayıcı bildirimi.
- Gelen çağrı için zil ve masaüstü bildirimi.
- **Rahatsız Etmeyin** mesaj ve çağrı bildirimlerinin tamamını bastırır.
- Bildirim sesi Ayarlar'dan açılıp kapatılabilir. Electron native Windows bildirimi kullanabilir.

---

## 15. Sesli sohbet ve WebRTC

### Topoloji

Signaling: `/api/channels/{channel_id}/voice`. Medya backend üzerinden geçmez; peer'ler arasında
WebRTC ile taşınır. Backend join/leave, offer/answer, ICE, mute, speaking ve roster olaylarını relay eder.
Mesh olduğu için katılımcı arttıkça istemci CPU/upload maliyeti artar.

### Oturum yaşam döngüsü

Metin kanalına (hatta başka sunucunun kanalına) geçmek sesli görüşmeden çıkarmaz. Oturum yalnız
kullanıcı açıkça ayrılırsa, başka ses kanalına geçerse, atılırsa veya pencere kapanırsa biter.
Backend ses bağlantılarını session kimliğiyle ayırır; kullanıcının kendi peer listesine girmesi engellenir.
F5/hızlı reconnect sırasında eski WebSocket'in yeni oturumu roster'dan silmesine yol açan yarış giderilmiştir.
Aynı hesabın birden çok sekme/cihaz oturumu signaling sahipliği için yarışmaz: en yeni oturum etkin kalır,
eski WebSocket `4409` ile kapatılır ve eski istemci otomatik yeniden bağlanmaz.

### Mikrofon ve dinleme

- Mikrofon izni reddedilse bile dinleyici olarak katılmak mümkündür (`recvonly` audio transceiver).
- Mikrofon toggle + deafen. Durum tüm peer'lere yansıtılır.
- Hoparlör seçimi `setSinkId` destekleyen Chrome/Edge'de çalışır.
- Gürültü bastırma / echo cancellation / auto gain gerçek `MediaTrackConstraints` ile uygulanır.
  Gürültü engelleme açıkken 80 Hz high-pass + yumuşak compressor da devreye girer.
- Mikrofon giriş seviyesi %0–200 (%100 üzeri yazılımsal yükseltme).
- **Uzak dinleme %0–100'dür ve WebRTC stream'i doğrudan `HTMLAudioElement` üzerinden oynatılır.**
  Geçmişte uzak sesi ikinci bir `AudioContext → MediaStreamDestination → HTMLAudioElement` zincirinden
  geçiren alıcı hattı iki tarafın da sessiz kalmasına yol açmıştı; o hat ve %101–200 aralığı kaldırıldı.
- Görüşme sırasında mikrofon değişimi `replaceTrack` ile bağlantı kesmeden yapılır.
- Suspend edilen giden Web Audio context'i görünürlük veya bir sonraki gerçek kullanıcı etkileşiminde
  yeniden çalıştırılır. Uzak `audio.play()` autoplay engeline takılırsa hata yutulmaz; kullanıcıya
  sayfaya tıklama yönlendirmesi gösterilir.
- Audio sender offer/answer ve `connected` sonrasında mevcut miks track'iyle yeniden doğrulanır;
  uzak oynatım `track.unmute`, SDP tamamlanması ve kullanıcı etkileşiminde tekrar çalıştırılır.
  **Yeni transceiver veya m-line oluşturulmaz.**

### Kaynak bazlı ses miksi (dinleyici başına ayrı miks)

Mikrofon, soundboard ve yayın sesi hâlâ **tek** WebRTC audio m-line'ında taşınır. Buna rağmen
dinleyici üç kaynağı ayrı ayrı ayarlayabilir; çünkü miksi dinleyici değil **yayıncı** üretir.

```text
mic → [high-pass → compressor] → gain (mikrofon ana seviyesi)  ─┐
soundboardGain (soundboard ana seviyesi)                        ├→ her dinleyici için:
screenGain (yayın sesi ana seviyesi)                            ┘   voiceGain / soundboardGain /
                                                                     streamGain → MediaStreamDestination
```

- Yayıncı tarafında `OutgoingAudioGraph.peerMixes`: dinleyici kimliği → `PeerAudioMix`.
  Her dinleyici kendi `MediaStreamDestination`'ından beslenir; giden track sayısı yine
  eş başına birdir.
- Dinleyici tercihi `audio-mix` signaling mesajıyla iletilir:
  `{type, to, voice?, soundboard?, stream?}`, her değer 0–200. Backend `_audio_mix_payload`
  ile doğrular ve 0–200 aralığına sıkıştırır; `from` alanını sunucu yazar.
- Tercih `nexus.peerAudioMix` altında localStorage'da kalıcıdır ve katılım/reconnect sonrası
  `announceAudioMix` ile yeniden bildirilir.
- Yayıncının kendi "yayın sesi" ana seviyesi ve aç/kapa düğmesi `VoicePanel`'dedir;
  mikrofonundan ve soundboard'ından bağımsızdır.
- **Ekran aboneliği artık track değiştirmez.** "Yayını izleme" denince eskiden sender track'i
  değişip yeniden pazarlık tetiklenebiliyordu; şimdi yalnız o dinleyicinin `streamGain`
  değeri 0'a iner. SDP, transceiver sırası ve m-line sayısı bu yoldan hiç etkilenmez.
- Giden ses hattı hiç kurulmadıysa (mikrofon izni yok, soundboard ve yayın sesi de yok)
  davranış eskisi gibidir: track `null` olur ve audio transceiver `recvonly` kalır.
- Ses bitrate tavanı `setParameters` ile ayarlanır (SDP'ye dokunulmaz): yalnız konuşma
  varken 64 kbit/sn, yayın sesi mikse girince ve ayar açıkken 160 kbit/sn.

### Push-to-talk

Web'de sekme odaktayken özelleştirilebilir PTT vardır; metin alanına yazarken tetiklenmez,
sekme blur olunca bırakılır. Tarayıcı güvenlik modeli nedeniyle başka uygulama ön plandayken
global PTT mümkün değildir. Electron global key hook ile Mouse4/Mouse5, Ctrl/Alt/CapsLock ve
kombinasyonları destekler.

### Çağrı daveti

Global gateway üzerinden `call-invite`/accept/reject/cancel. Üye listesinden çağrı, gelen çağrı
modalı, zil sesi ve arka plan bildirimi. Rahatsız Etmeyin çağrı bildirimini bastırır.

### Reconnect ve dayanıklılık

Gateway ve voice WebSocket jitter'lı exponential backoff kullanır (ilk retry ~250 ms).
ICE yapılandırması erişilemezse Cloudflare/Google STUN yedeğiyle katılım sürer.
Kısa ICE kopmalarında otomatik ICE restart yapılır. Kapanan bağlantıların beklenen
`connection aborted` hatası kullanıcıya ham gösterilmez. SDP mesajları sırayla işlenir;
offer glare/rollback giderilmiştir. **İlk teklifi yalnız kanala yeni katılan taraf üretir.**
Kamera/ekran aç-kapa renegotiation'ları kuyruklanır.

**Audio, camera ve screen transceiver/m-line sırası sabittir.** Bu sıra bozulursa şu hata döner:

```text
Failed to set remote offer sdp:
The order of m-lines in subsequent offer doesn't match order from previous offer/answer
```

---

## 16. Kamera, ekran paylaşımı ve medya sahnesi

### Eşzamanlılık

Kamera ve ekran paylaşımı ayrı, sırası sabit transceiver'lardır; ikisi aynı anda açık olabilir ve
birini kapatmak diğerini kesmez. Kamera kapanınca son kare donmuş kalmaz — durum eşlere ayrıca
`video-state` sinyaliyle iletilir, böylece tarayıcı `replaceTrack(null)` sonrası son kareyi tutsa
bile uzak döşeme anında kaldırılır. Yayın yoksa profil fotoğrafı veya baş harf görünür.

### Dinamik sahne

Medya yokken katılımcı profil kartları görünür. Sahne katılımcı sayısına göre tek kişi / iki kişi /
2×2 / üç sütun + gerekli satırlar biçiminde düzenlenir. İki kişi sahneyi gereksiz boşluk bırakmadan
paylaşır. Tek kişilik kamerada zorunlu 16:9 crop yoktur; doğal oran korunur ve `object-fit: contain`
ile tamamı görünür.

### Ekran paylaşımı

Aktif paylaşım ana sahneye alınır. Kullanıcı tarayıcının paylaşım penceresinde sekme/sistem sesini
seçerse yayın sesi mikrofondan bağımsız olarak mevcut audio hattına karıştırılır — **yeni m-line eklenmez**.
Mikrofonu susturmak yayın sesini susturmaz. Yayın sesi alındığında sol panelde "Yayın sesi açık",
yerel sahne etiketinde "EKRAN + SES" görünür.

**Kırpma yasağı:** `object-fit: cover` kullanılmaz, screen-share `contain` olur, sabit 16:9 crop ve
zorunlu capture width/height uygulanmaz. Kaynağın dört kenarı hiçbir sahne oranında kesilmemelidir.
Parent container `min-height: 0`, overflow ve absolute inset düzeni kontrol edilmelidir.

Normal sahnede tekrar eden üst yayın bilgi bloğu ve alt kontrol çubuğu yoktur; sahneyi gizle ve
tam ekran kontrolleri birleşik kanal header'ındadır. Tam ekranda kontroller alt güvenli alanda kalır,
sol üst köşe medya için açıktır.

### Soundboard ve bağlantı kalitesi

Hazır Komik/Oyun sesleri ve kullanıcıya özel kategorili klipler vardır. Soundboard'un burada
anlatılan seviye/mute kontrolü **yayıncının kendi** kontrolüdür; dinleyicinin başkasının
soundboard'ını ayrı kısması yukarıdaki kaynak bazlı miksle yapılır. Özel klipler yalnız
tarayıcının IndexedDB'sinde tutulur (server/Matrix'e yük bindirmez); dosya tipi sınırlı, üst sınır
2 MB, süre 12 saniye. Soundboard + mikrofon + varsa ekran sesi tek WebRTC audio m-line'ında Web Audio
ile karıştırılır. Soundboard gain'i hem giden miksere hem ayrı yerel monitor stream'ine bağlanır,
böylece efekti başlatan da duyar. Mikrofon mute yalnız mikrofon gain'ini kapatır; soundboard'un
ayrı mute/seviyesi korunur. **Deafen açıkken soundboard oynatılamaz.** Panel `document.body`
portalında açılır (sidebar overflow/blur tarafından kırpılmaz).

`getStats()` beş saniyede bir RTT ve inbound paket kaybı örnekler; iyi/orta/zayıf göstergesi sunar.

### Focus, izleme kapatma, fullscreen, kalite

- Karta tıklayınca focus geçer, sahnede yalnız o görünür; tekrar tıklayınca grid'e döner.
- Uzak kamera/ekran izlemesi ayrı ayrı kapatılabilir. **Bu yalnız CSS gizleme değildir** —
  WebRTC receiver yönü renegotiation ile kapatılır ve trafik durur. Yayını açan kendi yerel
  kaynağını bu yöntemle kapatmaz. Canlı sahne tamamen gizlenebilir; arka plandaki video
  elemanları duraklatılır, ses ayrı audio elemanından devam eder.
- Fullscreen'de mikrofon, deafen, kamera, ekran paylaşımı, ayrılma ve grid/focus erişimi korunur.
- Kalite ayarları **Ayarlar → Ses ve Video** içindedir: 480p/720p/1080p/1440p/2160p, 30/60 FPS.
  Presetler `frontend/src/settings.ts` içindeki `VIDEO_QUALITY_PRESETS` tablosundadır ve
  bitrate değerleri **tavan**dır (WebRTC ağ koşuluna göre aşağı iner). Medya sunucudan geçmez,
  bu yüzden sınır kullanıcının yükleme hızıdır. 1440p ve 2160p `demanding: true` işaretlidir ve
  Ayarlar'da seçildiklerinde kalabalık odalar için uyarı gösterilir. Ekran paylaşımında kaynak
  crop edilmez, kalite düşürme `scaleResolutionDownBy` ile orantılı yapılır.
- `highFidelityStreamAudio` (varsayılan açık) yayın sesi mikste iken Opus bitrate tavanını
  yükseltir. Stereo için `a=fmtp` SDP düzenlemesi **bilinçli olarak yapılmamıştır**; pazarlık
  akışına dokunmamak için ses mono kalır (bkz. §24).
- `Oyun · Akıcılığı koru` → `motion`/`maintain-framerate` (60 FPS için bitrate tavanı yükseltilir);
  `Metin · Netliği koru` → `detail`/`maintain-resolution`. Codec zorlanmaz.

---

## 17. Arayüz ve tema

Discord benzeri çok panelli koyu modern arayüz; glassmorphism ve mor vurgu. Açık ve sistem teması da
vardır. Ortak renk sistemi CSS değişkenleriyle; `color-scheme` temayla uyumlu. Metin ve arka plan
hiçbir kritik durumda kontrastsız bırakılmamalıdır.

**Yerleşim:** en solda hover/focus ile açılan sunucu şeridi → kanal listesi → ortada medya sahnesi ve
metin sohbeti → geniş ekranda sağda sabit üye kolonu (dar görünümde workspace'i kaydırmayan overlay).
Ayarlar ve sunucu yönetimi katman olarak açılır. Kullanılmayan eski/tekrarlı paneller kaldırılmalıdır.

**Ayarlar sekmeleri:** Hesabım, Durum, Ses ve Video, Bildirimler, Görünüm, (Electron) Kısayollar,
(Electron) Windows, Gelişmiş. Kalite/FPS, durum ve özel durum yalnız burada tutulur.

**Sunucu ayarları:** bot yönetimi ve genel yönetim ortak temalı `Sunucu Ayarları` penceresindedir.
Select/input/devre dışı butonların kontrastı okunabilir olmalıdır. Platform pluginleri kart tabanlı
gösterilir. Yeniden adlandırma, açıklama, ayrılma ve silme buradadır.

**İkonlar:** emoji/karışık sembol yerine ortak modern SVG seti. Ayarlar dişli simgesiyle açılır,
çıkış profil alanının içindedir ve bir kez "emin misiniz?" onayı gösterir.

**Görsel cila katmanı:** `App.css` sonunda ayrı bir bölümdür. Yalnız görünüm özellikleri
(renk, kenar, gölge, tipografi, geçiş, animasyon) içerir; `display/position/grid/flex` gibi
yerleşim kuralları bilinçli olarak dışarıdadır. Böylece sahne, sohbet kaydırması ve panel akışı
davranışsal olarak değişmez. İçerdikleri: hareket/easing token'ları, `--accent-gradient`,
tutarlı `:focus-visible` halkası, ince kaydırma çubukları, çok yavaş hareket eden ortam ışığı
(`body::before`), buton hover/active geri bildirimi ve `prefers-reduced-motion` altında bunların
tamamını kapatan blok.

### Nexus Lab — ayrı arayüz

Highlight, Meme, Party Lore, AI Yorumcu, Roast Battle ve dört oyun modülü **ana uygulamanın
içine gömülü değildir.** Kendi belgesinde (`frontend/lab.html`) ve kendi penceresinde çalışırlar.

```text
frontend/lab.html            ikinci Vite giriş noktası
frontend/src/lab/main.tsx    bootstrap
frontend/src/lab/LabApp.tsx  kabuk: sunucu seçici + modül kataloğu
frontend/src/lab/lab.css     Lab'e özel kabuk stilleri
```

- Aynı origin'de çalışır; oturum jetonu, tema tercihi ve `coreApi` olduğu gibi paylaşılır.
  Ayrı giriş akışı veya jeton devri yoktur.
- **Panel bileşenlerinin kendi kodu değişmedi.** Ana uygulamada katman/modal olarak açılan
  yerleşim, Lab'de `.lab-stage__surface` altındaki CSS ile sayfa akışına çevrilir.
- Seçim adres çubuğuna yansır (`/lab?server=<id>&module=<key>`), pencere yenilenince korunur.
- Ana araç çubuğundaki dokuz deneyim butonu tek bir **Lab** butonuna indi.
  `openLab()` (`App.tsx`) pencereyi açar; adresi `labUrl()` (`desktopBridge.ts`) üretir.
- Masaüstünde renderer `nexus://app` origin'indedir ve `window.open` yalnız `https://` için
  (harici tarayıcıda) izinlidir; `labUrl()` orada sunucunun genel adresini kullanır.
- `/lab` okunabilir adrestir: production'da `frontend/nginx.conf`, dev sunucusunda
  `vite.config.ts` içindeki `nexus-lab-dev-route` eklentisi `lab.html`e yönlendirir.
- Lab ayrı bir chunk'tır; ana uygulamanın paketini büyütmez.

---

## 18. Bot ve plugin sistemi

Plugin manifesti `plugins/<ad>/plugin.json`'dadır. Plugin kurulabilir, kaldırılabilir,
etkinleştirilebilir ve bir bota bağlanabilir. Bot yalnız eklendiği sunucularda çalışır;
bot-plugin bağlantısı açıkça yapılır.

Core'a güvenilir erişim gerektiren yerleşik pluginler yalnız tam ad allowlist ile local çalışır:
`music`, `ai_assistant`, `moderation`. Diğerleri `plugin-sandbox` içinde çalışır. Sandbox doğrudan
veritabanı anahtarı almaz; doğrulanmış eylem zarfı Core'a iletilir.

### Mevcut pluginler

**`ai_assistant`** — `/sor <soru>` benzeri komutlar. AI işi ana request'te bloklanmaz, worker kuyruğuna bırakılır.

**`chance_games`** — Taş-Kağıt-Makas (`/takama @kullanıcı`, `/kabul <kod>`, `/taş` `/kağıt` `/makas`;
ilk oyuncunun seçimi rakipten gizlenir ve Matrix'e açık yazılmaz, sonuç iki taraf tamamlayınca
aynı anda açıklanır), Yazı-Tura (`/yazıtura [@kullanıcı]`), Çark (`/ekleçark`, `/çarkliste`,
`/çıkarçark`, `/temizleçark`, `/çark`).
Dayanıklılık: sunucu tarafı `secrets` rastgeleliği, harici/ücretli API yok, davet ~2 dk /
aktif oyun ~5 dk timeout, kullanıcı aynı anda tek açık oyunda, kendine davet ve sunucu dışı etiket
reddedilir, oyunlar ve çarklar PostgreSQL'de kalıcı. Structured oyun kartı yalnız backend'in
`is_bot` doğruladığı mesajlarda açılır.

**`music`** — gerçek WebRTC ses akışı gönderir (`aiortc`), sahte "çalıyor" mesajı değildir.
`plugins/music/library/` klasöründeki dosyaları çalar; internetten şarkı indirmez.
Komutlar: `/muzik-katil <sesli-kanal>`, `/muzik-ekle`, `/muzik-kuyruk`, `/muzik-sonraki`,
`/muzik-ayril`, `/muzik-listele`. `/muzik-url <url>` ve `/radyo <url>` ile doğrudan ses/radyo
akışları çalınabilir — **SSRF koruması:** özel/yerel IP, kimlik bilgisi, doğrulanmamış içerik tipi
ve aşırı yönlendirme reddedilir. Bot yeni katılan taraf olduğunda mevcut ses katılımcılarına
offer gönderir; sonradan açılan metin kanallarında bot Matrix üyeliği otomatik oluşturulur,
eski kanallarda ilk cevapta bir kez onarılır.

**`moderation`** — mesaj redaction/silme; yetki Core üzerinden denetlenir.

**`game_status`** — Minecraft Server List Ping protokolüyle ham socket sorgusu.

**`server_monitor`** — sunucu/sistem durum bilgileri.

**Bilinen sınır:** Tam platform-admin, detaylı RBAC ve plugin permission approval akışı
tamamlanmamıştır; birçok yönetim kararı hâlâ sahiplik seviyesindedir.

---

## 19. Windows Electron istemcisi

React/Vite web istemcisini özellikleri yeniden yazmadan paketler; kendi `nexus://app` origin'ini
kullanır. API ve WSS sözleşmeleri web ile aynıdır.

Özellikler: global PTT ve kısayollar (mikrofon, deafen, focus; Mouse4/Mouse5), system tray,
X'e basınca tray'e küçült veya çık tercihi, Windows başlangıcında açılma, native bildirim,
kompakt özel titlebar, minimum pencere boyutu, always-on-top mini ses penceresi (kanal, katılımcı,
konuşan, mute/deafen, temel kontroller), Electron `desktopCapturer` ile ekran/pencere seçimi,
giriş gain %0–200 / çıkış %0–100.

NSIS installer Start Menu, masaüstü kısayolu, uninstall ve update metadata üretir.
Auto-update ilk kurulumda kapalıdır. **Production dağıtımı öncesi Authenticode kod imzası gerekir;**
imzasız installer sıkı Windows Application Control/SmartScreen politikalarında engellenebilir.

`desktop/release-delivery2/NexusSetup-1.0.0-x64.exe` bir geliştirme artifact'ıdır, imzalı
production release kabul edilmemelidir.

---

## 20. Operasyon runbook'u

Tüm komutlar sunucuda `/opt/nexus` içinde çalıştırılır.

### Durum

```bash
docker compose ps
docker compose logs --tail 120
```

### Güncelleme (kod değişikliği sonrası)

```bash
git fetch origin cekingen && git merge --ff-only origin/cekingen
docker compose build backend frontend matrix reverse-proxy
docker compose run --rm migrate          # migration varsa
docker compose up -d
```

Yerel değişiklik varsa doğrudan merge yapma; önce `git status` incele.

### Yalnız backend/frontend değişikliği

```bash
docker compose build backend frontend media-worker
docker compose up -d backend ai-worker media-worker plugin-sandbox frontend reverse-proxy
```

> ⚠️ **`media-worker` ayrı bir image'dır** (`nexus-media-worker:0.1.0`, `backend/Dockerfile.media`
> — ffmpeg içerir). `docker compose build backend` onu **kapsamaz**; build listesine ayrıca
> yazılmazsa `up -d` sonrası eski backend kodunu çalıştırmaya devam eder ve bunu yalnız
> `docker inspect nexus-media-worker-1 --format "{{.Image}}"` karşılaştırması ortaya çıkarır.
> `ai-worker` ve `plugin-sandbox` ise backend image'ını paylaşır, ayrı build gerektirmez.

### Sağlık kontrolleri

```bash
docker compose exec -T reverse-proxy wget -qO- http://127.0.0.1:8081/healthz   # -> ok
curl -s https://nexus.cekin.gen.tr/healthz                                     # -> ok
curl -s https://nexus.cekin.gen.tr/api/health                                  # -> {"status":"ok"}
curl -s https://nexus.cekin.gen.tr/.well-known/matrix/client
curl -s https://nexus.cekin.gen.tr/_matrix/client/versions
```

### Servis yönetimi

```bash
systemctl status nexus.service
docker compose stop        # volume silmez
docker compose up -d
```

### Sertifika

Caddy otomatik yeniler. Sorun varsa:

```bash
docker compose logs reverse-proxy | grep -iE "acme|certificate|error"
```

`CLOUDFLARE_API_TOKEN` geçerliliği:

```bash
curl -s -H "Authorization: Bearer $TOKEN" https://api.cloudflare.com/client/v4/user/tokens/verify
```

### PowerShell CLI (geliştirici makinesinden)

`scripts/nexus-server.ps1` Windows/Docker Desktop varsayımıyla yazılmıştır ve **yeni Linux VDS
için güncellenmemiştir.** Sunucuda doğrudan `docker compose` kullan. Script'ler yine de
backup/restore/AI gateway mantığı için referanstır.

---

## 21. Sorun giderme

### Site açılmıyor
`docker compose ps` ve `docker compose logs --tail 120 reverse-proxy` ile başla.
Yerel `wget .../healthz` başarılıysa sorun DNS/TLS tarafındadır.

### Sertifika alınamıyor
`CLOUDFLARE_API_TOKEN` geçerli mi, Zone:DNS:Edit yetkisi var mı, `cekin.gen.tr` zone'unu kapsıyor mu?
DNS-01 için A kaydının çözülmesi şart değildir ama token şarttır.

### Mesaj 403 "user not in room"
Core `ServerMember` kaydı var mı? Kanal gerçekten metin kanalı mı? Matrix oda üyeliği onarım akışının
loglarını incele: `messages.py`, `matrix_rooms.py`, `matrix_client.py`.
Ham Matrix hatası kullanıcıya gösterilmeden yeniden join onarımı uygulanmalıdır.

### Mesaj F5 sonrası kayboluyor
Optimistic listede görünüp Matrix send başarısız olmuş olabilir. Gateway payload'ı tek kaynak değildir;
kalıcı kaynak Matrix history'dir. `client_id`/transaction ID duplicate önlemeyi korumalıdır.

### Ses "Bağlanıyor"da kalıyor
Sayfa HTTPS secure context mi? Mikrofon izni ne döndü? `/api/channels/{id}/voice` WSS açılıyor mu?
`/api/voice/ice-servers` erişilebilir mi (başarısızsa fallback STUN devreye girmeli)?
Bağlantı sonsuza kadar spinner göstermemeli; timeout anlaşılır hata vermelidir.

### SDP m-line hatası
Transceiver sırasını değiştirme, her toggle'da yeni rastgele transceiver ekleme, renegotiation
kuyruğunu ve offer glare/polite-initiator rolünü bozma.

### Kamera kapanınca donmuş kare
Uzak track ended/mute durumunda video element stream'i temizlenmeli, avatar/baş harf fallback'i gösterilmeli.

### AI cevap vermiyor
Geliştirici makinesinde: Ollama çalışıyor mu? AI Gateway çalışıyor mu (`100.104.192.122:8090`)?
Doğru `.env` mi düzenlendi (`ai-gateway.env` değil)? Sunucudan test:

```bash
curl -s -H "Authorization: Bearer $OLLAMA_API_KEY" http://100.104.192.122:8090/ai/health
```

Sunucuda: `docker compose logs --tail 120 ai-worker backend`.
Tailscale bağlantısı: `tailscale status`.
AI kapalıyken mesajlaşma/ses/web yine çalışmalıdır.

### Müzik botu çalışmıyor
`music` plugin kurulu mu, bir bota bağlı mı, bot sunucuya ekli mi? Parça `plugins/music/library/`
içinde mi? Sesli kanal adı/kimliği doğru mu? Backend loglarında `aiortc`/PyAV yükleme hatası var mı?
Botun voice peer olarak roster'a girdiği doğrulanmalı.

---

## 22. Test durumu

Bu paket hazırlanırken bilinen sonuçlar:

```text
backend            97 passed   (test_meme_generator.py hariç — aşağıdaki nota bak)
ai-gateway          9 passed   (test_gateway.py::test_settings PytestReturnNotNoneWarning verir;
                                fonksiyon return yerine assert kullanacak şekilde temizlenebilir)
frontend lint      tsc --noEmit başarılı
frontend build     Vite production build başarılı (index + lab olmak üzere iki giriş noktası)
```

Testleri çalıştırma (geliştirici makinesi):

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
```

> ⚠️ **Yerel ortam eksiği:** `backend/.venv` içinde **Pillow (PIL) kurulu değildir**, bu yüzden
> `tests/test_meme_generator.py` toplama aşamasında `ModuleNotFoundError: No module named 'PIL'`
> verir. Bu kod hatası değil, ortam eksiğidir — Docker imajında Pillow vardır. Yerelde geçici
> çözüm `--ignore=tests/test_meme_generator.py`; kalıcı çözüm venv'e Pillow kurmaktır.
> Ayrıca `backend/.pytest_cache` yazılamıyor; `-p no:cacheprovider` uyarıları susturur.

Not: yereldeki dağıtılmamış modüllerin testleri (`test_ai_board_game`, `test_ai_escape_room`,
`test_hidden_role_game`, `test_shared_story`) bu toplama **dahildir**.
Değişiklik sonrası yeniden çalıştır.

### Mevcut kapsam
Auth retry/idempotency · şans oyunları · Matrix pagination · Matrix mention/reaction/search/pin
sözleşmeleri ve mesaj endpoint yetkileri · müzik botu WebRTC · Ollama client ve error mapping ·
plugin loader · sosyal sistem · voice connection/session

### Eksik katmanlar
Tam browser E2E paketi yok · çok kullanıcılı gerçek medya testi manuel · farklı NAT/CGNAT
WebRTC/TURN matrisi otomatik değil · Electron installer'ın imzalı production doğrulaması yapılmadı

### ⚠️ Yeni sunucuda henüz yapılmamış doğrulama
Taşıma sonrası **iki gerçek kullanıcıyla ses/kamera/ekran paylaşımı smoke testi yapılmamıştır.**
Endpoint'ler ve TLS doğrulandı, ancak gerçek mikrofon/RTP akışı ve TURN relay yolu canlı test edilmedi.

`0034708` dağıtımında doğrulananlar: `/healthz`, `/api/health`, `/_matrix/client/versions`,
`/lab` (200 + doğru başlık), canlı bundle hash'lerinin yerel build ile birebir eşleşmesi,
çalışan konteynerde `_audio_mix_payload`'ın varlığı, dört park edilmiş modülün konteynerde
**bulunmadığı**, alembic'in `0015`'te kaldığı ve logların temiz olduğu.

**Doğrulanmayan:** kaynak bazlı ses miksinin gerçek iki kullanıcıyla çalıştığı. Bu, yukarıdaki
smoke testinin parçasıdır ve hâlâ açıktır.

---

## 23. Performans ve kaynak tasarrufu

- Gerçek zamanlı payload geldiğinde son 50 mesaj tekrar indirilmez; gateway bağlıyken snapshot seyrekleşir.
- Sekme arka plandaysa polling dakikalar düzeyinde seyrekleşir, analyser durur, video render duraklatılır.
- Konuşma algılama ~60 Hz yerine ~13 Hz çalışır.
- Ekran/sekme sesi yalnız yayını izleyen kullanıcılar için ikincil tam miksten gönderilir;
  izleyici "Yayını izleme" dediğinde receiver yönü ve bu ses kesilir. **Yeni transceiver/m-line eklenmez.**
- Matrix HTTP client keep-alive session ve connect/read timeout kullanır.
- Mesaj geçmişi sayfalıdır; `content-visibility` uzun sohbetlerin render maliyetini azaltır.
- AI üretimi API process'inden ayrı worker'a taşınmıştır.
- Docker servislerinde CPU/RAM sınırları vardır.

Sunucu kapasitesi referansı (taşıma sonrası boşta): 13/50 GB disk, ~1.4 GB RAM kullanımda.

---

## 24. Bilinen mimari sınırlar

**WebRTC mesh** — 4–5 ve üzeri aktif video kullanıcısında CPU/upload maliyeti hızla artar.
Büyük odalar için SFU gerekir; bu büyük bir mimari değişikliktir. 1440p/2160p presetleri bu
sınırı değiştirmez, yalnız tavanı yükseltir.

**Ses stereo değil** — Yayın sesi bitrate'i yükseltilebiliyor (`setParameters`), ancak Opus'un
stereo pazarlığı yalnız SDP'de `a=fmtp ... stereo=1;sprop-stereo=1` ile mümkündür. Bu, mevcut
örtük `setLocalDescription()` akışının `createOffer` + SDP düzenleme + `setLocalDescription(offer)`
biçimine çevrilmesini gerektirir ve pazarlık/m-line riskini artırır. **Bilinçli olarak yapılmadı.**
İstenirse ayrı ve dikkatli bir iş olarak ele alınmalıdır.

**TURN** — Artık gerçek public IPv4 ve açık UDP portları var, yani relay çalışabilir durumda.
(Eski Cloudflare Tunnel kurulumunda bu mümkün değildi.)

**Gateway state** — Presence/gateway state'i büyük ölçüde process belleğindedir. Birden çok
backend replica'ya geçilirse Redis benzeri ortak pub/sub ve presence store gerekir.

**Tarayıcı kısıtları** — Global PTT tarayıcıda mümkün değil · `setSinkId` her tarayıcıda yok ·
sistem bildirimi izne bağlı · kamera/mikrofon yalnız güvenli context'te.

**Yetki sistemi** — Tam RBAC, audit log, kanal bazlı detaylı izin ve platform-admin akışı tamamlanmadı.

**Dil** — Arayüz metinleri büyük ölçüde bileşenlerde sabit Türkçedir; i18n altyapısı yoktur.

**Hesap güvenliği** — 2FA yok · aktif oturum listesi ve diğer cihazlardan çıkış yok ·
kullanıcı engelleme/raporlama/gelişmiş DM gizlilik tercihleri tamamlanmadı.

**IPv6** — Sunucuda IPv6 adresi yoktur; yalnız IPv4.

---

## 25. Portal projesi (planlandı, YAPILMADI)

Kullanıcının hedefi: `cekin.gen.tr` kökünde bir **proje seçim sitesi**. Ziyaretçi birden çok
projeyi görür ve istediğini açar. Nexus ana projedir.

Kabul edilen tasarım:

- **Her projeye bir subdomain** (`nexus.cekin.gen.tr`, `proje2.cekin.gen.tr`, …).
  Path tabanlı ayrım reddedildi çünkü Nexus frontend'i ve Matrix `/_matrix/*` yolları kök path varsayar.
- **Nexus hep açık kalır.** Diğer projeler yalnız açıldığında çalışır ki boşta kaynak tüketmesinler.
- **Launcher servisi:** Caddy'nin önünde küçük bir servis; bir projenin subdomain'ine istek gelince
  o projenin Compose stack'ini `up -d` eder, hazır olana kadar "başlatılıyor…" ekranı gösterir,
  sonra proxy'ler. Belirlenen süre (örn. 20 dk) trafik gelmezse `stop` eder.
  **Nexus bu mekanizmanın dışındadır.**
- Wildcard sertifika (`*.cekin.gen.tr`) DNS-01 ile alınabilir; altyapı buna hazır.
- Şimdilik portalda **yalnız Nexus kartı** olacak; diğer projeler sonra eklenecek.
- Portal'da giriş olup olmayacağı **henüz kararlaştırılmadı**.

Yapılacaklar:

1. Kök domain'deki ölü `cfargotunnel` CNAME'ini sil, A kaydı (45.155.124.254, gri bulut) ekle.
   Eski kurulum kapatıldığı için engel yok (bkz. §2).
2. Caddyfile'a kök domain ve wildcard (`*.cekin.gen.tr`) site bloklarını ekle.
3. Portal frontend'ini yaz (şimdilik tek kart: Nexus).
4. Launcher servisini yaz ve ikinci bir proje ile test et.

---

## 26. Sonraki adımlar

### P0
1. İki gerçek kullanıcıyla ses/kamera/ekran smoke testi (yeni sunucuda hiç yapılmadı).
   **Bu tur ayrıca kaynak bazlı ses miksini de kapsamalıdır:** A ekran+ses paylaşırken B,
   A'nın yayın sesini 0'a indirip konuşmasını duymaya devam edebiliyor mu; B, A'nın
   soundboard'ını ayrı kısabiliyor mu; "yayını izleme" kapatılınca yayın sesi kesiliyor mu.
2. TURN relay yolunun farklı ağlardan gerçekten çalıştığını doğrula.
3. AI Gateway'i Windows'ta kalıcı hale getir (oturum açılışında otomatik başlayan görev).
4. 1440p/2160p presetlerini gerçek yükleme hızıyla dene; kalabalık odada 1080p'ye dönmek
   gerekip gerekmediğini ölç.

### P1
- Portal + launcher (§25).
- Playwright ile iki kullanıcılı E2E: login/register retry, arkadaşlık/davet, optimistic send,
  F5 kalıcılığı, lazy history, Shift+Enter, edit/delete, attachment, voice roster reconnect,
  kamera+ekran eşzamanlı, focus/grid görsel regresyon.
- Gözlemlenebilirlik: Caddy/backend/Matrix health'i tek admin ekranında; `getStats()` göstergesini
  bitrate, selected candidate type ve çözünürlük/FPS ile genişlet; ham hata yerine eyleme dönük mesaj.
- `scripts/nexus-server.ps1`'i Linux VDS'e uyarla veya sunucu tarafı bir eşdeğerini yaz.
- `public-tunnel` servisini ve tunnel'a özgü script/dokümanları temizle.

### P2
- Matrix receipt tabanlı server-side unread/okundu.
- Reaksiyon veren kullanıcı listesi popover'ı.
- Arama sonucunun yüklenmemiş tarih sayfasını açma.
- Thread görünümü.
- Tam RBAC, audit log, ban/unban, kanal bazlı izin, 2FA, oturum yönetimi, engelleme/raporlama.

### P3
- Katılımcı sayısı büyürse self-hosted SFU değerlendirmesi, adaptif simulcast/SVC,
  otomatik kalite düşürme/yükseltme.

---

## 27. Kritik dosya rehberi

**Başlangıç:** `frontend/src/App.tsx` · `backend/app/main.py` · `docker-compose.yml` ·
`docker/reverse-proxy/Caddyfile` · `docker/reverse-proxy/Dockerfile`

**Mesajlaşma:** `frontend/src/components/ChatArea.tsx` · `frontend/src/api/client.ts` ·
`backend/app/core/routers/messages.py` · `backend/app/core/matrix_client.py` ·
`backend/app/core/matrix_rooms.py` · `backend/app/core/routers/gateway.py`

**Arkadaşlık/DM/davet:** `frontend/src/components/{ProfilePanel,ServerInvitesPanel,JoinServerPanel}.tsx` ·
`backend/app/core/routers/{friends,direct,server_invites,join_codes}.py`

**Ses ve medya:** `frontend/src/hooks/{useVoiceChannel,useMediaDevices,usePushToTalk}.ts` ·
`frontend/src/components/{VoicePanel,VideoStage,ChannelSidebar}.tsx` ·
`frontend/src/settings.ts` (kalite presetleri, ses bitrate) · `backend/app/core/routers/voice.py`
(`_audio_mix_payload` dahil signaling doğrulaması)

**Nexus Lab:** `frontend/lab.html` · `frontend/src/lab/` · `frontend/vite.config.ts`
(çoklu giriş + dev yönlendirmesi) · `frontend/nginx.conf` · `frontend/src/desktopBridge.ts`
(`labUrl`)

**Ayarlar ve tema:** `frontend/src/settings.ts` ·
`frontend/src/components/{SettingsPanel,ServerSettingsPanel}.tsx` ·
`frontend/src/App.css` · `frontend/src/index.css`

**Botlar, pluginler, AI:** `backend/app/bot_engine/dispatcher.py` · `backend/app/plugins_engine/` ·
`backend/app/plugins_sandbox/` · `backend/app/services/chance_games.py` ·
`backend/app/services/ollama/` · `backend/app/modules/` · `backend/app/platform/` ·
`plugins/` · `ai-gateway/gateway/`

**Desktop:** `frontend/src/desktopBridge.ts` · `desktop/src/` · `desktop/package.json` ·
`docs/desktop/DESKTOP_MIGRATION_PLAN.md`

**Deployment:** `docs/deployment/{SERVER_QUICKSTART,DOCKER_PRODUCTION,AI_WORKER,TAILSCALE_SETUP,
HTTPS_REVERSE_PROXY,DATABASE_SECURITY}.md` · `scripts/`

> ⚠️ `docs/deployment/PUBLIC_CLOUDFLARE_TUNNEL.md` ve tunnel'a özgü script/`.cmd` dosyaları
> artık geçersizdir; mimari tünel kullanmıyor.

**Modül tasarımları:** `docs/architecture/<modül-adı>/README.md` ve prompt dosyaları

---

## 28. Yeni görev geldiğinde çalışma sırası

1. İsteği bu belgedeki uygulanmış özelliklerle karşılaştır.
2. `rg` ile gerçek implementasyonu bul.
3. Çalışma ağacında kullanıcıya ait değişiklik var mı kontrol et (**çıktıyı kesme**).
4. Tanı isteğiyse önce kök nedeni kanıtla; kullanıcı istemeden kapsam dışı değişiklik yapma.
5. Değişiklik isteğiyse minimum ama uçtan uca çalışan değişikliği yap.
6. Backend API sözleşmesi değişiyorsa frontend tiplerini aynı turda güncelle.
7. DB modeli değişiyorsa yeni Alembic migration ekle; eskisini değiştirme.
8. WebSocket/WebRTC değişikliğinde reconnect, F5, duplicate event ve iki eşzamanlı kullanıcı
   senaryolarını düşün.
9. Medya UI değişikliğinde şu senaryoları kontrol et: tek kişi, iki kişi, dört kişi, yalnız profil,
   yalnız kamera, yalnız yayın, kamera+yayın, focus, fullscreen, dar ekran.
10. Mesaj UI değişikliğinde: optimistic send, kendi mesajında aşağı kaydırma, başkasının mesajında
    konum koruma, yeni mesaj oku, F5, lazy history, Shift+Enter, edit/delete, attachment.
11. Testleri çalıştır.
12. Kullanıcı açıkça isterse commit/push yap; aksi halde yerel değişikliği ve doğrulamayı raporla.
13. Önemli değişiklikleri bu belgeye işle; eski, çelişkili kayıtları biriktirme, sil.

---

## 29. Kısa özet

- Nexus, React + FastAPI + PostgreSQL + Matrix + WebRTC tabanlı işlevsel bir iletişim platformudur.
- **5 Ağustos 2026'da tek bir Ubuntu VDS'e (45.155.124.254) taşındı.** Hamachi, Cloudflare Tunnel
  ve iki-bilgisayarlı dağıtım kaldırıldı. Erişim: `https://nexus.cekin.gen.tr`.
- Sertifika Caddy + Cloudflare DNS-01 ile otomatik alınır ve yenilenir.
- AI, Tailscale üzerinden geliştirici makinesindeki Ollama'ya bağlanır; kapalıysa yalnız AI
  özellikleri pasifleşir.
- Sunucu `2aa6ce3` commit'inde ve DB `0015_user_auth_version` revizyonundadır.
  Yerelde dört yeni AI deneyim modülü ve dört migration bilinçli olarak dağıtılmamıştır.
- Mesajlaşma, sosyal sistem, DM, attachment, bot/plugin, ses, kamera, ekran paylaşımı, soundboard,
  kalite ayarları, dinamik sahne, AI deneyim modülleri ve Electron istemcisi uygulanmıştır.
- **Ses kaynakları artık dinleyici başına ayrı ayrı ayarlanabilir** (konuşma / soundboard /
  yayın sesi). Miksi yayıncı üretir; SDP, transceiver sırası ve m-line sayısı değişmedi (§15).
- **Kalite tavanı 2160p'ye çıktı** ve yayın sesi bitrate'i yükseltilebiliyor (§16).
- **Nexus Lab** ayrı bir belgede ve ayrı pencerede çalışır; dokuz deneysel modül ana araç
  çubuğundan çıkarıldı (§17).
- **Eski kurulum kapatıldı.** Ev bilgisayarındaki tunnel tabanlı Nexus durduruldu; verisi
  gerekmediğine karar verildi. Kök domain artık boştur ve portal için ayrılmıştır (§2).
- **Sıradaki büyük iş:** kök domainde hub/portal + on-demand proje launcher'ı (§25).
- **En önemli açık risk:** yeni sunucuda gerçek iki kullanıcılı ses/medya smoke testi henüz yapılmadı.
