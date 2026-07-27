@echo off
setlocal
title Nexus - Ucretsiz Public Tunnel Ayari
cd /d "%~dp0"

echo.
echo ============================================================
echo  Cloudflare Tunnel tokeni gizli olarak kaydedilecek.
echo  Tokeni kimseyle ve ekran goruntulerinde paylasmayin.
echo ============================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\configure-public-tunnel.ps1"
if errorlevel 1 (
  echo.
  echo Tunnel ayari tamamlanamadi. Yukaridaki mesaji kontrol edin.
  pause
  exit /b 1
)

echo.
pause
endlocal
