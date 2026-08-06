$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runtimeDir = Join-Path $repoRoot ".local-runtime"
$pidFile = Join-Path $runtimeDir "processes.json"
$localEnv = Join-Path $repoRoot ".env.local"

if (Test-Path -LiteralPath $pidFile) {
    $records = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
    foreach ($record in @($records)) {
        $process = Get-Process -Id ([int]$record.pid) -ErrorAction SilentlyContinue
        if (-not $process) { continue }
        $recorded = [DateTime]::Parse($record.started_at).ToUniversalTime()
        if ([Math]::Abs(($process.StartTime.ToUniversalTime() - $recorded).TotalSeconds) -lt 3) {
            Stop-Process -Id $process.Id -Force
        }
    }
    Remove-Item -LiteralPath $pidFile -Force
}

if (Test-Path -LiteralPath $localEnv) {
    & docker compose --env-file $localEnv `
        -f (Join-Path $repoRoot "docker-compose.yml") `
        -f (Join-Path $repoRoot "docker-compose.local.yml") `
        --project-name nexus-local stop matrix postgres
    if ($LASTEXITCODE -ne 0) { throw "Yerel altyapi durdurulamadi." }
}

Write-Host "Yerel servisler durduruldu. Veritabani ve medya dosyalari korundu." -ForegroundColor Green
