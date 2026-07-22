# Plugins

## TASK-010 sandbox sınırı

Plugin kodu production modunda Core API process'ine import edilmez. `PluginRegistry`,
komut context'ini yalnızca `plugin-sandbox` container'ına gönderir; sandbox da isteği
kısa ömürlü bir subprocess'te çalıştırır. Container read-only filesystem, ayrı internal
network, `no-new-privileges`, tüm capability'lerin kaldırılması, CPU/RAM/PID sınırları ve
timeout ile başlatılır. Sandbox'ın Postgres/Matrix credential'ı yoktur.

```dotenv
PLUGIN_EXECUTION_MODE=sandbox
PLUGIN_SANDBOX_URL=http://plugin-sandbox:8091
PLUGIN_SANDBOX_API_KEY=<uzun-rastgele-secret>
PLUGIN_SANDBOX_TIMEOUT_SECONDS=10
PLUGIN_SANDBOX_MAX_PAYLOAD_BYTES=65536
PLUGIN_SANDBOX_MAX_OUTPUT_BYTES=65536
```

`PLUGIN_EXECUTION_MODE=local` yalnızca kontrollü geliştirme/test içindir; bu mod plugin
Python kodunu doğrudan backend process'ine yükler ve güvenlik sınırı sağlamaz. Sandbox'a
taşınmamış plugin'ler Core DB/Matrix gibi backend içi kaynakları doğrudan import edemez;
bu yetenekler ileride açıkça tanımlı, izin kontrollü bir Plugin API üzerinden verilecektir.

Her plugin kendi klasöründe izole çalışır:

```
plugins/<plugin_adi>/
  plugin.json     # meta bilgi: name, version, description, entry_point, permissions, commands
  main.py         # entry_point'in işaret ettiği fonksiyonu içerir, örn. handle_command(context)
  config.yaml     # plugin'e özgü ayarlar (henüz plugin_engine tarafından okunmuyor)
```

`entry_point` formatı: `"<modül_dosyası>:<fonksiyon_adı>"`, örn. `"main:handle_command"`.
Fonksiyon bir `app.plugins_engine.context.PluginContext` alır, bir string döner.

## Yükleme akışı (`backend/app/plugins_engine/`)

1. `loader.discover_manifests()` — bu klasörü tarar, her `plugin.json`'ı okur/doğrular
2. `POST /plugins/{name}/install` — plugin'in `main.py`'ını içe aktarır, komutlarını
   `PluginRegistry`'ye kaydeder, Postgres'te `enabled=True` olarak işaretler
3. `POST /plugins/commands/run` — bir komutu ilgili plugin'e yönlendirir, çıktısını döner
4. `POST /plugins/{name}/uninstall` — komutları kayıt defterinden çıkarır, `enabled=False` yapar

Sunucu her yeniden başladığında, Postgres'te `enabled=True` olan pluginler otomatik olarak
belleğe geri yüklenir (`main.py::_reload_enabled_plugins`). Bir plugin'in `main.py`'ındaki
hata (import veya çalışma zamanı) sadece o plugine yansır, Core API çökmez.

## Uygulanmış örnekler

- **`server_monitor`** — `/sunucu-durumu` komutu, gerçek sistem bilgisini (CPU çekirdek
  sayısı, disk kullanımı) döndürür. Kurulmadan önce komut `404`, kaldırıldıktan sonra tekrar `404`.
- **`ai_assistant`** — `/sor <soru>` komutu, backend'in ortak `OllamaClient` servisini kullanır.
  Backend doğrudan Ollama'ya değil, Tailscale üzerindeki kimlik doğrulamalı AI Gateway'e
  bağlanır; gateway AI bilgisayarındaki `127.0.0.1:11434` Ollama'ya proxy olur. Varsayılan model
  `qwen2.5:7b`'dir ve çağrı öncesinde kurulu model listesinde doğrulanır. Anthropic/OpenAI gibi
  ücretli bir API kullanılmaz.
- **`game_status`** — `/oyun-durumu <host:port>` komutu, Minecraft Server List Ping
  protokolünü (varint + JSON el sıkışması) sıfırdan, ham TCP soketi ile uygular — üçüncü
  parti kütüphane kullanmaz. Gerçek bir public sunucuya (Hypixel) karşı test edildi.
- **`moderation`** — `/sil <event_id>` komutu, sadece sunucu sahibinin çalıştırabildiği,
  gerçek bir Matrix mesaj silme (redaction) işlemi. `PluginContext`'teki `server_id` ile
  yetki kontrolü yapar, sahibin kendi Matrix hesabıyla siler (bkz. `app.core.matrix_client.
  redact_message`). Bu plugin, `app.database`/`app.core.models`'ı doğrudan import eden ilk
  plugin — plugin'ler backend süreciyle aynı Python yorumlayıcısında çalıştığı için mümkün.
- **`music`** — `/muzik-katil`, `/muzik-ekle`, `/muzik-kuyruk`, `/muzik-sonraki`, `/muzik-ayril`,
  `/muzik-listele` komutları. Diğerlerinden farklı olarak sadece Matrix'e metin yazmıyor -
  bot gerçekten platformun kendi sesli kanal WebRTC mesh'ine (`backend/app/core/routers/voice.py`)
  katılıp `aiortc` (Python WebRTC) ile GERÇEK ses akıtıyor; kullanıcı adı `plugins/music/library/`
  klasöründeki bir dosyaya karşılık geliyor. Bot'un "kullanıcı id"si `-bot_id` (negatif) —
  ayrı bir platform hesabına ihtiyaç yok, detaylar için `plugins/music/README.md` ve
  `plugins/music/voice_session.py`'nin modül docstring'ine bakın. Uçtan uca test edildi:
  bot sesli kanala katıldı, gerçek tarayıcıda WebRTC `getStats()` ile doğrulandı — alıcı
  tarafın `media-playout` istatistiği gerçek zamanla birebir aynı hızda arttı (49.19s geçen
  sürede 49.19s ses çalındı), yani ses gerçekten sürekli akıyor, sadece bağlantı kurulup
  sessiz kalmıyor. `/muzik-sonraki` ve `/muzik-ayril` da doğrulandı. Bu çalışma sırasında
  `useVoiceChannel.ts`'de mikrofonsuz (sadece dinleyici) katılımı engelleyen iki pre-existing
  bug da düzeltildi (bkz. ROADMAP.md Aşama 6).

Hepsi Bot Engine üzerinden gerçek uçtan uca test edildi: bir bot sunucuya eklendi, kanala
`/komut` yazıldı, bot kendi gerçek Matrix hesabıyla (ya da `music` için kendi WebRTC bağlantısıyla)
aynı odaya doğru cevabı yazdı/sesi akıttı (bkz. [../backend/README.md](../backend/README.md)
Bot motoru bölümü).

## Henüz yapılmadı

- `permissions` alanı şu an sadece dokümantasyon amaçlı; gerçek bir onay/izin uygulaması yok
  (herhangi bir giriş yapmış kullanıcı plugin kurup kaldırabiliyor — platform admin rolü eksik)
- `@bot` mention formatı (şu an sadece `/komut` prefix'i çalışıyor)
> Production sandbox'ında backend/Matrix/DB'ye doğrudan import yapan plugin'ler, açıkça
> tanımlı güvenli Plugin API'ye taşınana kadar çalıştırılmaz. Mevcut uçtan uca senaryolar
> `PLUGIN_EXECUTION_MODE=local` geliştirme moduna aittir.
