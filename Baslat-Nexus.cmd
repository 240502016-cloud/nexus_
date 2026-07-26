@echo off
REM Nexus'u tek tikla baslatir: Docker Desktop + tum konteynerler + tarayici.
REM Bu dosyaya cift tiklamaniz yeterli.
title Nexus Baslatici
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-nexus.ps1"
echo.
echo Bu pencereyi kapatabilirsiniz.
pause
