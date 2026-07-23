[CmdletBinding()]
param([switch]$ValidateOnly)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[Windows.Forms.Application]::EnableVisualStyles()

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$serverScript = Join-Path $PSScriptRoot 'nexus-server.ps1'
$gatewayScript = Join-Path $repoRoot 'ai-gateway\start-gateway.ps1'
$gatewayTestScript = Join-Path $PSScriptRoot 'test-ai-gateway-tailscale.ps1'
$gatewayManagerScript = Join-Path $PSScriptRoot 'manage-ai-gateway.ps1'
$clientTestScript = Join-Path $PSScriptRoot 'test-nexus-client-access.ps1'
$firewallScript = Join-Path $PSScriptRoot 'configure-nexus-firewall.ps1'
$clientExportScript = Join-Path $PSScriptRoot 'export-nexus-client-package.ps1'
$restoreScript = Join-Path $PSScriptRoot 'restore-postgres.ps1'
$quickstartPath = Join-Path $repoRoot 'docs\deployment\SERVER_QUICKSTART.md'

foreach ($requiredFile in @(
    $serverScript, $gatewayScript, $gatewayTestScript, $gatewayManagerScript, $clientTestScript,
    $firewallScript, $clientExportScript, $restoreScript
)) {
    if (-not (Test-Path -LiteralPath $requiredFile)) {
        throw "Required file is missing: $requiredFile"
    }
}

function Start-ElevatedPowerShellWindow {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [string]$SuccessMessage = 'Administrator command started.'
    )
    $allArguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-NoExit') + $Arguments
    $argumentLine = ($allArguments | ForEach-Object { Quote-ProcessArgument ([string]$_) }) -join ' '
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = 'powershell.exe'
    $info.Arguments = $argumentLine
    $info.WorkingDirectory = $repoRoot
    $info.UseShellExecute = $true
    $info.Verb = 'runas'
    [void][Diagnostics.Process]::Start($info)
    $script:statusLabel.Text = $SuccessMessage
}

function Quote-ProcessArgument {
    param([string]$Value)
    return '"' + $Value.Replace('"', '\"') + '"'
}

function Start-PowerShellWindow {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [hashtable]$Environment = @{},
        [string]$SuccessMessage = 'Command started in a new PowerShell window.'
    )

    $oldValues = @{}
    try {
        foreach ($entry in $Environment.GetEnumerator()) {
            $oldValues[$entry.Key] = [Environment]::GetEnvironmentVariable($entry.Key, 'Process')
            [Environment]::SetEnvironmentVariable($entry.Key, [string]$entry.Value, 'Process')
        }
        $allArguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-NoExit') + $Arguments
        $argumentLine = ($allArguments | ForEach-Object { Quote-ProcessArgument ([string]$_) }) -join ' '
        $info = New-Object Diagnostics.ProcessStartInfo
        $info.FileName = 'powershell.exe'
        $info.Arguments = $argumentLine
        $info.WorkingDirectory = $repoRoot
        $info.UseShellExecute = $true
        [void][Diagnostics.Process]::Start($info)
        $script:statusLabel.Text = $SuccessMessage
    }
    finally {
        foreach ($entry in $oldValues.GetEnumerator()) {
            [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process')
        }
    }
}

function Show-UiError {
    param([string]$Message)
    [void][Windows.Forms.MessageBox]::Show(
        $Message,
        'Nexus Server Manager',
        [Windows.Forms.MessageBoxButtons]::OK,
        [Windows.Forms.MessageBoxIcon]::Error
    )
}

function Confirm-Action {
    param([string]$Message)
    $answer = [Windows.Forms.MessageBox]::Show(
        $Message,
        'Nexus Server Manager',
        [Windows.Forms.MessageBoxButtons]::YesNo,
        [Windows.Forms.MessageBoxIcon]::Question
    )
    return $answer -eq [Windows.Forms.DialogResult]::Yes
}

function Read-EnvValue {
    param([string]$Path, [string]$Name)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line.StartsWith("$Name=")) { return $line.Substring($Name.Length + 1).Trim() }
    }
    return $null
}

function Resolve-GatewayKey {
    if (-not [string]::IsNullOrWhiteSpace($script:gatewayKeyText.Text)) {
        return $script:gatewayKeyText.Text.Trim()
    }
    $localKey = Read-EnvValue -Path (Join-Path $repoRoot 'ai-gateway\.env') -Name 'AI_GATEWAY_API_KEY'
    if ($localKey) { return $localKey }
    return Read-EnvValue -Path (Join-Path $repoRoot '.env') -Name 'OLLAMA_API_KEY'
}

function Resolve-PublicUrl {
    $configured = Read-EnvValue -Path (Join-Path $repoRoot '.env') -Name 'NEXUS_PUBLIC_URL'
    if ($configured) { return $configured.TrimEnd('/') }
    $hostName = $script:serverAddressText.Text.Trim()
    if ($script:httpsPort.Value -eq 443) { return "https://$hostName" }
    return "https://${hostName}:$($script:httpsPort.Value)"
}

