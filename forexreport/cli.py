"""
Rozhraní příkazové řádky aplikace.

Použití:
    python report.py ReportHistory-498754.xlsx year=2026 [-o report.pdf]
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from typing import Optional, Sequence

from . import __version__
from .metrics import compute_metrics
from .mt5_parser import load_report
from .pdf_report import build_report
from .periods import PERIOD_HELP, PeriodError, parse_period, resolve_period
from .png_export import DEFAULT_DPI, clamp_dpi, default_png_path, pdf_to_long_png


def build_arg_parser() -> argparse.ArgumentParser:
    """Sestaví parser argumentů příkazové řádky."""
    parser = argparse.ArgumentParser(
        prog="report.py",
        description="Vytvoří moderní report z historie obchodování MetaTrader 5 "
                    "ve formátu PDF nebo jako jeden dlouhý PNG.",
        epilog=PERIOD_HELP + """

Na pořadí parametrů nezáleží, období lze zadat oběma způsoby:
  report.py ReportHistory-498754.xlsx --month=202608
  report.py --month=202608 ReportHistory-498754.xlsx
  report.py ReportHistory-498754.xlsx month=202608""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("soubor", help="vstupní soubor ReportHistory-*.xlsx z MetaTraderu 5")
    parser.add_argument(
        "obdobi", nargs="?", default=None,
        help="období reportu zápisem bez pomlček, např. month=202608 (výchozí: all)",
    )

    # Období lze zadat i přepínačem, takže na pořadí parametrů nezáleží
    period_group = parser.add_argument_group(
        "období reportu",
        "Lze uvést nejvýše jedno; bez zadání se použije celé období.",
    )
    period_group.add_argument(
        "--all", action="store_true",
        help="celé obchodní období obsažené v souboru",
    )
    period_group.add_argument(
        "--year", metavar="RRRR|last", help="kalendářní rok, např. --year=2026",
    )
    period_group.add_argument(
        "--month", metavar="RRRRMM|last", help="kalendářní měsíc, např. --month=202608",
    )
    period_group.add_argument(
        "--week", metavar="RRRRMMDD|last",
        help="týden, do kterého spadá zadaný den, např. --week=20260825",
    )
    period_group.add_argument(
        "--day", metavar="RRRRMMDD|last", help="jeden den, např. --day=20260825",
    )
    period_group.add_argument(
        "--from", dest="from_date", metavar="RRRRMMDD|last",
        help="od zadaného dne do posledního obchodu v souboru, např. --from=20260825",
    )
    parser.add_argument(
        "-o", "--output", dest="output", default=None,
        help="cesta k výstupnímu souboru (výchozí: odvozeno z názvu vstupu a období); "
             "koncovka .png přepne výstup na obrázek",
    )
    parser.add_argument(
        "-f", "--format", dest="format", default=None,
        choices=("pdf", "png", "both"),
        help="formát výstupu: pdf (výchozí), png (jeden dlouhý obrázek) "
             "nebo both (obojí)",
    )
    parser.add_argument(
        "--dpi", type=int, default=DEFAULT_DPI,
        help=f"rozlišení obrázku při exportu do PNG (72–300, výchozí {DEFAULT_DPI})",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="nevypisovat průběh, pouze chyby",
    )
    parser.add_argument(
        "--print-path", action="store_true",
        help="vypsat na výstup pouze cestu k vytvořenému PDF (pro skripty)",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="při chybě vypsat podrobný výpis zásobníku volání",
    )
    parser.add_argument(
        "--version", action="version", version=f"forex-report {__version__}",
    )
    return parser


# Druhy období, které hledáme mezi přepínači;
# hodnotou je název atributu, do kterého argparse přepínač uloží
# ("from" je klíčové slovo Pythonu, proto se ukládá jako from_date)
_PERIOD_KINDS = {
    "year": "year",
    "month": "month",
    "week": "week",
    "day": "day",
    "from": "from_date",
}


def period_from_args(args) -> str:
    """
    Sestaví zápis období z přepínačů nebo z pozičního argumentu.

    Přepínač (--month=202608) a poziční zápis (month=202608) jsou rovnocenné,
    díky čemuž nezáleží na pořadí parametrů.

    :raises PeriodError: pokud je zadáno více období najednou
    """
    selected = []
    if args.all:
        selected.append("all")
    for kind, attribute in _PERIOD_KINDS.items():
        value = getattr(args, attribute, None)
        if value:
            selected.append(f"{kind}={value}")
    if args.obdobi:
        selected.append(args.obdobi)

    if len(selected) > 1:
        raise PeriodError(
            "Zadali jste více období najednou: " + ", ".join(selected) + ".\n"
            "Uveďte prosím jen jedno."
        )
    return selected[0] if selected else "all"


