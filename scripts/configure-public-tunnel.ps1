[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$envPath = Join-Path $repoRoot '.env'

if (-not (Test-Path -LiteralPath $envPath)) {
    throw '.env bulunamadi. Once Nexus sunucu kurulumunu tamamlayin.'
}

function Read-SecretText {
    param([string]$Prompt)
    $secure = Read-Host $Prompt -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

$token = (Read-SecretText 'Cloudflare Tunnel tokenini yapistirin (ekranda gorunmez)').Trim()
if ($token.Length -lt 80 -or $token -match '\s') {
    throw 'Tunnel tokeni gecersiz gorunuyor. Cloudflare panelindeki Install connector adimindan yalnizca tokeni kopyalayin.'
}

$lines = [Collections.Generic.List[string]]::new()
$found = $false
foreach ($line in Get-Content -LiteralPath $envPath) {
    if ($line -match '^\s*CLOUDFLARE_TUNNEL_TOKEN\s*=') {
        if (-not $found) {
            $lines.Add("CLOUDFLARE_TUNNEL_TOKEN=$token")
            $found = $true
        }
        continue
    }
    $lines.Add($line)
}
if (-not $found) {
    $lines.Add('')
    $lines.Add('# Cloudflare Tunnel - keep this token secret')
    $lines.Add("CLOUDFLARE_TUNNEL_TOKEN=$token")
}

$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmss'Z'")
$backupPath = "$envPath.pre-tunnel-$stamp.bak"
Copy-Item -LiteralPath $envPath -Destination $backupPath
[IO.File]::WriteAllText(
    $envPath,
    (($lines -join [Environment]::NewLine).TrimEnd() + [Environment]::NewLine),
    (New-Object Text.UTF8Encoding($false))
)

Write-Host ''
Write-Host '[OK] Cloudflare Tunnel tokeni .env dosyasina guvenli sekilde kaydedildi.' -ForegroundColor Green
Write-Host "Yedek: $backupPath"
Write-Host ''
Write-Host 'Cloudflare panelinde zorunlu son kontrol:' -ForegroundColor Cyan
Write-Host '  Public Hostname: cekin.gen.tr'
Write-Host '  Service:         http://reverse-proxy:8081'
Write-Host '  DNS:             Eski 25.49.22.166 A kaydini kaldirin.'
Write-Host 'Furkan sertifika uyarisini gecmemeli; yalniz https://cekin.gen.tr adresini acmali.'
Write-Host 'Simdi Arkadas-Sunucuyu-Guncelle.cmd dosyasini calistirin.'
