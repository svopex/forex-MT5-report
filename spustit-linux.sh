#!/usr/bin/env bash
# Spouštěč aplikace pro Linux.
#
# Připraví virtuální prostředí, doinstaluje potřebné knihovny a spustí report.
# Bez parametrů se zeptá na vstupní soubor a období:
#     ./spustit-linux.sh
# S parametry běží rovnou:
#     ./spustit-linux.sh ReportHistory-498754.xlsx month=last

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/scripts/bootstrap.sh"

printf '%s\n\n' "${C_BOLD}Forex Report · Linux${C_RESET}"

bootstrap_main "$@"
