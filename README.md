# Nexus Communication Platform

Discord benzeri temel iletişim özelliklerine sahip, ancak Discord'un bir kopyası olmayı
hedeflemeyen; kendi plugin ve bot ekosistemine sahip özel bir iletişim platformu.

## Temel Fikir

Matrix Synapse yalnızca **iletişim motoru** (mesajlaşma/ses/video altyapısı) olarak kullanılır.
Platforma özgü tüm özellikler (kullanıcı sistemi, roller, yetkiler, plugin sistemi, bot motoru)
kendi backend katmanımızda yaşar.

Detaylı mimari için [ARCHITECTURE.md](./ARCHITECTURE.md), geliştirme aşamaları için
[ROADMAP.md](./ROADMAP.md) dosyalarına bakın.

## Monorepo Yapısı

```
nexus-communication-platform/
├── frontend/          # React + TypeScript istemci
├── backend/           # Python FastAPI - core, plugin engine, bot engine
│   ├── core/          # Kullanıcı, rol, yetki, sunucu/kanal yönetimi
│   ├── plugins_engine/# Plugin yükleme, yönetim, plugin API
│   └── bot_engine/    # Event tabanlı bot altyapısı, komut sistemi
├── plugins/           # Bağımsız plugin modülleri (ai_assistant, moderation, ...)
├── matrix/            # Matrix Synapse konfigürasyonu
├── docker/            # PostgreSQL, Matrix ve Caddy production yapılandırması
└── docs/              # Mimari ve deployment dokümantasyonu
```

## Teknoloji Yığını

| Katman     | Teknoloji              |
|------------|-------------------------|
| Frontend   | React + TypeScript      |
| Masaüstü   | Tauri / Electron (sonraki aşama) |
| Backend    | Python FastAPI          |
| Database   | PostgreSQL              |
| İletişim   | Matrix Synapse          |
| Container  | Docker                  |

## Durum

Core platform, Matrix metin mesajlaşması, plugin/bot sistemi, AI Gateway, WebRTC sesli kanal
ve production Docker topolojisi uygulanmış durumda. Güncel eksikler ve doğrulama notları için
[ROADMAP.md](./ROADMAP.md) dosyasına bakın.

## Production Docker

Production düzeni `frontend`, `backend`, `postgres`, `matrix` ve `reverse-proxy` ana servislerine
ek olarak tek-seferlik `migrate`, kalıcı `ai-worker` ve izole `plugin-sandbox` yardımcı servislerini içerir. Kurulumdan
önce veri migration uyarılarını ve gerekli secret/domain ayarlarını okuyun:
[docs/deployment/DOCKER_PRODUCTION.md](./docs/deployment/DOCKER_PRODUCTION.md).

Domain, otomatik HTTPS, WSS, Matrix discovery ve dış doğrulama adımları için
[docs/deployment/HTTPS_REVERSE_PROXY.md](./docs/deployment/HTTPS_REVERSE_PROXY.md) dosyasına bakın.

PostgreSQL dış port güvenliği, Alembic migration, backup ve restore akışı için
[docs/deployment/DATABASE_SECURITY.md](./docs/deployment/DATABASE_SECURITY.md) dosyasına bakın.

AI isteklerinin PostgreSQL kuyruğu ve ayrı worker ile işlenmesi için
[docs/deployment/AI_WORKER.md](./docs/deployment/AI_WORKER.md) dosyasına bakın.
AI çıktısının token bütçesi, SSE akışı ve kullanıcı iptali için aynı dokümandaki TASK-008 bölümüne bakın.
