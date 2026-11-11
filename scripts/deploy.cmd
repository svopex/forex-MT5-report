@echo off
rem ---------------------------------------------------------------------------
rem  Instalace a kompilace MQL5 skriptu projektu (mql5\*.mq5) do vsech
rem  nainstalovanych MetaTrader 5. Vlastni logika je v deploy.ps1; tento soubor
rem  ho jen spusti s obejitim ExecutionPolicy a vrati jeho navratovy kod.
rem ---------------------------------------------------------------------------
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy.ps1" %*
exit /b %ERRORLEVEL%
