@echo off
setlocal
cd /d "%~dp0"
echo Nexus kurulum hazirlik kontrolu baslatiliyor...
echo Bu kontrol servisleri veya verileri degistirmez.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\nexus-server.ps1" -Action SetupCheck
echo.
pause
endlocal
