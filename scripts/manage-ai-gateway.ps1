[CmdletBinding()]
param(
    [ValidateSet('Status', 'Stop')]
    [string]$Action = 'Status',
    [string]$HostAddress = '25.31.233.158',
    [ValidateRange(1, 65535)]
    [int]$Port = 8090,
    [switch]$ConfirmStop
)

$ErrorActionPreference = 'Stop'

function Get-GatewayListeners {
    $rows = @()
    $pattern = [regex]::Escape("${HostAddress}:$Port") + '\s+.*LISTENING\s+(\d+)$'
    foreach ($line in (& netstat.exe -ano -p tcp)) {
        if ($line.Trim() -match $pattern) {
            $pidValue = [int]$Matches[1]
            $process = Get-CimInstance Win32_Process -Filter "ProcessId=$pidValue" -ErrorAction SilentlyContinue
            $rows += [pscustomobject]@{
                Address = $HostAddress
                Port = $Port
                PID = $pidValue
                Name = $process.Name
                Executable = $process.ExecutablePath
                CommandLine = $process.CommandLine
                ProcessExists = [bool]$process
            }
        }
    }
    return $rows
}

$listeners = @(Get-GatewayListeners)
if (-not $listeners) {
    Write-Host "AI Gateway is not listening on ${HostAddress}:$Port."
    exit 0
}

$listeners | Select-Object Address, Port, PID, Name, ProcessExists, CommandLine | Format-List
if ($Action -eq 'Status') { exit 0 }

if (-not $ConfirmStop) {
    throw 'Stopping the Gateway requires -ConfirmStop.'
}

foreach ($listener in $listeners) {
    if (-not $listener.ProcessExists) {
        throw "Port is held by an orphan Windows listener (PID $($listener.PID)). Reboot Windows or use a different port."
    }
    if ($listener.CommandLine -notmatch 'uvicorn' -or $listener.CommandLine -notmatch 'gateway\.main') {
        throw "Refusing to stop PID $($listener.PID): it is not recognized as Nexus AI Gateway."
    }
    Stop-Process -Id $listener.PID -Force
    Write-Host "Stopped Nexus AI Gateway PID $($listener.PID)."
}
