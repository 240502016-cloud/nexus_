# Nexus Communication Platform — Mimari Plan

Bu doküman, `PROMPT_FOR_CODEX.md` içindeki prompt'a doğrudan cevap olarak, dış bir araca
(Codex vb.) gönderilmeden, bu oturumda hazırlanmıştır. Prompt'un istediği 6 maddeyi sırayla
karşılar. Henüz özellik kodu yazılmamıştır — bu bir mimari plandır.

---

## 1. Profesyonel Proje Mimarisi

```
                    Kullanıcı
                       |
              Desktop/Web Client
             (Bizim arayüzümüz)
                       |
              ----------------
              |              |
          Core API       Matrix API
              |              |
       Platform Engine    Matrix Server
              |
    ------------------------
    |          |            |
 Plugin     Bot Engine   Automation
 System
    |
 -------------------------
 |          |             |
AI Bot   Game Bot   Moderation Bot
```

Katman sorumlulukları:

| Katman            | Sorumluluk                                                         |
|--------------------|---------------------------------------------------------------------|
| Client             | Kullanıcı arayüzü; Core API + Matrix API'ye bağlanır               |
| Core API           | Kullanıcı/rol/yetki/sunucu/kanal yönetimi, REST + WebSocket        |
| Matrix Server      | Sadece iletişim motoru: metin/ses/video/dosya                      |
| Platform Engine    | Core API'nin arkasındaki iş mantığı (backend/core)                 |
| Plugin System       | Harici modüllerin yüklenmesi ve platforma entegrasyonu             |
| Bot Engine          | Event tabanlı bot altyapısı, komut yönlendirme                     |
| Automation          | Zamanlanmış görevler, otomasyon akışları                           |

Matrix, bilinçli olarak "aptal" bırakılır: sadece mesaj/medya taşır. Yetki, plugin, bot gibi
platforma özgü tüm mantık Core API + Platform Engine katmanında yaşar. Bu sayede Matrix
Synapse güncellemeleri platform mantığını etkilemez ve istenirse iletişim motoru
değiştirilebilir hale gelir.

## 2. Monorepo Klasör Yapısı

```
nexus-communication-platform/
├── frontend/               # React + TypeScript istemci
│   └── src/
├── backend/                 # Python FastAPI
│   ├── core/                 # kullanıcı, rol, yetki, sunucu/kanal, ayarlar, log
│   ├── plugins_engine/       # plugin yükleme/yönetim, plugin API
│   └── bot_engine/           # event sistemi, komut sistemi, bot yetki kontrolü
├── plugins/                 # bağımsız plugin modülleri
│   ├── ai_assistant/
│   ├── game_status/
│   ├── moderation/
│   ├── music/
│   └── server_monitor/
├── matrix/                  # Matrix Synapse konfigürasyonu
│   └── synapse/
├── docs/architecture/        # mimari dokümantasyon (bu dosya dahil)
├── docker-compose.yml         # Postgres + Synapse altyapı taslağı
├── .env.example
└── .gitignore
```

Bu yapı zaten repoda oluşturuldu (bkz. proje kökü).

## 3. Frontend / Backend / Plugin Ayrımı

