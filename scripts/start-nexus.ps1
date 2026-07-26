# Nexus tek-tikla baslatici.
# 1) Docker Desktop calismiyorsa baslatir ve motorun hazir olmasini bekler,
# 2) tum konteynerleri ayaga kaldirir,
# 3) saglik kontrolunden sonra tarayicida Nexus adresini acar.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

function Test-Docker { docker info *> $null; return $? }

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Nexus baslatiliyor" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# 1) Docker Desktop
if (-not (Test-Docker)) {
    Write-Host "Docker Desktop calismiyor, baslatiliyor..." -ForegroundColor Yellow
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe'),
        'C:\Program Files\Docker\Docker\Docker Desktop.exe'
    )
    $dd = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $dd) { Write-Host "HATA: Docker Desktop.exe bulunamadi." -ForegroundColor Red; exit 1 }
    Start-Process $dd
    $deadline = (Get-Date).AddMinutes(4)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 5
        if (Test-Docker) { break }
        Write-Host "  ... motor hazirlaniyor" -ForegroundColor DarkGray
    }
    if (-not (Test-Docker)) { Write-Host "HATA: Docker 4 dakika icinde hazir olmadi." -ForegroundColor Red; exit 1 }
}
Write-Host "Docker hazir." -ForegroundColor Green

# 2) Stack'i baslat
Write-Host "Konteynerler baslatiliyor (docker compose up -d)..." -ForegroundColor Cyan
docker compose up -d
if (-not $?) { Write-Host "HATA: docker compose up basarisiz oldu." -ForegroundColor Red; exit 1 }

# 3) Adresi .env'den oku
$url = (Get-Content (Join-Path $repo '.env') | Where-Object { $_ -like 'NEXUS_PUBLIC_URL=*' } | Select-Object -First 1) -replace '^NEXUS_PUBLIC_URL=', ''
if (-not $url) { $url = 'https://cekin.gen.tr' }

# 4) Kisa saglik beklemesi
Write-Host "Saglik kontrolu bekleniyor..." -ForegroundColor Cyan
$ok = $false
$deadline = (Get-Date).AddSeconds(90)
while ((Get-Date) -lt $deadline) {
    try {
        $r = Invoke-WebRequest -Uri "$url/healthz" -TimeoutSec 5 -UseBasicParsing
        if ($r.Content.Trim() -eq 'ok') { $ok = $true; break }
    } catch {}
    Start-Sleep -Seconds 4
}

Write-Host ""
if ($ok) {
    Write-Host "Nexus HAZIR:  $url" -ForegroundColor Green
} else {
    Write-Host "Konteynerler baslatildi ama saglik kontrolu henuz gecmedi." -ForegroundColor Yellow
    Write-Host "Birkac dakika sonra adresi deneyin:  $url" -ForegroundColor Yellow
}
Start-Process $url
