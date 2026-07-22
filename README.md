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
└── docs/architecture/ # Mimari diyagramlar ve notlar
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

Şu an sadece mimari plan ve monorepo iskeleti oluşturuldu. Henüz özellik kodu yazılmadı
(bkz. [ROADMAP.md](./ROADMAP.md) Aşama 1).
