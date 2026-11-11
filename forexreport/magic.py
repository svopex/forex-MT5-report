"""
Načtení magic numbers z doplňkového CSV a jejich přiřazení k pozicím.

Standardní export historie obchodování z MetaTraderu 5 magic number
neobsahuje. Doplňkový soubor proto vytváří skript
`mql5/ExportMagicNumbers.mq5` přímo v terminálu. Pozice se s ním párují podle
čísla pozice (Position ID), které je v exportu ve sloupci "Pozice".

Očekávaný formát (UTF-8, oddělovač středník, čárka nebo tabulátor):

    position;magic;symbol;time
    39594909;1001;XAUUSD;2026.07.03 02:20:37
"""

from __future__ import annotations

import csv
import os
from typing import Dict, Optional

from .mt5_parser import Mt5Report

# Název souboru, který vytváří skript ExportMagicNumbers.mq5; číslo účtu
# v názvu umožňuje najít soubor automaticky vedle exportu
MAGIC_FILE_PATTERN = "MagicNumbers-{login}.csv"


class MagicFileError(ValueError):
    """Chyba při čtení souboru s magic numbers."""


def default_magic_path(source: str, login: str) -> Optional[str]:
    """
    Najde soubor s magic numbers vedle vstupního exportu.

    :param source: cesta ke vstupnímu souboru ReportHistory-*.xlsx
    :param login: číslo účtu z hlavičky exportu
    :return: cesta k existujícímu souboru, nebo None
    """
    if not login:
        return None
    directory = os.path.dirname(os.path.abspath(source))
    candidate = os.path.join(directory, MAGIC_FILE_PATTERN.format(login=login))
    return candidate if os.path.isfile(candidate) else None


def load_magic_map(path: str) -> Dict[str, int]:
    """
    Načte CSV s magic numbers.

    Pokud se k jedné pozici vyskytne více řádků (pozice navyšovaná dalším
    vstupem), platí první z nich – tedy magic number obchodu, který pozici
    otevřel.

    :param path: cesta k souboru CSV
    :return: slovník číslo pozice -> magic number
    :raises MagicFileError: soubor nelze přečíst nebo nemá očekávaný formát
    """
    try:
        # utf-8-sig snese i BOM, který přidá Excel při uložení jako "CSV UTF-8"
        with open(path, encoding="utf-8-sig", newline="") as handle:
            lines = handle.read().splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise MagicFileError(f"Soubor {path} se nepodařilo přečíst: {exc}") from exc
    if not lines:
        raise MagicFileError(f"Soubor {path} je prázdný.")

    # Oddělovač volíme podle hlavičky – skript píše středník, ale po
    # přeuložení v tabulkovém editoru může být jiný
    delimiter = max(";,\t", key=lines[0].count)
    reader = csv.DictReader(lines, delimiter=delimiter)
    reader.fieldnames = [name.strip().lower() for name in reader.fieldnames or []]
    if "position" not in reader.fieldnames or "magic" not in reader.fieldnames:
        raise MagicFileError(
            f"V souboru {path} chybí hlavička se sloupci 'position' a 'magic'. "
            "Soubor vytvořte skriptem mql5/ExportMagicNumbers.mq5."
        )

    mapping: Dict[str, int] = {}
    for row in reader:
        position = (row["position"] or "").strip()
        magic = (row["magic"] or "").strip()
        # Řádky, které nejsou dvojicí celých nezáporných čísel, přeskočíme
        if position.isdecimal() and magic.isdecimal():
            mapping.setdefault(position, int(magic))

    if not mapping:
        raise MagicFileError(f"Soubor {path} neobsahuje žádné číslo pozice s magic number.")
    return mapping


def apply_magic(report: Mt5Report, mapping: Dict[str, int]) -> int:
    """
    Přiřadí pozicím reportu magic numbers podle čísla pozice.

    :param report: načtený export; pozice se upravují na místě
    :param mapping: slovník číslo pozice -> magic number
    :return: počet pozic, ke kterým se magic number našlo
    """
    matched = 0
    for position in report.positions:
        position.magic = mapping.get(position.ticket)
        if position.magic is not None:
            matched += 1
    # Bez jediné spárované pozice by sloupec Magic obsahoval samé pomlčky
    report.has_magic = matched > 0
    return matched
