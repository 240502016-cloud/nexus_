@echo off
setlocal
title Nexus Yerel Insan Test Ortami
cd /d "%~dp0"

echo.
echo ============================================================
echo  Nexus yerel test ortami baslatiliyor.
echo  Git push/deploy yapilmaz; production verileri kullanilmaz.
echo ============================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-local-dev.ps1" -Open
if errorlevel 1 (
  echo.
  echo Baslatma tamamlanamadi. Yukaridaki hata mesajini kontrol edin.
  pause
  exit /b 1
)

echo.
echo Arayuz: http://localhost:5173
echo Bu pencereyi kapatabilirsiniz; Docker servisleri calismaya devam eder.
pause
endlocal
