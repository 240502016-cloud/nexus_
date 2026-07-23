[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Server', 'Gateway', 'Status')]
    [string]$Role,
    [string]$LocalAddress,
    [string]$RemoteAddress = '25.0.0.0/8',
    [ValidateRange(1, 65535)]
    [int]$HttpPort = 8080,
    [ValidateRange(1, 65535)]
    [int]$HttpsPort = 8443,
    [ValidateRange(1, 65535)]
    [int]$GatewayPort = 8090,
    [ValidateRange(1, 65535)]
    [int]$TurnPort = 3478,
    [ValidateRange(1, 65535)]
    [int]$TurnMinPort = 50000,
    [ValidateRange(1, 65535)]
    [int]$TurnMaxPort = 50040,
    [switch]$ResolvePythonBlock
)

$ErrorActionPreference = 'Stop'
$group = 'Nexus Communication Platform'

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'This firewall action requires an Administrator PowerShell window.'
    }
}

function Remove-ManagedRule {
    param([string]$DisplayName)
    Get-NetFirewallRule -DisplayName $DisplayName -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule -ErrorAction Stop
}

function Add-ManagedRule {
    param(
        [string]$DisplayName,
        [ValidateSet('TCP', 'UDP', 'ICMPv4')][string]$Protocol,
        [string]$LocalPort
    )
    Remove-ManagedRule $DisplayName
    $parameters = @{
        DisplayName = $DisplayName
        Group = $group
        Direction = 'Inbound'
        Action = 'Allow'
        Enabled = 'True'
        Profile = 'Any'
        Protocol = $Protocol
        RemoteAddress = $RemoteAddress
    }
    if ($LocalAddress) { $parameters.LocalAddress = $LocalAddress }
    if ($LocalPort) { $parameters.LocalPort = $LocalPort }
    New-NetFirewallRule @parameters | Out-Null
    Write-Host "[OK] $DisplayName"
}

function Show-ManagedRules {
    $rules = @(Get-NetFirewallRule -Group $group -ErrorAction SilentlyContinue)
    if (-not $rules) {
        Write-Host 'No Nexus-managed firewall rules were found.'
        return
    }
    $rows = foreach ($rule in $rules) {
        $port = $rule | Get-NetFirewallPortFilter
        $address = $rule | Get-NetFirewallAddressFilter
        [pscustomobject]@{
            Name = $rule.DisplayName
            Enabled = $rule.Enabled
            Action = $rule.Action
            Protocol = $port.Protocol
            LocalPort = $port.LocalPort
            LocalAddress = $address.LocalAddress
            RemoteAddress = $address.RemoteAddress
        }
    }
    $rows | Sort-Object Name | Format-Table -AutoSize
}

Assert-Administrator

if ($Role -eq 'Status') {
    Show-ManagedRules
    exit 0
}

if (-not $LocalAddress) {
    throw 'LocalAddress is required for Server and Gateway firewall configuration.'
}

if ($Role -eq 'Server') {
    Add-ManagedRule -DisplayName 'Nexus Server HTTP (Hamachi)' -Protocol TCP -LocalPort ([string]$HttpPort)
    Add-ManagedRule -DisplayName 'Nexus Server HTTPS (Hamachi)' -Protocol TCP -LocalPort ([string]$HttpsPort)
    Add-ManagedRule -DisplayName 'Nexus TURN control TCP (Hamachi)' -Protocol TCP -LocalPort ([string]$TurnPort)
    Add-ManagedRule -DisplayName 'Nexus TURN control UDP (Hamachi)' -Protocol UDP -LocalPort ([string]$TurnPort)
    Add-ManagedRule -DisplayName 'Nexus TURN relay TCP (Hamachi)' -Protocol TCP -LocalPort "$TurnMinPort-$TurnMaxPort"
    Add-ManagedRule -DisplayName 'Nexus TURN relay UDP (Hamachi)' -Protocol UDP -LocalPort "$TurnMinPort-$TurnMaxPort"
    Add-ManagedRule -DisplayName 'Nexus Hamachi ping' -Protocol ICMPv4
}

if ($Role -eq 'Gateway') {
    if (-not $RemoteAddress -or $RemoteAddress -eq '25.0.0.0/8') {
        Write-Warning 'Gateway RemoteAddress is broad. Prefer the exact Nexus server Hamachi IP.'
    }
    if ($ResolvePythonBlock) {
        $tcpBlocks = @(
            Get-NetFirewallRule -DisplayName 'python.exe' -ErrorAction SilentlyContinue |
                Where-Object {
                    $_.Enabled -eq 'True' -and
                    $_.Direction -eq 'Inbound' -and
                    $_.Action -eq 'Block' -and
                    (($_ | Get-NetFirewallPortFilter).Protocol -eq 'TCP')
                }
        )
        if ($tcpBlocks) {
            $tcpBlocks | Disable-NetFirewallRule
            Write-Host "[OK] Disabled $($tcpBlocks.Count) conflicting inbound Python TCP block rule(s)."
        }
    }
    Add-ManagedRule -DisplayName 'Nexus AI Gateway (Hamachi)' -Protocol TCP -LocalPort ([string]$GatewayPort)
    Add-ManagedRule -DisplayName 'Nexus Hamachi ping' -Protocol ICMPv4
}

Write-Host ''
Show-ManagedRules
