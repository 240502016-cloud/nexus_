[CmdletBinding()]
param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '..\artifacts\nexus-client')
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repoRoot
$resolvedOutput = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $resolvedOutput | Out-Null

function Read-EnvValue {
    param([string]$Name)
    foreach ($line in Get-Content -LiteralPath (Join-Path $repoRoot '.env')) {
        if ($line.StartsWith("$Name=")) { return $line.Substring($Name.Length + 1).Trim() }
    }
    return $null
}

if (-not (Test-Path -LiteralPath (Join-Path $repoRoot '.env'))) {
    throw '.env was not found.'
}
$publicUrl = Read-EnvValue 'NEXUS_PUBLIC_URL'
if (-not $publicUrl) {
    $domain = Read-EnvValue 'NEXUS_DOMAIN'
    $port = Read-EnvValue 'NEXUS_HTTPS_PORT'
    $publicUrl = if ($port -and $port -ne '443') { "https://${domain}:$port" } else { "https://$domain" }
}

& docker compose cp 'reverse-proxy:/data/caddy/pki/authorities/local/root.crt' `
    (Join-Path $resolvedOutput 'nexus-caddy-root.crt')
if ($LASTEXITCODE -ne 0) {
    throw 'Caddy root certificate could not be copied. Ensure reverse-proxy is running and using local HTTPS.'
}

Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'install-nexus-client-certificate.ps1') `
    -Destination $resolvedOutput -Force

$instructions = @"
Nexus client access package
===========================

1. Install Hamachi and join the Nexus Hamachi network.
2. Verify connectivity:
   Test-NetConnection $(([Uri]$publicUrl).Host) -Port $(([Uri]$publicUrl).Port)
3. Open Administrator PowerShell in this directory.
4. Install the private Nexus root certificate:
   powershell.exe -ExecutionPolicy Bypass -File .\install-nexus-client-certificate.ps1 -ConfirmTrust
5. Open Nexus:
   $publicUrl

Do not share server .env files, database passwords or AI API keys with client users.
"@
[IO.File]::WriteAllText(
    (Join-Path $resolvedOutput 'README.txt'),
    ($instructions.Trim() + [Environment]::NewLine),
    (New-Object Text.UTF8Encoding($false))
)
Write-Host "Client package created: $resolvedOutput"
Write-Host "Nexus URL: $publicUrl"
