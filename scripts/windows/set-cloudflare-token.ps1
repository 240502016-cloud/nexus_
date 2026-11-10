# Cloudflare API token'ını sunucudaki /opt/nexus/.env dosyasına yazar.
# Token ekranda görünmez, sohbete veya dosyaya kaydedilmez. Doğrulama ve yazma işini
# scripts/server/set-cloudflare-token.sh yapar; bu script onu sunucuya kopyalayıp çalıştırır.
param(
    [string]$ServerHost = 'root@169.40.43.242',
    [string]$IdentityFile = (Join-Path $env:USERPROFILE '.ssh\nexus_vds_migration_ed25519')
)
$ErrorActionPreference = 'Stop'
$helper = Join-Path $PSScriptRoot '..\server\set-cloudflare-token.sh'
$remoteHelper = '/tmp/set-cloudflare-token.sh'

& scp -q -i $IdentityFile -o BatchMode=yes $helper "${ServerHost}:$remoteHelper"
if ($LASTEXITCODE -ne 0) { throw 'Yardimci script sunucuya kopyalanamadi.' }

Write-Host ''
Write-Host "Cloudflare token'ini yapistir (sag tik veya Ctrl+V) ve Enter'a bas." -ForegroundColor Yellow
Write-Host '(Yapistirdiginda ekranda yildiz gorunur, bu normal.)' -ForegroundColor Yellow
$sec = Read-Host 'Token' -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
try {
    $tok = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

$tok | ssh -i $IdentityFile -o BatchMode=yes $ServerHost "bash $remoteHelper; rc=`$?; rm -f $remoteHelper; exit `$rc"
$tok = $null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Tamam! Caddy'nin yeni token'i kullanmasi icin sunucuda: docker compose up -d --force-recreate reverse-proxy" -ForegroundColor Green
} else {
    Write-Host 'Olmadi. Yukaridaki hatayi kontrol et; .env degistirilmedi.' -ForegroundColor Red
}
