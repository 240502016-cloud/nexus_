# Nexus server quickstart

Sunucu işletimi için ana giriş noktası:

```text
scripts/nexus-server.ps1
```

Windows'ta komut yazmadan kullanmak için proje kökündeki şu dosyaya çift tıklayın:

```text
Nexus-Server-Manager.cmd
```

Başlatıcı aşağıdaki operasyonları sekmeli bir arayüzden sunar:

- Yeni sunucu `.env` üretimi ve tam ilk deploy
- Eski Docker volume'larıyla çakışmayı engelleyen kalıcı Compose kurulum adı
- Güvenli Git update, build, migration, start/stop/restart, status ve diagnose
- AI Gateway başlatma, gerçek API key ile health testi, PID/durum görüntüleme ve güvenli durdurma
- Server ve AI bilgisayarı için rol bazlı Windows Firewall yapılandırması
- PostgreSQL backup, Synapse locale onarımı ve doğrulanmış restore
- HTTPS/backend/Matrix istemci erişim testi
- Caddy root sertifikası ve son kullanıcı talimatlarından oluşan istemci paketi
- Sunucu ve Gateway `.env` dosyaları için zorunlu alan/placeholder denetimli düzenleyici ve otomatik yedek
- Compose, Caddy, README, proje ve yedek klasörlerine kontrollü erişim

Uzun işlemler ayrı PowerShell penceresinde çalışır; böylece canlı loglar görünür ve arayüz
kilitlenmez. Yönetici izni gereken firewall ve sertifika işlemleri UAC üzerinden yükseltilir.

Script `.env` dışındaki tracked dosyaları sunucu üzerinde elle düzenlemeyi gerektirmez. Yeni
kurulumda tüm PostgreSQL, Matrix, JWT, plugin ve TURN sırlarını güvenli rastgele değerlerle üretir.
AI Gateway anahtarını gizli prompt ile bir kez ister ve anahtarı terminal çıktısına yazmaz.

`Config Editor` sekmesi gerçek sırları gösterebildiği için dosyayı yalnızca açık kullanıcı onayıyla yükler.
Kaydetme sırasında bozuk satırları, tekrarlanan anahtarları, eksik zorunlu alanları ve örnek/placeholder
değerlerini reddeder. Var olan dosya değiştirilmeden önce UTC zaman damgalı yerel yedeği oluşturulur;
bu yedekler de Git tarafından yok sayılır.

## Bilgisayar rolleri

- **Sunucu bilgisayarı:** `Server`, `Database` ve `Server firewall` işlemlerini kullanır.
- **AI bilgisayarı:** `AI Gateway` ve `Gateway firewall` işlemlerini kullanır.
- Her iki bilgisayarda da aynı arayüz bulunabilir; yalnızca o bilgisayarın üstlendiği role ait işlemler
  çalıştırılır. Sunucu `.env` içindeki `OLLAMA_API_KEY` ile AI bilgisayarındaki
  `AI_GATEWAY_API_KEY` aynı değer olmalıdır.
- **Son kullanıcı bilgisayarı:** sunucu açıkken dışa aktarılan istemci paketindeki sertifikayı bir kez
  kurar ve pakette yazan Nexus URL'sini tarayıcıda açar.

## Yeni sunucu

Git ve Docker Desktop kurulduktan sonra:

```powershell
cd C:\Users\merte\Github
git clone https://github.com/240502016-cloud/nexus_.git nexus-server
cd .\nexus-server

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\nexus-server.ps1 `
  -Action Initialize `
  -ServerAddress 25.49.22.166 `
  -AcmeEmail 240502016@kocaelisaglik.edu.tr `
  -AiGatewayUrl http://25.31.233.158:8090 `
  -ComposeProjectName nexus_server_fresh
```

Prompt geldiğinde AI bilgisayarındaki `ai-gateway/.env` dosyasının `AI_GATEWAY_API_KEY` değerini
yapıştırın. Giriş gizli olduğu için terminalde karakter görünmez. `Initialize` bundan sonra:

1. `.env` dosyasını gerçek ve rastgele sırlarla oluşturur.
2. Compose yapılandırmasını doğrular.
3. AI Gateway bağlantı ve kimlik doğrulamasını test eder.
4. Image'ları build eder.
5. PostgreSQL rollerini/database'lerini idempotent biçimde hazırlar.
6. Eski Synapse locale'ini yedek alarak `C/C` biçimine dönüştürür.
7. Alembic migration'larını çalıştırır.
8. Stack'i başlatıp HTTPS, backend ve Matrix health endpoint'lerini test eder.

Var olan `.env` dosyasını `Initialize` ezmez. Mevcut sunucuda aşağıdaki güncelleme akışını kullanın.

### Eski kurulumu silmeden temiz kurulum

Eski stack önce durdurulmalıdır; iki stack aynı host portlarını aynı anda kullanamaz. Eski kurulumun
Compose adı `nexus` olarak kalırken yeni arayüzde **Installation name** alanı
`nexus_server_fresh` olmalıdır. Bu değer yeni `.env` içine `COMPOSE_PROJECT_NAME` olarak kaydedilir
ve sonraki start/update/deploy işlemlerinde otomatik kullanılır. Böylece yeni PostgreSQL, Matrix ve
Caddy volume'ları eski `nexus_*` volume'larından tamamen ayrı oluşturulur.

Yeni kurulum doğrulanana kadar eski proje klasörünü veya `nexus_*` volume'larını silmeyin. Geri dönüş
gerekirse yeni stack'i durdurup eski stack'i yeniden başlatın.

## Rutin güncelleme

```powershell
cd C:\Users\merte\Github\nexus-server
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\nexus-server.ps1 `
  -Action Update
```

`Update`, tracked yerel değişiklik varsa timestamp'li Git stash ile korur; `git pull --ff-only`
uygular ve tam deploy akışını çalıştırır. `.env` Git tarafından izlenmediği için korunur. Otomatik
stash kendiliğinden geri uygulanmaz; böylece eski `docker-compose.yml` değişiklikleri güncel kodun
üzerine yazılmaz.

## Günlük komutlar

Build/migration dahil mevcut kodu deploy etmek:

```powershell
.\scripts\nexus-server.ps1 -Action Deploy
```

Yalnızca mevcut container'ları başlatmak:

```powershell
.\scripts\nexus-server.ps1 -Action Start
```

Durum:

```powershell
.\scripts\nexus-server.ps1 -Action Status
```

Durum ve son servis logları:

```powershell
.\scripts\nexus-server.ps1 -Action Diagnose
```

## Güvenlik ve geri dönüş

- `.env`, `ai-gateway/.env`, dump dosyaları ve API anahtarları Git'e eklenmez.
- `Update` öncesi oluşan stash'ler `git stash list` ile görülebilir.
- Locale onarımı dump'ı `backups/postgres-locale-repair` altında ve eski database'i PostgreSQL
  içinde timestamp'li adla korur.
- `docker compose down -v` bu akışın hiçbir parçasında kullanılmaz; volume verilerini siler.
- Server IP/domain veya Matrix server name çalışan Matrix kurulumunda sonradan değiştirilmemelidir.
