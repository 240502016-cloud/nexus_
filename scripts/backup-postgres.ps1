[CmdletBinding()]
param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '..\backups\postgres'),
    [ValidateRange(1, 3650)]
    [int]$RetentionDays = 14,
    [switch]$Prune
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repoRoot
$resolvedOutput = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $resolvedOutput | Out-Null

$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmss'Z'")
$appFile = "nexus-$stamp.dump"
$synapseFile = "synapse-$stamp.dump"
$globalsFile = "globals-$stamp.sql"

function Invoke-PostgresShell {
    param([Parameter(Mandatory = $true)][string]$Command)
    & docker compose exec -T postgres sh -c $Command
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL backup komutu başarısız oldu (exit=$LASTEXITCODE)."
    }
}

function Copy-FromPostgres {
    param([string]$FileName)
    & docker compose cp "postgres:/backups/$FileName" $resolvedOutput
    if ($LASTEXITCODE -ne 0) { throw "Backup dosyası host'a kopyalanamadı: $FileName" }
}

# Container içindeki admin rolü local socket üzerinden iki uygulama veritabanını da okuyabilir.
    # Şifreler komut satırına veya backup manifestine yazılmaz.
    Invoke-PostgresShell ('pg_dump --format=custom --username="$POSTGRES_USER" --dbname="$APP_POSTGRES_DB" --file="/backups/' + $appFile + '"')
    Invoke-PostgresShell ('pg_dump --format=custom --username="$POSTGRES_USER" --dbname="$SYNAPSE_POSTGRES_DB" --file="/backups/' + $synapseFile + '"')
    Invoke-PostgresShell ('pg_dumpall --globals-only --username="$POSTGRES_USER" > "/backups/' + $globalsFile + '"')
    Copy-FromPostgres $appFile
    Copy-FromPostgres $synapseFile
    Copy-FromPostgres $globalsFile

    $dumpFiles = @($appFile, $synapseFile, $globalsFile) | ForEach-Object {
        $path = Join-Path $resolvedOutput $_
        if (-not (Test-Path -LiteralPath $path)) {
            throw "Beklenen backup dosyası oluşmadı: $path"
        }
        $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        [pscustomobject]@{ name = $_; sha256 = $hash; bytes = (Get-Item -LiteralPath $path).Length }
    }

    $manifest = [pscustomobject]@{
        created_at_utc = (Get-Date).ToUniversalTime().ToString('o')
        app_database = 'APP_POSTGRES_DB'
        synapse_database = 'SYNAPSE_POSTGRES_DB'
        files = $dumpFiles
    }
    $manifestPath = Join-Path $resolvedOutput "manifest-$stamp.json"
    $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

    if ($Prune) {
        $cutoff = (Get-Date).ToUniversalTime().AddDays(-$RetentionDays)
        Get-ChildItem -LiteralPath $resolvedOutput -File |
            Where-Object { $_.LastWriteTimeUtc -lt $cutoff -and $_.Extension -in '.dump', '.sql', '.json' } |
            Remove-Item -Force
        Write-Host "Eski backup dosyaları $RetentionDays günden sonra temizlendi."
    }

Write-Host "PostgreSQL backup tamamlandı: $resolvedOutput"
Write-Host "Manifest: $manifestPath"