- **frontend/** — sadece sunum katmanı. İş mantığı içermez; Core API ve Matrix API'den veri
  çeker/gönderir. Roller, yetkiler gibi kararlar burada değil backend'de verilir.
- **backend/** — platformun beyni. Üç alt modüle ayrılır (core, plugins_engine, bot_engine)
  ki her biri bağımsız test edilip geliştirilebilsin.
- **plugins/** — backend'in *dışında*, kendi klasöründe izole yaşar. Böylece bir plugin bozulsa
  bile core platform çalışmaya devam eder. Plugin'ler backend'e yalnızca `plugins_engine`
  üzerinden, tanımlı bir API sözleşmesiyle konuşur — doğrudan core'un içine gömülmez.

Bu ayrımın amacı: frontend'i değiştirmeden backend'i, backend'i değiştirmeden plugin'leri
geliştirebilmek.

## 4. API Mimarisi

- **Core API** (FastAPI, REST + WebSocket)
  - `/users`, `/roles`, `/permissions` — kullanıcı ve yetki yönetimi
  - `/servers`, `/channels` — sunucu/kanal yönetimi
  - `/plugins` — plugin listeleme, yükleme, yapılandırma
  - `/bots` — bot kayıt, yetkilendirme, event abonelikleri
  - WebSocket — gerçek zamanlı olaylar (bildirim, durum güncellemesi)
- **Matrix API** — Matrix Synapse'in standart Client-Server API'si; mesajlaşma/ses/video/dosya
  için doğrudan kullanılır, yeniden icat edilmez.
- İstemci her iki API'ye de bağlanır. Core API, gerektiğinde (ör. bir bot mesaj gönderdiğinde)
  Matrix API'yi sunucu tarafında çağırır — istemci Matrix detaylarıyla uğraşmak zorunda kalmaz.
- Kimlik doğrulama: Core API kendi oturum/token sistemini yönetir, Matrix hesapları Core API
  tarafından arka planda provision edilir (kullanıcı Matrix'in varlığını hissetmez).

## 5. Plugin Sisteminin Çalışma Şekli

Her plugin kendi klasöründe, sabit bir sözleşmeyle yaşar:

```
plugins/<plugin_adi>/
  plugin.json     # isim, versiyon, gerekli izinler, giriş noktası
  main.py         # plugin_engine'in çağıracağı giriş fonksiyonları
  config.yaml     # plugin'e özel ayarlar
```

Akış:
1. `plugins_engine`, `plugins/` klasörünü tarar, her `plugin.json`'ı okur.
2. İzin (permission) beyan eden plugin'ler, kullanıcı/yönetici onayına sunulur.
3. Onaylanan plugin `main.py` üzerinden yüklenir ve Plugin API'ye (event abonelikleri,
   komut kaydı, HTTP çağrı yetkisi vb.) erişim kazanır.
4. Bot Engine, bir komut/mesaj geldiğinde ilgili plugin'e yönlendirir.

Örnek: `"Minecraft sunucum açık mı?"` → Bot Engine → `game_status` plugin'i → harici oyun
sunucusu API'sine sorgu → `"Online, 23 oyuncu"` yanıtı kullanıcıya döner.

Bu tasarımın kuralı: plugin'ler platformun *çekirdeğine* asla doğrudan erişemez, sadece
`plugins_engine`'in sunduğu API yüzeyi üzerinden konuşur. Böylece kötü/hatalı bir plugin
core platformu çökertemez.

## 6. Geliştirme Aşamaları

1. **Arayüz + Core Yapı** — monorepo iskeleti, core modelleri (kullanıcı/rol/yetki/sunucu/kanal), frontend iskeleti
2. **Matrix Bağlantısı** — Synapse'in Docker ile ayağa kalkması, Core API ↔ Matrix API entegrasyonu
3. **Plugin Sistemi** — plugin yükleme mekanizması, Plugin API, ilk örnek plugin ile uçtan uca test
4. **Bot Motoru** — event sistemi, komut sistemi, bot yetki kontrolü
5. **AI ve Özel Modüller** — `ai_assistant`, `game_status`, `moderation`, `music`, otomasyon araçları

Detaylar için [../../ROADMAP.md](../../ROADMAP.md).

---

**Sonuç:** Yukarıdaki 6 madde, `PROMPT_FOR_CODEX.md`'deki isteğin tam karşılığıdır ve dış bir
araca gönderilmeden bu oturumda üretilmiştir. Henüz hiçbir özellik kodu yazılmadı; sıradaki adım
Aşama 1 kapsamında `backend/core` için gerçek FastAPI modellerinin kurulmasıdır.