function Resolve-SelectedConfigPath {
    if ($script:configSelector.SelectedIndex -eq 0) {
        return (Join-Path $repoRoot '.env')
    }
    return (Join-Path $repoRoot 'ai-gateway\.env')
}

function Load-ConfigEditor {
    $path = Resolve-SelectedConfigPath
    if (-not (Test-Path -LiteralPath $path)) {
        $script:configEditor.Text = ''
        $script:configPathLabel.Text = "File does not exist yet: $path"
        return
    }
    $script:configEditor.Text = Get-Content -LiteralPath $path -Raw
    $script:configPathLabel.Text = $path
    $script:statusLabel.Text = 'Sensitive configuration loaded. Do not share screenshots containing secrets.'
}

function Assert-ConfigEditorContent {
    param([string]$Content)
    if ([string]::IsNullOrWhiteSpace($Content)) { throw 'Configuration content cannot be empty.' }
    $seen = @{}
    foreach ($line in ($Content -split '\r?\n')) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
        $separator = $trimmed.IndexOf('=')
        if ($separator -lt 1) { throw "Invalid configuration line: $line" }
        $key = $trimmed.Substring(0, $separator).Trim()
        $value = $trimmed.Substring($separator + 1)
        if ($seen.ContainsKey($key)) { throw "Duplicate configuration key: $key" }
        if ($value -match 'replace-with-|<[^>]+>') { throw "Placeholder value is not allowed: $key" }
        $seen[$key] = $value
    }
    if ($seen.Count -eq 0) { throw 'No configuration keys were found.' }
    if ($script:configSelector.SelectedIndex -eq 0) {
        foreach ($required in @(
            'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB',
            'SYNAPSE_POSTGRES_USER', 'SYNAPSE_POSTGRES_PASSWORD', 'SYNAPSE_POSTGRES_DB',
            'NEXUS_DOMAIN', 'MATRIX_SERVER_NAME', 'OLLAMA_BASE_URL', 'OLLAMA_API_KEY'
        )) {
            if (-not $seen.ContainsKey($required) -or [string]::IsNullOrWhiteSpace($seen[$required])) {
                throw "Required server setting is missing: $required"
            }
        }
        if ($seen['MATRIX_SERVER_NAME'] -match '://|/') {
            throw 'MATRIX_SERVER_NAME must not contain protocol or path.'
        }
    }
    else {
        foreach ($required in @('AI_GATEWAY_API_KEY', 'AI_GATEWAY_ALLOWED_NETWORKS', 'OLLAMA_BASE_URL')) {
            if (-not $seen.ContainsKey($required) -or [string]::IsNullOrWhiteSpace($seen[$required])) {
                throw "Required AI Gateway setting is missing: $required"
            }
        }
    }
}

function Save-ConfigEditor {
    try {
        Assert-ConfigEditorContent $script:configEditor.Text
        $path = Resolve-SelectedConfigPath
        if (-not (Confirm-Action "Save this sensitive configuration file?`n`n$path")) { return }
        if (Test-Path -LiteralPath $path) {
            $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmss'Z'")
            $backupPath = "$path.backup-$stamp"
            Copy-Item -LiteralPath $path -Destination $backupPath -Force
        }
        $parent = Split-Path $path
        if (-not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Path $parent | Out-Null
        }
        [IO.File]::WriteAllText(
            $path,
            ($script:configEditor.Text.Trim() + [Environment]::NewLine),
            (New-Object Text.UTF8Encoding($false))
        )
        $script:configPathLabel.Text = $path
        $script:statusLabel.Text = 'Configuration saved. A timestamped backup was retained when replacing a file.'
    }
    catch { Show-UiError $_.Exception.Message }
}

function Start-ServerAction {
    param([string]$Action)
    try {
        if ($Action -in @('Initialize', 'Deploy', 'Update')) {
            $message = switch ($Action) {
                'Initialize' { 'This creates a new .env and performs the full first deployment. Continue?' }
                'Deploy' { 'This builds images, reconciles databases, runs migrations and starts the stack. Continue?' }
                'Update' { 'This safely stashes tracked changes, pulls origin/main and deploys. Continue?' }
            }
            if (-not (Confirm-Action $message)) { return }
        }

        $arguments = @('-File', $serverScript, '-Action', $Action)
        $environment = @{}
        if ($Action -eq 'Initialize') {
            if ([string]::IsNullOrWhiteSpace($script:serverAddressText.Text)) {
                throw 'Server address is required.'
            }
            if ([string]::IsNullOrWhiteSpace($script:emailText.Text)) {
                throw 'ACME email is required.'
            }
            if ([string]::IsNullOrWhiteSpace($script:gatewayUrlText.Text)) {
                throw 'AI Gateway URL is required.'
            }
            $gatewayKey = Resolve-GatewayKey
            if ([string]::IsNullOrWhiteSpace($gatewayKey) -or $gatewayKey.Length -lt 32) {
                throw 'AI Gateway API key is missing or shorter than 32 characters.'
            }
            $arguments += @(
                '-ServerAddress', $script:serverAddressText.Text.Trim(),
                '-AcmeEmail', $script:emailText.Text.Trim(),
                '-AiGatewayUrl', $script:gatewayUrlText.Text.Trim(),
                '-HttpPort', [string]$script:httpPort.Value,
                '-HttpsPort', [string]$script:httpsPort.Value
            )
            $environment['NEXUS_SETUP_AI_GATEWAY_API_KEY'] = $gatewayKey
        }
        Start-PowerShellWindow -Arguments $arguments -Environment $environment `
            -SuccessMessage "$Action started in a new PowerShell window."
    }
    catch {
        Show-UiError $_.Exception.Message
    }
}

function Start-Gateway {
    try {
        $hostAddress = $script:gatewayHostText.Text.Trim()
        if ([string]::IsNullOrWhiteSpace($hostAddress)) { throw 'Gateway host address is required.' }
        $arguments = @(
            '-File', $gatewayScript,
            '-HostAddress', $hostAddress,
            '-Port', [string]$script:gatewayPort.Value
        )
        Start-PowerShellWindow -Arguments $arguments `
            -SuccessMessage 'AI Gateway started in a new PowerShell window. Keep that window open.'
    }
    catch {
        Show-UiError $_.Exception.Message
    }
}

