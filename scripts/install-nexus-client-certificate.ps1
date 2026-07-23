[CmdletBinding()]
param(
    [string]$CertificatePath = (Join-Path $PSScriptRoot 'nexus-caddy-root.crt'),
    [switch]$ConfirmTrust
)

$ErrorActionPreference = 'Stop'
if (-not $ConfirmTrust) {
    throw 'A root certificate can trust certificates issued by this Nexus server. Use -ConfirmTrust after verifying the source.'
}
if (-not (Test-Path -LiteralPath $CertificatePath -PathType Leaf)) {
    throw "Certificate was not found: $CertificatePath"
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an Administrator PowerShell window.'
}

$certificate = New-Object Security.Cryptography.X509Certificates.X509Certificate2($CertificatePath)
Write-Host "Subject    : $($certificate.Subject)"
Write-Host "Thumbprint : $($certificate.Thumbprint)"
Import-Certificate -FilePath $CertificatePath -CertStoreLocation 'Cert:\LocalMachine\Root' | Out-Null
Write-Host 'Nexus local root certificate was installed into LocalMachine Trusted Root.'
