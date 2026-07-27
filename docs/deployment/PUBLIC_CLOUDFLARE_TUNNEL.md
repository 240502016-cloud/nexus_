# Ücretsiz dış erişim: Cloudflare Tunnel

Bu kurulum `cekin.gen.tr` adresini, ziyaretçilere Hamachi kurdurmadan Nexus sunucusuna bağlar.
Cloudflare Tunnel dışarıya doğru bağlantı kurduğu için modemden 80/443 portu açılması ve sabit
genel IP gerekmez. Nexus'un HTTP, HTTPS, API, Matrix ve WebSocket trafiği bu bağlantıdan geçer.

## Bir kez yapılacak Cloudflare ayarı

1. Cloudflare Zero Trust panelinde **Networks → Connectors → Cloudflare Tunnels** bölümünü açın.
2. **Create a tunnel → Cloudflared** seçin ve tünele `nexus` adını verin.
3. **Add a public hostname** bölümünde:
   - Subdomain: boş bırakın
   - Domain: `cekin.gen.tr`
   - Type: `HTTP`
   - URL: `reverse-proxy:8081`
4. DNS bölümünde daha önce Hamachi IP'sine bakan `cekin.gen.tr` A kaydı varsa kaldırın. Tünelin
   oluşturduğu proxied CNAME kaydı kalmalıdır.
5. Connector kurulum ekranındaki komutta `--token` sonrasında bulunan tünel tokenini kopyalayın.
   Token bir paroladır; Git'e, mesaja veya ekran görüntüsüne koymayın.

## Sunucu bilgisayarında

Arkadaşınız güncel `cekingen` dalını çektikten sonra:

1. `Public-Tunnel-Ayarla.cmd` dosyasına çift tıklar.
2. Cloudflare tokenini görünmeyen giriş alanına yapıştırıp Enter'a basar.
3. `Arkadas-Sunucuyu-Guncelle.cmd` dosyasını çalıştırır.

Güncelleme yöneticisi `.env` içinde token bulunduğunu algılar, `public-tunnel` profilini otomatik
başlatır ve `https://cekin.gen.tr/healthz` adresini doğrular. Sonraki normal başlatmalarda
`Baslat-Nexus.cmd` da tüneli otomatik açar.

Mevcut kurulumda şu değerler korunmalı veya bu biçime getirilmelidir:

```dotenv
NEXUS_DOMAIN=cekin.gen.tr
NEXUS_PUBLIC_URL=https://cekin.gen.tr
NEXUS_MATRIX_SERVER_AUTHORITY=cekin.gen.tr:443
```

Mevcut Matrix hesabı kimliklerini bozmamak için çalışan kurulumdaki `MATRIX_SERVER_NAME` değeri
değiştirilmemelidir.

## Ses, kamera ve yayın

Uygulama ücretsiz `stun:stun.cloudflare.com:3478` sunucusunu doğrudan eşler arası bağlantı için
kullanır. Bu, çoğu ev ve mobil ağda medyanın sunucuya uğramadan çalışmasını sağlar.

Cloudflare Tunnel genel UDP/TURN relay taşımaz. İki kullanıcının ağı doğrudan WebRTC bağlantısını
engelliyorsa kesin yedek için sunucu bilgisayarında genel IPv4 ve modem üzerinde coturn'un
`3478` ile `.env` içindeki `TURN_MIN_PORT`–`TURN_MAX_PORT` aralığının yönlendirilmesi gerekir.
Bu, kendi coturn servisinizi kullandığı için ücretli bir servis gerektirmez; CGNAT arkasında ise
internet sağlayıcısından genel IPv4 alınmadan garantili TURN mümkün değildir.

## Kontrol

```powershell
docker compose --profile public-tunnel ps
docker compose --profile public-tunnel logs --tail 100 public-tunnel
curl.exe https://cekin.gen.tr/healthz
```

İlk komutta `public-tunnel` çalışıyor, son komutta `ok` görünmelidir.
