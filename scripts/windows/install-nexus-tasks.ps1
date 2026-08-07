<#
.SYNOPSIS
    Nexus'un geliştirici makinesindeki zamanlanmış görevlerini kurar veya kaldırır.

.DESCRIPTION
    Üç görev kurar:

      Nexus - AI Gateway        oturum açılışında gateway'i başlatır (DEVIR §9'daki
                                "her yeniden başlatmada elle açılması gerekiyor" eksiği)
      Nexus - Saglik izleme     15 dakikada bir siteyi dışarıdan yoklar, durum değişince
                                bildirim gösterir
      Nexus - Yedek cekme       sunucudaki yedeklerin kopyasını günlük indirir

    Görevler yalnız kullanıcı oturum açtığında çalışır: gateway kullanıcının Ollama'sına
    erişmeli ve izleme bildirimi görünür bir masaüstü gerektirir.

    Tekrar çalıştırmak güvenlidir; var olan görevleri günceller.

.PARAMETER Remove
    Görevleri kurmak yerine kaldırır.

.EXAMPLE
    .\scripts\windows\install-nexus-tasks.ps1
.EXAMPLE
    .\scripts\windows\install-nexus-tasks.ps1 -Remove
#>
[CmdletBinding()]
param(
    [string]$GatewayHostAddress = '100.104.192.122',
    [int]$GatewayPort = 8090,
    [ValidateRange(1, 1440)]
    [int]$HealthCheckMinutes = 15,
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

$tasks = @(
    @{ Name = 'Nexus - AI Gateway';    Description = 'Oturum acilisinda AI Gateway servisini baslatir.' }
    @{ Name = 'Nexus - Saglik izleme'; Description = 'Nexus sitesini disaridan yoklar, durum degisince bildirir.' }
    @{ Name = 'Nexus - Yedek cekme';   Description = 'Sunucudaki PostgreSQL yedeklerini bu makineye indirir.' }
)

$startupShortcut = Join-Path ([Environment]::GetFolderPath('Startup')) 'Nexus AI Gateway.lnk'

if ($Remove) {
    foreach ($task in $tasks) {
        if (Get-ScheduledTask -TaskName $task.Name -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $task.Name -Confirm:$false
            Write-Host "kaldirildi: $($task.Name)"
        }
    }
    if (Test-Path -LiteralPath $startupShortcut) {
        Remove-Item -LiteralPath $startupShortcut -Force
        Write-Host 'kaldirildi: Nexus AI Gateway baslangic kisayolu'
    }
    return
}

function Register-NexusTask {
    param(
        [string]$Name,
        [string]$Description,
        [string]$ScriptPath,
        [string]$Arguments,
        $Trigger,
        [switch]$Hidden,
        [switch]$RestartOnFailure
    )
    if (-not (Test-Path -LiteralPath $ScriptPath)) { throw "Script bulunamadi: $ScriptPath" }

    # -ExecutionPolicy Bypass: script'ler imzasiz ve makinenin politikasi bilinmiyor.
    # -NoProfile: kullanici profili yuklenmesin, acilis hizlansin ve profil hatalari etkilemesin.
    # -File tercih edilir: -Command bicimi ic ice tirnak gerektirir ve yol/arguman
    # kombinasyonlarinda kolayca bozulur.
    $argumentList = "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""
    if ($Arguments) { $argumentList += " $Arguments" }

    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argumentList -WorkingDirectory $repoRoot

    # RestartInterval/RestartCount nesneye sonradan atanirsa Task Scheduler bozuk XML
    # uretir ("hatali bicimlendirilmis veya aralik disi deger"); cmdlet parametresi olarak
    # verilmeleri gerekir.
    $settingsArgs = @{
        AllowStartIfOnBatteries    = $true
        DontStopIfGoingOnBatteries = $true
        StartWhenAvailable         = $true
        MultipleInstances          = 'IgnoreNew'
    }
    if ($RestartOnFailure) {
        # Gateway cokerse kendiliginden geri gelsin.
        $settingsArgs.RestartInterval = (New-TimeSpan -Minutes 2)
        $settingsArgs.RestartCount = 5
    }
    $settings = New-ScheduledTaskSettingsSet @settingsArgs
    if ($Hidden) { $settings.Hidden = $true }
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

    if (Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false
    }
    Register-ScheduledTask -TaskName $Name -Description $Description -Action $action -Trigger $Trigger -Settings $settings -Principal $principal | Out-Null
    Write-Host "kuruldu: $Name"
}

# AI Gateway zamanlanmis gorev degil, Baslangic klasoru kisayolu olarak kurulur.
# Sebep: oturum acilisi (AtLogOn) tetikleyicisi olan bir gorev kaydetmek yonetici hakki
# ister ve bu makinede "Erisim engellendi" doner. Baslangic klasoru ayni isi yonetici
# hakki olmadan yapar.
$gatewayScript = Join-Path $repoRoot 'ai-gateway\start-gateway.ps1'
if (-not (Test-Path -LiteralPath $gatewayScript)) { throw "Gateway script bulunamadi: $gatewayScript" }
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Startup')) 'Nexus AI Gateway.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = (Get-Command powershell.exe).Source
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$gatewayScript`" -HostAddress $GatewayHostAddress -Port $GatewayPort"
$shortcut.WorkingDirectory = (Join-Path $repoRoot 'ai-gateway')
$shortcut.Description = 'Nexus AI Gateway (oturum acilisinda baslar)'
$shortcut.WindowStyle = 7  # simge durumunda
$shortcut.Save()
Write-Host "kuruldu: Nexus AI Gateway (Baslangic klasoru kisayolu)"

# Durum ve log yollari kurulum aninda mutlak olarak sabitlenir. Zamanlanmis gorevin
# ortam degiskenleri (ozellikle LOCALAPPDATA) bu oturumdakiyle ayni olmayabilir; yol
# script icinde $env: uzerinden kurulursa gorev sessizce baska bir dosyaya yazar.
$monitorDir = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'nexus-monitor'
New-Item -ItemType Directory -Force -Path $monitorDir | Out-Null

Register-NexusTask -Name 'Nexus - Saglik izleme' `
    -Description $tasks[1].Description `
    -ScriptPath (Join-Path $repoRoot 'scripts\windows\check-nexus-health.ps1') `
    -Arguments ("-Notify -StateFile `"{0}`" -LogFile `"{1}`"" -f (Join-Path $monitorDir 'state.json'), (Join-Path $monitorDir 'health.log')) `
    -Trigger (New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $HealthCheckMinutes)) `
    -Hidden

Register-NexusTask -Name 'Nexus - Yedek cekme' `
    -Description $tasks[2].Description `
    -ScriptPath (Join-Path $repoRoot 'scripts\pull-server-backups.ps1') `
    -Trigger (New-ScheduledTaskTrigger -Daily -At '09:00') `
    -Hidden

Write-Host ''
Write-Host 'Kurulu Nexus gorevleri:'
Get-ScheduledTask -TaskName 'Nexus - *' | Select-Object TaskName, State | Format-Table -AutoSize
