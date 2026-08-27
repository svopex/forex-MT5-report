# Forex Report

Generátor moderních reportů z historie obchodování **MetaTrader 5**
(soubor `ReportHistory-*.xlsx`). Aplikace se spouští z příkazové řádky,
spočítá běžné obchodní metriky za zvolené období a vysází přehledný report
ve formátu A4 na šířku – jako PDF, nebo jako jeden dlouhý PNG.

První strana je **zhuštěný přehled**, který se celý vejde na jednu obrazovku;
teprve další strany rozvádějí analýzu výkonnosti, podrobné ukazatele a seznam
jednotlivých obchodů.

---

## Rychlé spuštění

Nejjednodušší cesta – spouštěč sám ověří Python, vytvoří virtuální prostředí,
doinstaluje potřebné knihovny, vygeneruje report a otevře hotové PDF.

| Systém | Spouštěč |
|---|---|
| macOS | `spustit-macos.command` (lze spustit i dvojklikem ve Finderu) |
| Linux | `./spustit-linux.sh` |
| Windows | `spustit-windows.bat` (lze spustit i dvojklikem) |

Spouštěč se ptá **jen na to, co jste nezadal**. Bez parametrů se zeptá na vstupní
soubor, období i formát; s částí parametrů doplní jen zbytek; se všemi
parametry se neptá vůbec:

```bash
./spustit-linux.sh                                    # zeptá se na vše
./spustit-linux.sh --month=last                       # zeptá se jen na formát
./spustit-linux.sh --day=last --format=png            # nezeptá se na nic
./spustit-linux.sh ReportHistory-498754.xlsx --all -f both
```

```bat
spustit-windows.bat
spustit-windows.bat --month=last
spustit-windows.bat ReportHistory-498754.xlsx --day=last --format=png
```

Je-li v adresáři jediný soubor `.xlsx`, použije se automaticky bez ptaní.

Na macOS a Linuxu je při prvním použití potřeba nastavit právo ke spuštění:

```bash
chmod +x spustit-macos.command spustit-linux.sh
```

Automatické otevření hotového PDF lze vypnout proměnnou prostředí
`FOREXREPORT_NO_OPEN=1`. Knihovny se přeinstalují jen tehdy, když se změní
`requirements.txt` – běžný start je tedy okamžitý.

### Řešení potíží

