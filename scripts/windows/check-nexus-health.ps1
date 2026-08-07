<#
.SYNOPSIS
    Nexus'un ayakta olup olmadığını dışarıdan kontrol eder ve durum değişince haber verir.

.DESCRIPTION
    5 Ağustos 2026 gecesi sunucu on saat erişilemez kaldı ve bu ancak birisi siteye
    girmeye çalışınca fark edildi. Bu script o boşluğu kapatır.

    İzleme sunucunun **dışından** yapılır: sunucu düştüğünde üzerinde çalışan bir izleyici
    de düşeceği için haber veremezdi.

    Yalnız durum **değiştiğinde** bildirim gösterir (ayakta -> düştü, düştü -> döndü).
    Aksi hâlde her kontrolde bildirim yağardı. Geçici bir ağ takılmasını arıza saymamak
    için birkaç kez dener.

.PARAMETER Notify
    Durum değişince masaüstü bildirimi göster. Zamanlanmış görev bunu kullanır.

.EXAMPLE
    .\scripts\windows\check-nexus-health.ps1 -Notify
#>
[CmdletBinding()]
param(
    [string]$BaseUrl = 'https://nexus.cekin.gen.tr',
    [string]$StateFile = (Join-Path $env:LOCALAPPDATA 'nexus-monitor\state.json'),
    [string]$LogFile = (Join-Path $env:LOCALAPPDATA 'nexus-monitor\health.log'),
    [ValidateRange(1, 10)]
    [int]$Attempts = 3,
    [ValidateRange(1, 120)]
    [int]$TimeoutSeconds = 15,
    [switch]$Notify
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $StateFile) | Out-Null

function Write-Log {
    param([string]$Message)
    $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz'), $Message
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

function Get-ResponseText {
    param($Content)
    # /healthz yanıtı Content-Type'ında charset taşımadığı için PowerShell içeriği
    # Byte[] olarak döndürür; desen eşleştirmeden önce metne çevrilmeli.
    if ($Content -is [byte[]]) { return [Text.Encoding]::UTF8.GetString($Content) }
    return [string]$Content
}

function Test-Endpoint {
    param([string]$Url, [string]$Expected)
    try {
        $response = Invoke-WebRequest -Uri $Url -TimeoutSec $TimeoutSeconds -UseBasicParsing -ErrorAction Stop
        if ($response.StatusCode -ne 200) { return "HTTP $($response.StatusCode)" }
        $text = Get-ResponseText $response.Content
        if ($Expected -and $text -notmatch $Expected) {
            # Yanlış uca gidilirse tüm HTML sayfası dönebilir; logu şişirmemek için kırp.
            $preview = $text.Trim() -replace '\s+', ' '
            if ($preview.Length -gt 120) { $preview = $preview.Substring(0, 120) + '…' }
            return "beklenmeyen yanıt: $preview"
        }
        return $null
    } catch {
        return $_.Exception.Message
    }
}

# Tek seferlik takılmayı arıza saymamak için birkaç deneme yapılır.
$failure = $null
for ($i = 1; $i -le $Attempts; $i++) {
    $failure = Test-Endpoint -Url "$BaseUrl/healthz" -Expected 'ok'
    if (-not $failure) {
        $failure = Test-Endpoint -Url "$BaseUrl/api/health" -Expected '"status"\s*:\s*"ok"'
    }
    if (-not $failure) { break }
    if ($i -lt $Attempts) { Start-Sleep -Seconds 5 }
}

$isUp = -not $failure

$previous = $null
if (Test-Path -LiteralPath $StateFile) {
    try { $previous = (Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json).up } catch { $previous = $null }
}

[pscustomobject]@{
    up = $isUp
    checked_at = (Get-Date).ToUniversalTime().ToString('o')
    detail = $failure
} | ConvertTo-Json | Set-Content -LiteralPath $StateFile -Encoding UTF8

function Show-Notification {
    param([string]$Title, [string]$Body, [string]$Icon)
    if (-not $Notify) { return }
    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        $balloon = New-Object System.Windows.Forms.NotifyIcon
        $balloon.Icon = [System.Drawing.SystemIcons]::Information
        $balloon.BalloonTipIcon = $Icon
        $balloon.BalloonTipTitle = $Title
        $balloon.BalloonTipText = $Body
        $balloon.Visible = $true
        $balloon.ShowBalloonTip(20000)
        Start-Sleep -Seconds 12
        $balloon.Dispose()
    } catch {
        # Bildirim gösterilemese bile log kaydı kalır; kontrol başarısız sayılmaz.
        Write-Log "bildirim gösterilemedi: $($_.Exception.Message)"
    }
}

if ($isUp -and $previous -eq $false) {
    Write-Log 'DURUM: Nexus yeniden erişilebilir'
    Show-Notification -Title 'Nexus geri döndü' -Body 'Site yeniden erişilebilir durumda.' -Icon 'Info'
} elseif (-not $isUp -and $previous -ne $false) {
    Write-Log "DURUM: Nexus erişilemiyor -> $failure"
    Show-Notification -Title 'Nexus erişilemiyor' -Body "Site yanıt vermiyor: $failure" -Icon 'Error'
} elseif ($isUp) {
    Write-Log 'ayakta'
} else {
    Write-Log "hâlâ erişilemiyor -> $failure"
}

if (-not $isUp) { exit 1 }
