@echo off
rem ---------------------------------------------------------------------------
rem  Spoustec aplikace pro Windows.
rem
rem  Pripravi virtualni prostredi, doinstaluje potrebne knihovny a spusti report.
rem  Doptava se jen na to, co nebylo zadano na prikazove radce.
rem
rem  Priklady:
rem      spustit-windows.bat
rem      spustit-windows.bat --month=202608
rem      spustit-windows.bat ReportHistory-498754.xlsx --day=last --format=png
rem ---------------------------------------------------------------------------
setlocal enabledelayedexpansion
chcp 65001 >nul

cd /d "%~dp0"
rem Konzole bezi v UTF-8 (chcp 65001), proto v nem musi vypisovat i Python
set "PYTHONIOENCODING=utf-8"
set "VENV_DIR=%~dp0.venv"
set "PYTHON=%VENV_DIR%\Scripts\python.exe"
set "STAMP=%VENV_DIR%\.requirements.stamp"
rem Docasny soubor pro predani vystupu z pomocnych prikazu
set "TMPOUT=%TEMP%\forexreport-%RANDOM%%RANDOM%.txt"
set "NAVRAT=0"

echo Forex Report - Windows
echo.

rem === priprava prostredi ====================================================
call :najdi_python || goto :konec
call :priprav_venv || goto :konec
call :nainstaluj_knihovny || goto :konec

rem === zjisteni, co uzivatel uz zadal ========================================
rem Na co se zeptal sam, na to uz se neptame; doplnime jen chybejici udaje
set "MA_SOUBOR="
set "MA_OBDOBI="
set "MA_FORMAT="
set "PREDCHOZI="
for %%A in (%*) do (
    set "ARG=%%~A"
    call :rozpoznej_argument
    set "PREDCHOZI=!ARG!"
)

set "SOUBOR="
set "OBDOBI="
set "FORMAT="
if not defined MA_SOUBOR call :zeptej_se_na_soubor || goto :konec
if not defined MA_OBDOBI call :zeptej_se_na_obdobi
if not defined MA_FORMAT call :zeptej_se_na_format

rem === spusteni ==============================================================
echo.
echo Pripravuji report ...
rem Prepinac --print-path vypise na vystup pouze cestu k vytvorenemu souboru;
rem pripadne chyby jdou na chybovy vystup primo do okna
"%PYTHON%" report.py %* !SOUBOR! !OBDOBI! !FORMAT! --print-path > "%TMPOUT%"
set "NAVRAT=%ERRORLEVEL%"

set "VYSTUP="
if exist "%TMPOUT%" set /p VYSTUP=<"%TMPOUT%"
del "%TMPOUT%" >nul 2>&1

if not "%NAVRAT%"=="0" goto :konec
if not defined VYSTUP (
    echo Report se nepodarilo vytvorit.
    set "NAVRAT=1"
    goto :konec
)

echo Report ulozen: !VYSTUP!
if exist "!VYSTUP!" start "" "!VYSTUP!"
goto :konec


rem ===========================================================================
rem  Podprogramy
rem ===========================================================================

:najdi_python
rem Hleda Python 3.10 nebo novejsi, nejprve pres Python Launcher
set "PY_LAUNCHER="
where py >nul 2>&1 && set "PY_LAUNCHER=py -3"
if not defined PY_LAUNCHER (
    where python >nul 2>&1 && set "PY_LAUNCHER=python"
)
if not defined PY_LAUNCHER (
    echo Chyba: Nenasel jsem Python.
    echo Nainstalujte Python 3.10 nebo novejsi z https://www.python.org/downloads/
    echo Pri instalaci zaskrtnete volbu "Add python.exe to PATH".
    set "NAVRAT=1"
    exit /b 1
)
%PY_LAUNCHER% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo Chyba: Nalezeny Python je starsi nez 3.10.
    echo Nainstalujte novejsi verzi z https://www.python.org/downloads/
    set "NAVRAT=1"
    exit /b 1
)
exit /b 0

:priprav_venv
rem Vytvori virtualni prostredi, pokud jeste neexistuje
if not exist "%PYTHON%" (
    echo Vytvarim virtualni prostredi v .venv ...
    %PY_LAUNCHER% -m venv "%VENV_DIR%"
)
if not exist "%PYTHON%" (
    echo Chyba: Nepodarilo se vytvorit virtualni prostredi.
    set "NAVRAT=1"
    exit /b 1
)
exit /b 0

:nainstaluj_knihovny
rem Instaluje zavislosti, jen kdyz se zmenil requirements.txt.
rem Otisk predavame pres docasny soubor; "for /f" s prikazem v uvozovkach
rem cmd nespolehlive rozdeluje na slova
%PY_LAUNCHER% -c "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest())" > "%TMPOUT%" 2>nul
set "REQ_HASH="
if exist "%TMPOUT%" set /p REQ_HASH=<"%TMPOUT%"
del "%TMPOUT%" >nul 2>&1

set "OLD_HASH="
if exist "%STAMP%" set /p OLD_HASH=<"%STAMP%"
if "%REQ_HASH%"=="%OLD_HASH%" exit /b 0

echo Instaluji potrebne knihovny ...
rem Aktualizace pipu je jen prijemnost, pripadne selhani neni chyba
"%PYTHON%" -m pip install --quiet --disable-pip-version-check --upgrade pip >nul 2>&1
"%PYTHON%" -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo Chyba: Instalace knihoven se nezdarila. Zkontrolujte pripojeni k internetu.
    set "NAVRAT=1"
    exit /b 1
)
>"%STAMP%" echo %REQ_HASH%
echo Knihovny jsou pripravene.
echo.
exit /b 0

