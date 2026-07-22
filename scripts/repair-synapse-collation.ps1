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

Write-Host 'PostgreSQL başlatılıyor ve roller doğrulanıyor...'
Invoke-DockerCompose @('up', '-d', 'postgres')
Invoke-DockerCompose @('run', '--rm', 'postgres-bootstrap')

$localeCommand = 'psql --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --tuples-only --no-align --set=target_db="$SYNAPSE_POSTGRES_DB" --command="SELECT datcollate || ''|'' || datctype FROM pg_database WHERE datname = :''target_db''"'
$currentLocale = Invoke-PostgresShell -Command $localeCommand -Capture
if (-not $currentLocale) {
    throw 'Synapse veritabanı bulunamadı.'
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
Invoke-PostgresShell -Command ('pg_dump --format=custom --username="$POSTGRES_USER" --dbname="$SYNAPSE_POSTGRES_DB" --file="/backups/' + $dumpFile + '"')
Invoke-PostgresShell -Command ('test -s "/backups/' + $dumpFile + '"')
Invoke-DockerCompose @('cp', "postgres:/backups/$dumpFile", $hostBackupDirectory)

$hostDump = Join-Path $hostBackupDirectory $dumpFile
if (-not (Test-Path -LiteralPath $hostDump) -or (Get-Item -LiteralPath $hostDump).Length -le 0) {
    throw "Host backup doğrulanamadı: $hostDump"
}
$dumpHash = (Get-FileHash -LiteralPath $hostDump -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "Backup doğrulandı (SHA-256: $dumpHash)."

Write-Host "Eski veritabanı geri dönüş için yeniden adlandırılıyor: $legacyDatabase"
$renameCommand = 'rename_sql="$(psql --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --tuples-only --no-align --set=target_db="$SYNAPSE_POSTGRES_DB" --set=legacy_db="' + $legacyDatabase + '" --command="SELECT format(''ALTER DATABASE %I RENAME TO %I'', :''target_db'', :''legacy_db'')")" && psql --set=ON_ERROR_STOP=1 --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --command="SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = ''$SYNAPSE_POSTGRES_DB'' AND pid <> pg_backend_pid()" --command="$rename_sql"'
Invoke-PostgresShell -Command $renameCommand

Write-Host 'Yeni Synapse veritabanı UTF8 + C/C locale ile oluşturuluyor...'
Invoke-PostgresShell -Command 'createdb --username="$POSTGRES_USER" --owner="$SYNAPSE_POSTGRES_USER" --encoding=UTF8 --lc-collate=C --lc-ctype=C --template=template0 "$SYNAPSE_POSTGRES_DB"'

Write-Host 'Synapse verisi yeni veritabanına geri yükleniyor...'
Invoke-PostgresShell -Command ('pg_restore --exit-on-error --no-owner --role="$SYNAPSE_POSTGRES_USER" --username="$POSTGRES_USER" --dbname="$SYNAPSE_POSTGRES_DB" "/backups/' + $dumpFile + '"')

$repairedLocale = Invoke-PostgresShell -Command $localeCommand -Capture
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
