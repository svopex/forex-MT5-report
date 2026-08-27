#!/usr/bin/env bash
# Společné funkce pro spouštěcí skripty na macOS a Linuxu.
# Skript se načítá přes "source", samostatně se nespouští.

set -euo pipefail

# Kořen projektu (adresář o úroveň výš než tento soubor)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
STAMP_FILE="$VENV_DIR/.requirements.stamp"

# Barvy pro přehlednější výstup; při přesměrování do souboru se vypnou
if [ -t 1 ]; then
    C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'; C_RED=$'\033[31m'
    C_GREEN=$'\033[32m'; C_RESET=$'\033[0m'
else
    C_BOLD=""; C_DIM=""; C_RED=""; C_GREEN=""; C_RESET=""
fi

info()  { printf '%s\n' "${C_DIM}$*${C_RESET}"; }
ok()    { printf '%s\n' "${C_GREEN}$*${C_RESET}"; }
fail()  { printf '%s\n' "${C_RED}Chyba: $*${C_RESET}" >&2; }

# Vypíše nápovědu k instalaci Pythonu podle platformy.
python_hint() {
    case "$(uname -s)" in
        Darwin) echo "Nainstalujte Python 3: brew install python  (nebo z https://www.python.org/downloads/)" ;;
        Linux)
            if command -v apt-get >/dev/null 2>&1; then
                echo "Nainstalujte Python 3: sudo apt-get install python3 python3-venv"
            elif command -v dnf >/dev/null 2>&1; then
                echo "Nainstalujte Python 3: sudo dnf install python3"
            else
                echo "Nainstalujte Python 3 pomocí správce balíčků své distribuce."
            fi
            ;;
        *) echo "Nainstalujte Python 3.10 nebo novější." ;;
    esac
}

# Najde interpret Pythonu ve verzi alespoň 3.10.
find_python() {
    local candidate
    for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then
            if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
                echo "$candidate"
                return 0
            fi
        fi
    done
    return 1
}

# Vytvoří virtuální prostředí, pokud ještě neexistuje.
ensure_venv() {
    local python_bin="$1"
    if [ ! -x "$VENV_DIR/bin/python" ]; then
        info "Vytvářím virtuální prostředí v .venv …"
        if ! "$python_bin" -m venv "$VENV_DIR"; then
            fail "Nepodařilo se vytvořit virtuální prostředí."
            echo "Na Debianu/Ubuntu bývá potřeba balíček python3-venv: sudo apt-get install python3-venv" >&2
            return 1
        fi
    fi
}

# Nainstaluje závislosti, pokud se od minulého běhu změnil requirements.txt.
install_deps() {
    local requirements="$PROJECT_DIR/requirements.txt"
    local current
    # Otisk souboru se závislostmi – jen podle něj poznáme, že je třeba přeinstalovat
    if command -v shasum >/dev/null 2>&1; then
        current="$(shasum -a 256 "$requirements" | cut -d' ' -f1)"
    else
        current="$(sha256sum "$requirements" | cut -d' ' -f1)"
    fi

    if [ -f "$STAMP_FILE" ] && [ "$(cat "$STAMP_FILE")" = "$current" ]; then
        return 0
    fi

    info "Instaluji potřebné knihovny (openpyxl, matplotlib, reportlab) …"
    # Aktualizace pipu je jen příjemnost, případné selhání nesmí zastavit instalaci
    "$VENV_DIR/bin/python" -m pip install --quiet --disable-pip-version-check \
        --upgrade pip >/dev/null 2>&1 || true
    if ! "$VENV_DIR/bin/python" -m pip install --quiet --disable-pip-version-check \
            -r "$requirements"; then
        fail "Instalace knihoven se nezdařila. Zkontrolujte připojení k internetu."
        return 1
    fi
    echo "$current" > "$STAMP_FILE"
    ok "Knihovny jsou připravené."
}

# Otevře vygenerovaný soubor ve výchozí aplikaci systému.
# Nastavením FOREXREPORT_NO_OPEN=1 lze automatické otevírání vypnout.
open_result() {
    local file="$1"
    [ -f "$file" ] || return 0
    [ "${FOREXREPORT_NO_OPEN:-0}" = "1" ] && return 0
    case "$(uname -s)" in
        Darwin) open "$file" >/dev/null 2>&1 || true ;;
        Linux)  command -v xdg-open >/dev/null 2>&1 && (xdg-open "$file" >/dev/null 2>&1 &) || true ;;
    esac
}

# Zjistí, zda mezi argumenty je vstupní soubor (.xlsx).
has_source_arg() {
    local arg
    for arg in "$@"; do
        case "$arg" in
            *.xlsx|*.XLSX|*.xlsm|*.XLSM) return 0 ;;
        esac
    done
    return 1
}

# Zjistí, zda mezi argumenty je zadané období – přepínačem i zápisem bez pomlček.
has_period_arg() {
    local arg
    for arg in "$@"; do
        case "$arg" in
            --all|--year|--year=*|--month|--month=*|--week|--week=*|--day|--day=*) return 0 ;;
            all|year=*|month=*|week=*|day=*) return 0 ;;
        esac
    done
    return 1
}

