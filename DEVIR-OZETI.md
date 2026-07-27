# Nexus — Devir Özeti (yeni sohbete yapıştırılabilir)

Tarih: 26 Temmuz 2026
Sunucu makinesi: `C:\Users\merte\Github\nexus-server`
**Bu dosya, önceki `yol haritası.md`'nin yerini alır (o dosya artık eskidir: IP + kendi sertifikası dönemini anlatıyor).**

---

## 1. Şu anki durum: ÇALIŞIYOR

- **Adres:** https://cekin.gen.tr (port 80/443)
- **Sertifika:** Let's Encrypt, **gerçek/güvenilir** — istemciler artık sertifika KURMUYOR.
  DNS-01 doğrulaması (Cloudflare) ile alınır, otomatik yenilenir.
- **Erişim modeli:** Hâlâ **Hamachi gerekiyor** (A kaydı Hamachi IP'sine bakıyor: `25.49.22.166`).
  Kullanıcı adımları: Hamachi kur + ağa katıl → https://cekin.gen.tr → kayıt ol.
- Tüm container'lar healthy. Compose proje adı: `nexus_server_fresh`.

### Başlatma / durdurma (kolay yol)
- `Baslat-Nexus.cmd` (çift tıkla) → Docker Desktop'ı gerekirse açar, stack'i başlatır, tarayıcıyı açar.
- `Durdur-Nexus.cmd` → container'ları durdurur (veri korunur).

---

## 2. Mimari (kısa)

- **Frontend:** React 18 + TypeScript + Vite (state: hook'lar + localStorage, Redux yok)
- **Backend:** FastAPI + SQLAlchemy + PostgreSQL
- **Mesajlaşma:** Matrix/Synapse (backend arka planda kullanıcı/oda yönetir)
- **Ses/görüntü:** WebRTC **mesh** (sunucu medya relay etmez) + coturn (TURN/STUN)
- **Signaling:** kanal WS `/api/channels/{id}/voice` + **global gateway WS `/api/gateway`**
- **Reverse proxy:** Caddy (özel imaj, Cloudflare DNS eklentili)

### Kritik yapılandırma notları
- `MATRIX_SERVER_NAME=25.49.22.166` — **KASITLI olarak değiştirilmedi.** Değiştirmek mevcut
  kullanıcıların Matrix hesaplarını/token'larını geçersiz kılar. Domaine geçerken dokunulmadı.
- Backend `read_only: true` → yazma gerektiren her şey **volume** ister (avatar için `avatar_data`).
- Özel Caddy imajı: `nexus-caddy:2.11.4-cf` (kaynak: `docker/reverse-proxy/Dockerfile`).
- `.env`'de yeni: `CLOUDFLARE_API_TOKEN` (DNS-01 için). `AVATAR_DIR` opsiyonel (varsayılan `/srv/avatars`).
- **ASLA `docker compose down -v` çalıştırma** (volume'ları siler).

### Deploy döngüsü (kod değişince)
```
docker compose build backend frontend
docker compose up -d backend ai-worker plugin-sandbox frontend
```
Frontend kontrolü: `cd frontend && npm run lint && npm run build`

### Test yöntemi (bu oturumda kullanılan)
Backend container'ı içinden gerçek token + istek/WS ile uçtan uca test:
```
docker compose exec -T backend python3 -c "
from app.core.auth import create_access_token
import requests, websockets, asyncio, json
..."
```
Mevcut kullanıcılar: `mutbelagtest` (id 1), `apeacefulman` (id 2), id 3.

---

## 3. Bu oturumda YAPILANLAR (hepsi test edildi + canlıda)

### Altyapı
1. **TLS kök nedeni bulundu ve çözüldü** — sorun Windows/curl değildi: IP'ye bağlanırken SNI
   gönderilmediği için Caddy sertifika seçemiyordu. (Sonra domaine geçilince konu kapandı.)
2. **Domaine geçiş** — `cekin.gen.tr`, Cloudflare DNS-01 + Let's Encrypt, özel Caddy imajı,
   portlar 8080/8443 → 80/443.
3. **Tek tıkla başlatma/durdurma** script'leri.

### Ses / görüntü / çağrı
4. **Deafen (sağıra alma)** + Discord tarzı kompakt ses kontrol çubuğu.
5. **Ekran paylaşımı + kamera** — WebRTC "perfect negotiation"a geçirildi (eski kod bağlantı
   sonrası track eklemeyi desteklemiyordu).
6. **Çağrı sistemi** — global gateway WS: presence + `call-invite/accept/reject/cancel`,
   zil sesi, Kabul/Reddet modalı, üye listesinden 📞 ile çağırma.
7. **KRİTİK HATA 1 — kamera açınca sesin gitmesi:** `ontrack` artık her peer için track'leri tek
   birleşik `MediaStream`'de biriktiriyor (ses ve video ayrı MSID ile geliyordu, ses eziliyordu).
8. **KRİTİK HATA 2 — kanala girmeden katılımcıları görme:** voice roster'ı callback ile gateway'e
   yayınlanıyor; sunucunun tüm üyeleri (kanalda olmasa da) canlı listeyi görüyor + snapshot +
   hayalet temizliği + yetki kontrolü.
9. **KRİTİK HATA 3 — cihaz yönetimi:** mikrofon/hoparlör/kamera listeleme ve seçimi, `setSinkId`,
   görüşme sırasında canlı mikrofon değişimi (`replaceTrack`), mikrofon seviye testi, kamera
   önizleme, hoparlör test sesi, gürültü/yankı/kazanç (gerçek MediaTrackConstraints), kalıcı tercih.
10. **PTT düzeltmesi** — metin alanına yazarken tetiklenmiyor ve yazmayı engellemiyor.

### Hesap / arayüz
11. **Sekmeli Ayarlar:** Hesabım · Ses ve Video · Bildirimler · Görünüm.
12. **Hesabım** — görünen ad düzenleme, **parola değiştirme** (mevcut parola doğrulamalı).
13. **Avatar yükleme** — güvenli: magic-byte MIME kontrolü, 2 MB limiti, rate limit, path-traversal
    koruması, eski dosya temizliği, istemcide kare kırpma + 256px. Avatarlar üye/roster listelerinde.
14. **Bildirimler** — gelen çağrı için masaüstü bildirimi (sekme arka plandayken) + izin yönetimi +
    zil sesi anahtarı.
15. **Tema** — açık/koyu/sistem (tüm renkler CSS değişkenlerine taşındı, `color-scheme` dahil).
16. **Kullanıcı durumları** — çevrimiçi/boşta/rahatsız etmeyin/**görünmez** + özel durum metni,
    üye listesinde renkli durum noktaları.

### Yönetim / mesajlaşma
17. **Mesaj silme** (Matrix redact; silinenler listeden eleniyor).
18. **Kanal yönetimi** — yeniden adlandır + sil (sahip-only, backend'de doğrulanıyor).
19. **Üye çıkarma (kick)** + üyenin kendi ayrılması; sunucu sahibi korunuyor.
20. **Sunucu yönetimi** — yeniden adlandır + sil (cascade) + ayrıl.
21. **GERÇEK ZAMANLI MESAJLAŞMA** — gateway `channel-message` sinyali; mesaj ~126 ms'de düşüyor
    (eskiden 4 sn polling). Polling yedek olarak 10 sn'ye çıkarıldı.

---

## 4. YAPILMADI — planlanan sıradaki işler

### Orta boy (her biri ~1 tur)
- **Mesaj düzenleme** (Matrix `m.replace`; edit event'lerini orijinalle birleştirme gerekir — bu
  yüzden ertelendi, `get_messages` ciddi değişecek)
- Emoji tepkileri · mesaj yanıtlama · mesaj arama · sabitlenmiş mesajlar
- Yazıyor ("typing") göstergesi · okunmamış mesaj sayacı · bahsetmeler (@)
- Dosya/görsel eki (avatar altyapısı örnek alınabilir)
- Otomatik "boşta" algılama (şu an durum manuel)
- Kullanıcı başına ses seviyesi + yerel susturma
- Video kalite seçimi / bağlantı kalitesi göstergesi
- Sesli kanal için otomatik yeniden bağlanma (gateway'de var, voice WS'te yok)
- Üye **ban**/unban · rol renkleri · kanal bazlı izinler
- Mobil/responsive gözden geçirme (masaüstü odaklı test edildi)

### Büyük (her biri birkaç tur, ayrı mini-proje)
- **Tam RBAC + audit log** (izinler şu an "sahip mi?" düzeyinde; model/permissions altyapısı var
  ama uçtan uca kullanılmıyor)
- **Otomatik test paketi** (unit/integration/E2E — şu an yalnızca `backend/tests/` içinde Ollama
  testleri var; bu oturumdaki tüm doğrulamalar elle yazılan geçici script'lerle yapıldı)
- **i18n / dil desteği** (metinler bileşenlerin içinde sabit, Türkçe)
- **2FA** + oturum yönetimi (aktif oturumlar, diğer cihazlardan çıkış)
- Gizlilik: engelleme/DM tercihleri/raporlama

### Bilinen sınırlamalar
- Ses/görüntü **mesh** — 4-5 kişiden sonra CPU/bant genişliği artar (SFU gerekir).
- PTT yalnızca sekme odaktayken çalışır (tarayıcı kısıtı).
- `setSinkId` (hoparlör seçimi) yalnızca Chrome/Edge'de; diğerlerinde bilgi mesajı gösteriliyor.
- Gateway/presence **tek process** bellek içi — birden çok worker'a geçilirse Redis vb. gerekir.
- Manuel 2-kullanıcı testleri (kamera+ses birlikte, ekran paylaşımı, çağrı zili) kullanıcı
  tarafından son kez doğrulanmalı.

---

## 5. Güvenlik notları (ÖNEMLİ)

- `.env`, `ai-gateway/.env`, `artifacts/`, DB yedekleri **Git'e gönderilmez**.
- ⚠️ `.env.bak.*` dosyaları gizli anahtar içerir ve eski `.gitignore` deseni (`.env.backup-*`)
  bunları YAKALAMIYORDU. Push öncesi `.gitignore`'a `*.bak.*` ve `.env.bak*` eklenmelidir.
- API anahtarları sohbette paylaşılmaz.
- Parolalar DB'de **PBKDF2-SHA256 (200k tur, salt)** ile hash'li — düz metin okunamaz, yalnızca
  sıfırlanabilir.
- Eski kurulum (`nexus-current`) ve eski `nexus_*` volume'ları hâlâ duruyor; yeni sistem stabil
  kaldıkça kontrollü silinebilir.

---

## 6. 27 Temmuz 2026 — Arayüz ve performans güncellemesi

### Arayüz / yayın
- Ana arayüz ve giriş/kayıt ekranları koyu cam efektli + açık profesyonel tema ile yenilendi.
- Video sahnesi odak yayın + küçük önizlemeler düzenine geçti; görüntü `contain` ile kaydırmasız,
  eksiksiz gösteriliyor.
- Gerçek tam ekran ve tam ekranda mikrofon, ses, kamera, ekran paylaşımı ve ayrılma kontrolleri eklendi.
- Kamera/ekran paylaşımı için kullanıcı seçimi: **480p / 720p / 1080p** ve **30 / 60 FPS**.

### Mesajlaşma / gecikme
- Mesajlar Enter'a basıldığı anda iyimser olarak görünür; başarısız olursa tekrar deneme sunulur.
- `client_id`, Matrix transaction ID olarak kullanılır; zaman aşımı/tekrar denemede çift mesaj önlenir.
- Gateway `channel-message` artık mesaj payload'ını ve silme olaylarını doğrudan taşır. Normal mesajlarda
  her olay için son 50 mesajı yeniden indirme kaldırıldı.
- Senkron bot cevapları da payload olarak anında iletilir. Ayrı AI worker cevapları için düşük frekanslı
  snapshot güvenlik ağı devam eder.

### Kaynak tüketimi / dayanıklılık
- Mesaj snapshot aralığı gateway bağlıyken 30 sn, bağlantı yokken 10 sn, arka planda 5 dk.
- Konuşma algılama ~60 Hz'den ~13 Hz'e düşürüldü; sekme arka plandayken analyser tamamen durur.
- Arka plandaki video elemanları duraklatılır (ses ayrı audio elemanından devam eder).
- Gateway ve ses kanalı WebSocket'lerine jitter'lı exponential backoff ve ağ geri gelince hızlı
  yeniden bağlanma eklendi. Ses kanalında mevcut mikrofon/kamera track'leri korunur.
- Matrix HTTP çağrıları thread-local keep-alive session kullanır; connect/read timeout eklendi.

### Bu sürümün deploy'u
Bu güncelleme hem backend hem frontend içerir:
```
docker compose build backend frontend
docker compose up -d backend ai-worker plugin-sandbox frontend
```

---

## 7. 27 Temmuz 2026 — Şans Ustası oyun botu

### Eklenen oyunlar
- **Taş · Kağıt · Makas:** `/takama @kullanıcı` daveti, ekranda Kabul/Reddet kartı,
  `/kabul <kod>` alternatifi ve kabulden sonra otomatik komut rehberi.
- `/taş`, `/kağıt`, `/makas` hamleleri **Matrix'e hiç yazılmaz**. İlk oyuncunun seçimi
  rakip tamamlayana kadar PostgreSQL'de gizli kalır; iki hamle aynı anda açıklanır.
- **Yazı · Tura:** `/yazıtura` tek kişilik; `/yazıtura @kullanıcı` davetli düello.
- **Çarkıfelek:** kullanıcı+kanal başına kalıcı çark; `/ekleçark`, `ekleçark: elma`,
  `/çarkliste`, `/çıkarçark`, `/temizleçark`, `/çark`. Ağırlıklı seçenek:
  `/ekleçark elma | 3`.

### Güvenlik / dayanıklılık
- Rastgelelik sunucu tarafında `secrets` ile sağlanır; harici/ücretli API yoktur.
- Davet 2 dakika, aktif karşılaşma 5 dakika zaman aşımlıdır.
- Kullanıcı aynı anda tek açık oyunda olabilir; kendine davet ve sunucu dışı etiket reddedilir.
- Oyunlar ve çarklar backend yeniden başladığında kaybolmaz (`0005_chance_games` migration).
- `chance_games` yalnız açıkça bağlandığı botta çalışır; aynı sunucuda ikinci bağ engellenir.
- Yapılandırılmış oyun kartları yalnız backend'in `is_bot` olarak doğruladığı mesajlarda açılır.
- Sandbox DB anahtarı almaz; yalnız doğrulanmış eylem zarfı Core oyun servisine iletilir.

### Yönetim ekranından etkinleştirme
1. **Botlar → Platform pluginleri → `chance_games` → Kur**
2. Yeni bot oluştururken **Bota özel plugin: `chance_games`** seç; veya mevcut botta
   **chance_games bağla** düğmesini kullan.
3. Sohbette `/şans` ile tam rehberi aç.

### Deploy (migration içerir)
```
docker compose build backend frontend
docker compose run --rm migrate
docker compose up -d backend ai-worker plugin-sandbox frontend
```

Doğrulama: 16 backend testi, frontend TypeScript lint ve production build başarılı.