function Test-Gateway {
    try {
        $gatewayKey = Resolve-GatewayKey
        if ([string]::IsNullOrWhiteSpace($gatewayKey) -or $gatewayKey.Length -lt 32) {
            throw 'AI Gateway API key is missing or shorter than 32 characters.'
        }
        $url = $script:gatewayUrlText.Text.Trim()
        if ([string]::IsNullOrWhiteSpace($url)) { throw 'AI Gateway URL is required.' }
        Start-PowerShellWindow `
            -Arguments @('-File', $gatewayTestScript, '-GatewayBaseUrl', $url) `
            -Environment @{ OLLAMA_API_KEY = $gatewayKey } `
            -SuccessMessage 'AI Gateway test started in a new PowerShell window.'
    }
    catch {
        Show-UiError $_.Exception.Message
    }
}

function Configure-ServerFirewall {
    try {
        if (-not (Confirm-Action 'Configure Windows Firewall for Nexus HTTPS, HTTP and TURN on the server computer?')) {
            return
        }
        Start-ElevatedPowerShellWindow -Arguments @(
            '-File', $firewallScript,
            '-Role', 'Server',
            '-LocalAddress', $script:serverFirewallAddressText.Text.Trim(),
            '-RemoteAddress', $script:serverRemoteNetworkText.Text.Trim(),
            '-HttpPort', [string]$script:httpPort.Value,
            '-HttpsPort', [string]$script:httpsPort.Value,
            '-TurnPort', '3478',
            '-TurnMinPort', '50000',
            '-TurnMaxPort', '50040'
        ) -SuccessMessage 'Server firewall configuration opened with Administrator privileges.'
    }
    catch { Show-UiError $_.Exception.Message }
}

function Configure-GatewayFirewall {
    try {
        if (-not (Confirm-Action 'Configure the AI computer firewall and disable conflicting inbound Python TCP block rules?')) {
            return
        }
        Start-ElevatedPowerShellWindow -Arguments @(
            '-File', $firewallScript,
            '-Role', 'Gateway',
            '-LocalAddress', $script:gatewayHostText.Text.Trim(),
            '-RemoteAddress', $script:gatewayRemoteServerText.Text.Trim(),
            '-GatewayPort', [string]$script:gatewayPort.Value,
            '-ResolvePythonBlock'
        ) -SuccessMessage 'AI Gateway firewall configuration opened with Administrator privileges.'
    }
    catch { Show-UiError $_.Exception.Message }
}

function Export-ClientPackage {
    try {
        if (-not (Confirm-Action 'Export the Caddy root certificate and client access instructions?')) { return }
        Start-PowerShellWindow -Arguments @('-File', $clientExportScript) `
            -SuccessMessage 'Client access package export started.'
    }
    catch { Show-UiError $_.Exception.Message }
}

function Restore-DatabaseBackup {
    $dialog = New-Object Windows.Forms.FolderBrowserDialog
    $dialog.Description = 'Select the PostgreSQL backup directory containing manifest and dump files.'
    $dialog.ShowNewFolderButton = $false
    if ($dialog.ShowDialog() -ne [Windows.Forms.DialogResult]::OK) { return }
    $message = "Restore PostgreSQL from this directory?`n`n$($dialog.SelectedPath)`n`nThis overwrites current database contents."
    if (-not (Confirm-Action $message)) { return }
    if (-not (Confirm-Action 'Final confirmation: stop services and restore this backup now?')) { return }
    Start-PowerShellWindow -Arguments @(
        '-File', $restoreScript,
        '-BackupDirectory', $dialog.SelectedPath,
        '-ConfirmRestore',
        '-StartServices'
    ) -SuccessMessage 'Database restore started in a new PowerShell window.'
}

