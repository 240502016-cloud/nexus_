# Mimari Plan

## Genel Bakış

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

Matrix Synapse sadece iletişim motoru (mesajlaşma/ses/video) olarak kullanılır.
Kendi katmanımız (Core Platform + Plugin System + Bot Engine) bunun üzerine oturur.

## Katmanlar

### 1. Client (frontend/)
- React + TypeScript web istemcisi
- İleride Tauri/Electron ile masaüstü uygulamasına dönüştürülecek
- Matrix API'ye ve Core API'ye konuşur

### 2. Core Platform (backend/core/)
Kendi yazacağımız temel katman:
- Kullanıcı profilleri
- Roller ve yetki sistemi
- Sunucu / kanal yönetimi
- Ayarlar
- Log sistemi

### 3. Matrix Server (matrix/)
- Matrix Synapse, sadece iletişim altyapısı (metin, ses, kamera, ekran paylaşımı, dosya)
- Core Platform, Matrix API üzerinden mesajlaşma/medya işlevlerini kullanır

### 4. Plugin System (backend/plugins_engine/, plugins/)
Harici modülleri platforma entegre eden sistem:
- Plugin yükleme / kaldırma / yönetim
- Plugin API (platformun sunduğu kancalar/hooks)
- Her plugin kendi klasöründe izole çalışır:
  ```
  plugins/<plugin_adi>/
    plugin.json     # meta bilgi (isim, versiyon, izinler)
    main.py         # giriş noktası
    config.yaml     # plugin ayarları
  ```

Örnek akış:
```
Kullanıcı: "Minecraft sunucum açık mı?"
   → Bot Engine, komutu ilgili plugin'e yönlendirir
   → game_status plugin'i harici API'ye sorar
   → Sonuç: "Online, 23 oyuncu" olarak kullanıcıya döner
```

### 5. Bot Engine (backend/bot_engine/)
Botlar normal kullanıcı değil, **servis** olarak tasarlanır:
- Event tabanlı sistem (mesaj, katılım, ayrılma vb. olaylarını dinler)
- Komut sistemi (`/weather Istanbul`, `@AI bana bu kodu açıkla`)
- Plugin API erişimi
- Yetki kontrolü (bir botun hangi kanal/sunucuda ne yapabileceği)

### 6. Özel Modüller (plugins/)
İlk hedeflenen pluginler:
- `ai_assistant` — AI destekli asistan
- `game_status` — oyun sunucusu durum takibi
- `moderation` — moderasyon araçları
- `music` — müzik botu
- `server_monitor` — sistem/sunucu izleme

## Teknoloji Kararları ve Gerekçeleri

- **Frontend: React + TypeScript** — büyük ekosistem, Discord benzeri arayüz kurmak kolay, ileride Electron'a taşınabilir.
- **Backend: Python FastAPI** — bot geliştirmek ve AI entegrasyonu kolay, API yazımı hızlı.
- **Database: PostgreSQL** — platforma özgü verilerin (kullanıcı, rol, plugin config) saklandığı yer.
- **Container: Docker** — Matrix Synapse + Postgres + backend servislerinin birlikte çalıştırılması için.

## API Mimarisi (taslak)

- `Core API` (FastAPI, REST + WebSocket): kullanıcı/rol/sunucu/kanal yönetimi, plugin yönetimi, bot yönetimi.
- `Matrix API`: Matrix Synapse'in sunduğu Client-Server API; mesajlaşma/ses/video/dosya için doğrudan kullanılır.
- İstemci hem Core API'ye hem Matrix API'ye bağlanır; Core API gerektiğinde Matrix API'yi de çağırabilir (ör. bot mesajı gönderme).
