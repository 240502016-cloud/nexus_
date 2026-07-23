[CmdletBinding()]
param(
    [switch]$ConfirmRepair,
    [switch]$StartServices
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repoRoot

if (-not $ConfirmRepair) {
    throw 'Onarım Synapse veritabanını yeniden adlandırıp C locale ile yeniden oluşturur. Devam etmek için -ConfirmRepair verin.'
}

function Invoke-DockerCompose {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    & docker compose @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose komutu başarısız oldu: $($Arguments -join ' ') (exit=$LASTEXITCODE)"
    }
}

function Invoke-PostgresShell {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [switch]$Capture
    )

    $output = & docker compose exec -T postgres sh -c $Command
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL komutu başarısız oldu (exit=$LASTEXITCODE)."
    }
    if ($Capture) {
        return (($output | Out-String).Trim())
    }
}

function Get-ComposeDatabaseSettings {
    $json = & docker compose config --format json
    if ($LASTEXITCODE -ne 0) {
        throw 'docker compose config could not resolve database settings.'
    }
    $config = ($json | Out-String) | ConvertFrom-Json
    return [pscustomobject]@{
        AdminUser = [string]$config.services.postgres.environment.POSTGRES_USER
        MaintenanceDatabase = [string]$config.services.postgres.environment.POSTGRES_DB
        SynapseUser = [string]$config.services.postgres.environment.SYNAPSE_POSTGRES_USER
        SynapseDatabase = [string]$config.services.postgres.environment.SYNAPSE_POSTGRES_DB
    }
}

function Invoke-PostgresTool {
    param(
        [Parameter(Mandatory = $true)][string]$Tool,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$Capture
    )

    $output = & docker compose exec -T postgres $Tool @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL tool failed: $Tool (exit=$LASTEXITCODE)."
    }
    if ($Capture) {
        return (($output | Out-String).Trim())
    }
}

Write-Host 'PostgreSQL başlatılıyor ve roller doğrulanıyor...'
Invoke-DockerCompose @('up', '-d', 'postgres')
Invoke-DockerCompose @('run', '--rm', 'postgres-bootstrap')

$databaseSettings = Get-ComposeDatabaseSettings
if ($databaseSettings.SynapseDatabase -notmatch '^[A-Za-z_][A-Za-z0-9_-]*$') {
    throw "Unsupported Synapse database name: $($databaseSettings.SynapseDatabase)"
}
$escapedSynapseDatabase = $databaseSettings.SynapseDatabase.Replace("'", "''")
$localeSql = "SELECT datcollate || '|' || datctype FROM pg_database WHERE datname = '$escapedSynapseDatabase'"
$psqlLocaleArguments = @(
    "--username=$($databaseSettings.AdminUser)",
    "--dbname=$($databaseSettings.MaintenanceDatabase)",
    '--tuples-only',
    '--no-align',
    "--command=$localeSql"
)
$currentLocale = Invoke-PostgresTool -Tool 'psql' -Arguments $psqlLocaleArguments -Capture
if (-not $currentLocale) {
    throw "Synapse database was not found: $($databaseSettings.SynapseDatabase)"
}
if ($currentLocale -eq 'C|C') {
    Write-Host 'Synapse veritabanı zaten C/C locale kullanıyor; onarım gerekmiyor.'
    if ($StartServices) { Invoke-DockerCompose @('up', '-d') }
    exit 0
}

$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmss'Z'")
$dumpFile = "synapse-before-locale-repair-$stamp.dump"
$legacyDatabase = "synapse_locale_backup_$($stamp.Replace('-', '').Replace('Z', ''))"
$hostBackupDirectory = Join-Path $repoRoot 'backups\postgres-locale-repair'
New-Item -ItemType Directory -Force -Path $hostBackupDirectory | Out-Null

Write-Host "Mevcut locale: $currentLocale. Matrix bağımlıları durduruluyor..."
Invoke-DockerCompose @('stop', 'reverse-proxy', 'backend', 'matrix')

Write-Host "Synapse dump alınıyor: $dumpFile"
Invoke-PostgresTool -Tool 'pg_dump' -Arguments @(
    '--format=custom',
    "--username=$($databaseSettings.AdminUser)",
    "--dbname=$($databaseSettings.SynapseDatabase)",
    "--file=/backups/$dumpFile"
)
Invoke-PostgresShell -Command ('test -s "/backups/' + $dumpFile + '"')
Invoke-DockerCompose @('cp', "postgres:/backups/$dumpFile", $hostBackupDirectory)

$hostDump = Join-Path $hostBackupDirectory $dumpFile
if (-not (Test-Path -LiteralPath $hostDump) -or (Get-Item -LiteralPath $hostDump).Length -le 0) {
    throw "Host backup doğrulanamadı: $hostDump"
}
$dumpHash = (Get-FileHash -LiteralPath $hostDump -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "Backup doğrulandı (SHA-256: $dumpHash)."

Write-Host "Eski veritabanı geri dönüş için yeniden adlandırılıyor: $legacyDatabase"
$terminateSql = "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$escapedSynapseDatabase' AND pid <> pg_backend_pid()"
$quotedSynapseDatabase = '"' + $databaseSettings.SynapseDatabase.Replace('"', '""') + '"'
$quotedLegacyDatabase = '"' + $legacyDatabase.Replace('"', '""') + '"'
$renameSql = "ALTER DATABASE $quotedSynapseDatabase RENAME TO $quotedLegacyDatabase"
Invoke-PostgresTool -Tool 'psql' -Arguments @(
    '--set=ON_ERROR_STOP=1',
    "--username=$($databaseSettings.AdminUser)",
    "--dbname=$($databaseSettings.MaintenanceDatabase)",
    "--command=$terminateSql",
    "--command=$renameSql"
)

Write-Host 'Yeni Synapse veritabanı UTF8 + C/C locale ile oluşturuluyor...'
Invoke-PostgresTool -Tool 'createdb' -Arguments @(
    "--username=$($databaseSettings.AdminUser)",
    "--owner=$($databaseSettings.SynapseUser)",
    '--encoding=UTF8',
    '--lc-collate=C',
    '--lc-ctype=C',
    '--template=template0',
    $databaseSettings.SynapseDatabase
)

Write-Host 'Synapse verisi yeni veritabanına geri yükleniyor...'
Invoke-PostgresTool -Tool 'pg_restore' -Arguments @(
    '--exit-on-error',
    '--no-owner',
    "--role=$($databaseSettings.SynapseUser)",
    "--username=$($databaseSettings.AdminUser)",
    "--dbname=$($databaseSettings.SynapseDatabase)",
    "/backups/$dumpFile"
)

$repairedLocale = Invoke-PostgresTool -Tool 'psql' -Arguments $psqlLocaleArguments -Capture
if ($repairedLocale -ne 'C|C') {
    throw "Onarım sonrası locale beklenen C|C değil: $repairedLocale"
}

Write-Host 'Synapse collation onarımı tamamlandı.'
Write-Host "Eski veritabanı korundu: $legacyDatabase"
Write-Host "Backup: $hostDump"
if ($StartServices) {
    Invoke-DockerCompose @('up', '-d')
    Invoke-DockerCompose @('ps', '-a')
}
else {
    Write-Host 'Servisleri başlatmak için docker compose up -d çalıştırın.'
}