| Problém | Řešení |
|---|---|
| `Nenasel jsem Python` (Windows) | Nainstalujte Python z [python.org](https://www.python.org/downloads/) a při instalaci zaškrtněte **Add python.exe to PATH**. |
| `Nepodarilo se vytvorit virtualni prostredi` (Debian/Ubuntu) | `sudo apt-get install python3-venv` |
| macOS hlásí, že soubor nelze otevřít | Klikněte na `spustit-macos.command` pravým tlačítkem → *Otevřít*, nebo v Terminálu spusťte `chmod +x spustit-macos.command`. |
| Instalace knihoven selže | Zkontrolujte připojení k internetu, případně firewall či proxy. Po opravě stačí spustit skript znovu. |
| Chci vynutit čistou instalaci | Smažte adresář `.venv` a spusťte skript znovu. |
| Aplikace skončí chybou a nevím proč | Spusťte ji z příkazové řádky s přepínačem `--debug`, který vypíše podrobnosti. |

---

## Ruční instalace

Vyžaduje Python 3.10 nebo novější.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Závislosti:

| Balíček | K čemu slouží |
|---|---|
| `openpyxl` | čtení exportu `.xlsx` z MetaTraderu 5 |
| `matplotlib` | vykreslení grafů |
| `reportlab` | sazba výsledného PDF |
| `pypdfium2` + `pillow` | export do jednoho dlouhého PNG |

Aplikace nepotřebuje žádné externí fonty – pokud v systému nenajde některý
z preferovaných bezpatkových fontů (Inter, Roboto, Source Sans, Open Sans,
Lato, Noto Sans), použije DejaVu Sans dodávaný spolu s matplotlibem. Všechny
tyto fonty obsahují českou diakritiku.

---

## Použití

```bash
python report.py <soubor.xlsx> [období] [přepínače]
```

Na **pořadí parametrů nezáleží** a období lze zadat dvěma rovnocennými způsoby –
přepínačem s pomlčkami, nebo zápisem bez nich:

```bash
python report.py ReportHistory-498754.xlsx --all
python report.py ReportHistory-498754.xlsx --year=2026
python report.py --month=last ReportHistory-498754.xlsx
python report.py --week=20260825 -o tyden.pdf ReportHistory-498754.xlsx
python report.py ReportHistory-498754.xlsx --day=last -q

python report.py ReportHistory-498754.xlsx month=202608     # zápis bez pomlček
```

Bez zadaného období se použije celé období. Uvedete-li období dvakrát
(např. ), aplikace to ohlásí jako chybu.

### Formát výstupu

Kromě PDF umí aplikace uložit report jako **jeden dlouhý PNG** – stejná sazba,
jen jsou všechny strany poskládané pod sebe do jediného obrázku. Hodí se pro
sdílení v chatu nebo vložení na web, kde je PDF nepohodlné.

```bash
python report.py ReportHistory-498754.xlsx month=last --format png
python report.py ReportHistory-498754.xlsx month=last -o report.png
python report.py ReportHistory-498754.xlsx month=last --format both
python report.py ReportHistory-498754.xlsx month=last --format png --dpi 220
```

Obrázek vzniká vykreslením hotového PDF, takže je s ním shodný do posledního
bodu. Při výchozích 150 DPI má strana šířku 1754 px; report za celé období
(5 stran) vyjde zhruba na 1754 × 6250 px a 1,5 MB. Nižší `--dpi` dá menší
soubor, vyšší ostřejší text – rozsah je omezen na 72–300 DPI.

Při `--format png` slouží PDF jen jako mezikrok a po vykreslení se smaže;
při `--format both` zůstanou oba soubory.

### Parametr období

| Přepínač | Bez pomlček | Význam |
|---|---|---|
| `--all` | `all` | celé obchodní období obsažené v souboru (výchozí) |
| `--year=2026` | `year=2026` | kalendářní rok |
| `--year=last` | `year=last` | poslední rok s obchodní aktivitou |
| `--month=202608` | `month=202608` | kalendářní měsíc ve tvaru `RRRRMM` |
| `--month=last` | `month=last` | poslední měsíc s obchodní aktivitou |
| `--week=20260825` | `week=20260825` | týden (pondělí–neděle), do kterého spadá zadaný den `RRRRMMDD` |
| `--week=last` | `week=last` | poslední týden s obchodní aktivitou |
| `--day=20260825` | `day=20260825` | jeden den ve tvaru `RRRRMMDD` |
| `--day=last` | `day=last` | poslední den s obchodní aktivitou |

Hodnota `last` se vždy vztahuje k **datům v souboru**, nikoli k systémovému
datu – `day=last` tedy znamená poslední den, kdy byl uzavřen nějaký obchod.
V zadání data lze používat i oddělovače (`2026-08-25`, `2026.08.25`).

### Další přepínače

| Přepínač | Význam |
|---|---|
| `-o`, `--output` | cesta k výstupnímu souboru (výchozí: `<vstup>-<období>.pdf` vedle vstupního souboru); koncovka `.png` přepne výstup na obrázek |
| `-f`, `--format` | `pdf` (výchozí), `png` (jeden dlouhý obrázek) nebo `both` |
| `--dpi` | rozlišení PNG, 72–300 (výchozí 150) |
| `-q`, `--quiet` | vypisovat pouze chyby |
| `--print-path` | vypsat pouze cestu k vytvořenému PDF (pro skripty) |
| `--debug` | při chybě vypsat podrobný výpis zásobníku volání |
| `--version` | verze aplikace |
| `-h`, `--help` | nápověda včetně seznamu období |

Návratové kódy: `0` úspěch, `1` chyba při čtení souboru nebo sazbě PDF,
`2` chybné zadání parametrů.

---

## Obsah reportu

### Strana 1 – Přehled (dashboard)

* **KPI dlaždice:** čistý zisk, zhodnocení, počet obchodů, Win Rate,
  RRR (ve tvaru `1 : x`), Profit Factor, maximální pokles
* **Vývoj zůstatku účtu** – schodová křivka (zůstatek se mění při uzavření pozice)
* **Klíčové ukazatele** – konečný a nejvyšší zůstatek, průměrný zisk a ztráta,
  největší zisk a ztráta, nejlepší a nejhorší den, nejdelší série,
  průměrná doba obchodu, Sharpeho poměr, poplatky a swapy
* **Výsledek po úsecích** – hodiny / dny / týdny / měsíce podle délky období
* **Výsledek podle symbolu**
* **Dlouhé vs. krátké pozice**

U **denního** reportu (`day=…`) nahrazuje tato tři poslední dlaždice rovnou
**seznam obchodů** – pro jediný den se vejde a je zajímavější než rozpady.
Rozpady se v takovém případě přesouvají na druhou stranu.

### Strana 2 – Analýza výkonnosti

* Pokles zůstatku od lokálního maxima (underwater křivka)
* Rizikový profil (maximální pokles, faktor zotavení, Sharpe, série, extrémy)
* Rozdělení výsledků obchodů (histogram s hranicemi zarovnanými na nulu)
* Výsledek podle dne v týdnu
* Nejlepší a nejhorší obchody

U denního reportu jsou poslední tři dlaždice nahrazeny rozpady podle úseků,
symbolů a směru – histogram ani dny v týdnu pro jediný den nedávají smysl.

### Strana 3 – Podrobné ukazatele

* Výsledky a rizika, struktura obchodů
* Tabulka výkonnosti podle jednotlivých symbolů
* Průměrná velikost ziskového a ztrátového obchodu

### Strana 4 a dále – Seznam obchodů

Kompletní tabulka uzavřených pozic (čas otevření a uzavření, symbol, směr,
objem, ceny, provize, swap, hrubý zisk a čistý výsledek).

---

## Ochrana údajů

Číslo účtu se v hlavičce reportu zobrazuje **zamaskované** – zůstává první
a poslední znak, mezi nimi jsou tři hvězdičky:

```
498754 (USD, FTTrading-Server, demo, Hedge)  ->  4***4 (USD, FTTrading-Server, demo, Hedge)
```

Plné číslo se do PDF nedostane ani do jeho textové vrstvy nebo metadat, takže
report lze bez obav sdílet. Doplňující údaje v závorce (měna, server, typ účtu)
zůstávají čitelné, protože pro pochopení reportu jsou podstatné.

---

## Jak se metriky počítají

* **Obchod = jedna uzavřená pozice** ze sekce *Pozice* v exportu.
* **Čistý výsledek obchodu** = zisk + provize + swap. Součet čistých výsledků
  proto přesně odpovídá změně zůstatku účtu.
* Obchod patří do období podle **času uzavření** – realizovaný zisk se počítá
  do období, ve kterém byl realizován.
* **Počáteční zůstatek období** = počáteční kapitál účtu plus vše realizované
  před začátkem období (včetně dřívějších vkladů a výběrů).
* **Profit Factor** = hrubý zisk / hrubá ztráta.
* **RRR** = průměrný zisk / průměrná ztráta, zobrazeno jako `1 : x`.
* **Maximální pokles** se počítá z křivky zůstatku jako největší propad od
  posledního lokálního maxima (absolutně i v procentech).
* **Faktor zotavení** = čistý zisk / maximální pokles.
* **Sharpeho poměr** vychází z denních výnosů vztažených k počátečnímu
  zůstatku, anualizovaný přes 252 obchodních dnů; při méně než dvou obchodních
  dnech se neuvádí.

> Poznámka: MetaTrader ve své sekci *Výsledky* člení obchody podle hrubého
> zisku bez poplatků, zatímco tento report pracuje s čistými výsledky. Součty
> (čistý zisk, maximální pokles) proto sedí, ale rozdělení na ziskové
> a ztrátové obchody se může o několik kusů lišit.

---

## Struktura projektu

```
report.py                  spouštěč z příkazové řádky
spustit-macos.command      startovací skript pro macOS
spustit-linux.sh           startovací skript pro Linux
spustit-windows.bat        startovací skript pro Windows
scripts/bootstrap.sh       společná logika startovacích skriptů (macOS + Linux)
forexreport/
├── cli.py                 zpracování argumentů a orchestrace
├── mt5_parser.py          čtení exportu z MetaTraderu 5
├── periods.py             rozbor a vyhodnocení parametru období
├── metrics.py             výpočet obchodních metrik
├── charts.py              vykreslení grafů (matplotlib)
├── pdf_report.py          sazba PDF (ReportLab)
├── png_export.py          export do jednoho dlouhého PNG
├── theme.py               barevná paleta, typografie, fonty
└── formatting.py          české formátování čísel, částek a časů
requirements.txt
```

---

## Vstupní soubor

Parser je napsaný obecně – nespoléhá na pevné pozice řádků, ale hledá sekce
(*Pozice*, *Pokyny*, *Nabídky*, *Výsledky*) a sloupce podle jejich názvů.
Zvládá českou i anglickou lokalizaci exportu a UTF-16 kódování, ve kterém
MetaTrader sešity ukládá. Funguje tedy na libovolném souboru
`ReportHistory-*.xlsx`, nejen na přiloženém vzorku.

Pokud export sekci *Pozice* neobsahuje, aplikace pozice zrekonstruuje párováním
vstupních a výstupních obchodů ze sekce *Nabídky* metodou FIFO.

Když ve zvoleném období není žádný uzavřený obchod, vygeneruje se jednostránkový
report s upozorněním a s informací, jaký rozsah dat soubor obsahuje.
