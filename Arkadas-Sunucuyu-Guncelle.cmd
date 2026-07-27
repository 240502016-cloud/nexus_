@echo off
setlocal
title Nexus - Cekingen Branch Guncelleme
cd /d "%~dp0"

echo.
echo ============================================================
echo  Nexus sunucusu origin/cekingen dalindan guncellenecek.
echo  Yerel degisiklikler varsa Git stash icinde korunacak.
echo  Veritabani volume'lari SILINMEYECEK.
echo ============================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\nexus-server.ps1" -Action Update -GitBranch cekingen
if errorlevel 1 (
  echo.
  echo Guncelleme tamamlanamadi. Yukaridaki hata mesajini kontrol edin.
  echo Yerel degisiklikler stash'e alindiysa otomatik olarak geri uygulanmamistir.
  pause
  exit /b 1
)

echo.
echo Nexus basariyla guncellendi ve servisler yeniden yayinlandi.
pause
endlocal
