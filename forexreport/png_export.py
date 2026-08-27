"""
Export reportu do jediného dlouhého PNG.

Obrázek vzniká vykreslením hotového PDF, takže sazba je s PDF shodná do
posledního bodu – jednotlivé strany se jen poskládají pod sebe.
"""

from __future__ import annotations

import os
from typing import List, Tuple

from . import theme

# Rozumné meze rozlišení: pod 72 DPI je text nečitelný, nad 300 DPI roste
# soubor rychleji, než přibývá čitelnosti
MIN_DPI = 72
MAX_DPI = 300
DEFAULT_DPI = 150

# Výška předělu mezi stranami v bodech (přepočítá se podle rozlišení)
SEPARATOR_PT = 6.0


def _hex_to_rgb(color: str) -> Tuple[int, int, int]:
    """Převede hexadecimální barvu motivu na trojici RGB."""
    text = color.lstrip("#")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


def clamp_dpi(dpi: int) -> int:
    """Ořízne požadované rozlišení na podporovaný rozsah."""
    return max(MIN_DPI, min(MAX_DPI, int(dpi)))


def pdf_to_long_png(pdf_path: str, png_path: str, dpi: int = DEFAULT_DPI) -> Tuple[int, int]:
    """
    Vykreslí všechny strany PDF pod sebe do jediného PNG.

    :param pdf_path: cesta ke zdrojovému PDF
    :param png_path: cesta k výslednému PNG
    :param dpi: rozlišení rastru (72–300)
    :return: rozměry výsledného obrázku v pixelech (šířka, výška)
    :raises RuntimeError: pokud chybí knihovna pro vykreslení PDF
    """
    try:
        import pypdfium2 as pdfium
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "Pro export do PNG jsou potřeba knihovny pypdfium2 a Pillow. "
            "Nainstalujete je příkazem: pip install -r requirements.txt"
        ) from exc

    dpi = clamp_dpi(dpi)
    scale = dpi / 72.0
    separator = max(1, round(SEPARATOR_PT * scale))
    separator_color = _hex_to_rgb(theme.HAIRLINE)

    document = pdfium.PdfDocument(pdf_path)
    try:
        pages: List["Image.Image"] = [
            document[index].render(scale=scale).to_pil().convert("RGB")
            for index in range(len(document))
        ]
    finally:
        document.close()

    if not pages:
        raise RuntimeError(f"PDF {pdf_path} neobsahuje žádnou stranu.")

    width = max(page.width for page in pages)
    height = sum(page.height for page in pages) + separator * (len(pages) - 1)

    canvas = Image.new("RGB", (width, height), separator_color)
    offset = 0
    for index, page in enumerate(pages):
        # Užší stranu (neměla by nastat) vycentrujeme, ať obrázek nemá zub
        canvas.paste(page, ((width - page.width) // 2, offset))
        offset += page.height + separator

    # PNG ukládáme s informací o rozlišení, aby se v prohlížečích a v tisku
    # zobrazovalo ve správné velikosti
    canvas.save(png_path, format="PNG", optimize=True, dpi=(dpi, dpi))
    return canvas.size


def default_png_path(pdf_path: str) -> str:
    """Odvodí název PNG ze jména PDF (stejné umístění, jiná přípona)."""
    base, _ = os.path.splitext(pdf_path)
    return base + ".png"
