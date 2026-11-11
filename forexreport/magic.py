"""
Načtení magic numbers z doplňkového CSV a jejich přiřazení k pozicím.

Standardní export historie obchodování z MetaTraderu 5 magic number
neobsahuje. Doplňkový soubor proto vytváří skript
`mql5/ExportMagicNumbers.mq5` přímo v terminálu. Pozice se s ním párují podle
čísla pozice (Position ID), které je v exportu ve sloupci "Pozice".

Očekávaný formát (oddělovač středník, čárka nebo tabulátor):

    position;magic;symbol;time
    39594909;1001;XAUUSD;2026.07.03 02:20:37
"""

from __future__ import annotations

import codecs
import csv
import os
import re
from typing import Dict, List, Optional

from .mt5_parser import Mt5Report

# Název souboru, který vytváří skript ExportMagicNumbers.mq5; číslo účtu
# v názvu umožňuje najít soubor automaticky vedle exportu
MAGIC_FILE_PATTERN = "MagicNumbers-{login}.csv"

# Přípustné názvy sloupců v hlavičce CSV (porovnává se bez velikosti písmen)
_POSITION_HEADERS = {"position", "position id", "position_id", "positionid", "pozice", "ticket"}
_MAGIC_HEADERS = {"magic", "magic number", "magic_number", "magické číslo"}


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


def _decode(raw: bytes) -> str:
    """
    Převede obsah souboru na text.

    Skript MQL5 zapisuje UTF-8, ale soubor mohl projít i Excelem či jiným
    editorem – zvládáme proto i UTF-16 s BOM a jako poslední možnost cp1250.
    """
    if raw.startswith(codecs.BOM_UTF16_LE) or raw.startswith(codecs.BOM_UTF16_BE):
        return raw.decode("utf-16")
    if raw.startswith(codecs.BOM_UTF8):
        return raw[len(codecs.BOM_UTF8):].decode("utf-8")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1250")


def _detect_delimiter(line: str) -> str:
    """Zvolí oddělovač podle toho, který se v prvním řádku vyskytuje nejčastěji."""
    counts = {delimiter: line.count(delimiter) for delimiter in (";", ",", "\t")}
    best = max(counts, key=counts.get)
    return best if counts[best] else ";"


def _column_index(header: List[str], names: set) -> Optional[int]:
    """Vrátí index prvního sloupce hlavičky, jehož název patří mezi zadané."""
    for index, cell in enumerate(header):
        if cell.strip().lower() in names:
            return index
    return None


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
        with open(path, "rb") as handle:
            text = _decode(handle.read())
    except OSError as exc:
        raise MagicFileError(f"Soubor {path} se nepodařilo přečíst: {exc}") from exc

    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise MagicFileError(f"Soubor {path} je prázdný.")

    rows = list(csv.reader(lines, delimiter=_detect_delimiter(lines[0])))
    header = rows[0]
    position_index = _column_index(header, _POSITION_HEADERS)
    magic_index = _column_index(header, _MAGIC_HEADERS)

    # Soubor bez hlavičky akceptujeme, pokud první řádek tvoří čísla
    # (pak je první sloupec číslo pozice a druhý magic number)
    if position_index is None or magic_index is None:
        if len(header) >= 2 and header[0].strip().isdigit() and header[1].strip().isdigit():
            position_index, magic_index = 0, 1
            data = rows
        else:
            raise MagicFileError(
                f"V souboru {path} chybí hlavička se sloupci 'position' a 'magic'. "
                "Soubor vytvořte skriptem mql5/ExportMagicNumbers.mq5."
            )
    else:
        data = rows[1:]

    mapping: Dict[str, int] = {}
    needed = max(position_index, magic_index)
    for row in data:
        if len(row) <= needed:
            continue
        position = row[position_index].strip()
        magic = row[magic_index].strip()
        # Řádky, které nejsou dvojicí celých nezáporných čísel, přeskočíme
        if not re.fullmatch(r"\d+", position) or not re.fullmatch(r"\d+", magic):
            continue
        mapping.setdefault(position, int(magic))

    if not mapping:
        raise MagicFileError(f"Soubor {path} neobsahuje žádné číslo pozice s magic number.")
    return mapping


def apply_magic(report: Mt5Report, mapping: Dict[str, int], source: str) -> int:
    """
    Přiřadí pozicím reportu magic numbers podle čísla pozice.

    :param report: načtený export; pozice se upravují na místě
    :param mapping: slovník číslo pozice -> magic number
    :param source: cesta k souboru, ze kterého magic numbers pocházejí
    :return: počet pozic, ke kterým se magic number našlo
    """
    matched = 0
    for position in report.positions:
        position.magic = mapping.get(position.ticket)
        if position.magic is not None:
            matched += 1
    report.magic_source = source
    return matched
