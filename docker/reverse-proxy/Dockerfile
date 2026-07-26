# Cloudflare DNS-01 doğrulaması için Caddy'ye caddy-dns/cloudflare eklentisi gömülür.
# Sunucu Hamachi'de olduğundan HTTP-01/TLS-ALPN doğrulaması yapılamaz; DNS-01 dışarıdan
# erişim gerektirmeden (yalnızca DNS TXT kaydı ile) güvenilir Let's Encrypt sertifikası alır.
FROM caddy:2.11.4-builder-alpine AS builder
RUN xcaddy build --with github.com/caddy-dns/cloudflare

FROM caddy:2.11.4-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
