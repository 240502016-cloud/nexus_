# Backend

Python FastAPI ile yazılan Core Platform.

```
app/
├── main.py            # FastAPI giriş noktası, router'ların bağlandığı yer
├── config.py           # ortam değişkenleri (.env)
├── database.py         # SQLAlchemy engine/session
├── core/                # kullanıcı, rol, yetki, sunucu/kanal, auth, Matrix entegrasyonu
│   ├── models.py          # SQLAlchemy ORM modelleri
│   ├── schemas.py          # Pydantic şemaları (Create/Read)
│   ├── permissions.py       # Permission bitmask enum'u
│   ├── security.py           # parola hashleme (pbkdf2)
│   ├── auth.py                 # JWT üretme/doğrulama, get_current_user dependency'si
│   ├── authz.py                 # yetkilendirme yardımcıları (üye mi, sahip mi)
│   ├── matrix_client.py           # Matrix Admin/Client-Server API sarmalayıcısı
│   └── routers/                    # REST uç noktaları
│       ├── auth.py                    # POST /auth/login
│       ├── users.py                   # POST /users, GET /users/me, GET /users/{id}
│       ├── servers.py                 # POST /servers, GET /servers/{id}
│       ├── channels.py                # POST /servers/{id}/channels, GET .../channels
│       ├── members.py                 # POST /servers/{id}/members
│       ├── messages.py                # POST/GET /channels/{id}/messages
│       ├── plugins.py                 # GET /plugins, install/uninstall, commands/run
│       └── voice.py                   # WS /channels/{id}/voice - WebRTC signaling relay
├── plugins_engine/       # plugin yükleme/yönetim, Plugin API
│   ├── manifest.py         # plugin.json şeması (Pydantic)
│   ├── context.py           # PluginContext (kanal/oda/sunucu bağlamı dahil)
│   └── loader.py              # discover_manifests(), PluginRegistry
├── bot_engine/            # event tabanlı komut yönlendirme
│   └── dispatcher.py         # MessageEvent, parse_command, handle_message_event
└── services/
    └── ollama/               # AI (Ollama) servis katmanı - bkz. aşağıdaki bölüm
        ├── client.py            # OllamaClient (yapılandırılabilir base_url/api_key)
        ├── models.py             # AiConversation/AiMessage/AiTokenUsage + Pydantic şemaları
        ├── tokenizer.py           # Ollama'nın gerçek token sayımını kaydetme/toplama
        └── requests.py             # /ai REST uç noktaları
```

## Modeller (Aşama 1)

- `User` — kullanıcı hesabı; `matrix_user_id`/`matrix_access_token` ile Matrix hesabına bağlanır
- `Server` — sunucu (guild); bir `owner`, birden çok `channel` ve `role` içerir
- `ServerMember` — bir kullanıcının bir sunucudaki üyeliği (nickname, katılma tarihi)
- `Channel` — `TEXT` veya `VOICE` tipinde, bir sunucuya bağlı; `matrix_room_id` ile bir Matrix odasına bağlanır
- `Role` — sunucuya özgü, `Permission` bitmask'i taşıyan rol; `User`larla çoktan-çoğa ilişkili

Yetkiler Discord tarzı bir bitmask (`app/core/permissions.py::Permission`) olarak tutulur;
ayrı bir `permissions` tablosu yoktur.

## Matrix entegrasyonu (Aşama 2)

`app/core/matrix_client.py::matrix_client` — Synapse Admin/Client-Server API sarmalayıcısı:
`register_user`, `create_room`, `invite_user`, `join_room`, `send_message`, `get_messages`.

`MATRIX_REGISTRATION_SHARED_SECRET` ortam değişkeni, `matrix/synapse/homeserver.yaml`
içindeki `registration_shared_secret` ile aynı olmalı (bkz. [../matrix/README.md](../matrix/README.md)).

## Auth ve yetkilendirme

- `POST /auth/login` — `username`/`password` (form-encoded, OAuth2 password flow) alır,
  JWT (`access_token`) döner. Parolalar `security.py::hash_password` (pbkdf2) ile saklanır.
- Diğer tüm uç noktalar `Authorization: Bearer <token>` bekler; `auth.py::get_current_user`
  token'ı çözüp `User` nesnesini enjekte eder.
- `authz.py`: `ensure_server_owner` (sadece sahip kanal/üye ekleyebilir),
  `ensure_server_member` (sadece üyeler mesaj okuyup yazabilir). İhlalde `403` döner.

