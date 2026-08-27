#!/usr/bin/env bash
# Spouštěč aplikace pro macOS.
#
# Připraví virtuální prostředí, doinstaluje potřebné knihovny a spustí report.
# Lze spustit dvojklikem ve Finderu (pak se aplikace zeptá na soubor a období),
# nebo z Terminálu s parametry:
#     ./spustit-macos.command ReportHistory-498754.xlsx month=last

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/scripts/bootstrap.sh"

printf '%s\n\n' "${C_BOLD}Forex Report · macOS${C_RESET}"

# Po dvojkliku ve Finderu okno hned zmizí, proto na závěr počkáme na Enter
INTERACTIVE=0
[ "$#" -eq 0 ] && INTERACTIVE=1

status=0
bootstrap_main "$@" || status=$?

if [ "$INTERACTIVE" -eq 1 ]; then
    echo
    read -r -p "Stiskněte Enter pro zavření okna…" _
fi
exit "$status"
