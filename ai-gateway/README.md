# Nexus AI Gateway

Nexus ana sunucusunun, Ollama portunu internete doğrudan açmadan ayrı bir AI bilgisayarına
erişmesini sağlayan güvenlik katmanıdır.

Gateway şu uçları sunar:

| Uç | Amaç |
|---|---|
| `GET /ai/health` | Ollama erişimi ve kurulu model adları |
| `GET /api/tags` | Nexus `OllamaClient.list_models()` uyumlu proxy |
| `POST /api/chat` | Nexus `OllamaClient.chat()` uyumlu proxy; `stream: true` gövdesi NDJSON olarak akıtılır |

Her istek iki kontrolden geçer:

1. İstemci IP'si `AI_GATEWAY_ALLOWED_NETWORKS` CIDR listesinde olmalıdır.
2. `Authorization: Bearer <key>` veya `X-API-Key: <key>` geçerli olmalıdır.

`X-Forwarded-For` varsayılan olarak güvenilmez ve yok sayılır. Yalnızca doğrudan bağlantıyı
yapan proxy `AI_GATEWAY_TRUSTED_PROXIES` içinde olduğunda kullanılır.

## Windows üzerinde çalıştırma

Gateway'in doğrudan Tailscale adaptörünün `100.x` IP'sinde çalıştırılması, gerçek kaynak IP'yi
koruduğu için önerilen kurulumdur. İki bilgisayarın tam kurulum akışı için ayrıca
[`docs/deployment/TAILSCALE_SETUP.md`](../docs/deployment/TAILSCALE_SETUP.md) dosyasına bakın:

```powershell
cd ai-gateway
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env` içindeki API anahtarını ve Nexus ana sunucusunun VPN IP adresini düzenleyin. Ardından:

Rastgele bir anahtar üretmek için örneğin aşağıdaki komut kullanılabilir:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Örnek dosyadaki placeholder anahtarla gateway başlamaz. Ayarlar hazır olduğunda:

```powershell
.\.venv\Scripts\python.exe -m uvicorn gateway.main:app --host 100.90.0.20 --port 8090
```

Buradaki `100.90.0.20`, AI bilgisayarının örnek Tailscale IP adresidir. Windows Firewall'da
TCP 8090 için yalnızca bu yerel IP ve Nexus ana sunucusunun Tailscale IP'si izinli olmalıdır. Modem üzerinde
port yönlendirmesi yapılmamalıdır.

## Health kontrolü

```powershell
$headers = @{ Authorization = "Bearer <AI_GATEWAY_API_KEY>" }
Invoke-RestMethod -Uri "http://100.90.0.20:8090/ai/health" -Headers $headers
```

Örnek yanıt, bilgisayarda gerçekten kurulu modellere göre üretilir:

```json
{
  "status": "online",
  "models": ["qwen2.5:7b"]
}
```

Ollama kapalıysa veya ulaşılamıyorsa endpoint HTTP `503` döner.

## Nexus ana sunucusu ayarları

Arkadaş bilgisayarındaki Nexus `.env` dosyasında:

```dotenv
OLLAMA_BASE_URL=http://100.90.0.20:8090
OLLAMA_API_KEY=<AI_GATEWAY_API_KEY ile aynı değer>
OLLAMA_DEFAULT_MODEL=qwen2.5:7b
```

Mevcut Nexus backend'i Bearer anahtarını zaten gönderdiği ve `/api/tags` ile `/api/chat`
yollarını kullandığı için Core API tarafında ek kod değişikliği gerekmez.

## Docker notu

Gateway için `Dockerfile` sağlanmıştır. Ollama host işletim sisteminde çalışıyorsa container
içinden `OLLAMA_BASE_URL=http://host.docker.internal:11434` kullanılmalıdır. Docker Desktop
NAT'i gerçek istemci IP'sini değiştirebildiğinden whitelist davranışı doğrulanmadan public veya
VPN portu açılmamalıdır; ilk kurulumda host üzerinde doğrudan çalıştırmak daha öngörülebilirdir.

## Test

```powershell
cd ai-gateway
..\backend\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