function Add-Label {
    param($Parent, [string]$Text, [int]$X, [int]$Y, [int]$Width = 180)
    $control = New-Object Windows.Forms.Label
    $control.Text = $Text
    $control.Location = New-Object Drawing.Point($X, $Y)
    $control.Size = New-Object Drawing.Size($Width, 22)
    $Parent.Controls.Add($control)
    return $control
}

function Add-TextBox {
    param($Parent, [string]$Text, [int]$X, [int]$Y, [int]$Width = 300, [switch]$Password)
    $control = New-Object Windows.Forms.TextBox
    $control.Text = $Text
    $control.Location = New-Object Drawing.Point($X, $Y)
    $control.Size = New-Object Drawing.Size($Width, 25)
    if ($Password) { $control.UseSystemPasswordChar = $true }
    $Parent.Controls.Add($control)
    return $control
}

function Add-Button {
    param($Parent, [string]$Text, [int]$X, [int]$Y, [int]$Width = 170, [int]$Height = 42)
    $control = New-Object Windows.Forms.Button
    $control.Text = $Text
    $control.Location = New-Object Drawing.Point($X, $Y)
    $control.Size = New-Object Drawing.Size($Width, $Height)
    $control.FlatStyle = [Windows.Forms.FlatStyle]::System
    $Parent.Controls.Add($control)
    return $control
}

$form = New-Object Windows.Forms.Form
$form.Text = 'Nexus Server Manager'
$form.StartPosition = [Windows.Forms.FormStartPosition]::CenterScreen
$form.Size = New-Object Drawing.Size(930, 700)
$form.MinimumSize = New-Object Drawing.Size(930, 700)
$form.Font = New-Object Drawing.Font('Segoe UI', 9)

$title = Add-Label -Parent $form -Text 'Nexus Communication Platform - Control Center' -X 20 -Y 15 -Width 700
$title.Font = New-Object Drawing.Font('Segoe UI Semibold', 16)
$subtitle = Add-Label -Parent $form -Text 'Server deployment, updates, diagnostics and AI Gateway controls' -X 22 -Y 50 -Width 700
$subtitle.ForeColor = [Drawing.Color]::DimGray

$tabs = New-Object Windows.Forms.TabControl
$tabs.Location = New-Object Drawing.Point(20, 82)
$tabs.Size = New-Object Drawing.Size(875, 510)
$form.Controls.Add($tabs)

$serverTab = New-Object Windows.Forms.TabPage
$serverTab.Text = 'Server'
$tabs.TabPages.Add($serverTab)

$gatewayTab = New-Object Windows.Forms.TabPage
$gatewayTab.Text = 'AI Gateway'
$tabs.TabPages.Add($gatewayTab)

$databaseTab = New-Object Windows.Forms.TabPage
$databaseTab.Text = 'Database'
$tabs.TabPages.Add($databaseTab)

$networkTab = New-Object Windows.Forms.TabPage
$networkTab.Text = 'Network & Client'
$tabs.TabPages.Add($networkTab)

$configTab = New-Object Windows.Forms.TabPage
$configTab.Text = 'Config Editor'
$tabs.TabPages.Add($configTab)

$helpTab = New-Object Windows.Forms.TabPage
$helpTab.Text = 'Help'
$tabs.TabPages.Add($helpTab)

$settingsGroup = New-Object Windows.Forms.GroupBox
$settingsGroup.Text = 'New server settings (used only by Initialize)'
$settingsGroup.Location = New-Object Drawing.Point(15, 15)
$settingsGroup.Size = New-Object Drawing.Size(825, 225)
$serverTab.Controls.Add($settingsGroup)

[void](Add-Label $settingsGroup 'Server IP / domain' 20 32)
$script:serverAddressText = Add-TextBox $settingsGroup '25.49.22.166' 200 29 260
[void](Add-Label $settingsGroup 'ACME email' 20 70)
$script:emailText = Add-TextBox $settingsGroup '240502016@kocaelisaglik.edu.tr' 200 67 340
[void](Add-Label $settingsGroup 'AI Gateway URL' 20 108)
$script:gatewayUrlText = Add-TextBox $settingsGroup 'http://25.31.233.158:8090' 200 105 340
[void](Add-Label $settingsGroup 'AI Gateway API key' 20 146)
$script:gatewayKeyText = Add-TextBox $settingsGroup '' 200 143 500 -Password

[void](Add-Label $settingsGroup 'HTTP port' 560 32 90)
$script:httpPort = New-Object Windows.Forms.NumericUpDown
$script:httpPort.Location = New-Object Drawing.Point(655, 29)
$script:httpPort.Minimum = 1
$script:httpPort.Maximum = 65535
$script:httpPort.Value = 8080
$settingsGroup.Controls.Add($script:httpPort)

[void](Add-Label $settingsGroup 'HTTPS port' 560 70 90)
$script:httpsPort = New-Object Windows.Forms.NumericUpDown
$script:httpsPort.Location = New-Object Drawing.Point(655, 67)
$script:httpsPort.Minimum = 1
$script:httpsPort.Maximum = 65535
$script:httpsPort.Value = 8443
$settingsGroup.Controls.Add($script:httpsPort)

