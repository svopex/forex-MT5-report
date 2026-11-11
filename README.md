# Forex Report

Generátor moderních reportů z historie obchodování **MetaTrader 5**.
Historii účtu vyexportuje přímo v terminálu skript `mql5/ExportHistory.mq5`
do souboru `ReportHistory-<účet>.csv` (viz [Export historie z MetaTraderu 5](#export-historie-z-metatraderu-5)).
Aplikace se spouští z příkazové řádky, spočítá běžné obchodní metriky za
zvolené období a vysází přehledný report ve formátu A4 na šířku – jako PDF,
nebo jako jeden dlouhý PNG.

První strana je **zhuštěný přehled**, který se celý vejde na jednu obrazovku;
teprve další strany rozvádějí analýzu výkonnosti, podrobné ukazatele a seznam
jednotlivých obchodů. Podle magic number report navíc rozdělí obchody
**podle strategií**.

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
./spustit-linux.sh ReportHistory-498754.csv --all -f both
```

```bat
spustit-windows.bat
spustit-windows.bat --month=last
spustit-windows.bat ReportHistory-498754.csv --day=last --format=png
```

Je-li v adresáři jediný export `ReportHistory-*.csv`, použije se automaticky
bez ptaní; při více účtech se spouštěč zeptá, který použít.

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
python report.py <soubor.csv> [období] [přepínače]
```

Na **pořadí parametrů nezáleží** a období lze zadat dvěma rovnocennými způsoby –
přepínačem s pomlčkami, nebo zápisem bez nich:

```bash
python report.py ReportHistory-498754.csv --all
python report.py ReportHistory-498754.csv --year=2026
python report.py --month=last ReportHistory-498754.csv
python report.py --week=20260825 -o tyden.pdf ReportHistory-498754.csv
python report.py ReportHistory-498754.csv --day=last -q
python report.py ReportHistory-498754.csv --from=20260801

python report.py ReportHistory-498754.csv month=202608     # zápis bez pomlček
```

Bez zadaného období se použije celé období. Uvedete-li období dvakrát
(např. ), aplikace to ohlásí jako chybu.

### Formát výstupu

Kromě PDF umí aplikace uložit report jako **jeden dlouhý PNG** – stejná sazba,
jen jsou všechny strany poskládané pod sebe do jediného obrázku. Hodí se pro
sdílení v chatu nebo vložení na web, kde je PDF nepohodlné.

```bash
python report.py ReportHistory-498754.csv month=last --format png
python report.py ReportHistory-498754.csv month=last -o report.png
python report.py ReportHistory-498754.csv month=last --format both
python report.py ReportHistory-498754.csv month=last --format png --dpi 220
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
| `--from=20260825` | `from=20260825` | od zadaného dne `RRRRMMDD` do posledního obchodu v souboru |
| `--from=last` | `from=last` | od posledního dne s obchodní aktivitou |

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

### Export historie z MetaTraderu 5

Vstupem aplikace je soubor `ReportHistory-<účet>.csv`, který v terminálu
vytváří skript `mql5/ExportHistory.mq5`. Obsahuje údaje o účtu a všechny
obchody (deals) včetně vkladů a výběrů – na rozdíl od exportu historie, který
nabízí MetaTrader, i s **číslem pozice a magic number** u každého obchodu.
Jeden soubor tak stačí na celý report včetně rozdělení podle strategií.

Jednorázová instalace skriptu – automaticky do **všech nainstalovaných MT5**
na Windows:

```bat
scripts\deploy.cmd
```

Skript najde všechny terminály MetaTrader 5, které mají MetaEditor a datovou
složku (běžné instalace podle `%APPDATA%\MetaQuotes\Terminal\*\origin.txt`
i přenosné instalace v *Program Files*), do každého zkopíruje `mql5\*.mq5`
do `MQL5\Scripts` a skript tam přeloží. Výchozí hodnotu vstupu *InpOutputDir*
přitom nastaví na adresář projektu, takže export pak skončí rovnou v projektu.
U každého terminálu vypíše výsledek
kompilace (`Result: 0 errors, …`) a skončí řádkem `Nasazeno do N terminalu.`;
při chybě vrací návratový kód `1`. Po aktualizaci skriptu stačí `deploy.cmd`
spustit znovu. Běžící terminál zavírat nemusíte; pokud se skript v *Navigátoru*
hned neobjeví, klikněte na *Skripty* pravým tlačítkem → *Obnovit*.

Ruční instalace (jiný systém nebo jediný terminál):

1. V MetaTraderu 5 otevřete *Soubor → Otevřít složku dat*.
2. Zkopírujte `mql5/ExportHistory.mq5` do podsložky `MQL5/Scripts`.
3. V *Navigátoru* klikněte na *Skripty* pravým tlačítkem → *Obnovit*
   (případně skript otevřete v MetaEditoru a přeložte klávesou F7).

Export (pokaždé, když chcete report s aktuálními daty):

1. Přetáhněte skript *ExportHistory* z *Navigátoru* (záložka *Obecné*,
   složka *Skripty*) na libovolný graf a potvrďte.
2. Skript zapíše `ReportHistory-<účet>.csv` do adresáře ze vstupu
   *InpOutputDir* – po instalaci přes `deploy.cmd` je to adresář projektu –
   a ukáže, kam soubor uložil. Starší export téhož účtu přepíše.

MQL5 smí sám zapisovat jen do `MQL5\Files` ve složce dat. Skript proto soubor
vytvoří tam a do *InpOutputDir* ho přesune funkcí Windows, což vyžaduje povolený
**import DLL** (*Nástroje → Možnosti → Experti → Povolit import DLL*, případně
zaškrtnutí na záložce *Závislosti* při spuštění skriptu). Je-li *InpOutputDir*
prázdný (ruční instalace), import DLL není povolen nebo přesun selže (adresář
neexistuje, soubor je otevřený v Excelu), soubor zůstane v `MQL5\Files`, skript
ohlásí proč a soubor je potřeba zkopírovat do adresáře projektu ručně.

Export XLSX z MetaTraderu (*Report → Open XML*) aplikace nepodporuje – nemá
u obchodů číslo pozice ani magic number. Exporty `ReportHistory-*.csv` obsahují
údaje o účtu, proto jsou v `.gitignore` a do repozitáře se neukládají.

Magic number pozice je magic number obchodu, který ji otevřel; ruční obchody
mají magic number `0`. Report podle něj:

* vypíše v **seznamu obchodů** sloupec *Magic*,
* jsou-li ve zvoleném období **alespoň dvě strategie**, přidá před seznam
  obchodů srovnávací stranu strategií a pro každou strategii jednu stranu
  (viz [Obsah reportu](#strany-podle-strategie)).

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
**seznam obchodů** – pro jediný den je zajímavější než rozpady. Na úvodní
straně se vypíše nejvýše prvních 10 obchodů, ostatní pokračují v seznamu
obchodů na dalších stranách. Rozpady se v takovém případě přesouvají na
druhou stranu.

### Strana 2 – Analýza výkonnosti

* Pokles zůstatku od lokálního maxima (underwater křivka) – v popisu je
  uvedeno, od jakého maxima a kdy maximální pokles vznikl a o kolik je
  zůstatek na konci křivky pod maximem
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

### Strany podle strategie

Jen při alespoň dvou strategiích (magic numbers) v období.
U jediné strategie by strany jen opakovaly report celého účtu.

**Přehled strategií** (jedna strana):

* Kumulativní výsledek podle strategie – jedna čára na strategii; barva patří
  strategii (přiděluje se podle magic number), nad osm strategií se zbytek
  sloučí do šedé řady *Ostatní*
* Výsledek podle strategie
* Tabulka výkonnosti podle strategie (počet obchodů, úspěšnost, Profit Factor,
  RRR, průměrný obchod, loty, maximální pokles, hrubý zisk a ztráta, čistý
  výsledek) se souhrnným řádkem celého účtu

**Strana strategie** (jedna pro každou strategii, ve stejném pořadí jako
v tabulce):

* KPI dlaždice jako na úvodní straně
* Kumulativní výsledek strategie
* Klíčové ukazatele – podíl na obchodech účtu, průměrný obchod, zisk a ztráta,
  extrémy, nejlepší a nejhorší den, série, doba obchodu, Sharpe, poplatky
* Výsledek po úsecích, podle symbolu a dlouhé vs. krátké pozice

### Seznam obchodů (poslední strany)

Kompletní tabulka uzavřených pozic (čas otevření a uzavření včetně vteřin,
magic number, symbol, směr, objem, ceny, provize, swap, hrubý zisk a čistý
výsledek).

---

## Ochrana údajů

Číslo účtu se v hlavičce reportu zobrazuje **zamaskované** – zůstává první
a poslední znak, mezi nimi jsou tři hvězdičky:

```
498754 (USD, FTTrading-Server, demo, Hedge)  ->  4***4 (USD, FTTrading-Server, demo, Hedge)
```

Plné číslo se do PDF nedostane ani do jeho textové vrstvy nebo metadat, takže
report lze bez obav sdílet. Totéž platí pro název vstupního souboru, který
číslo účtu obsahuje – v reportu se neuvádí. Doplňující údaje v závorce (měna, server, typ účtu)
zůstávají čitelné, protože pro pochopení reportu jsou podstatné.

---

## Jak se metriky počítají

* **Obchod = jedna uzavřená pozice**, sestavená z obchodů (deals) se stejným
  číslem pozice. Otevírací a zavírací cena jsou průměry vážené objemem
  (u postupného navyšování či částečného uzavírání). Pozice, které ještě
  nejsou úplně uzavřené, se nezapočítávají.
* **Čistý výsledek obchodu** = zisk + provize + swap; poplatky (*fee*) se
  počítají do provize. Součet čistých výsledků proto přesně odpovídá změně
  zůstatku účtu.
* Obchod patří do období podle **času uzavření** – realizovaný zisk se počítá
  do období, ve kterém byl realizován.
* **Počáteční zůstatek období** = počáteční kapitál účtu (první vklad) plus vše
  realizované před začátkem období (včetně dřívějších vkladů, výběrů a jiných
  neobchodních pohybů – korekcí, bonusů, úroků).
* **Profit Factor** = hrubý zisk / hrubá ztráta.
* **RRR** = průměrný zisk / průměrná ztráta, zobrazeno jako `1 : x`.
* **Maximální pokles** se počítá z křivky zůstatku jako největší propad od
  posledního lokálního maxima (absolutně i v procentech).
* **Faktor zotavení** = čistý zisk / maximální pokles.
* **Sharpeho poměr** vychází z denních výnosů vztažených k počátečnímu
  zůstatku, anualizovaný přes 252 obchodních dnů; při méně než dvou obchodních
  dnech se neuvádí.
* **Strategie = magic number.** Metriky strategie se počítají stejně jako
  u účtu, jen z jejích obchodů. Výchozím bodem je počáteční zůstatek účtu,
  takže zhodnocení a maximální pokles v procentech vyjadřují dopad strategie
  na účet. Maximální pokles strategie se měří na jejím kumulativním výsledku;
  souhrnný řádek tabulky strategií uvádí pokles celého účtu, který není
  součtem poklesů strategií.

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
scripts/deploy.cmd         instalace a kompilace mql5/*.mq5 do všech MT5 (Windows)
scripts/deploy.ps1         vlastní logika instalace, spouští ji deploy.cmd
mql5/ExportHistory.mq5     skript pro MT5: export historie účtu do ReportHistory-<účet>.csv
forexreport/
├── cli.py                 zpracování argumentů a orchestrace
├── mt5_parser.py          načtení CSV ze skriptu ExportHistory, sestavení pozic z obchodů
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

`ReportHistory-<účet>.csv` je v UTF-8 s oddělovačem středník a má dvě části
oddělené prázdným řádkem – údaje o účtu ve tvaru `klíč;hodnota` a tabulku
všech obchodů:

```
# forex-MT5-report – historie obchodů z MetaTraderu 5 (mql5/ExportHistory.mq5)
format;1
login;498754
name;$15K - Classic - Phase 1
company;FT Trading Ltd.
server;FTTrading-Server
currency;USD
trade_mode;demo
margin_mode;Hedge
balance;15015.27
exported;2026.11.11 16:05:12

time;deal;order;position;type;entry;symbol;volume;price;sl;tp;commission;fee;swap;profit;magic;comment
2026.06.30 19:41:46;27520449;0;0;balance;in;;0;0;0;0;0;0;0;15000;0;
2026.08.05 09:11:45;31810972;43670387;43670387;sell;in;EURCAD;0.86;1.62317;0;0;-2.58;0;0;0;1003;
2026.08.05 15:55:32;31892364;43755120;43670387;buy;out;EURCAD;0.45;1.61948;1.62508;1.61624;0;0;0;118.4;1003;[sl 1.62508]
```

* `format` – verze formátu; aplikace odmítne soubor jiné verze.
* `type` a `entry` – zkrácené názvy typu a směru obchodu z MT5 (`buy`, `sell`,
  `balance`, `credit`… a `in`, `out`, `inout`, `out_by`).
* Časy obchodů jsou v čase serveru (stejně jako v terminálu), `exported` je
  místní čas exportu.

Na účtech typu *Netting* může jeden obchod pozici otočit (`inout`); aplikace
ho rozdělí na uzavření dosavadní pozice a otevření nové se stejným číslem.

Když ve zvoleném období není žádný uzavřený obchod, vygeneruje se jednostránkový
report s upozorněním a s informací, jaký rozsah dat soubor obsahuje.
