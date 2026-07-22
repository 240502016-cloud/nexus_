[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupDirectory,
    [string]$Timestamp,
    [switch]$ConfirmRestore,
    [switch]$StartServices
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repoRoot
if (-not $ConfirmRestore) {
    throw 'Geri yükleme veri üzerine yazabilir. Devam etmek için -ConfirmRestore verin.'
}

$resolvedBackup = [IO.Path]::GetFullPath($BackupDirectory)
if (-not (Test-Path -LiteralPath $resolvedBackup -PathType Container)) {
    throw "Backup dizini bulunamadı: $resolvedBackup"
}

function Select-BackupFile {
    param([string]$Prefix, [string]$Suffix, [string]$SelectedTimestamp)
    $pattern = if ($SelectedTimestamp) { "$Prefix-$SelectedTimestamp$Suffix" } else { "$Prefix-*${Suffix}" }
    $matches = @(Get-ChildItem -LiteralPath $resolvedBackup -File -Filter $pattern | Sort-Object Name -Descending)
    if ($matches.Count -ne 1 -and -not $SelectedTimestamp) { return $matches[0] }
    if ($matches.Count -eq 1) { return $matches[0] }
    throw "Backup dosyası seçilemedi: $pattern"
}

$app = Select-BackupFile -Prefix 'nexus' -Suffix '.dump' -SelectedTimestamp $Timestamp
if (-not $app) { throw 'nexus-*.dump backup bulunamadı.' }
$selected = $app.BaseName.Substring('nexus-'.Length)
$synapse = Select-BackupFile -Prefix 'synapse' -Suffix '.dump' -SelectedTimestamp $selected
$globals = Select-BackupFile -Prefix 'globals' -Suffix '.sql' -SelectedTimestamp $selected
if (-not $synapse -or -not $globals) { throw "Aynı timestamp için Synapse/global backup eksik: $selected" }
$manifestPath = Join-Path $resolvedBackup "manifest-$selected.json"
if (-not (Test-Path -LiteralPath $manifestPath)) { throw "SHA-256 manifest bulunamadı: $manifestPath" }
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($entry in $manifest.files) {
    $filePath = Join-Path $resolvedBackup $entry.name
    if (-not (Test-Path -LiteralPath $filePath)) { throw "Manifest dosyası eksik: $filePath" }
    $actualHash = (Get-FileHash -LiteralPath $filePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $entry.sha256.ToLowerInvariant()) { throw "SHA-256 doğrulaması başarısız: $filePath" }
}
Write-Host "Backup SHA-256 doğrulandı: $selected"

function Invoke-PostgresShell {
    param([Parameter(Mandatory = $true)][string]$Command)
    & docker compose exec -T postgres sh -c $Command
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL restore komutu başarısız oldu (exit=$LASTEXITCODE)." }
}

function Copy-ToPostgres {
    param([System.IO.FileInfo]$File)
    & docker compose cp $File.FullName "postgres:/backups/$($File.Name)"
    if ($LASTEXITCODE -ne 0) { throw "Backup dosyası container'a kopyalanamadı: $($File.Name)" }
}

Copy-ToPostgres $app
Copy-ToPostgres $synapse
Copy-ToPostgres $globals
Write-Host 'Backend, Matrix ve reverse proxy durduruluyor...'
& docker compose stop reverse-proxy backend matrix
if ($LASTEXITCODE -ne 0) { throw 'Servisler güvenli restore için durdurulamadı.' }

# Önce roller/şifreler, sonra Nexus ve Synapse veritabanları geri yüklenir.
# Aynı cluster'da roller zaten varsa CREATE ROLE hataları beklenir; dump içindeki
# ALTER ROLE ifadelerinin çalışması için psql devam eder.
Invoke-PostgresShell ('psql --set ON_ERROR_STOP=0 --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --file="/backups/' + $globals.Name + '"')
Invoke-PostgresShell ('pg_restore --exit-on-error --clean --if-exists --username="$POSTGRES_USER" --dbname="$APP_POSTGRES_DB" "/backups/' + $app.Name + '"')
Invoke-PostgresShell ('pg_restore --exit-on-error --clean --if-exists --username="$POSTGRES_USER" --dbname="$SYNAPSE_POSTGRES_DB" "/backups/' + $synapse.Name + '"')

Write-Host "Restore tamamlandı: $selected"
if ($StartServices) {
    & docker compose up -d matrix backend reverse-proxy
    if ($LASTEXITCODE -ne 0) { throw 'Restore sonrası servisler başlatılamadı.' }
    Write-Host 'Matrix, backend ve reverse proxy yeniden başlatıldı.'
}
else {
    Write-Host 'Servisler durdurulmuş bırakıldı. Kontrolden sonra docker compose up -d çalıştırın.'
}
