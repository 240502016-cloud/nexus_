# Matrix Synapse

Matrix, Nexus'un metin odaları ve mesaj geçmişi için iletişim motorudur. Platform kullanıcı,
sunucu, kanal, bot ve yetki mantığı backend'de kalır.

## Production düzeni

TASK-004 ile Matrix şu şekilde containerize edilmiştir:

- Image: `matrixdotorg/synapse:v1.153.0` tabanlı [Dockerfile](./Dockerfile)
- Runtime config: `docker/matrix/render_config.py` tarafından environment'tan üretilir
- Kalıcı config/signing key/media: `matrix_data` Docker volume'u
- Veritabanı: PostgreSQL içindeki ayrı `synapse` kullanıcı/veritabanı
- Dahili adres: `http://matrix:8008`
- Public istemci/federasyon adresi: `https://<NEXUS_DOMAIN>/_matrix/*`
- `/_synapse/admin/*` public reverse proxy üzerinden yayınlanmaz
- Genel kayıt kapalı; Core API shared-secret admin kayıt API'sini dahili ağdan kullanır

Detaylı kurulum ve eski SQLite verisi için migration uyarısı:
[../docs/deployment/DOCKER_PRODUCTION.md](../docs/deployment/DOCKER_PRODUCTION.md).

## Eski geliştirme verisi

`matrix/synapse/` dizini önceki geliştirme kurulumunda üretilmiş SQLite config/verisini içerir
ve `.gitignore` kapsamındadır. Yeni production Compose bu dizini mount etmez. Bu veriler gerekli
ise PostgreSQL'e açık bir migration yapılmadan dizini silmeyin.

## Core API entegrasyonu

`backend/app/core/matrix_client.py`: shared-secret kullanıcı kaydı, oda oluşturma, davet,
katılım, mesaj gönderme/okuma ve redaction işlemlerini gerçekleştirir. Compose backend'e
`MATRIX_HOMESERVER_URL=http://matrix:8008` değerini zorunlu olarak uygular.