$keyHint = Add-Label $settingsGroup 'Key is masked and passed through the child process environment, not the command line.' 200 178 590
$keyHint.ForeColor = [Drawing.Color]::DimGray

$actionsGroup = New-Object Windows.Forms.GroupBox
$actionsGroup.Text = 'Server actions'
$actionsGroup.Location = New-Object Drawing.Point(15, 255)
$actionsGroup.Size = New-Object Drawing.Size(825, 205)
$serverTab.Controls.Add($actionsGroup)

$initializeButton = Add-Button $actionsGroup 'Initialize new server' 20 35 180
$updateButton = Add-Button $actionsGroup 'Safe update' 215 35 180
$deployButton = Add-Button $actionsGroup 'Deploy current code' 410 35 180
$startButton = Add-Button $actionsGroup 'Start stack' 605 35 180
$statusButton = Add-Button $actionsGroup 'Status' 20 95 180
$diagnoseButton = Add-Button $actionsGroup 'Diagnose' 215 95 180
$envButton = Add-Button $actionsGroup 'Open .env' 410 95 180
$folderButton = Add-Button $actionsGroup 'Open project folder' 605 95 180
$validateButton = Add-Button $actionsGroup 'Validate configuration' 20 150 180 36
$stopButton = Add-Button $actionsGroup 'Stop stack (safe)' 215 150 180 36
$restartButton = Add-Button $actionsGroup 'Restart stack' 410 150 180 36
$dockerButton = Add-Button $actionsGroup 'Open Docker Desktop' 605 150 180 36

$initializeButton.Add_Click({ Start-ServerAction 'Initialize' })
$updateButton.Add_Click({ Start-ServerAction 'Update' })
$deployButton.Add_Click({ Start-ServerAction 'Deploy' })
$startButton.Add_Click({ Start-ServerAction 'Start' })
$statusButton.Add_Click({ Start-ServerAction 'Status' })
$diagnoseButton.Add_Click({ Start-ServerAction 'Diagnose' })
$validateButton.Add_Click({ Start-ServerAction 'Validate' })
$stopButton.Add_Click({
    if (Confirm-Action 'Stop all Nexus containers without deleting data or volumes?') {
        Start-ServerAction 'Stop'
    }
})
$restartButton.Add_Click({ Start-ServerAction 'Restart' })
$dockerButton.Add_Click({
    $dockerDesktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (Test-Path -LiteralPath $dockerDesktop) {
        Start-Process -FilePath $dockerDesktop
    }
    else {
        Show-UiError 'Docker Desktop was not found in the default installation path.'
    }
})
$envButton.Add_Click({
    $path = Join-Path $repoRoot '.env'
    if (Test-Path -LiteralPath $path) {
        Start-Process notepad.exe -ArgumentList (Quote-ProcessArgument $path)
    }
    else {
        Show-UiError '.env does not exist yet. Use Initialize for a new server.'
    }
})
$folderButton.Add_Click({ Start-Process explorer.exe -ArgumentList (Quote-ProcessArgument $repoRoot) })

$gatewayGroup = New-Object Windows.Forms.GroupBox
$gatewayGroup.Text = 'AI computer'
$gatewayGroup.Location = New-Object Drawing.Point(15, 15)
$gatewayGroup.Size = New-Object Drawing.Size(825, 255)
$gatewayTab.Controls.Add($gatewayGroup)

[void](Add-Label $gatewayGroup 'Listen address' 20 40)
$script:gatewayHostText = Add-TextBox $gatewayGroup '25.31.233.158' 190 37 260
[void](Add-Label $gatewayGroup 'Port' 500 40 60)
$script:gatewayPort = New-Object Windows.Forms.NumericUpDown
$script:gatewayPort.Location = New-Object Drawing.Point(565, 37)
$script:gatewayPort.Minimum = 1
$script:gatewayPort.Maximum = 65535
$script:gatewayPort.Value = 8090
$gatewayGroup.Controls.Add($script:gatewayPort)

$gatewayStartButton = Add-Button $gatewayGroup 'Start AI Gateway' 20 95 220 48
$gatewayTestButton = Add-Button $gatewayGroup 'Test URL + key' 260 95 220 48
$gatewayOpenEnvButton = Add-Button $gatewayGroup 'Open ai-gateway .env' 500 95 260 48
$gatewayStatusButton = Add-Button $gatewayGroup 'Gateway status / PID' 20 165 220 40
$gatewayStopButton = Add-Button $gatewayGroup 'Stop AI Gateway safely' 260 165 220 40
$gatewayStartButton.Add_Click({ Start-Gateway })
$gatewayTestButton.Add_Click({ Test-Gateway })
$gatewayOpenEnvButton.Add_Click({
    $path = Join-Path $repoRoot 'ai-gateway\.env'
    if (Test-Path -LiteralPath $path) {
        Start-Process notepad.exe -ArgumentList (Quote-ProcessArgument $path)
    }
    else {
        Show-UiError 'ai-gateway/.env does not exist.'
    }
})
$gatewayStatusButton.Add_Click({
    Start-PowerShellWindow -Arguments @(
        '-File', $gatewayManagerScript,
        '-Action', 'Status',
        '-HostAddress', $script:gatewayHostText.Text.Trim(),
        '-Port', [string]$script:gatewayPort.Value
    ) -SuccessMessage 'AI Gateway status opened.'
})
$gatewayStopButton.Add_Click({
    if (-not (Confirm-Action 'Stop the verified Nexus AI Gateway process on this address and port?')) { return }
    Start-ElevatedPowerShellWindow -Arguments @(
        '-File', $gatewayManagerScript,
        '-Action', 'Stop',
        '-HostAddress', $script:gatewayHostText.Text.Trim(),
        '-Port', [string]$script:gatewayPort.Value,
        '-ConfirmStop'
    ) -SuccessMessage 'AI Gateway stop command opened with Administrator privileges.'
})

