# Geliştirme Aşamaları

Proje "tek seferde Discord yap" mantığı yerine aşama aşama ilerler.

## Aşama 1 — Arayüz + Core Yapı ✅
- Monorepo iskeleti ✅
- Core Platform temel modelleri: kullanıcı, rol, yetki, sunucu, kanal ✅
- Frontend iskeleti (React + TypeScript), temel layout ✅
- Frontend gerçek Core API'ye bağlandı ✅ — login ekranı (JWT), gerçek sunucu/kanal/mesaj
  verisi (mock veri kaldırıldı), sunucu/kanal oluşturma, mesaj gönderme/polling ile okuma.
  Tarayıcıda gerçek kullanıcıyla uçtan uca test edildi: giriş, mesaj geçmişi (bot cevapları
  ve silinen mesajlar dahil) doğru göründü, yeni mesaj gönderme çalıştı.
  Eksik: gerçek zamanlı push (şu an 4sn'lik polling)
- Sunucuya üye ekleme arayüzü ✅ — `frontend/src/components/MembersPanel.tsx`, kanal
  başlığındaki 👥 butonuyla açılıyor: üye listesini gösterir, sunucu sahibi için kullanıcı
  adıyla davet formu sunar. Backend tarafında `GET /servers/{id}/members` (üye listesi,
  herhangi bir üye görebilir) ve `POST /servers/{id}/members?username=...` (sadece sahip,
  artık numeric id yerine kullanıcı adı alıyor) — `backend/app/core/routers/members.py`.
  Tarayıcıda iki gerçek hesapla uçtan uca test edildi: `mert2`, `yenikullanici`yı kullanıcı
  adıyla "Nexus HQ" sunucusuna davet etti (üye listesi anında güncellendi), `yenikullanici`
  ayrı bir oturumda giriş yapıp sunucuyu, tüm kanalları ve mesaj geçmişini gördü, gönderdiği
  mesaj kanalda gerçek zamanlı göründü — yani artık farklı hesaplar gerçekten aynı sunucuda
  buluşabiliyor (önceden bu sadece backend API'sinde vardı, arayüzü yoktu).
- Bot ve plugin yönetimi arayüzü ✅ — `frontend/src/components/BotsPanel.tsx`, kanal
  başlığındaki 🤖 butonuyla açılıyor: bu sunucudaki botları listeler, sunucu sahibi için
  "yeni bot oluştur ve sunucuya ekle" formu (tek adımda `POST /bots` + `POST /bots/{id}/servers/{id}`)
  ve platform genelindeki pluginleri (kurulu/etkin durumuyla) listeleyip Kur/Kaldır butonu
  sunar. Backend: `GET /servers/{id}/bots` eklendi (`backend/app/core/routers/bots.py`).
  Tarayıcıda uçtan uca test edildi: panel açıldığında mevcut `nexus-bot` ve kurulu 4 plugin
  (`ai_assistant`, `game_status`, `moderation`, `server_monitor`) doğru listelendi; "yardimci-bot"
  adında yeni bir bot oluşturulup sunucuya eklendi (panel anında güncellendi); ardından
  kanala `/sunucu-durumu` yazıldığında hem `nexus-bot` hem de yeni `yardimci-bot` kendi
  gerçek Matrix hesaplarıyla ayrı ayrı cevap yazdı — yani arayüzden oluşturulan bot gerçekten
  çalışan bir bot.

## Aşama 2 — Matrix Bağlantısı ✅ (metin dışı kısımlar hariç)
- Matrix Synapse'in Docker ile ayağa kaldırılması ✅
- Core API'nin Matrix Client-Server API ile entegrasyonu ✅
  (`backend/app/core/matrix_client.py`: shared-secret kullanıcı kaydı, oda oluşturma,
  davet/katılma, mesaj gönderme/okuma)
- Metin kanalı akışının bağlanması ✅ — REST API üzerinden uçtan uca test edildi:
  `POST /users`, `POST /servers`, `POST /servers/{id}/channels`, `POST /servers/{id}/members`,
  `POST /channels/{id}/messages`, `GET /channels/{id}/messages`. İki gerçek kullanıcı,
  gerçek Postgres + gerçek Synapse'e karşı bir kanalda karşılıklı mesajlaştı.
- Ses/kamera/ekran paylaşımı/dosya paylaşımı — henüz yapılmadı (Matrix VoIP sinyalleşmesi
  ve dosya yükleme uç noktaları)

## Auth (Aşama 1-2 arası eksiği kapatıldı) ✅
- `POST /auth/login` — JWT tabanlı giriş (`backend/app/core/auth.py`, `routers/auth.py`)
- Tüm uç noktalar `Authorization: Bearer <token>` gerektiriyor; `owner_id`/`sender_id`/
  `viewer_id` query parametreleri kaldırıldı, kimlik token'dan (`current_user`) okunuyor
- Yetkilendirme (`authz.py`): sadece sahip kanal/üye ekleyebilir, sadece üyeler mesaj
  okuyup yazabilir. Gerçek Postgres+Synapse'e karşı test edildi: 401/403 doğru davranıyor

## Aşama 3 — Plugin Sistemi ✅
- Plugin yükleme/kaldırma mekanizması ✅ (`backend/app/plugins_engine/loader.py::PluginRegistry`,
  `POST /plugins/{name}/install`, `POST /plugins/{name}/uninstall`; kurulu/etkin durumu Postgres'te)
- Plugin API tasarımı ve dokümantasyonu ✅ (`plugin.json` sözleşmesi + `PluginContext`,
  bkz. [plugins/README.md](plugins/README.md))
- İlk örnek plugin (`server_monitor`) ile uçtan uca test ✅ — kurulmadan önce komut 404,
  kurulduktan sonra gerçek sistem bilgisi dönüyor, kaldırıldıktan sonra tekrar 404;
  sunucu yeniden başladığında önceden kurulu plugin otomatik geri yükleniyor
- Eksik: platform admin rolü (şu an herhangi bir kullanıcı plugin kurup kaldırabiliyor),
  `permissions` alanının gerçek bir onay akışıyla uygulanması

## Aşama 4 — Bot Motoru ✅ (temel akış; `@bot` mention'ı hariç)
- Event tabanlı bot altyapısı ✅ — `backend/app/bot_engine/dispatcher.py::handle_message_event`,
  mesaj gönderme akışından tetiklenen `MessageEvent` (şu an senkron; gerçek bir event
  bus/kuyruk değil — ileride Matrix `/sync`'e taşınabilir)
- Komut sistemi ✅ — `/komut arg` ayrıştırılıp yüklü plugin'e yönlendiriliyor
  (`@bot ...` mention biçimi henüz yok, sadece prefix tabanlı komutlar)
- Bot yetki kontrolü ✅ — `Bot`/`BotServerLink`: bir bot sadece eklendiği sunucularda
  komuta cevap verir. Uçtan uca test edildi: bot bir sunucuya eklendi, `/sunucu-durumu`
  komutuna kendi gerçek Matrix hesabıyla aynı odaya cevap yazdı; botun eklenmediği başka
  bir sunucuda aynı komuta hiç cevap vermedi
- Eksik: platform admin rolü (bkz. Aşama 3 notu), `@bot` mention formatı, bot başına
  komut/izin kısıtlaması (şu an bir bot, yüklü olan HER komutu çalıştırabiliyor)

## Aşama 5 — AI ve Özel Özellikler (devam ediyor)
- `ai_assistant` plugin'i ✅ — `plugins/ai_assistant/`: `/sor <soru>` komutu, yerel Ollama
  (`qwen2.5:7b`) modeline konuşuyor. Anthropic/OpenAI gibi ücretli bir API değil; internet
  bağlantısı veya API anahtarı gerekmez, token faturası oluşmaz. Uçtan uca test edildi:
  `aylin` kanala `/sor Türkiye'nin başkenti neresidir?` yazdı, `nexus-bot` gerçek Matrix
  odasına doğru cevabı ("Ankara") yazdı — tamamen yerel model üzerinden.
- `game_status` plugin'i ✅ — `plugins/game_status/`: `/oyun-durumu <host:port>` komutu,
  Minecraft Server List Ping protokolünü (varint + JSON el sıkışması) sıfırdan, ham socket
  ile uygular — üçüncü parti kütüphane yok. Gerçek canlı bir sunucuya (Hypixel) karşı test
  edildi ve doğru sürüm/oyuncu sayısını döndürdü; kanaldan `/oyun-durumu` ile de doğrulandı.
- `moderation` plugin'i ✅ — `plugins/moderation/`: `/sil <event_id>` komutu, sadece sunucu
  sahibinin çalıştırabildiği, gerçek bir Matrix mesaj silme (redaction) işlemi. Uçtan uca
  test edildi: sahip olmayanın denemesi reddedildi (403 benzeri bot cevabı), sahibin
  denemesi mesajı gerçekten Matrix'ten sildi (`content` boşaldığı doğrulandı).
- `music` plugin'i ✅ — `plugins/music/`: botu gerçekten sesli kanala katıp platformun kendi
  WebRTC mesh'i üzerinden GERÇEK ses akıtan bir kuyruk sistemi (durum mesajı yazan bir
  "now playing" panosu değil). `aiortc` (Python WebRTC, `backend/requirements.txt`'e eklendi)
  ile bot, `-bot_id` (negatif) sözde-id'siyle `voice_manager`'a (`backend/app/core/routers/
  voice.py`) doğrudan Python çağrısıyla katılıyor — gerçek bir WebSocket/ekstra kullanıcı
  hesabı gerekmiyor (bkz. `plugins/music/voice_session.py` docstring'i). Komutlar:
  `/muzik-katil <sesli-kanal>`, `/muzik-ekle <parça>`, `/muzik-kuyruk`, `/muzik-sonraki`,
  `/muzik-ayril`, `/muzik-listele`. Parçalar `plugins/music/library/` klasöründen dosya
  adıyla bulunuyor — plugin internetten şarkı indirmiyor, kullanıcı kendi ses dosyalarını
  koyuyor. Uçtan uca gerçek tarayıcıda test edildi: bot bir sesli kanala katıldı, gerçek bir
  kullanıcı (mert2) aynı kanala bağlandı, WebRTC `getStats()` ile alıcı tarafın `media-playout`
  istatistiği ölçüldü — 49.19 saniyelik gerçek zamanda tam 49.19 saniyelik ses çalınmış
  olduğu doğrulandı (yani bağlantı kurulup sessiz kalmıyor, gerçekten sürekli ses akıyor).
  `/muzik-sonraki` (sıradaki parçaya geçiş) ve `/muzik-ayril` (kanaldan ayrılma, katılımcı
  listesinden düşme) de doğrulandı. Kurulum notu: `aiortc`'nin bağımlılığı `av` (PyAV) ilk
  içe aktarmada bir kerelik "Uygulama Denetimi ilkesi engelledi" hatası verebilir (Windows
  Defender'ın yeni DLL'e ilk erişimde yaptığı bulut itibar kontrolü) — tekrar denemek yeterli,
  kod hatası değil.
  Bu çalışma sırasında `frontend/src/hooks/useVoiceChannel.ts`'de önceden var olan iki hata
  da düzeltildi: (1) mikrofon reddedilince/yoksa fonksiyon erken `return` edip WebSocket'i
  hiç açmıyordu — artık mikrofonsuz da "sadece dinleyici" olarak kanala katılınabiliyor;
  (2) yerel ses akışı olmayan bir katılımcının offer'ında hiç audio m-line olmadığından karşı
  taraflar (ör. müzik botu) ses gönderemiyordu — artık mikrofon yoksa `recvonly` bir audio
  transceiver ekleniyor. İkisi de bu plugin'in gerçek testinde ortaya çıkan, platformun genel
  sesli kanal deneyimini etkileyen pre-existing (önceden var olan) hatalardı.
- Platform admin rolü — bilinçli olarak ertelendi (şu an ihtiyaç yok)
- Otomasyon araçları — henüz yapılmadı

## Aşama 6 — Hibrit AI Mimarisi ve Sesli İletişim (devam ediyor)

Kullanıcının 2. geliştirme aşaması promptu: hibrit sunucu (ayrı "ana sunucu" + "AI işlem
sunucusu"), Ollama connector servisi, Discord tarzı bas-konuş (push-to-talk) ve sesli kanal.

- **Ollama connector servisi** ✅ — `backend/app/services/ollama/` (`client`/`models`/
  `tokenizer`/`requests`): model seçimi, sohbet geçmişi, context yönetimi (son 20 mesaj),
  token kullanım takibi (Ollama'nın gerçek `prompt_eval_count`/`eval_count` değerlerinden).
  `OllamaClient`'ın `base_url`/`api_key`'i `.env` üzerinden yapılandırılabilir — hibrit
  mimaride ayrı bir "AI işlem sunucusu"na işaret edecek şekilde tasarlandı, ama bu makinede
  sadece tek makineye karşı test edilebildi (ikinci fiziksel makineye erişim yok).
  `ai_assistant` plugin'i de bu paylaşılan servisi kullanacak şekilde refactor edildi.
  Uçtan uca test edildi: çok turlu sohbette context doğru çalıştı (model önceki turdaki
  bilgiyi hatırladı), token kullanımı doğru toplandı.
- **Gerçek iki-makine hibrit kurulum** — henüz yapılmadı (bu makineden ikinci bir fiziksel
  makineye bağlanılamıyor; kod hazır, gerçek dağıtım kullanıcı tarafında yapılmalı)
- **TASK-001/002 — AI Gateway + Tailscale güvenlik katmanı** ✅ (repo tarafı) — bağımsız
  `ai-gateway/` servisi; Bearer API key, CIDR whitelist, güvenilir proxy kontrolü,
  `/ai/health`, `/api/tags` ve `/api/chat` proxy uçları. İki Windows bilgisayar için Tailscale
  Grants/Firewall kurulumu `docs/deployment/TAILSCALE_SETUP.md` altında hazırlandı. Gerçek
  100.x adresleriyle fiziksel iki-makine kurulumu hâlâ kullanıcı tarafında yapılmalı.
- **TASK-003 — Backend → AI Gateway → Ollama yönlendirmesi** ✅ — Backend OllamaClient artık
  gateway `/ai/health` üzerinden model doğrular; bağlantı/geçici `429/502/503` hatalarında
  sınırlı exponential-backoff retry uygular; chat read-timeout/504 sonrasında çift üretimi
  önlemek için retry yapmaz. Model/auth/unavailable/timeout hataları Core API'de sırasıyla
  `422/502/503/504` olarak ayrıştırılır. Yerel gerçek gateway+Ollama zincirinde uçtan uca test edildi.
- **TASK-004 — Production Docker düzeni** ✅ (config/build doğrulaması) — `frontend`, `backend`,
  `postgres`, `matrix`, `reverse-proxy` servisleri; frontend/backend multi-stage image'ları,
  Caddy otomatik HTTPS ve aynı-origin `/api`/WebSocket/Matrix proxy, healthcheck/depends_on,
  internal data ağı ve kalıcı volume'lar eklendi. Synapse SQLite yerine aynı PostgreSQL
  container'ındaki ayrı kullanıcı/veritabanını kullanacak şekilde yapılandırıldı. Compose
  config ve frontend production build doğrulandı; Docker daemon kapalı olduğu için image'lar
  bu makinede henüz build edilip topluca ayağa kaldırılmadı. Eski SQLite/Postgres verisi için
  otomatik migration yapılmaz; production geçişinden önce yedek/migration gerekir.
- **TASK-005 — HTTPS / Reverse Proxy** ✅ (repo tarafı) — Caddy için zorunlu domain ve ACME
  e-postası, otomatik public HTTPS/HTTP yönlendirmesi, TLS 1.2–1.3, aynı-origin WSS proxy,
  Matrix `.well-known` discovery yanıtları ve dış doğrulama scripti eklendi. Gerçek domain/DNS
  henüz verilmediği ve Docker daemon kapalı olduğu için public sertifika alımı ile internetten
  HTTPS/WSS testi kullanıcı tarafında yapılmalıdır.
- **TASK-006 — Database güvenliği** ✅ (repo tarafı) — PostgreSQL host portu yayınlanmıyor ve
  internal data ağında kalıyor; tek-seferlik Alembic `migrate` servisi, PostgreSQL/Synapse
  custom-format dump + globals backup'ı, SHA-256 manifesti, onaylı restore scripti ve operasyon
  dokümantasyonu eklendi. Gerçek production backup/restore tatbikatı Docker/PostgreSQL çalışan
  ortamda kullanıcı tarafında yapılmalıdır.
- **TASK-007 — AI Worker sistemi** ✅ (repo tarafı) — AI sohbet mesajları artık 202 ile kalıcı
  `ai_jobs` kuyruğuna, kanal içi `/sor` bot komutları `ai_bot_jobs` kuyruğuna alınır; ayrı
  `ai-worker` process'i lease/timeout/retry mantığıyla Ollama üretimini yapar. API process'i model
  üretiminde bloke olmaz; canlı çoklu kullanıcı/worker ölçek testi Docker ortamında ayrıca
  yapılmalıdır.
- **Sesli kanal (WebRTC)** ✅ — Matrix'in karmaşık grup çağrı protokolü (MSC3401) yerine,
  Core API üzerinde kendi hafif WebSocket signaling'imiz (`backend/app/core/routers/voice.py`):
  offer/answer/ICE candidate relay, mesh topoloji (yeni katılan herkese offer gönderir),
  mute/speaking broadcast. Ses verisi sunucudan geçmez, katılımcılar arasında doğrudan akar.
  Frontend: `useVoiceChannel` hook'u (`getUserMedia`, `RTCPeerConnection` mesh, Web Audio
  `AnalyserNode` ile konuşma tespiti), `VoicePanel` (🟢/🔴/⚪ durum göstergeleri, mute/ayrıl).
  Backend uçtan uca gerçek WebSocket istemcileriyle test edildi (join/offer/answer/ICE/mute/
  leave akışı + yetkisiz erişim reddi). Frontend'de mikrofon gerektiren kısımlar bu ortamın
  tarayıcı sandbox'ında test edilemedi (`getUserMedia` engelleniyor) — UI/hata yönetimi/
  katıl-ayrıl döngüsü doğrulandı, gerçek ses akışı gerçek bir tarayıcıda elle test edilmeli.
- **Push-to-talk / mute kısayolları** ✅ (sekme odakta olduğu sürece) — `frontend/src/settings.ts`
  (localStorage'da saklanan `VoiceSettings`: mod `toggle`/`ptt` + özelleştirilebilir tuş
  kombinasyonu), `frontend/src/hooks/usePushToTalk.ts` (keydown/keyup ile combo takibi,
  sekme blur olunca otomatik bırakır), `useVoiceChannel` PTT modunda mikrofonu varsayılan
  kapalı başlatıp tuş basılıyken açacak şekilde genişletildi. Tarayıcıda uçtan uca test
  edildi: ayarlar paneli açıldı, PTT moduna geçildi, varsayılan `Ctrl+Shift` etiketi doğru
  göründü, ses kanalına katılınca "Sustur" butonu gizlenip "Konuşmak için Ctrl+Shift tuşuna
  basılı tutun" ipucu çıktı; `toggle` moduna geri dönülünce "Sustur" butonu doğru şekilde
  geri geldi (regresyon yok); ayar sayfa yenilemesinden sonra da localStorage'dan doğru
  yüklendi. Gerçek mikrofon akışı bu ortamda test edilemedi (bilinen sandbox kısıtı, bkz.
  yukarıdaki sesli kanal notu) — tuş algılama mantığı koddan doğrulandı.
  Not: tarayıcı güvenlik modeli gereği, sekme odakta değilken (ör. oyun ön plandayken)
  klavye olaylarını yakalamak mümkün değil — gerçek "global hotkey" için küçük bir masaüstü
  yardımcı uygulama (Tauri/Electron) gerekir; kullanıcı bu aşamada tarayıcı sınırları içinde
  kalmayı tercih etti
- **Ayarlar paneli (PTT/mute tuş özelleştirme)** ✅ — `frontend/src/components/SettingsPanel.tsx`,
  App.tsx'te dişli (⚙️) butonuyla açılıyor. Mod seçimi (sürekli açık / push-to-talk) ve
  "Tuşu değiştir" ile yeni bir kombinasyon kaydetme (basılı tutulan tüm modifier'lar +
  varsa modifier olmayan tuş) içeriyor.
- **Docker kaynak sınırlama (CPU/RAM)** ✅ — `docker-compose.yml`: `postgres` (1 CPU/512MB),
  `synapse` (1.5 CPU/1GB) için `deploy.resources.limits`. `docker compose config` ile
  doğrulandı (limitler doğru parse ediliyor); gerçek kapsayıcılara uygulanması için
  `docker compose up -d` ile yeniden başlatma gerekiyor (henüz yapılmadı — çalışan
  kapsayıcıları kesintiye uğratmamak için kullanıcı onayı bekleniyor).
- **Rate limit güvenliği** ✅ — `backend/app/core/rate_limit.py`: harici bağımlılık
  gerektirmeyen, tek process içi sabit pencereli sayaç. İki yerde uygulandı:
  `POST /auth/login` (IP başına 5 dakikada 10 deneme — kaba kuvvet koruması,
  `routers/auth.py`) ve bot komut çalıştırma (`bot_engine/dispatcher.py`: kullanıcı başına
  10 saniyede 5 komut — özellikle Ollama gibi CPU maliyetli plugin'lerin mesaj spam'iyle
  kötüye kullanılmasını önler). Login limiti gerçek sunucuya karşı `curl` ile test edildi:
  ilk 10 deneme 401 (yanlış parola), 11. ve sonrası 429 döndü. Komut limiti `RateLimiter`
  sınıfının kendisi izole test edildi (5/10 True, sonrası False) — tam bot akışı (Matrix +
  Docker gerektirdiği için) ayrıca uçtan uca denenmedi.

Not: Her aşama bir öncekinin üzerine inşa edilir; bir aşama tamamlanmadan bir sonrakine geçilmez.
- **TASK-008 — AI geliştirmeleri** ✅ (repo tarafı) — Token bütçeli context seçimi, Ollama
  streaming çıktısının kalıcı job alanına flush edilmesi, SSE ile istemci akışı, cooperative
  kullanıcı iptali ve konuşma oluştururken kurulu model doğrulaması eklendi.
- **TASK-009 — Auth açıkları** ✅ (repo tarafı) — Kaynak endpoint'lerindeki eksik Bearer
  doğrulaması kapatıldı; sunucu ayrıntısı üyelik kontrolüne alındı ve pasif kullanıcıların
  token'ları hem login hem de mevcut oturum doğrulamasında reddediliyor. Login/kayıt/health
  endpoint'leri bilerek public bırakıldı.
- **TASK-010 — Plugin sandbox** ✅ (altyapı) — Production plugin çağrıları artık Core API
  process'ine import edilmeden internal `plugin-sandbox` container'ına yönlendiriliyor;
  subprocess timeout, read-only filesystem, network izolasyonu, capability/PID/RAM/CPU
  sınırları ve shared-secret doğrulaması eklendi. `local` modu yalnızca geliştirme içindir.
- **TASK-011 — TURN Server** ✅ (repo tarafı) — Coturn servisi, public relay port aralığı,
  internal signaling ile kısa ömürlü HMAC credential endpoint'i ve frontend ICE yapılandırması
  eklendi. Gerçek NAT/CGNAT bağlantı testi production public IP ve DNS ile ayrıca yapılmalıdır.
- **TASK-012 — WebRTC tamamlanması** ✅ (repo tarafı) — ICE credential'larının bağlantı öncesi
  alınması, erken gelen ICE adaylarının kuyruğa alınması, TURN/firewall hata geri bildirimi
  ve LAN geliştirme erişimi eklendi. Gerçek iki tarayıcı/NAT testi deployment sırasında yapılmalıdır.
- **TASK-013 — Push To Talk** ✅ (repo tarafı) — Bas-konuş modu, özelleştirilebilir Ctrl/Shift/Alt+
  tuş kombinasyonu, localStorage kalıcılığı, kayıt sırasında varsayılan davranış engelleme ve
  sekme görünürlüğü değişince güvenli mikrofon sıfırlaması eklendi. Global hotkey desteği tarayıcı
  güvenlik modeli nedeniyle kapsam dışıdır.
