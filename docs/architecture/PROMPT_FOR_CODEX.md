# Codex için ilk prompt

Bu prompt, Aşama 1 mimari çalışmasını Codex'e (veya benzeri bir kod asistanına) yaptırmak için hazırlanmıştır.

```
Bir proje geliştiriyoruz.

Proje adı:
Nexus Communication Platform

Amaç:
Discord benzeri ancak Discord alternatifi olmaktan daha fazlasını hedefleyen,
kendi plugin ve bot ekosistemine sahip özel iletişim platformu oluşturmak.

Temel altyapı:
- Matrix Synapse iletişim sunucusu olarak kullanılacak.
- Kendi frontend istemcimiz geliştirilecek.
- Matrix sadece mesajlaşma/ses/video altyapısı olarak kullanılacak.
- Platforma ait özel özellikler bizim backend katmanımızda bulunacak.

Hedef özellikler:

Core:
- Kullanıcı sistemi
- Roller
- Yetkiler
- Sunucu yönetimi
- Kanal yönetimi
- Profil sistemi
- Ayarlar

İletişim:
- Metin kanalları
- Ses kanalları
- Kamera
- Ekran paylaşımı
- Dosya paylaşımı

Plugin sistemi:
- Harici modül desteği
- Plugin yükleme
- Plugin yönetimi
- Plugin API

Bot sistemi:
- Event tabanlı bot altyapısı
- Komut sistemi
- API erişimi
- Yetki kontrolü

Özel modüller:
- AI asistan
- Oyun entegrasyonları
- Sistem izleme
- Otomasyon araçları

Teknoloji:
Frontend:
React + TypeScript

Backend:
Python FastAPI

Database:
PostgreSQL

Container:
Docker

İlk aşama:

Kod yazmaya başlamadan önce:

1. Profesyonel proje mimarisi oluştur.
2. Monorepo klasör yapısını tasarla.
3. Frontend/backend/plugin klasörlerini ayır.
4. API mimarisini planla.
5. Plugin sisteminin nasıl çalışacağını açıkla.
6. Geliştirme aşamalarını oluştur.

Henüz özellik kodlama.
Önce mimari plan hazırla.
```

Not: Monorepo iskeleti ve mimari plan zaten bu repoda oluşturuldu
(bkz. [../../ARCHITECTURE.md](../../ARCHITECTURE.md), [../../ROADMAP.md](../../ROADMAP.md)).
Codex'e bu prompt'u verirken mevcut yapıyı da referans gösterebilirsiniz.