$gatewayInfo = Add-Label $gatewayTab 'Keep the Gateway PowerShell window open. Check Status before starting it a second time.' 25 290 780
$gatewayInfo.ForeColor = [Drawing.Color]::DarkOrange

$databaseGroup = New-Object Windows.Forms.GroupBox
$databaseGroup.Text = 'PostgreSQL and Synapse'
$databaseGroup.Location = New-Object Drawing.Point(15, 15)
$databaseGroup.Size = New-Object Drawing.Size(825, 205)
$databaseTab.Controls.Add($databaseGroup)

$backupButton = Add-Button $databaseGroup 'Create PostgreSQL backup' 20 40 235 48
$repairButton = Add-Button $databaseGroup 'Repair Synapse locale' 285 40 235 48
$restoreButton = Add-Button $databaseGroup 'Restore verified backup' 550 40 235 48
$openBackupButton = Add-Button $databaseGroup 'Open backup folders' 20 110 235 48

$backupButton.Add_Click({ Start-ServerAction 'Backup' })
$repairButton.Add_Click({
    if (Confirm-Action 'Back up and repair the Synapse database locale now?') {
        Start-ServerAction 'RepairDatabase'
    }
})
$restoreButton.Add_Click({ Restore-DatabaseBackup })
$openBackupButton.Add_Click({
    $path = Join-Path $repoRoot 'backups'
    if (-not (Test-Path -LiteralPath $path)) { New-Item -ItemType Directory -Path $path | Out-Null }
    Start-Process explorer.exe -ArgumentList (Quote-ProcessArgument $path)
})

$databaseInfo = New-Object Windows.Forms.TextBox
$databaseInfo.Multiline = $true
$databaseInfo.ReadOnly = $true
$databaseInfo.Location = New-Object Drawing.Point(15, 240)
$databaseInfo.Size = New-Object Drawing.Size(825, 180)
$databaseInfo.Text = @'
Backup:
- Creates Nexus, Synapse and PostgreSQL globals backups.
- Copies dumps to the host backup directory.

Locale repair:
- Creates a dump before changing anything.
- Keeps the old database under a timestamped name.
- Recreates Synapse with UTF8 and C/C locale.

Restore:
- Requires two confirmations.
- Verifies the backup manifest and SHA-256 before stopping services.
'@
$databaseTab.Controls.Add($databaseInfo)

$serverFirewallGroup = New-Object Windows.Forms.GroupBox
$serverFirewallGroup.Text = 'Server firewall (run on the server computer)'
$serverFirewallGroup.Location = New-Object Drawing.Point(15, 12)
$serverFirewallGroup.Size = New-Object Drawing.Size(825, 125)
$networkTab.Controls.Add($serverFirewallGroup)

[void](Add-Label $serverFirewallGroup 'Server Hamachi IP' 18 30 140)
$script:serverFirewallAddressText = Add-TextBox $serverFirewallGroup '25.49.22.166' 165 27 190
[void](Add-Label $serverFirewallGroup 'Allowed client network' 380 30 150)
$script:serverRemoteNetworkText = Add-TextBox $serverFirewallGroup '25.0.0.0/8' 535 27 170
$serverFirewallButton = Add-Button $serverFirewallGroup 'Configure server firewall' 18 70 260 38
$serverFirewallButton.Add_Click({ Configure-ServerFirewall })

$gatewayFirewallGroup = New-Object Windows.Forms.GroupBox
$gatewayFirewallGroup.Text = 'AI Gateway firewall (run on the AI computer)'
$gatewayFirewallGroup.Location = New-Object Drawing.Point(15, 145)
$gatewayFirewallGroup.Size = New-Object Drawing.Size(825, 125)
$networkTab.Controls.Add($gatewayFirewallGroup)

