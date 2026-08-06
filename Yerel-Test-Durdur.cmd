@echo off
setlocal
title Nexus Yerel Test Ortami Durduruluyor
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-local-dev.ps1"
if errorlevel 1 (
  echo.
  echo Durdurma tamamlanamadi. Yukaridaki hata mesajini kontrol edin.
  pause
  exit /b 1
)

echo.
echo Yerel veriler korundu. Yeniden baslatmak icin Yerel-Test-Baslat.cmd dosyasini calistirin.
pause
endlocal
