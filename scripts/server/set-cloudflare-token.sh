#!/bin/bash
# Sunucuda çalışır: stdin'den Cloudflare token'ını okur, Cloudflare'e doğrulatır ve
# /opt/nexus/.env'e yazar. Token ekrana yazılmaz. Geliştirici makinesinden
# scripts/windows/set-cloudflare-token.ps1 ile çağrılır; değişince Caddy'yi yeniden başlat:
#   docker compose up -d --force-recreate reverse-proxy
set -euo pipefail
read -r T || true
T=$(printf %s "$T" | tr -d '\r\n\t ')
len=${#T}
if [ "$len" -eq 0 ]; then echo "HATA: token bos geldi, .env degistirilmedi."; exit 1; fi
if [[ "$T" =~ ^[0-9a-f]{37}$ ]]; then
  echo "HATA: bu bir API token degil, 'Global API Key' gibi gorunuyor (37 karakter)."
  echo "      Global key tum hesaba erisim verir, kullanmiyoruz. Yeni bir API token olusturulmali."
  exit 1
fi
if [[ "$T" =~ ^[0-9a-f]{32}$ ]]; then
  echo "HATA: bu 32 karakterlik bir kimlik (Zone ID / Account ID / token ID) gibi gorunuyor, token degil."
  exit 1
fi

# Hem kullanici hem hesap (account-owned) token'larinda calisan kontrol: zone'u gorebiliyor mu
zone=$(curl -s -H "Authorization: Bearer $T" "https://api.cloudflare.com/client/v4/zones?name=cekin.gen.tr")
if ! printf %s "$zone" | grep -q '"name":"cekin.gen.tr"'; then
  code=$(printf %s "$zone" | grep -o '"code":[0-9]*' | head -1)
  echo "HATA: token cekin.gen.tr zone'unu goremiyor (uzunluk $len, Cloudflare $code). .env degistirilmedi."
  echo "      Token gecersiz/silinmis olabilir ya da 'Zone:Read' izni ve cekin.gen.tr secimi eksik."
  exit 1
fi
zid=$(printf %s "$zone" | grep -o '"id":"[0-9a-f]\{32\}"' | head -1 | cut -d'"' -f4)
# DNS düzenleme yetkisi: kayıtları listeleyebiliyor mu
recs=$(curl -s -H "Authorization: Bearer $T" "https://api.cloudflare.com/client/v4/zones/$zid/dns_records?per_page=1")
if ! printf %s "$recs" | grep -q '"success":true'; then
  echo "HATA: token zone'u goruyor ama DNS kayitlarina erisemiyor ('Zone:DNS:Edit' eksik). .env degistirilmedi."
  exit 1
fi
sed -i "s|^CLOUDFLARE_API_TOKEN=.*|CLOUDFLARE_API_TOKEN=$T|" /opt/nexus/.env
echo "TOKEN_KAYDEDILDI (gecerli, cekin.gen.tr zone'una ve DNS kayitlarina erisiyor)"
