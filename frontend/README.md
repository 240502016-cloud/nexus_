# Frontend

React + TypeScript istemcisi (Vite). Discord'a benzer 3 panelli temel layout:
sunucu rail'i / kanal listesi / sohbet alanı. Gerçek Core API'ye bağlı — mock veri yok.
İleride Tauri/Electron ile masaüstü uygulamasına (`.exe`) dönüştürülecek.

```
src/
├── main.tsx              # giriş noktası
├── App.tsx                # auth state, sunucu/kanal/mesaj veri akışı, tüm API çağrıları
├── types.ts                # backend/app/core/schemas.py ile uyumlu tipler (snake_case)
├── api/client.ts             # Core API fetch sarmalayıcısı; JWT'yi localStorage'da tutar
├── hooks/
│   └── useVoiceChannel.ts     # WebRTC mesh + WS signaling + konuşma tespiti (bkz. aşağı)
└── components/
    ├── LoginForm.tsx            # kullanıcı adı/parola -> POST /auth/login
    ├── RegisterForm.tsx          # kullanıcı adı/e-posta/parola -> POST /users, sonra otomatik giriş
    ├── ServerRail.tsx            # sunucu ikonları + yeni sunucu oluşturma
    ├── ChannelSidebar.tsx          # kanallar + yeni kanal oluşturma (metin/ses seçimi, sadece sahip)
    ├── ChatArea.tsx                  # mesaj listesi (4sn'de bir yenilenir) + gönderme formu
    └── VoicePanel.tsx                  # sesli kanal katılımcı listesi + mute/ayrıl
```

## Veri akışı

1. Açılışta `localStorage`'daki token ile `GET /users/me` denenir; geçersizse login ekranı gösterilir
2. Giriş sonrası `GET /servers` (current_user'ın üyesi olduğu sunucular)
3. Sunucu seçilince `GET /servers/{id}/channels`
4. Kanal seçilince `GET /channels/{id}/messages` (4 saniyede bir yeniden çekilir — gerçek zamanlı
   push değil, basit polling; bkz. [ROADMAP.md](../ROADMAP.md))
5. Mesaj gönderme: `POST /channels/{id}/messages`, ardından mesaj listesi yeniden çekilir

Tarayıcıda gerçek bir kullanıcıyla (`mert2`) uçtan uca test edildi: login, gerçek sunucu/kanal/
mesaj geçmişi (bot cevapları, silinen mesajlar "(silindi)" olarak dahil) doğru göründü, yeni
mesaj gönderme çalıştı.

## Sesli kanal

`ChannelSidebar`'da `🔊` tipi bir kanala tıklamak (metin kanalından farklı olarak) o kanala
**katılır** — `VoicePanel` açılır, `useVoiceChannel` hook'u:
1. `getUserMedia({audio:true})` ile mikrofona erişir
2. Auth ile `/api/voice/ice-servers` endpoint'inden kısa ömürlü coturn credential'ı alır
3. `WS /api/channels/{id}/voice?token=...`'a bağlanır (backend'deki signaling relay)
4. Mevcut katılımcıların her birine `RTCPeerConnection` kurup offer gönderir (mesh topoloji)
5. Web Audio `AnalyserNode` ile kendi ses seviyesini izler, eşiği geçince `speaking` bildirir

Durum göstergeleri: 🟢 konuşuyor, 🔴 sessize alınmış, ⚪ boşta.

**Test kısıtı:** Bu geliştirme ortamındaki tarayıcı sandbox'ı mikrofon erişimini engelliyor
(`getUserMedia` "Permission denied" döner) — bu yüzden gerçek ses akışını burada test
edemedim. Doğruladığım kısımlar: hata durumunun düzgün yakalanıp Türkçe mesajla gösterilmesi
(çökme yok), katılımcı listesinin/butonların doğru render olması, kanal oluşturma formundaki
metin/ses seçiminin çalışması, katıl/ayrıl döngüsünün temiz (konsol hatasız) çalışması.
Signaling protokolünün kendisi (offer/answer/ICE relay/mute/leave) backend tarafında gerçek
WebSocket istemcileriyle uçtan uca doğrulandı (bkz. [../backend/README.md](../backend/README.md)).
Gerçek mikrofonlu bir tarayıcıda iki kullanıcıyla elle test edilmesi önerilir.

### Push-to-talk (TASK-013)

Ses ayarları panelinden `toggle` veya bas-konuş modu seçilebilir. Bas-konuş modunda varsayılan
kombinasyon `Ctrl + Shift`'tir; kombinasyon değiştirilebilir ve `localStorage`'da saklanır.
Kombinasyon yalnızca tarayıcı sekmesi odaktayken yakalanır. Sekme gizlenince basılı tuş durumu
otomatik sıfırlanır ve mikrofon açık kalmaz. Tarayıcı güvenlik modeli nedeniyle oyun gibi arka
plandaki uygulamalarda gerçek global hotkey desteği mümkün değildir.

## Çalıştırma

```bash
cd frontend
npm install
npm run dev
```

`vite.config.ts` içindeki proxy, `/api/*` isteklerini `http://localhost:8000`'e (Core API)
yönlendirir. Backend ve Postgres/Synapse'in ayakta olması gerekir (proje kökünden
`docker compose up -d`, sonra `cd backend && uvicorn app.main:app --reload`).

LAN geliştirme: Vite `0.0.0.0:5173` üzerinde dinlediği için aynı ağdaki cihazlardan
`http://192.168.1.174:5173` adresiyle açılabilir. Gerçek WebRTC relay testi için TURN değişkenlerini
`.env` içinde ayarlayın; `192.168.1.174` yalnızca LAN içi test adresidir.
