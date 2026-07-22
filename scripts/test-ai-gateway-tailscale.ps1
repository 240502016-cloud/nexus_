param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^https?://')]
    [string]$GatewayBaseUrl,

    [string]$ApiKey = $env:OLLAMA_API_KEY
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($ApiKey)) {
    throw 'API anahtarı verilmedi. OLLAMA_API_KEY ortam değişkenini ayarlayın veya -ApiKey kullanın.'
}

$baseUrl = $GatewayBaseUrl.TrimEnd('/')
$healthUri = "$baseUrl/ai/health"
$headers = @{ Authorization = "Bearer $ApiKey" }

try {
    $health = Invoke-RestMethod -Method Get -Uri $healthUri -Headers $headers -TimeoutSec 15
} catch {
    throw "AI Gateway health isteği başarısız ($healthUri): $($_.Exception.Message)"
}

if ($health.status -ne 'online') {
    throw "AI Gateway online değil: $($health | ConvertTo-Json -Compress)"
}

Write-Output "Gateway status : $($health.status)"
Write-Output "Models         : $($health.models -join ', ')"

