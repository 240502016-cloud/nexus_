@echo off
REM Nexus konteynerlerini durdurur (veriler korunur; volume'lar silinmez).
title Nexus Durduruluyor
cd /d "%~dp0"
echo Nexus konteynerleri durduruluyor...
powershell -NoProfile -ExecutionPolicy Bypass -Command "docker compose stop"
echo.
echo Durduruldu. Yeniden baslatmak icin Baslat-Nexus.cmd dosyasini calistirin.
pause
