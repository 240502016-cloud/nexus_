[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^https://')]
    [string]$PublicUrl
)

$ErrorActionPreference = 'Stop'
$uri = [Uri]$PublicUrl
$port = if ($uri.IsDefaultPort) { 443 } else { $uri.Port }

Write-Host "Testing Nexus client access: $PublicUrl"
$tcp = Test-NetConnection $uri.Host -Port $port -WarningAction SilentlyContinue
if (-not $tcp.TcpTestSucceeded) {
    throw "TCP connection failed: $($uri.Host):$port"
}
Write-Host "[OK] TCP $($uri.Host):$port"

if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) {
    throw 'curl.exe was not found.'
}

$health = & curl.exe --fail --silent --show-error --insecure --max-time 10 "$($PublicUrl.TrimEnd('/'))/healthz"
if ($LASTEXITCODE -ne 0 -or ($health | Out-String).Trim() -ne 'ok') {
    throw 'Reverse proxy health check failed.'
}
Write-Host '[OK] reverse proxy'

& curl.exe --fail --silent --show-error --insecure --max-time 10 "$($PublicUrl.TrimEnd('/'))/api/health" | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Backend health check failed.' }
Write-Host '[OK] backend'

$matrix = & curl.exe --fail --silent --show-error --insecure --max-time 10 "$($PublicUrl.TrimEnd('/'))/_matrix/client/versions"
if ($LASTEXITCODE -ne 0 -or ($matrix | Out-String) -notmatch '"versions"') {
    throw 'Matrix client endpoint failed.'
}
Write-Host '[OK] Matrix'
Write-Host 'Nexus client access is ready.'
