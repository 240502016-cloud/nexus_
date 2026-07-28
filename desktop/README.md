# Nexus Desktop

Windows masaüstü istemcisi mevcut React arayüzünü, Core API'yi ve WebRTC bağlantılarını paylaşır.
Backend/veritabanı için ayrı bir masaüstü kurulumu gerekmez.

## Gereksinimler

- Windows 10/11 x64
- Node.js (yalnız geliştirme/paketleme için)
- Çalışan Nexus sunucusu; varsayılan `https://cekin.gen.tr`

## Geliştirme

```powershell
cd desktop
npm.cmd install
npm.cmd run dev
```

Farklı yerel sunucu için Electron sürecine `NEXUS_SERVER_URL=http://127.0.0.1:8081` verilebilir.
HTTPS yalnız `localhost`/`127.0.0.1` geliştirmesinde isteğe bağlıdır.

## Windows installer

```powershell
cd desktop
npm.cmd ci
npm.cmd run dist
```

Çıktı `desktop/release/NexusSetup-<version>-x64.exe` olur. NSIS kurulumu kullanıcı başına çalışır,
Start Menu ve masaüstü kısayollarını oluşturur ve Windows'un standart kaldırma ekranına kaydolur.

## Release ve auto-update

Production sürümü yayınlamadan önce Windows kod imzası yapılandırılmalıdır. Aynı build'den çıkan:

- `NexusSetup-*.exe`
- `NexusSetup-*.exe.blockmap`
- `latest.yml`

dosyaları birlikte `https://cekin.gen.tr/desktop-updates/` altında yayınlanır. Metadata veya
installer'ı farklı build'lerden karıştırmak checksum doğrulamasını bozar. Güncelleme denetimi ilk
kurulumda kapalıdır; kullanıcı Ayarlar → Gelişmiş bölümünden açar. İstemci update paketinin
Authenticode publisher değerini açıkça `Nexus Communication Platform` olarak doğrular; production
sertifikasının subject/common-name değeri bununla aynı olmalıdır.

## Runtime güvenliği

- Uygulama kaynakları `nexus://app` üzerinden yerelden yüklenir.
- Node.js renderer'da kapalıdır; preload yalnız sınırlı, tipli eylemler açar.
- Token Windows DPAPI tabanlı `safeStorage` ile şifrelenir.
- Navigasyon ve popup'lar uygulama içinde açılmaz.
- Mikrofon/kamera/ekran izinleri yalnız yerel uygulama origin'ine verilir.
