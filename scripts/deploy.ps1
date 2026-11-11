# ---------------------------------------------------------------------------
# Instalace a kompilace MQL5 skriptů projektu do všech nainstalovaných MetaTrader 5.
#
# Najde všechny terminály, které mají MetaEditor a datový adresář, do každého
# zkopíruje mql5\*.mq5 do <data>\MQL5\Scripts\ a skripty tam přeloží.
# Výchozí hodnotu vstupu InpOutputDir přitom nastaví na adresář projektu,
# aby skripty ukládaly výstupy (ReportHistory-*.csv) přímo sem.
# Úspěšná kompilace končí v logu řádkem "Result: 0 errors, ...".
#
# Návratový kód: 0 = vše nasazeno, 1 = žádný terminál nebo chyba kopírování či kompilace.
#
# Spuštění:  scripts\deploy.cmd
# ---------------------------------------------------------------------------
$ErrorActionPreference = 'Stop'

# Zdrojové soubory projektu (adresář mql5 vedle adresáře scripts)
$projectDir = Split-Path $PSScriptRoot -Parent
$sourceDir = Join-Path $projectDir 'mql5'
$sources = @(Get-ChildItem -Path $sourceDir -Filter '*.mq5' -File -ErrorAction SilentlyContinue)
if ($sources.Count -eq 0) {
    Write-Host "Chyba: v $sourceDir neni zadny soubor .mq5." -ForegroundColor Red
    exit 1
}