[void](Add-Label $gatewayFirewallGroup 'Gateway Hamachi IP' 18 30 140)
$gatewayFirewallAddressMirror = Add-TextBox $gatewayFirewallGroup '25.31.233.158' 165 27 190
$gatewayFirewallAddressMirror.Add_TextChanged({ $script:gatewayHostText.Text = $gatewayFirewallAddressMirror.Text })
[void](Add-Label $gatewayFirewallGroup 'Nexus server IP' 380 30 150)
$script:gatewayRemoteServerText = Add-TextBox $gatewayFirewallGroup '25.49.22.166' 535 27 170
$gatewayFirewallButton = Add-Button $gatewayFirewallGroup 'Configure Gateway firewall' 18 70 260 38
$firewallStatusButton = Add-Button $gatewayFirewallGroup 'Show managed rules' 295 70 220 38
$hamachiButton = Add-Button $gatewayFirewallGroup 'Open Hamachi' 535 70 220 38
$gatewayFirewallButton.Add_Click({ Configure-GatewayFirewall })
$firewallStatusButton.Add_Click({
    Start-ElevatedPowerShellWindow -Arguments @('-File', $firewallScript, '-Role', 'Status') `
        -SuccessMessage 'Firewall status opened with Administrator privileges.'
})
$hamachiButton.Add_Click({
    $hamachi = Join-Path ${env:ProgramFiles(x86)} 'LogMeIn Hamachi\hamachi-2-ui.exe'
    if (Test-Path -LiteralPath $hamachi) {
        Start-Process -FilePath $hamachi
    }
    else {
        Show-UiError 'LogMeIn Hamachi was not found in the default installation path.'
    }
})

$clientGroup = New-Object Windows.Forms.GroupBox
$clientGroup.Text = 'External client access'
$clientGroup.Location = New-Object Drawing.Point(15, 280)
$clientGroup.Size = New-Object Drawing.Size(825, 180)
$networkTab.Controls.Add($clientGroup)

[void](Add-Label $clientGroup 'Nexus URL' 18 32 100)
$script:clientUrlText = Add-TextBox $clientGroup 'https://25.49.22.166:8443' 120 29 370
$refreshUrlButton = Add-Button $clientGroup 'Refresh from .env' 510 26 180 32
$openNexusButton = Add-Button $clientGroup 'Open Nexus' 18 80 180 42
$copyUrlButton = Add-Button $clientGroup 'Copy URL' 215 80 180 42
$testClientButton = Add-Button $clientGroup 'Test client access' 412 80 180 42
$exportClientButton = Add-Button $clientGroup 'Export client package' 609 80 180 42

$refreshUrlButton.Add_Click({ $script:clientUrlText.Text = Resolve-PublicUrl })
$openNexusButton.Add_Click({ Start-Process $script:clientUrlText.Text.Trim() })
$copyUrlButton.Add_Click({
    [Windows.Forms.Clipboard]::SetText($script:clientUrlText.Text.Trim())
    $script:statusLabel.Text = 'Nexus URL copied to clipboard.'
})
$testClientButton.Add_Click({
    Start-PowerShellWindow -Arguments @(
        '-File', $clientTestScript,
        '-PublicUrl', $script:clientUrlText.Text.Trim()
    ) -SuccessMessage 'Client access test started.'
})
$exportClientButton.Add_Click({ Export-ClientPackage })

$script:configSelector = New-Object Windows.Forms.ComboBox
$script:configSelector.DropDownStyle = [Windows.Forms.ComboBoxStyle]::DropDownList
$script:configSelector.Items.Add('Server .env') | Out-Null
$script:configSelector.Items.Add('AI Gateway .env') | Out-Null
$script:configSelector.SelectedIndex = 0
$script:configSelector.Location = New-Object Drawing.Point(15, 15)
$script:configSelector.Size = New-Object Drawing.Size(210, 28)
$configTab.Controls.Add($script:configSelector)

$loadConfigButton = Add-Button $configTab 'Load sensitive config' 240 12 190 34
$saveConfigButton = Add-Button $configTab 'Validate + save backup' 445 12 210 34
$clearConfigButton = Add-Button $configTab 'Clear editor' 670 12 155 34

$script:configPathLabel = Add-Label $configTab 'Select a file and click Load.' 15 55 810
$script:configPathLabel.ForeColor = [Drawing.Color]::DimGray

$script:configEditor = New-Object Windows.Forms.TextBox
$script:configEditor.Multiline = $true
$script:configEditor.AcceptsReturn = $true
$script:configEditor.AcceptsTab = $true
$script:configEditor.ScrollBars = [Windows.Forms.ScrollBars]::Both
$script:configEditor.WordWrap = $false
$script:configEditor.Font = New-Object Drawing.Font('Consolas', 9)
$script:configEditor.Location = New-Object Drawing.Point(15, 82)
$script:configEditor.Size = New-Object Drawing.Size(810, 330)
$configTab.Controls.Add($script:configEditor)

$configWarning = Add-Label $configTab 'WARNING: This editor can display real passwords and API keys. Do not share screenshots.' 15 425 800
$configWarning.ForeColor = [Drawing.Color]::DarkRed
$loadConfigButton.Add_Click({
    if (Confirm-Action 'Load a sensitive configuration file into the editor? Values will be visible on screen.') {
        Load-ConfigEditor
    }
})
$saveConfigButton.Add_Click({ Save-ConfigEditor })
$clearConfigButton.Add_Click({
    $script:configEditor.Clear()
    $script:configPathLabel.Text = 'Editor cleared; no file was changed.'
})
$script:configSelector.Add_SelectedIndexChanged({
    $script:configEditor.Clear()
    $script:configPathLabel.Text = 'Selection changed. Click Load to display sensitive values.'
})

$helpText = New-Object Windows.Forms.TextBox
$helpText.Multiline = $true
$helpText.ReadOnly = $true
$helpText.ScrollBars = [Windows.Forms.ScrollBars]::Vertical
$helpText.Location = New-Object Drawing.Point(15, 15)
$helpText.Size = New-Object Drawing.Size(825, 390)
$helpText.Font = New-Object Drawing.Font('Consolas', 10)
$helpText.Text = @'
First installation:
1. Clone the repository.
2. Open Nexus-Server-Manager.cmd.
3. Fill new server settings and the AI Gateway key.
4. Click "Initialize new server".

Routine operation:
- "Safe update" preserves tracked local changes in Git stash, pulls and deploys.
- "Deploy current code" builds, repairs databases, migrates and starts.
- "Start stack" starts existing containers without rebuilding.
- "Diagnose" prints service states and recent logs.

Database:
- Create verified PostgreSQL backups.
- Repair Synapse locale with an automatic dump and retained old database.
- Restore a manifest-verified backup with two confirmations.

Network & Client:
- Configure role-specific Windows Firewall rules with UAC.
- Test the public Nexus URL.
- Export the Caddy root certificate and client installation instructions.

Safety:
- Existing .env is never overwritten by Initialize.
- Database locale repair creates a dump and keeps the old database.
- No action uses docker compose down -v.
- Real secrets must stay out of Git.
'@
$helpTab.Controls.Add($helpText)

$quickstartButton = Add-Button $helpTab 'Open quickstart' 15 420 190 42
$composeButton = Add-Button $helpTab 'Open docker-compose.yml' 215 420 190 42
$caddyButton = Add-Button $helpTab 'Open Caddyfile' 415 420 190 42
$readmeButton = Add-Button $helpTab 'Open README' 615 420 190 42
$quickstartButton.Add_Click({
    if (Test-Path -LiteralPath $quickstartPath) {
        Start-Process notepad.exe -ArgumentList (Quote-ProcessArgument $quickstartPath)
    }
})
$composeButton.Add_Click({
    Start-Process notepad.exe -ArgumentList (Quote-ProcessArgument (Join-Path $repoRoot 'docker-compose.yml'))
})
$caddyButton.Add_Click({
    Start-Process notepad.exe -ArgumentList (Quote-ProcessArgument (Join-Path $repoRoot 'docker\reverse-proxy\Caddyfile'))
})
$readmeButton.Add_Click({
    Start-Process notepad.exe -ArgumentList (Quote-ProcessArgument (Join-Path $repoRoot 'README.md'))
})

$script:statusLabel = New-Object Windows.Forms.Label
$script:statusLabel.Text = 'Ready. Actions open in a separate PowerShell window so logs remain visible.'
$script:statusLabel.Location = New-Object Drawing.Point(22, 610)
$script:statusLabel.Size = New-Object Drawing.Size(870, 30)
$script:statusLabel.BorderStyle = [Windows.Forms.BorderStyle]::Fixed3D
$script:statusLabel.Padding = New-Object Windows.Forms.Padding(8, 5, 0, 0)
$form.Controls.Add($script:statusLabel)

if ($ValidateOnly) {
    $script:configSelector.SelectedIndex = 0
    Assert-ConfigEditorContent @'
POSTGRES_USER=nexus
POSTGRES_PASSWORD=validation-secret
POSTGRES_DB=nexus
SYNAPSE_POSTGRES_USER=synapse
SYNAPSE_POSTGRES_PASSWORD=validation-secret
SYNAPSE_POSTGRES_DB=synapse
NEXUS_DOMAIN=25.49.22.166
MATRIX_SERVER_NAME=25.49.22.166
OLLAMA_BASE_URL=http://25.31.233.158:8090
OLLAMA_API_KEY=validation-key
'@
    $script:configSelector.SelectedIndex = 1
    Assert-ConfigEditorContent @'
AI_GATEWAY_API_KEY=validation-key
AI_GATEWAY_ALLOWED_NETWORKS=25.49.22.166/32
OLLAMA_BASE_URL=http://127.0.0.1:11434
'@
    $placeholderRejected = $false
    try {
        Assert-ConfigEditorContent @'
AI_GATEWAY_API_KEY=<AI_GATEWAY_API_KEY>
AI_GATEWAY_ALLOWED_NETWORKS=25.49.22.166/32
OLLAMA_BASE_URL=http://127.0.0.1:11434
'@
    }
    catch {
        $placeholderRejected = $true
    }
    if (-not $placeholderRejected) {
        throw 'Config editor validation accepted a placeholder unexpectedly.'
    }
    Write-Output 'Nexus Server Manager UI construction and config validation: OK'
    $form.Dispose()
    exit 0
}

[void]$form.ShowDialog()
