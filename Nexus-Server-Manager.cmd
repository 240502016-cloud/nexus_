@echo off
setlocal
set "NEXUS_ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File "%NEXUS_ROOT%scripts\nexus-server-ui.ps1"
if errorlevel 1 (
  echo.
  echo Nexus Server Manager could not be opened.
  pause
)
endlocal