:rozpoznej_argument
rem Podle jednoho argumentu urci, ktery udaj uz uzivatel zadal
if /i "!ARG:~-5!"==".xlsx" set "MA_SOUBOR=1"
if /i "!ARG:~-5!"==".xlsm" set "MA_SOUBOR=1"
rem Obdobi - prepinacem i zapisem bez pomlcek
if /i "!ARG!"=="--all" set "MA_OBDOBI=1"
if /i "!ARG!"=="all" set "MA_OBDOBI=1"
if /i "!ARG!"=="--year" set "MA_OBDOBI=1"
if /i "!ARG!"=="--month" set "MA_OBDOBI=1"
if /i "!ARG!"=="--week" set "MA_OBDOBI=1"
if /i "!ARG!"=="--day" set "MA_OBDOBI=1"
if /i "!ARG:~0,7!"=="--year=" set "MA_OBDOBI=1"
if /i "!ARG:~0,8!"=="--month=" set "MA_OBDOBI=1"
if /i "!ARG:~0,7!"=="--week=" set "MA_OBDOBI=1"
if /i "!ARG:~0,6!"=="--day=" set "MA_OBDOBI=1"
if /i "!ARG:~0,5!"=="year=" set "MA_OBDOBI=1"
if /i "!ARG:~0,6!"=="month=" set "MA_OBDOBI=1"
if /i "!ARG:~0,5!"=="week=" set "MA_OBDOBI=1"
if /i "!ARG:~0,4!"=="day=" set "MA_OBDOBI=1"
rem Format - prepinacem, nebo koncovkou vystupniho souboru
if /i "!ARG!"=="-f" set "MA_FORMAT=1"
if /i "!ARG!"=="--format" set "MA_FORMAT=1"
if /i "!ARG:~0,9!"=="--format=" set "MA_FORMAT=1"
if /i "!ARG:~-4!"==".png" set "MA_FORMAT=1"
if /i "!PREDCHOZI!"=="-o" if /i "!ARG:~-4!"==".pdf" set "MA_FORMAT=1"
if /i "!PREDCHOZI!"=="--output" if /i "!ARG:~-4!"==".pdf" set "MA_FORMAT=1"
goto :eof

:zeptej_se_na_soubor
rem Pri jedinem nalezenem sesitu se neptame a pouzijeme ho rovnou
set /a POCET=0
for %%F in ("%~dp0*.xlsx") do (
    set /a POCET+=1
    set "SOUBOR_!POCET!=%%~nxF"
)
if %POCET%==0 (
    echo Chyba: V adresari neni zadny soubor .xlsx.
    echo Zkopirujte sem export ReportHistory-*.xlsx z MetaTraderu 5.
    set "NAVRAT=2"
    exit /b 2
)
if %POCET%==1 (
    set "SOUBOR=!SOUBOR_1!"
    echo Vstupni soubor: !SOUBOR_1!
) else (
    echo Vyberte vstupni soubor:
    for /l %%I in (1,1,%POCET%) do echo   %%I^) !SOUBOR_%%I!
    set /p VOLBA_S="Cislo [1]: "
    if "!VOLBA_S!"=="" set "VOLBA_S=1"
    for %%I in (!VOLBA_S!) do set "SOUBOR=!SOUBOR_%%I!"
    if "!SOUBOR!"=="" set "SOUBOR=!SOUBOR_1!"
)
rem Nazev souboru muze obsahovat mezery, proto ho predavame v uvozovkach
set SOUBOR="!SOUBOR!"
exit /b 0

:zeptej_se_na_obdobi
echo.
echo Vyberte obdobi reportu:
echo   1^) --all         cele obdobi
echo   2^) --year=last   posledni rok
echo   3^) --month=last  posledni mesic
echo   4^) --week=last   posledni tyden
echo   5^) --day=last    posledni den
echo   6^) vlastni zadani ^(napr. --month=202608^)
set /p VOLBA_O="Cislo [1]: "
if "!VOLBA_O!"=="" set "VOLBA_O=1"
set "OBDOBI=--all"
if "!VOLBA_O!"=="2" set "OBDOBI=--year=last"
if "!VOLBA_O!"=="3" set "OBDOBI=--month=last"
if "!VOLBA_O!"=="4" set "OBDOBI=--week=last"
if "!VOLBA_O!"=="5" set "OBDOBI=--day=last"
if "!VOLBA_O!"=="6" set /p OBDOBI="Zadejte obdobi: "
rem Vlastni zadani muze obsahovat mezery, proto uvozovky
set OBDOBI="!OBDOBI!"
goto :eof

:zeptej_se_na_format
echo.
echo Vyberte format vystupu:
echo   1^) PDF
echo   2^) PNG   jeden dlouhy obrazek
echo   3^) oboji
set /p VOLBA_F="Cislo [1]: "
if "!VOLBA_F!"=="" set "VOLBA_F=1"
set "FORMAT=--format=pdf"
if "!VOLBA_F!"=="2" set "FORMAT=--format=png"
if "!VOLBA_F!"=="3" set "FORMAT=--format=both"
goto :eof

:konec
if exist "%TMPOUT%" del "%TMPOUT%" >nul 2>&1
echo.
if "%~1"=="" pause
endlocal & exit /b %NAVRAT%
