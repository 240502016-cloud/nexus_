# Matrix

Matrix Synapse konfigürasyonu. Sadece iletişim motoru (mesajlaşma/ses/video/dosya) olarak kullanılır;
platforma özgü mantık burada değil `backend/core` içinde yaşar.

`matrix/synapse/` içeriği (`homeserver.yaml`, signing key, veritabanı) `docker compose ... generate`
ile üretilir ve **secret içerdiği için git'e girmez** (bkz. `.gitignore`).

## Kurulum (ilk sefer)

```bash
cd nexus-communication-platform
docker run --rm \
  -v "$(pwd)/matrix/synapse:/data" \
  -e SYNAPSE_SERVER_NAME=nexus.local \
  -e SYNAPSE_REPORT_STATS=no \
  matrixdotorg/synapse:latest generate

docker compose up -d synapse
```

Üretilen `homeserver.yaml` içindeki `registration_shared_secret` değerini kopyalayıp proje
kökündeki `.env` dosyasına `MATRIX_REGISTRATION_SHARED_SECRET` olarak yapıştırın — Core API,
kullanıcı hesaplarını bu secret ile arka planda (admin API üzerinden) provision eder; genel
kayıt (`enable_registration`) kapalı kalır.

Doğrulama: `curl http://localhost:8008/_matrix/client/versions`

## Core API entegrasyonu

`backend/app/core/matrix_client.py` şu anda: `register_user`, `create_room`, `invite_user`,
`join_room`, `send_message`, `get_messages`. Bunlar `backend/app/core/routers/` altındaki REST
uç noktalarından kullanılıyor (bkz. [../backend/README.md](../backend/README.md)).

Bu akış gerçek Synapse + Postgres'e karşı uçtan uca test edildi: iki gerçek kullanıcı REST API
üzerinden oluşturuldu, bir sunucu/kanal açıldı, ikinci kullanıcı kanala eklendi (davet+katılma)
ve iki kullanıcı gerçek bir Matrix odasında karşılıklı mesajlaştı.

Henüz eklenmedi: sesli kanal (VoIP) sinyalleşmesi, ekran paylaşımı, dosya paylaşımı — bkz.
[../ROADMAP.md](../ROADMAP.md) Aşama 2'nin devamı.