REST akışı (Matrix provizyonunu otomatik tetikler, `current_user` = token'daki kullanıcı):

```
POST /users                    -> kullanıcı + gerçek Matrix hesabı oluşturur (auth gerekmez)
POST /auth/login                -> JWT access_token döner
POST /servers                    -> sunucu + @everyone rolü; sahip = current_user
GET  /servers                     -> current_user'ın üyesi olduğu sunucuları listeler
POST /servers/{id}/channels        -> kanal + gerçek Matrix odası (sadece sahip)
POST /servers/{id}/members?user_id= -> kullanıcıyı sunucu+kanal odalarına ekler (sadece sahip)
POST /channels/{id}/messages          -> Matrix odasına mesaj gönderir (sadece üyeler)
GET  /channels/{id}/messages           -> Matrix odasından mesajları okur (sadece üyeler)
```

Gerçek Postgres + Synapse'e karşı doğrulandı: 401 (token yok/yanlış parola), 403 (sahip
olmayanın kanal açması / üye olmayanın mesaj okuması), ve tam akış (login → sunucu/kanal
oluştur → üye ekle → iki kullanıcı karşılıklı mesajlaşır).

## Plugin sistemi (Aşama 3)

`plugins/<isim>/plugin.json` + `main.py` sözleşimi ve REST akışı için
[../plugins/README.md](../plugins/README.md)'ye bakın. Kısaca:

```
GET  /plugins                    -> plugins/ altında keşfedilenler + kurulu/etkin durumu
POST /plugins/{name}/install       -> plugin'i belleğe yükler, Postgres'te enabled=True yapar
POST /plugins/commands/run           -> {"command": "..."} -> ilgili plugin'i çalıştırır
POST /plugins/{name}/uninstall     -> belleğe yüklüyü kaldırır, enabled=False yapar
```

Uçtan uca test edilen örnek plugin: `server_monitor` (gerçek sistem bilgisini döner).
Sunucu her yeniden başladığında, `enabled=True` olan pluginler otomatik geri yüklenir.

**Not:** Platform genelinde bir "admin" rolü henüz yok; şu an herhangi bir giriş yapmış
kullanıcı plugin kurup kaldırabiliyor. Gerçek yetkilendirme sonraki bir adım.

## Bot motoru (Aşama 4)

Botlar normal kullanıcı değil, servistir: kendi gerçek Matrix hesaplarıyla kanallara mesaj
yazabilirler ama sadece eklendikleri sunucularda (bot yetki kontrolü).

```
POST /bots                          -> bot + gerçek Matrix hesabı oluşturur
GET  /bots                          -> botları listeler
POST /bots/{bot_id}/servers/{id}      -> botu sunucuya ekler (sadece sahip); tüm kanal
                                          odalarına davet edilip katılır
```