# Obsah nasazovaných souborů: řádek "input string InpOutputDir = "...";" dostane
# jako výchozí hodnotu adresář projektu. Cesta jde do řetězcového literálu MQL5,
# proto se zdvojí zpětná lomítka. Zapisuje se v UTF-8 s BOM kvůli češtině.
$outputDirLiteral = $projectDir.Replace('\', '\\')
$outputDirPattern = '(?m)^(\s*input\s+string\s+InpOutputDir\s*=\s*)"[^"]*"'
$utf8Bom = New-Object System.Text.UTF8Encoding $true
$deployItems = foreach ($source in $sources) {
    $content = [IO.File]::ReadAllText($source.FullName)
    # Skript, který InpOutputDir používá, ale regex jeho deklaraci nenajde (jiný zápis,
    # sinput...), by potichu zapisoval jen do MQL5\Files – to je chyba nasazení
    if ($content.Contains('InpOutputDir') -and -not [regex]::IsMatch($content, $outputDirPattern)) {
        Write-Host "Chyba: v $($source.Name) chybi radek input string InpOutputDir = `"...`";" -ForegroundColor Red
        exit 1
    }
    $content = [regex]::Replace($content, $outputDirPattern, { param($m) $m.Groups[1].Value + '"' + $outputDirLiteral + '"' })
    [pscustomobject]@{ Name = $source.Name; Content = $content }
}
Write-Host "Vystupni adresar skriptu (InpOutputDir): $projectDir"

# Vytvoří popis terminálu.
# Parametry: $name - zobrazovaný název, $installDir - adresář s MetaEditor64.exe,
# $dataDir - datový adresář terminálu (obsahuje MQL5).
function New-Terminal([string]$name, [string]$installDir, [string]$dataDir) {
    [pscustomobject]@{
        Name       = $name
        DataDir    = $dataDir
        MetaEditor = Join-Path $installDir 'MetaEditor64.exe'
        Mql5Dir    = Join-Path $dataDir 'MQL5'
    }
}

# Vrátí terminály MT5, do kterých lze nasadit, seřazené podle názvu.
# Běžná instalace má data v %APPDATA%\MetaQuotes\Terminal\<hash>, kde origin.txt
# obsahuje cestu k instalaci; přenosná instalace (/portable) má MQL5 přímo
# v instalačním adresáři.
function Find-Terminals {
    # Běžné instalace podle origin.txt (soubor je v UTF-16, Get-Content to pozná podle BOM)
    $terminalsRoot = Join-Path $env:APPDATA 'MetaQuotes\Terminal'
    $candidates = @(foreach ($dir in @(Get-ChildItem -Path $terminalsRoot -Directory -ErrorAction SilentlyContinue)) {
        $originFile = Join-Path $dir.FullName 'origin.txt'
        if (Test-Path $originFile) {
            $installDir = (Get-Content -Path $originFile -Raw).Trim()
            New-Terminal (Split-Path $installDir -Leaf) $installDir $dir.FullName
        }
    })

    # Přenosné instalace v Program Files: datový adresář je zároveň instalační
    $programDirs = @($env:ProgramFiles, ${env:ProgramFiles(x86)}) | Where-Object { $_ }
    $candidates += @(foreach ($dir in @(Get-ChildItem -Path $programDirs -Directory -ErrorAction SilentlyContinue)) {
        if ((Test-Path (Join-Path $dir.FullName 'terminal64.exe')) -and (Test-Path (Join-Path $dir.FullName 'MQL5'))) {
            New-Terminal $dir.Name $dir.FullName $dir.FullName
        }
    })

    # Terminál bez MetaEditoru nebo bez adresáře MQL5 (např. odinstalovaný – zůstal
    # po něm jen datový adresář) vynecháme s upozorněním
    foreach ($terminal in $candidates | Sort-Object Name) {
        if ((Test-Path $terminal.MetaEditor) -and (Test-Path $terminal.Mql5Dir)) {
            $terminal
        } else {
            Write-Host "Preskakuji $($terminal.Name): chybi MetaEditor64.exe nebo adresar MQL5." -ForegroundColor Yellow
        }
    }
}

# Přeloží jeden .mq5 soubor MetaEditorem daného terminálu a vypíše řádek "Result: ...".
# Parametry: $metaEditor - cesta k MetaEditor64.exe, $sourceFile - nasazený .mq5,
# $mql5Dir - adresář MQL5 terminálu (pro include). Vrací $true při 0 chybách.
function Invoke-Compile([string]$metaEditor, [string]$sourceFile, [string]$mql5Dir) {
    $logFile = Join-Path $env:TEMP ("deploy-{0}.log" -f [guid]::NewGuid().ToString('N'))

    # MetaEditor je okenní aplikace – bez -Wait by PowerShell nečekal na konec kompilace.
    # Návratový kód MetaEditoru není spolehlivý, výsledek se proto čte z logu.
    $arguments = @("/compile:`"$sourceFile`"", "/inc:`"$mql5Dir`"", "/log:`"$logFile`"")
    Start-Process -FilePath $metaEditor -ArgumentList $arguments -Wait -WindowStyle Hidden

    if (-not (Test-Path $logFile)) {
        Write-Host "    Chyba: MetaEditor nevytvoril log kompilace." -ForegroundColor Red
        return $false
    }
    try {
        # Log je v UTF-16 LE; souhrnný řádek vypadá např. takto:
        # "Result: 0 errors, 0 warnings, 61 msec elapsed, cpu='X64 Regular'"
        $result = Select-String -Path $logFile -Encoding Unicode -Pattern '^Result:\s*(\d+)\s+error' | Select-Object -Last 1
        if (-not $result) {
            Write-Host "    Chyba: v logu kompilace chybi radek Result." -ForegroundColor Red
            Get-Content -Path $logFile -Encoding Unicode | ForEach-Object { Write-Host "    $_" }
            return $false
        }

        # Při chybách vypíšeme i jednotlivé chybové řádky logu
        $errorCount = [int]$result.Matches[0].Groups[1].Value
        if ($errorCount -gt 0) {
            Write-Host "    $($result.Line)" -ForegroundColor Red
            Select-String -Path $logFile -Encoding Unicode -Pattern ':\s*error\s' |
                ForEach-Object { Write-Host "    $($_.Line)" -ForegroundColor Red }
            return $false
        }
        Write-Host "    $($result.Line)" -ForegroundColor Green
        return $true
    } finally {
        Remove-Item -Path $logFile -Force -ErrorAction SilentlyContinue
    }
}

$terminals = @(Find-Terminals)
if ($terminals.Count -eq 0) {
    Write-Host "Chyba: nenasel jsem zadny nainstalovany MetaTrader 5." -ForegroundColor Red
    exit 1
}

$deployed = 0
$failed = 0
foreach ($terminal in $terminals) {
    Write-Host ""
    Write-Host "== $($terminal.Name)" -ForegroundColor Cyan
    Write-Host "   data: $($terminal.DataDir)"

    $scriptsDir = Join-Path $terminal.Mql5Dir 'Scripts'
    New-Item -ItemType Directory -Path $scriptsDir -Force | Out-Null

    # Zapsání a kompilace každého skriptu; terminál je nasazený, jen když projdou všechny
    $terminalOk = $true
    foreach ($item in $deployItems) {
        $target = Join-Path $scriptsDir $item.Name
        Write-Host "   $($item.Name)"
        try {
            [IO.File]::WriteAllText($target, $item.Content, $utf8Bom)
        } catch {
            Write-Host "    Chyba kopirovani: $($_.Exception.Message)" -ForegroundColor Red
            $terminalOk = $false
            continue
        }
        if (-not (Invoke-Compile $terminal.MetaEditor $target $terminal.Mql5Dir)) {
            $terminalOk = $false
        }
    }

    if ($terminalOk) { $deployed++ } else { $failed++ }
}

Write-Host ""
if ($failed -gt 0) {
    Write-Host "Chyba: nasazeni selhalo v $failed terminalech (uspesne: $deployed)." -ForegroundColor Red
    exit 1
}
Write-Host "Nasazeno do $deployed terminalu." -ForegroundColor Green
exit 0
