param(
    [switch]$SkipTests,
    [switch]$Open
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$localEnv = Join-Path $repoRoot ".env.local"
$localEnvExample = Join-Path $repoRoot ".env.local.example"
$runtimeDir = Join-Path $repoRoot ".local-runtime"
$pidFile = Join-Path $runtimeDir "processes.json"
$composeBase = Join-Path $repoRoot "docker-compose.yml"
$composeLocal = Join-Path $repoRoot "docker-compose.local.yml"

function New-LocalSecret {
    $bytes = [byte[]]::new(48)
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Initialize-LocalEnvironment {
    if (Test-Path -LiteralPath $localEnv) { return }
    $content = [IO.File]::ReadAllText($localEnvExample)
    @(
        "local-admin-secret-placeholder", "local-app-secret-placeholder",
        "local-synapse-db-secret-placeholder", "local-core-secret-placeholder",
        "local-matrix-registration-secret-placeholder", "local-matrix-macaroon-secret-placeholder",
        "local-matrix-form-secret-placeholder", "local-ai-gateway-secret-placeholder",
        "local-plugin-secret-placeholder", "local-turn-secret-placeholder"
    ) | ForEach-Object { $content = $content.Replace($_, (New-LocalSecret)) }
    [IO.File]::WriteAllText($localEnv, $content, [Text.UTF8Encoding]::new($false))
}

function Import-LocalEnvironment {
    foreach ($line in [IO.File]::ReadAllLines($localEnv)) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
        $separatorIndex = $trimmed.IndexOf('=')
        if ($separatorIndex -gt 0) {
            $name = $trimmed.Substring(0, $separatorIndex)
            $value = $trimmed.Substring($separatorIndex + 1)
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }

    $env:POSTGRES_HOST = "127.0.0.1"
    $env:POSTGRES_PORT = "55432"
    $env:MATRIX_HOMESERVER_URL = "http://127.0.0.1:18008"
    $env:OLLAMA_BASE_URL = "http://127.0.0.1:18090"
    $env:OLLAMA_API_KEY = $env:AI_GATEWAY_API_KEY
    $env:PLUGIN_EXECUTION_MODE = "local"
    $env:NEXUS_DEV_API_TARGET = "http://127.0.0.1:18100"
    $env:ATTACHMENT_DIR = Join-Path $runtimeDir "attachments"
    $env:GENERATED_MEDIA_DIR = Join-Path $runtimeDir "generated-media"
    $env:HIGHLIGHT_MEDIA_DIR = Join-Path $runtimeDir "highlight-media"
    $env:AVATAR_DIR = Join-Path $runtimeDir "avatars"
}

function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & docker compose --env-file $localEnv -f $composeBase -f $composeLocal --project-name nexus-local @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose komutu basarisiz oldu." }
}

function Stop-PreviousProcesses {
    if (-not (Test-Path -LiteralPath $pidFile)) { return }
    $records = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
    foreach ($record in @($records)) {
        $process = Get-Process -Id ([int]$record.pid) -ErrorAction SilentlyContinue
        if (-not $process) { continue }
        $recorded = [DateTime]::Parse($record.started_at).ToUniversalTime()
        if ([Math]::Abs(($process.StartTime.ToUniversalTime() - $recorded).TotalSeconds) -lt 3) {
            Stop-Process -Id $process.Id -Force
        }
    }
}

function Start-TrackedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory
    )
    $process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $runtimeDir "$Name.stdout.log") `
        -RedirectStandardError (Join-Path $runtimeDir "$Name.stderr.log")
    return [pscustomobject]@{
        name = $Name
        pid = $process.Id
        started_at = $process.StartTime.ToUniversalTime().ToString("O")
    }
}

function Find-MediaBinary {
    param([Parameter(Mandatory = $true)][string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $packageRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    $package = Get-ChildItem -LiteralPath $packageRoot -Directory -Filter "Gyan.FFmpeg.Essentials*" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $package) { return $null }
    return (Get-ChildItem -LiteralPath $package.FullName -Filter "$Name.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
}

Initialize-LocalEnvironment
Import-LocalEnvironment
New-Item -ItemType Directory -Path $runtimeDir, $env:ATTACHMENT_DIR, $env:GENERATED_MEDIA_DIR, $env:HIGHLIGHT_MEDIA_DIR, $env:AVATAR_DIR -Force | Out-Null

if (-not $SkipTests) {
    Write-Host "`n==> Kod testleri calistiriliyor" -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "test-local.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Kod testleri gecmeden ortam baslatilmadi." }
}

