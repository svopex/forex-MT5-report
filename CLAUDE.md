# Instrukce pro tento projekt

## Dokumentace

- `README.md` průběžně aktualizuj: při každé změně, která mění chování aplikace, ovládání,
  parametry příkazové řádky, obsah či vzhled reportu, výpočet metrik, formát vstupních
  souborů, export, spuštění, instalaci MQL5 skriptů nebo strukturu projektu, uprav
  odpovídající část `README.md` ve stejném commitu.
- Před commitem zkontroluj, zda `README.md` odpovídá změnám v commitu; pokud úprava není
  potřeba (refaktoring, testy, kosmetika), README neměň.

## Postup po změně kódu v `mql5/`

1. Zvyš `#property version` ve změněném skriptu (oprava +0.01, nová funkce +0.10,
   zásadní změna +1.00).
2. Dokud neproběhne `/simplify`, kompiluj jen kopii ve scratchpadu, ne v terminálu:
   `MetaEditor64.exe /compile:"<scratchpad>\ExportHistory.mq5" /log:"<scratchpad>\compile.log"`
   (log je v UTF-16; `MetaEditor64.exe` je v instalačním adresáři kteréhokoli MT5,
   např. `C:\Program Files\FT Trading MT5 Terminal`).
3. Spusť `/simplify` a zapracuj jeho nálezy.
4. Spusť instalaci a kompilaci do **všech nainstalovaných MT5**: `scripts\deploy.cmd`.
   Skript najde všechny terminály s MetaEditorem a datovým adresářem, do každého
   zkopíruje `mql5\*.mq5` do `<data>\MQL5\Scripts\` a skripty tam zkompiluje.
5. Úkol je hotový, až když skript u každého souboru v každém terminálu vypíše
   `Result: 0 errors` a skončí řádkem `Nasazeno do N terminalu.`; chyby kompilace oprav.
6. Změní-li se formát CSV, které skript `ExportHistory.mq5` zapisuje, uprav ve stejném
   commitu i jeho načítání ve `forexreport/mt5_parser.py` a popis v `README.md`
   (sekce *Vstupní soubor*). Nekompatibilní změna zvyšuje verzi formátu – `CSV_FORMAT`
   ve skriptu a `SUPPORTED_FORMAT` v parseru.

## Pravidla

- Zdrojové soubory MQL5 a `.ps1` ukládej v UTF-8 s BOM (MetaEditor i PowerShell 5.1
  jinak špatně načtou češtinu).
- Soubory `.bat` a `.cmd` piš jen v ASCII bez diakritiky (cmd.exe je čte v kódové
  stránce konzole).
- Exporty `ReportHistory-*.csv` obsahují údaje o účtu – necommituj je (jsou v `.gitignore`).

## Commit a push

- Po dokončení každého úkolu změny automaticky commitni a pushni, bez ptaní.
- Do commitu přidávej jen soubory, které k úkolu patří (ne `git add -A`).
