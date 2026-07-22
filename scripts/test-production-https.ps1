[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9.-]+$')]
    [string]$Domain,

    [string]$Jwt = $env:NEXUS_JWT,

    [string]$VoiceChannelId = $env:NEXUS_VOICE_CHANNEL_ID
)

$ErrorActionPreference = 'Stop'

function Write-Check {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

Write-Host "Nexus HTTPS/WSS doğrulaması: $Domain"

$dnsRecords = Resolve-DnsName -Name $Domain -Type A -ErrorAction Stop
if (-not ($dnsRecords | Where-Object { $_.IPAddress })) {
    throw "DNS A kaydı IP adresi döndürmedi: $Domain"
}
Write-Check "DNS A kaydı çözümlendi"

$redirectHandler = [System.Net.Http.HttpClientHandler]::new()
$redirectHandler.AllowAutoRedirect = $false
$redirectClient = [System.Net.Http.HttpClient]::new($redirectHandler)
try {
    $redirectResponse = $redirectClient.GetAsync("http://$Domain/healthz").GetAwaiter().GetResult()
    $redirectStatus = [int]$redirectResponse.StatusCode
    $redirectLocation = $redirectResponse.Headers.Location
    if ($redirectStatus -notin @(301, 302, 307, 308) -or -not $redirectLocation -or
        $redirectLocation.Scheme -ne 'https') {
        throw "HTTP isteği HTTPS'e yönlenmedi (status=$redirectStatus, location=$redirectLocation)"
    }
}
finally {
    $redirectClient.Dispose()
    $redirectHandler.Dispose()
}
Write-Check "HTTP -> HTTPS yönlendirmesi çalışıyor"

$proxyHealth = Invoke-WebRequest -Uri "https://$Domain/healthz" -UseBasicParsing
if ($proxyHealth.StatusCode -ne 200 -or $proxyHealth.Content.Trim() -ne 'ok') {
    throw "Reverse proxy health yanıtı beklenenden farklı"
}
Write-Check "HTTPS sertifikası ve reverse proxy health çalışıyor"

$apiHealth = Invoke-RestMethod -Uri "https://$Domain/api/health"
if ($apiHealth.status -ne 'ok') {
    throw "Core API health yanıtı beklenenden farklı"
}
Write-Check "Core API HTTPS üzerinden erişilebilir"

$matrixVersions = Invoke-RestMethod -Uri "https://$Domain/_matrix/client/versions"
if (-not $matrixVersions.versions) {
    throw "Matrix versions yanıtı sürüm listesi içermiyor"
}
Write-Check "Matrix HTTPS üzerinden erişilebilir"

$matrixClient = Invoke-RestMethod -Uri "https://$Domain/.well-known/matrix/client"
if ($matrixClient.'m.homeserver'.base_url -ne "https://$Domain") {
    throw "Matrix client discovery yanıtı beklenenden farklı"
}
Write-Check "Matrix .well-known client discovery doğru"

if ($Jwt -and $VoiceChannelId) {
    $encodedJwt = [System.Uri]::EscapeDataString($Jwt)
    $webSocketUri = [System.Uri]::new("wss://$Domain/api/channels/$VoiceChannelId/voice?token=$encodedJwt")
    $socket = [System.Net.WebSockets.ClientWebSocket]::new()
    $timeout = [System.Threading.CancellationTokenSource]::new([TimeSpan]::FromSeconds(15))
    try {
        $socket.ConnectAsync($webSocketUri, $timeout.Token).GetAwaiter().GetResult()
        if ($socket.State -ne [System.Net.WebSockets.WebSocketState]::Open) {
            throw "WSS bağlantısı açık duruma gelmedi: $($socket.State)"
        }
        Write-Check "Yetkili WSS ses kanalı bağlantısı kuruldu"
        $socket.CloseAsync(
            [System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure,
            'TASK-005 doğrulaması tamamlandı',
            [System.Threading.CancellationToken]::None
        ).GetAwaiter().GetResult()
    }
    finally {
        $timeout.Dispose()
        $socket.Dispose()
    }
}
else {
    Write-Host '[SKIP] WSS testi için NEXUS_JWT ve NEXUS_VOICE_CHANNEL_ID birlikte verilmedi.' -ForegroundColor Yellow
}

Write-Host 'Tüm uygulanabilir kontroller başarılı.' -ForegroundColor Green