# Zjistí, zda je zadaný formát výstupu – přepínačem, nebo koncovkou v -o.
has_format_arg() {
    local arg previous=""
    for arg in "$@"; do
        case "$arg" in
            -f|--format|--format=*) return 0 ;;
            *.png|*.PNG) return 0 ;;
        esac
        # Koncovka souboru za -o rozhoduje o formátu, takže se také počítá
        case "$previous" in
            -o|--output)
                case "$arg" in *.pdf|*.PDF|*.png|*.PNG) return 0 ;; esac
                ;;
        esac
        previous="$arg"
    done
    return 1
}

# Zeptá se na vstupní soubor; při jediném nalezeném ho použije rovnou.
ask_source() {
    local files=()
    while IFS= read -r line; do files+=("$line"); done < <(
        find "$PROJECT_DIR" -maxdepth 1 -name '*.xlsx' ! -name '~$*' | sort
    )

    if [ ${#files[@]} -eq 0 ]; then
        fail "V adresáři $PROJECT_DIR není žádný soubor .xlsx."
        echo "Zkopírujte sem export ReportHistory-*.xlsx z MetaTraderu 5 a spusťte skript znovu." >&2
        return 2
    fi

    if [ ${#files[@]} -eq 1 ]; then
        info "Vstupní soubor: $(basename "${files[0]}")" >&2
        printf '%s' "${files[0]}"
        return 0
    fi

    echo "${C_BOLD}Vyberte vstupní soubor:${C_RESET}" >&2
    local index=1
    for file in "${files[@]}"; do
        printf '  %d) %s
' "$index" "$(basename "$file")" >&2
        index=$((index + 1))
    done
    local choice
    read -r -p "Číslo [1]: " choice
    choice="${choice:-1}"
    printf '%s' "${files[$((choice - 1))]:-${files[0]}}"
}

# Zeptá se na období reportu a vrátí ho jako přepínač.
ask_period() {
    echo >&2
    echo "${C_BOLD}Vyberte období reportu:${C_RESET}" >&2
    echo "  1) --all         celé období" >&2
    echo "  2) --year=last   poslední rok" >&2
    echo "  3) --month=last  poslední měsíc" >&2
    echo "  4) --week=last   poslední týden" >&2
    echo "  5) --day=last    poslední den" >&2
    echo "  6) vlastní zadání (např. --month=202608)" >&2
    local answer custom
    read -r -p "Číslo [1]: " answer
    case "${answer:-1}" in
        2) printf '%s' "--year=last" ;;
        3) printf '%s' "--month=last" ;;
        4) printf '%s' "--week=last" ;;
        5) printf '%s' "--day=last" ;;
        6) read -r -p "Zadejte období: " custom; printf '%s' "${custom:---all}" ;;
        *) printf '%s' "--all" ;;
    esac
}

# Zeptá se na formát výstupu a vrátí ho jako přepínač.
ask_format() {
    echo >&2
    echo "${C_BOLD}Vyberte formát výstupu:${C_RESET}" >&2
    echo "  1) PDF" >&2
    echo "  2) PNG   jeden dlouhý obrázek" >&2
    echo "  3) obojí" >&2
    local answer
    read -r -p "Číslo [1]: " answer
    case "${answer:-1}" in
        2) printf '%s' "--format=png" ;;
        3) printf '%s' "--format=both" ;;
        *) printf '%s' "--format=pdf" ;;
    esac
}

# Doplní k zadaným argumentům jen to, co chybí, a report vytvoří.
# Na co se uživatel zeptal už na příkazové řádce, na to se skript neptá.
interactive_run() {
    # Argumenty držíme v pozičních parametrech, ne v poli: prázdné pole se
    # v bashi 3.2 (výchozí na macOS) neexpanduje, dokud platí "set -u"
    if ! has_source_arg "$@"; then
        local source_file
        source_file="$(ask_source)" || return $?
        [ -n "$source_file" ] || return 2
        set -- "$@" "$source_file"
    fi

    if ! has_period_arg "$@"; then
        set -- "$@" "$(ask_period)"
    fi

    if ! has_format_arg "$@"; then
        set -- "$@" "$(ask_format)"
    fi

    echo
    info "Připravuji report …"
    run_and_open "$@"
}

# Spustí aplikaci s běžným výpisem průběhu.
run_report() {
    "$VENV_DIR/bin/python" "$PROJECT_DIR/report.py" "$@"
}

# Spustí aplikaci v interaktivním režimu a po úspěchu otevře výsledné PDF.
# Cestu k souboru si necháme vypsat přepínačem --print-path, aby se nemusel
# rozebírat text hlášek.
run_and_open() {
    local status=0 output
    set +e
    output="$("$VENV_DIR/bin/python" "$PROJECT_DIR/report.py" "$@" --print-path)"
    status=$?
    set -e

    if [ "$status" -eq 0 ] && [ -n "$output" ]; then
        ok "Report uložen: $output"
        open_result "$output"
    fi
    return "$status"
}

# Hlavní tělo: připraví prostředí a předá řízení aplikaci.
bootstrap_main() {
    cd "$PROJECT_DIR"

    local python_bin
    if ! python_bin="$(find_python)"; then
        fail "Nenašel jsem Python 3.10 nebo novější."
        python_hint
        return 1
    fi

    ensure_venv "$python_bin" || return 1
    install_deps || return 1

    # Chybějící údaje doplníme dotazem; ostatní přebíráme z příkazové řádky.
    # Bez terminálu (skriptované volání) se neptáme a spoléháme na výchozí hodnoty.
    if [ -t 0 ]; then
        interactive_run "$@"
    else
        run_report "$@"
    fi
}
