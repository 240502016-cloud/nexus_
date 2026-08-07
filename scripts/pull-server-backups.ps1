<#
.SYNOPSIS
    Sunucudaki PostgreSQL yedeklerini geliştirici makinesine indirir.

.DESCRIPTION
    Yedek sunucuda systemd timer'ı ile alınır (scripts/server/). Bu script kopyayı
    makineye çeker, böylece sunucu tamamen kaybedilse bile veri elde kalır.

    Çekme yönü bilinçlidir: Windows makinesinde SSH sunucusu yok, dolayısıyla sunucu
    buraya push edemez. Ayrıca makine her zaman açık olmadığı için yedeğin **birincil**
    kopyası sunucuda durur; buradaki ikinci kopyadır.

    Yalnız eksik dosyaları indirir, sha256 manifestiyle doğrular ve saklama süresi
    dolanları siler.

.PARAMETER Destination
    Yerel hedef dizin. Varsayılan: C:\Users\<kullanıcı>\nexus-backups

.PARAMETER RetentionDays
    Yerel kopyaların saklanma süresi. Varsayılan 60 gün (sunucuda 30).

.EXAMPLE
    .\scripts\pull-server-backups.ps1
#>
[CmdletBinding()]
param(
    [string]$Destination = (Join-Path $env:USERPROFILE 'nexus-backups'),
    [string]$ServerHost = 'root@45.155.124.254',
    [string]$IdentityFile = (Join-Path $env:USERPROFILE '.ssh\nexus_vds_migration_ed25519'),
    [string]$RemoteDirectory = '/var/backups/nexus',
    [ValidateRange(1, 3650)]
    [int]$RetentionDays = 60
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $IdentityFile)) {
    throw "SSH anahtarı bulunamadı: $IdentityFile"
}
New-Item -ItemType Directory -Force -Path $Destination | Out-Null

function Invoke-Remote {
    param([Parameter(Mandatory = $true)][string]$Command)
    $output = & ssh -i $IdentityFile -o ConnectTimeout=20 -o BatchMode=yes $ServerHost $Command
    if ($LASTEXITCODE -ne 0) { throw "Sunucu komutu başarısız (exit=$LASTEXITCODE): $Command" }
    return $output
}

Write-Host "Sunucudaki yedekler listeleniyor..."
$remoteFiles = @(Invoke-Remote "ls -1 $RemoteDirectory 2>/dev/null" | Where-Object { $_ })
if ($remoteFiles.Count -eq 0) {
    Write-Warning "Sunucuda hiç yedek yok. Timer çalıştı mı? (systemctl list-timers nexus-backup.timer)"
    return
}

$localNames = @(Get-ChildItem -LiteralPath $Destination -File | Select-Object -ExpandProperty Name)
$missing = @($remoteFiles | Where-Object { $localNames -notcontains $_ })

if ($missing.Count -eq 0) {
    Write-Host "Yerel kopya güncel; indirilecek yeni dosya yok."
} else {
    Write-Host "$($missing.Count) yeni dosya indiriliyor..."
    foreach ($name in $missing) {
        # Boşluklu isim beklenmiyor ama uzak yolu yine de tırnakla.
        & scp -i $IdentityFile -q "${ServerHost}:${RemoteDirectory}/${name}" $Destination
        if ($LASTEXITCODE -ne 0) { throw "İndirilemedi: $name" }
        Write-Host "  indirildi: $name"
    }
}

# Manifest varsa indirilen dosyaları sha256 ile doğrula: sessiz bozulmayı yakalar.
$verified = 0
$failed = @()
foreach ($manifest in Get-ChildItem -LiteralPath $Destination -Filter 'manifest-*.sha256' -File) {
    foreach ($line in Get-Content -LiteralPath $manifest.FullName) {
        if ($line -notmatch '^([0-9a-f]{64})\s+\*?(.+)$') { continue }
        $expected = $Matches[1]
        $file = Join-Path $Destination $Matches[2].Trim()
        if (-not (Test-Path -LiteralPath $file)) { continue }
        $actual = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -eq $expected) { $verified++ } else { $failed += $Matches[2].Trim() }
    }
}
if ($failed.Count -gt 0) {
    throw "sha256 uyuşmayan dosya(lar): $($failed -join ', ')"
}
Write-Host "Doğrulama: $verified dosyanın sha256 değeri manifestle uyuşuyor."

$cutoff = (Get-Date).ToUniversalTime().AddDays(-$RetentionDays)
$stale = @(Get-ChildItem -LiteralPath $Destination -File |
    Where-Object { $_.LastWriteTimeUtc -lt $cutoff -and $_.Extension -in '.dump', '.gz', '.sha256' })
if ($stale.Count -gt 0) {
    $stale | Remove-Item -Force
    Write-Host "$($stale.Count) eski yerel kopya silindi ($RetentionDays günden eski)."
}

$total = (Get-ChildItem -LiteralPath $Destination -File | Measure-Object -Property Length -Sum).Sum
Write-Host ("Yerel yedek dizini: {0} ({1:N1} MB)" -f $Destination, ($total / 1MB))