`app/bot_engine/dispatcher.py::handle_message_event` — bir mesaj gönderildiğinde
(`routers/messages.py::send_message` içinden senkron çağrılır; henüz gerçek bir event
bus/kuyruk değil, ileride Matrix `/sync`'e taşınabilir) mesaj `bot.command_prefix` ile
başlıyorsa (`/komut arg`), o sunucuya eklenmiş her aktif bot için:
1. Komutla eşleşen, o an yüklü bir plugin var mı bakar (`plugin_registry.get_handler`)
2. Varsa çalıştırır, çıktısını botun kendi Matrix hesabıyla aynı odaya yazar

Uçtan uca test edildi: bir bot oluşturup bir sunucuya eklendi, kanala `/sunucu-durumu`
yazıldığında bot gerçekten aynı Matrix odasına kendi hesabıyla cevap yazdı. Botun
eklenmediği başka bir sunucuda aynı komut denendi — bot hiç cevap vermedi (yetki kontrolü
doğru çalışıyor).

**Not:** Platform admin rolü eksikliği burada da geçerli (bkz. plugin notu yukarıda).

## AI (Ollama) servisi

`app/services/ollama/` — hibrit mimariye hazır bir Ollama connector: `OllamaClient`'ın
`base_url`/`api_key`'i `.env` üzerinden yapılandırılabilir (`OLLAMA_BASE_URL`), yani ileride
ayrı bir "AI işlem sunucusu"na (başka bir makine) işaret edebilir. `plugins/ai_assistant`
de artık kendi HTTP çağrısını yapmıyor, bu paylaşılan client'ı kullanıyor.

```
GET  /ai/models                              -> Ollama'daki kurulu modelleri listeler
POST /ai/conversations                        -> yeni sohbet oluşturur (model seçimi opsiyonel)
GET  /ai/conversations                         -> current_user'ın sohbetlerini listeler
GET  /ai/conversations/{id}/messages            -> sohbet geçmişini okur
POST /ai/conversations/{id}/messages             -> mesaj gönderir; son 20 mesaj context
                                                     olarak Ollama'ya gönderilir, cevap +
                                                     her iki mesaj da Postgres'e yazılır
GET  /ai/usage                                    -> modele göre gruplanmış token kullanımı
```

Token sayımı, Ollama'nın `/api/chat` yanıtındaki gerçek `prompt_eval_count`/`eval_count`
değerlerinden alınır (ayrı bir tahmini tokenizer kütüphanesi kullanılmaz — farklı modellerin
tokenizer'ları farklıdır, kaynağından okumak her zaman doğrudur).

`DEFAULT_SYSTEM_PROMPT` (`client.py`) her istekte otomatik eklenir (DB'ye yazılmaz) - küçük
yerel modelin (`qwen2.5:7b`) tutarsız/uydurma cevap verme eğilimini azaltır. Örnek: sistem
promptu öncesi "Fransanın başkenti neresidir?" sorusuna "Frasnes'in başkenti Lokeren'dir..."
gibi tutarsız bir cevap alınırken, sonrasında doğru şekilde "Paris" döndü. **Bu bir sınır,
tam çözüm değil** - 7B parametrelik yerel bir model, ticari/büyük modellere (Claude, GPT-4)
kıyasla belirgin şekilde daha zayıf kalır; bu, "ücretsiz+yerel" tercihinin doğal bedelidir.

Uçtan uca test edildi: çok turlu bir sohbette model önceki turdaki bilgiyi (isim) doğru
hatırladı (context yönetimi çalışıyor); token kullanımı doğru toplandı; `/sor` bot komutu yeniden düzenleme
(refactor) sonrası hâlâ çalışıyor.

## Sesli kanal (WebRTC signaling)

`app/core/routers/voice.py` — Matrix'in kendi grup çağrı protokolünü (MSC3401, karmaşık)
kullanmak yerine, Core API üzerinde kendi hafif WebSocket signaling'imiz var. Ses verisinin
kendisi buradan geçmez; katılımcılar arasında doğrudan (mesh, WebRTC) akar — sunucu sadece
offer/answer/ICE candidate mesajlarını ilgili karşı tarafa relay eder.

```
WS /channels/{id}/voice?token=<jwt>   -> sadece VOICE tipi kanallar, sadece üyeler/sahip
```

Protokol (JSON mesajlar): `peers` (katılınca mevcut listeyi alırsın), `peer-joined`/
`peer-left` (broadcast), `offer`/`answer`/`ice-candidate` (`to` ile hedeflenir, sunucu
`from` ekleyip relay eder), `mute`/`mute-changed`, `speaking`/`speaking-changed`.

Bağlantı kurma sorumluluğu her zaman **yeni katılan tarafta**: `peers` mesajıyla gelen
listedeki herkese offer gönderir - böylece aynı ikili arasında çift bağlantı oluşmaz.

Backend tarafı Python WebSocket istemcileriyle uçtan uca test edildi: iki kullanıcı
join/offer/answer/ICE/mute/leave akışının tamamını doğru şekilde geçti; metin kanalına
bağlanma, geçersiz token ve var olmayan kanal denemeleri doğru reddedildi (HTTP 403,
pre-accept close). Frontend tarafı (mikrofon + gerçek ses) bu ortamda test edilemedi -
bkz. [../frontend/README.md](../frontend/README.md).

## Çalıştırma

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp ../.env.example ../.env    # ve değerleri doldurun (özellikle MATRIX_REGISTRATION_SHARED_SECRET)
uvicorn app.main:app --reload
```

`GET /health` ile ayakta olduğunu doğrulayabilirsiniz. Uygulama açılışta (`startup` event)
tabloları otomatik oluşturur — bu geçici bir kolaylıktır, ileride Alembic migration'larına
geçilecektir. Postgres ve Synapse'in ayakta olması gerekir: proje kökünden `docker compose up -d`.

Genel proje durumu için bkz. [ROADMAP.md](../ROADMAP.md).