def default_output_path(source: str, short_label: str, suffix: str = ".pdf") -> str:
    """Odvodí název výstupního souboru ze vstupního souboru a zvoleného období."""
    base = os.path.splitext(os.path.basename(source))[0]
    directory = os.path.dirname(os.path.abspath(source))
    return os.path.join(directory, f"{base}-{short_label}{suffix}")


def resolve_output(args, short_label: str) -> tuple[str, Optional[str], Optional[str]]:
    """
    Určí formát výstupu a cesty k souborům.

    Formát lze zadat přepínačem --format, nebo se odvodí z koncovky souboru
    v --output. PDF vzniká vždy, protože PNG se vykresluje z něj; při volbě
    "png" se ale PDF po vykreslení smaže.

    :return: (cesta k PDF, cesta k PNG nebo None, dočasné PDF ke smazání nebo None)
    """
    output = args.output
    extension = os.path.splitext(output)[1].lower() if output else ""

    # Koncovka .png v --output přepne formát, pokud si uživatel neřekl jinak
    fmt = args.format or ("png" if extension == ".png" else "pdf")

    if fmt == "pdf":
        return (output or default_output_path(args.soubor, short_label, ".pdf"), None, None)

    if fmt == "both":
        pdf_path = output or default_output_path(args.soubor, short_label, ".pdf")
        if extension == ".png":
            pdf_path = os.path.splitext(output)[0] + ".pdf"
        return (pdf_path, os.path.splitext(pdf_path)[0] + ".png", None)

    # Pouze PNG – PDF je jen mezikrok a po vykreslení se smaže
    png_path = output if extension == ".png" else default_png_path(
        output or default_output_path(args.soubor, short_label, ".pdf")
    )
    pdf_path = os.path.splitext(png_path)[0] + ".pdf"
    return (pdf_path, png_path, pdf_path)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """
    Vstupní bod aplikace.

    Vrací návratový kód procesu (0 = úspěch).
    """
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if not os.path.isfile(args.soubor):
        print(f"Chyba: vstupní soubor '{args.soubor}' neexistuje.", file=sys.stderr)
        return 2

    try:
        spec = parse_period(period_from_args(args))
    except PeriodError as exc:
        print(f"Chyba: {exc}", file=sys.stderr)
        return 2

    # Režim pro skripty: na stdout smí jít jen výsledná cesta
    quiet = args.quiet or args.print_path

    def log(message: str) -> None:
        """Vypíše informaci o průběhu, pokud není zapnut tichý režim."""
        if not quiet:
            # flush kvůli tomu, aby se pořadí zpráv nerozešlo s chybami na stderr
            print(message, flush=True)

    try:
        log(f"Načítám {args.soubor} …")
        report = load_report(args.soubor)
    except Exception as exc:
        print(f"Chyba při čtení souboru: {exc}", file=sys.stderr)
        if args.debug:
            traceback.print_exc()
        return 1

    try:
        period = resolve_period(spec, [p.close_time for p in report.positions])
    except PeriodError as exc:
        print(f"Chyba: {exc}", file=sys.stderr)
        return 2

    metrics = compute_metrics(report, period)
    pdf_path, png_path, temporary_pdf = resolve_output(args, period.short_label)

    log(f"Období: {period.label}")
    if metrics.is_empty:
        log("Upozornění: ve zvoleném období nebyl uzavřen žádný obchod.")
    else:
        log(f"Obchodů: {metrics.trades} · čistý výsledek: "
            f"{metrics.net_profit:+.2f} {metrics.currency}")

    try:
        build_report(report, metrics, pdf_path)
    except Exception as exc:
        print(f"Chyba při generování PDF: {exc}", file=sys.stderr)
        if args.debug:
            traceback.print_exc()
        else:
            print("Podrobnosti vypíšete opakovaným spuštěním s přepínačem --debug.",
                  file=sys.stderr)
        return 1

    if png_path:
        try:
            log(f"Vykresluji obrázek v rozlišení {clamp_dpi(args.dpi)} DPI …")
            width, height = pdf_to_long_png(pdf_path, png_path, args.dpi)
            log(f"Rozměr obrázku: {width} × {height} px")
        except Exception as exc:
            print(f"Chyba při vytváření PNG: {exc}", file=sys.stderr)
            if args.debug:
                traceback.print_exc()
            return 1
        finally:
            # Pomocné PDF mažeme jen tehdy, když si uživatel přál pouze obrázek
            if temporary_pdf and os.path.exists(temporary_pdf):
                os.remove(temporary_pdf)

    # Pro skripty vypisujeme cestu k tomu souboru, který uživatel chtěl
    created = [path for path in (pdf_path if not temporary_pdf else None, png_path) if path]
    if args.print_path:
        print(os.path.abspath(png_path or pdf_path))
    else:
        for path in created:
            log(f"Report uložen: {path}")
    return 0
