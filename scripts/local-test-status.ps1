param([switch]$Logs)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$localEnv = Join-Path $repoRoot ".env.local"

if (-not (Test-Path -LiteralPath $localEnv)) {
    throw ".env.local bulunamadi. Once Yerel-Test-Baslat.cmd dosyasini calistirin."
}

$baseArgs = @(
    "compose",
    "--env-file", $localEnv,
    "-f", (Join-Path $repoRoot "docker-compose.yml"),
    "-f", (Join-Path $repoRoot "docker-compose.local.yml"),
    "--project-name", "nexus-local"
)

if ($Logs) {
    $runtimeDir = Join-Path $repoRoot ".local-runtime"
    Get-ChildItem -LiteralPath $runtimeDir -Filter "*.log" -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host "`n--- $($_.Name)" -ForegroundColor Cyan
        Get-Content -LiteralPath $_.FullName -Tail 120
    }
    & docker @baseArgs logs --tail 120 matrix postgres
    exit $LASTEXITCODE
}

& docker @baseArgs ps postgres matrix
if ($LASTEXITCODE -ne 0) { throw "Yerel altyapi durumu alinamadi." }

Write-Host "`nHost servisleri:" -ForegroundColor Cyan
$pidFile = Join-Path $repoRoot ".local-runtime\processes.json"
if (Test-Path -LiteralPath $pidFile) {
    $records = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
    foreach ($record in @($records)) {
        $process = Get-Process -Id ([int]$record.pid) -ErrorAction SilentlyContinue
        $status = if ($process) { "calisiyor" } else { "kapali" }
        Write-Host ("{0,-14} PID {1,-7} {2}" -f $record.name, $record.pid, $status)
    }
}
else { Write-Host "Host PID kaydi bulunamadi." -ForegroundColor Yellow }

foreach ($endpoint in @("http://127.0.0.1:5173", "http://127.0.0.1:18100/health")) {
    try { $code = (Invoke-WebRequest -UseBasicParsing $endpoint -TimeoutSec 3).StatusCode }
    catch { $code = "ulasamiyor" }
    Write-Host "$endpoint -> $code"
}
