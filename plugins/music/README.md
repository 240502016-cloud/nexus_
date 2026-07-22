# music

Botu gerçekten sesli kanala katıp, platformun kendi WebRTC mesh'i üzerinden GERÇEK ses akıtan
bir kuyruk sistemi. Ollama'daki gibi durum mesajı yazan bir "now playing" panosu değil - bot
sesli kanala bir katılımcı gibi bağlanır ve diğer katılımcılar sesi gerçekten duyar.

## Komutlar

- `/muzik-katil <sesli-kanal-adı>` — bot, belirtilen sesli kanala katılır
- `/muzik-listele` — `library/` klasöründeki mevcut parçaları listeler
- `/muzik-ekle <parça-adı>` — kuyruğa ekler; kuyruk boşsa hemen çalmaya başlar
- `/muzik-kuyruk` — şu an çalan parçayı ve kuyruğu gösterir
- `/muzik-sonraki` — sıradaki parçaya geçer (kuyruk boşsa sessizleşir, kanaldan ayrılmaz)
- `/muzik-ayril` — bot sesli kanaldan ayrılır

## `library/` klasörü

Parçalar dosya adına göre (uzantısız, örn. `library/gece-yolculugu.mp3` → `/muzik-ekle
gece-yolculugu`) bulunur. `av` (FFmpeg tabanlı) kütüphanesinin okuyabildiği her format
(mp3/wav/ogg/flac/...) çalışır. **Bu plugin internetten şarkı indirmez** — kendi (yasal
olarak sahip olduğunuz) ses dosyalarınızı bu klasöre elle koymanız gerekir.

`library/test-tonu-440hz.wav` ve `library/test-tonu-880hz.wav`: gerçek müzik değil, ses
akışının uçtan uca çalıştığını doğrulamak için üretilmiş sentetik test tonları (saf Python
`wave` modülüyle üretildi, telif/indirme sorunu yok). Silinebilir.

## Mimari not

Bot'un sesli kanal katılımı, `backend/plugins/music/voice_session.py`'de `aiortc` (Python
WebRTC) ile uygulanıyor; bot'un "kullanıcı id"si olarak `-bot_id` (negatif) kullanılıyor, bu
yüzden ayrı bir platform hesabına ihtiyaç yok. Detaylı mimari için `voice_session.py`'nin
modül docstring'ine bakın.

## Bilinen sınırlamalar

- Bir sunucuda birden fazla bot varsa, hepsi aynı `/muzik-*` komutuna cevap vermeye çalışır
  (mevcut bot motorunun genel davranışı, bu plugin'e özgü değil).
- Otomatik parça-sonu ilerlemesi dosyanın süresini önceden hesaplayıp bekliyor; `/muzik-sonraki`
  her zaman güvenilir manuel yol.
