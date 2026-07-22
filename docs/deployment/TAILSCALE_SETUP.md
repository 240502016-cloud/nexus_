# TASK-002 — Nexus ↔ AI Gateway Tailscale bağlantısı

Bu kurulumda yalnızca Nexus ana sunucusu AI Gateway'e erişir. Ollama'nın `11434` portu
internete, yerel ağa veya tailnet'e açılmaz.

```text
Arkadaş PC / Nexus                 Senin PC / AI
100.x.y.z                          100.a.b.c
Core API ── Tailscale/WireGuard ── AI Gateway :8090 ── Ollama 127.0.0.1:11434
```

Tailscale her cihaza `100.64.0.0/10` aralığında sabit bir IPv4 adresi verir. Fiziksel ağ veya
internet bağlantısı değişse de bu adres cihaz için sabit kalır. Gateway whitelist'i ve Nexus
`OLLAMA_BASE_URL` ayarı bu doğrudan Tailscale IP'lerini kullanır.

## Güvenlik kuralları

- Modemde port yönlendirmesi yapılmaz.
- AI Gateway yalnızca AI bilgisayarının Tailscale IP'sinde `8090/tcp` dinler.
- Gateway whitelist'inde yalnızca Nexus bilgisayarının Tailscale IP'si `/32` olarak bulunur.
- Tailnet policy yalnızca `Nexus PC -> AI PC:8090/tcp` bağlantısına izin verir.
- `11434/tcp` yalnızca `127.0.0.1` üzerinden kullanılabilir.
- Tailscale şifrelemesine ek olarak Gateway API anahtarı da zorunlu kalır.

## 1. Tailscale kurulumu

Her iki Windows bilgisayara resmi Tailscale istemcisini kurun ve aynı tailnet hesabına giriş
yapın. Kurulumdan sonra iki bilgisayarda da:

```powershell
tailscale status
tailscale ip -4
```

çıktılarını alın. Aşağıdaki isimleri kullanacağız:

```text
NEXUS_TAILSCALE_IP = arkadaş bilgisayarının 100.x adresi
AI_TAILSCALE_IP    = senin bilgisayarının 100.x adresi
```

`100.100.100.100` adresi Tailscale'in özel Quad100 servis adresidir; cihaz adresi olarak
kullanılmamalıdır.

## 2. Tailnet erişim politikası

Tailscale Admin Console içindeki Access controls bölümünde mevcut geniş `allow all` kuralını
korumak, aşağıdaki dar kuralın güvenlik etkisini ortadan kaldırır. Mevcut policy'yi yedekleyin,
sonra [tailscale-policy.hujson.example](./tailscale-policy.hujson.example) içindeki iki
placeholder IP'yi gerçek adreslerle değiştirip mevcut policy ile dikkatlice birleştirin.

Kuralın amacı:

```text
NEXUS_TAILSCALE_IP -> AI_TAILSCALE_IP:8090/tcp  ALLOW
NEXUS_TAILSCALE_IP -> AI_TAILSCALE_IP:11434     DENY
diğer kaynaklar    -> AI_TAILSCALE_IP:8090      DENY
```

Policy dosyasındaki testler kaydetme sırasında yanlışlıkla geniş erişim verilmesini yakalamak
içindir. Tailscale'in yeni yapılandırmalarda önerdiği `grants` sözdizimi kullanılmıştır.

## 3. AI bilgisayarını yapılandırma

`ai-gateway/.env`:

```dotenv
AI_GATEWAY_API_KEY=<en-az-32-karakter-rastgele-anahtar>
AI_GATEWAY_ALLOWED_NETWORKS=<NEXUS_TAILSCALE_IP>/32
AI_GATEWAY_TRUSTED_PROXIES=
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_CONNECT_TIMEOUT_SECONDS=5
OLLAMA_READ_TIMEOUT_SECONDS=120
AI_GATEWAY_MAX_REQUEST_BYTES=1048576
```

Gateway'i yalnızca AI bilgisayarının Tailscale IP'sine bind edin:

```powershell
cd ai-gateway
.\.venv\Scripts\python.exe -m uvicorn gateway.main:app `
  --host <AI_TAILSCALE_IP> `
  --port 8090 `
  --workers 1
```

`--host 0.0.0.0` kullanmayın. Böylece gateway yerel Wi-Fi/Ethernet IP'sinde dinlemez.

Windows Firewall için yönetici PowerShell'de yalnızca bu akışa izin veren kural oluşturun:

```powershell
New-NetFirewallRule `
  -DisplayName "Nexus AI Gateway - Tailscale only" `
  -Direction Inbound `
  -Action Allow `
  -Protocol TCP `
  -LocalAddress <AI_TAILSCALE_IP> `
  -RemoteAddress <NEXUS_TAILSCALE_IP> `
  -LocalPort 8090
```

Uvicorn için daha önce oluşturulmuş geniş kapsamlı bir Windows Firewall izin kuralı varsa
kapatın veya silin; aksi halde bu dar kural tek başına yeterli koruma sağlamaz.

Ollama'nın yalnızca localhost'ta olduğunu doğrulayın:

```powershell
Get-NetTCPConnection -LocalPort 11434 -State Listen |
  Select-Object LocalAddress,LocalPort,OwningProcess
```

Beklenen `LocalAddress`, `127.0.0.1` veya `::1` olmalıdır; `0.0.0.0` olmamalıdır.

## 4. Nexus ana sunucusunu yapılandırma

Arkadaş bilgisayarındaki Nexus kök `.env` dosyası:

```dotenv
OLLAMA_BASE_URL=http://<AI_TAILSCALE_IP>:8090
OLLAMA_API_KEY=<AI_GATEWAY_API_KEY-ile-ayni-deger>
OLLAMA_DEFAULT_MODEL=qwen2.5:7b
```

Core API'yi bu ayarlarla yeniden başlatın. Core API, gateway'e Bearer anahtarıyla `/api/tags`
ve `/api/chat` istekleri gönderir; `/ai/health` üzerinden gateway durumunu ve model varlığını
kontrol eder. Timeout/retry ayarları için kök `.env.example` dosyasındaki `OLLAMA_*` değerlerini
kullanın.

## 5. Bağlantıyı doğrulama

Arkadaş bilgisayarında, Nexus `.env` yüklendikten sonra:

```powershell
$env:OLLAMA_API_KEY = "<AI_GATEWAY_API_KEY>"
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\test-ai-gateway-tailscale.ps1 `
  -GatewayBaseUrl "http://<AI_TAILSCALE_IP>:8090"
```

Beklenen sonuç:

```text
Gateway status : online
Models         : qwen2.5:7b
```

Negatif kontroller de yapılmalıdır:

1. Yanlış API anahtarı `401` döndürmeli.
2. Tailnet'teki üçüncü bir cihaz `8090` portuna erişememeli.
3. Arkadaş PC, AI PC'nin `11434` portuna erişememeli.
4. Gateway kapatılınca Core API kontrollü bir `502` hatası üretmeli; Nexus'un diğer işlevleri
   çalışmaya devam etmeli.

## 6. Sorun giderme

- `tailscale status`: İki cihaz aynı tailnet'te ve çevrimiçi mi?
- `tailscale ping <AI_TAILSCALE_IP>`: Tailscale yolu kuruluyor mu?
- `Test-NetConnection <AI_TAILSCALE_IP> -Port 8090`: Grant ve firewall izin veriyor mu?
- Gateway `403`: `AI_GATEWAY_ALLOWED_NETWORKS` içinde Nexus IP `/32` olarak doğru mu?
- Gateway `401`: İki taraftaki API anahtarları bire bir aynı mı?
- Gateway `503`: AI bilgisayarında `http://127.0.0.1:11434/api/tags` yanıt veriyor mu?

Resmi başvuru kaynakları:

- https://tailscale.com/docs/install/windows
- https://tailscale.com/docs/concepts/tailscale-ip-addresses
- https://tailscale.com/docs/features/access-control/grants
