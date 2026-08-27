"""
Vizuální motiv reportu: barevná paleta, typografie a registrace fontů.

Paleta vychází z ověřené (colour-blind safe) sady barev pro datové vizualizace.
Sémantické barvy zisk/ztráta jsou stavové (good/critical), nikoli řadové, protože
zisk a ztráta jsou stav, nikoli identita datové řady.
"""

from __future__ import annotations

import os
from typing import List


# ---------------------------------------------------------------------------
# Barvy
# ---------------------------------------------------------------------------

# Plochy a inkousty (světlý režim)
SURFACE = "#ffffff"          # plocha grafu (shodná s plochou karty)
PAGE = "#f4f4f1"             # plocha stránky
CARD = "#ffffff"             # plocha karty / dlaždice
INK = "#0b0b0b"              # primární text
INK_SECONDARY = "#52514e"    # sekundární text
INK_MUTED = "#898781"        # popisky os, tlumený text
GRID = "#e6e5df"             # mřížka (vlasová linka)
AXIS = "#c3c2b7"             # osa / základní linie
HAIRLINE = "#e1e0d9"         # oddělovače v sazbě

# Tmavá plocha pro hlavičku reportu
DARK_SURFACE = "#1a1a19"
DARK_SURFACE_ALT = "#262624"
DARK_INK = "#ffffff"
DARK_INK_SECONDARY = "#c3c2b7"

# Kategoriální paleta v pevném pořadí (nikdy necyklovat, max 8 slotů)
SERIES: List[str] = [
    "#2a78d6",  # 1 modrá
    "#eb6834",  # 2 oranžová
    "#1baf7a",  # 3 akvamarínová
    "#eda100",  # 4 žlutá
    "#e87ba4",  # 5 purpurová
    "#008300",  # 6 zelená
    "#4a3aa7",  # 7 fialová
    "#e34948",  # 8 červená
]

# Sekvenční rampa (jeden odstín, světlá -> tmavá) pro spojité veličiny
SEQUENTIAL = [
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec",
    "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab",
    "#184f95", "#104281", "#0d366b",
]

# Stavové barvy (vyhrazené, nikdy nepoužívat jako barvu datové řady)
GOOD = "#0ca30c"
WARNING = "#fab219"
SERIOUS = "#ec835a"
CRITICAL = "#d03b3b"

# Sémantika zisku a ztráty
PROFIT = GOOD
LOSS = CRITICAL
PROFIT_TEXT = "#006300"       # zelená s dostatečným kontrastem pro text
LOSS_TEXT = "#b02525"
PROFIT_SOFT = "#d6f0d6"       # tlumená výplň pro plochy
LOSS_SOFT = "#f7dcdc"

# Akcentní barva reportu (slot 1)
ACCENT = SERIES[0]
ACCENT_SOFT = "#dceafc"


# ---------------------------------------------------------------------------
# Typografie
# ---------------------------------------------------------------------------

FONT_REGULAR = "ReportSans"
FONT_BOLD = "ReportSans-Bold"

# Kandidáti na hlavní bezpatkový font. Hledáme dvojici (regular, bold) v TTF,
# protože reportlab i matplotlib musí použít stejný soubor kvůli konzistenci.
_FONT_CANDIDATES = [
    ("Inter-Regular.ttf", "Inter-Bold.ttf"),
    ("Inter_18pt-Regular.ttf", "Inter_18pt-Bold.ttf"),
    ("Roboto-Regular.ttf", "Roboto-Bold.ttf"),
    ("SourceSans3-Regular.ttf", "SourceSans3-Bold.ttf"),
    ("OpenSans-Regular.ttf", "OpenSans-Bold.ttf"),
    ("Lato-Regular.ttf", "Lato-Bold.ttf"),
    ("NotoSans-Regular.ttf", "NotoSans-Bold.ttf"),
    ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
]

_font_paths: dict[str, str] = {}


def _matplotlib_font_dir() -> str:
    """Vrátí adresář s fonty dodávanými spolu s matplotlib (fallback DejaVu Sans)."""
    import matplotlib

    return os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf")


def _search_dirs() -> List[str]:
    """Seznam adresářů, ve kterých hledáme systémové fonty (macOS, Linux i Windows)."""
    home = os.path.expanduser("~")
    directories = [
        # macOS
        os.path.join(home, "Library", "Fonts"),
        "/Library/Fonts",
        "/System/Library/Fonts/Supplemental",
        # Linux
        os.path.join(home, ".fonts"),
        os.path.join(home, ".local", "share", "fonts"),
        "/usr/share/fonts",
        "/usr/local/share/fonts",
    ]

    # Windows: systémové fonty i fonty nainstalované jen pro přihlášeného uživatele
    windir = os.environ.get("WINDIR")
    if windir:
        directories.append(os.path.join(windir, "Fonts"))
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        directories.append(os.path.join(local_appdata, "Microsoft", "Windows", "Fonts"))

    # Poslední v pořadí je záložní DejaVu Sans dodávaný s matplotlibem
    directories.append(_matplotlib_font_dir())
    return directories


def _find_font_pair() -> tuple[str, str]:
    """
    Najde první dostupnou dvojici regular/bold z kandidátů.

    Prohledávání je rekurzivní jen do rozumné hloubky, aby se u velkých
    systémových stromů (např. /usr/share/fonts) nezdržovalo.
    """
    index: dict[str, str] = {}
    for directory in _search_dirs():
        if not os.path.isdir(directory):
            continue
        for root, _dirs, files in os.walk(directory):
            # Omezení hloubky prohledávání kvůli rychlosti
            if root[len(directory):].count(os.sep) > 3:
                continue
            for name in files:
                index.setdefault(name, os.path.join(root, name))

    for regular, bold in _FONT_CANDIDATES:
        if regular in index and bold in index:
            return index[regular], index[bold]

    # Poslední záchrana: DejaVu Sans přímo z matplotlib
    mpl_dir = _matplotlib_font_dir()
    return (
        os.path.join(mpl_dir, "DejaVuSans.ttf"),
        os.path.join(mpl_dir, "DejaVuSans-Bold.ttf"),
    )


def register_fonts() -> dict[str, str]:
    """
    Zaregistruje fonty do reportlabu a nastaví je pro matplotlib.

    Vrací slovník s cestami k použitým souborům fontů (klíče 'regular', 'bold').
    Výsledek se cachuje, opakované volání je levné.
    """
    global _font_paths
    if _font_paths:
        return _font_paths

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.fonts import addMapping

    regular_path, bold_path = _find_font_pair()

    pdfmetrics.registerFont(TTFont(FONT_REGULAR, regular_path))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, bold_path))
    # Mapování rodiny, aby <b> v odstavcích fungovalo
    addMapping(FONT_REGULAR, 0, 0, FONT_REGULAR)
    addMapping(FONT_REGULAR, 1, 0, FONT_BOLD)

    _font_paths = {"regular": regular_path, "bold": bold_path}
    return _font_paths


def matplotlib_font_family() -> str:
    """
    Zaregistruje font do matplotlib a vrátí název rodiny pro rcParams.

    Pokud font nelze načíst, vrátí obecné 'sans-serif'.
    """
    from matplotlib import font_manager

    paths = register_fonts()
    try:
        font_manager.fontManager.addfont(paths["regular"])
        font_manager.fontManager.addfont(paths["bold"])
        return font_manager.FontProperties(fname=paths["regular"]).get_name()
    except Exception:
        return "sans-serif"