& cmd.exe /d /c "docker info >nul 2>nul"
if ($LASTEXITCODE -ne 0) { throw "Docker Desktop calismiyor." }

Write-Host "`n==> Izole PostgreSQL ve Matrix baslatiliyor" -ForegroundColor Cyan
Invoke-Compose up -d --no-build --wait --wait-timeout 240 postgres postgres-bootstrap matrix

Write-Host "`n==> Yerel veritabanina migration uygulanıyor" -ForegroundColor Cyan
Push-Location (Join-Path $repoRoot "backend")
try {
    & $venvPython -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "Yerel migration basarisiz oldu." }
}
finally { Pop-Location }

Stop-PreviousProcesses
$processes = @()
try {
    Write-Host "`n==> Gateway, backend, worker ve React arayuzu baslatiliyor" -ForegroundColor Cyan
    $backendGatewayUrl = $env:OLLAMA_BASE_URL
    $gatewayUpstreamUrl = $env:LOCAL_OLLAMA_BASE_URL
    if (-not $gatewayUpstreamUrl) { $gatewayUpstreamUrl = "http://127.0.0.1:11434" }
    $gatewayUpstreamUrl = $gatewayUpstreamUrl.Replace("host.docker.internal", "127.0.0.1")
    $env:OLLAMA_BASE_URL = $gatewayUpstreamUrl
    $processes += Start-TrackedProcess "ai-gateway" $venvPython @("-m", "uvicorn", "gateway.main:app", "--host", "127.0.0.1", "--port", "18090") (Join-Path $repoRoot "ai-gateway")
    $env:OLLAMA_BASE_URL = $backendGatewayUrl
    $processes += Start-TrackedProcess "backend" $venvPython @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "18100") (Join-Path $repoRoot "backend")
    $processes += Start-TrackedProcess "ai-worker" $venvPython @("-m", "app.services.ollama.worker") (Join-Path $repoRoot "backend")
    $ffmpegPath = Find-MediaBinary "ffmpeg"
    $ffprobePath = Find-MediaBinary "ffprobe"
    if ($ffmpegPath -and $ffprobePath) {
        $env:FFMPEG_BINARY = $ffmpegPath
        $env:FFPROBE_BINARY = $ffprobePath
        $processes += Start-TrackedProcess "media-worker" $venvPython @("-m", "app.modules.highlight_generator.media_worker") (Join-Path $repoRoot "backend")
    }
    $processes += Start-TrackedProcess "frontend" "cmd.exe" @("/d", "/c", "npm.cmd", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173") (Join-Path $repoRoot "frontend")
    $processes | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding UTF8

    $deadline = (Get-Date).AddMinutes(3)
    $frontendReady = $false
    $backendReady = $false
    do {
        Start-Sleep -Seconds 2
        try { $frontendReady = (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:5173" -TimeoutSec 3).StatusCode -eq 200 } catch { $frontendReady = $false }
        try { $backendReady = (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:18100/health" -TimeoutSec 3).StatusCode -eq 200 } catch { $backendReady = $false }
    } while ((-not ($frontendReady -and $backendReady)) -and (Get-Date) -lt $deadline)
    if (-not ($frontendReady -and $backendReady)) { throw "Yerel arayuz veya backend hazir olmadi. .local-runtime loglarini kontrol edin." }
}
catch {
    foreach ($record in $processes) { Stop-Process -Id $record.pid -Force -ErrorAction SilentlyContinue }
    throw
}

Write-Host "`nYerel insan test ortami hazir." -ForegroundColor Green
Write-Host "Arayuz:     http://localhost:5173"
Write-Host "API saglik: http://localhost:18100/health"
Write-Host "Ollama ve yerel AI Gateway aktif; dokuz modul arayuzden gorulebilir."
if (-not (Find-MediaBinary "ffmpeg") -or -not (Find-MediaBinary "ffprobe")) {
    Write-Host "Not: ffmpeg hostta kurulu degil; Highlight video render worker'i simdilik baslatilmadi." -ForegroundColor Yellow
}
if ($Open) { Start-Process "http://localhost:5173" }
