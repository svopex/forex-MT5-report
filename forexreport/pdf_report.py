"""
Sazba PDF reportu pomocí ReportLabu.

První strana je zhuštěný přehled navržený tak, aby se celý vešel na jednu
obrazovku (formát na šířku). Následující strany rozvádějí analýzu výkonnosti,
podrobné ukazatele a seznam jednotlivých obchodů.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Callable, List, Optional, Sequence, Tuple, Union

from reportlab.lib.colors import HexColor, Color
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdfcanvas

from . import charts, theme
from .formatting import (compact_money, cs_number, datetime_cs, duration,
                         mask_account, money, percent, plural, ratio, rrr,
                         signed_money)
from .metrics import Metrics, StrategyMetrics
from .mt5_parser import Mt5Report, Position

# Rozměry stránky (A4 na šířku) a okraje sazby
PAGE_WIDTH, PAGE_HEIGHT = landscape(A4)
MARGIN = 26.0
GUTTER = 9.0
HEADER_HEIGHT = 64.0
FOOTER_HEIGHT = 20.0

# Sazba tabulky obchodů: výška řádku a místo, které v kartě zaberou
# odsazení, titulek, podtitulek a hlavička tabulky
TRADE_ROW_HEIGHT = 13.0
TRADE_CARD_OVERHEAD = 59.0

# Nejvyšší počet obchodů vypsaných na úvodní straně denního reportu;
# zbývající obchody pokračují na stranách se seznamem obchodů
OVERVIEW_TRADE_LIMIT = 10

# Rozvržení dashboardu (úvodní strana a strana strategie): podíl šířky
# hlavního grafu v prostředním pásu a výška spodního pásu s rozpady
MAIN_CHART_RATIO = 0.665
LOWER_BAND_HEIGHT = 178.0

# Sazba tabulky strategií: nejmenší výška grafů nad ní, místo, které v kartě
# zaberou odsazení, titulek, podtitulek a hlavička tabulky, a nejmenší výška
# řádku, na kterou se tabulka smí zhustit
STRATEGY_CHART_MIN_HEIGHT = 170.0
STRATEGY_TABLE_OVERHEAD = 63.0
STRATEGY_ROW_HEIGHT = 15.0
STRATEGY_ROW_MIN_HEIGHT = 9.0


# Obsah buňky tabulky obchodů: z pořadového čísla a pozice vrátí (text, barva)
TradeCell = Callable[[int, Position], Tuple[str, Optional[str]]]


def _c(hex_color: str) -> Color:
    """Převede hexadecimální barvu motivu na barvu ReportLabu."""
    return HexColor(hex_color)


def _trade_card_height(rows: int) -> float:
    """
    Výška karty se seznamem obchodů pro zadaný počet řádků.

    Z výšky karty se zpětně odvozuje, kolik řádků se do ní vejde, proto ji
    přehled i karta musí počítat stejně.
    """
    return TRADE_CARD_OVERHEAD + rows * TRADE_ROW_HEIGHT + 4


class ReportPdf:
    """
    Staví PDF report nad spočtenými metrikami.

    :param report: načtený export z MT5 (kvůli údajům o účtu)
    :param metrics: metriky za zvolené období
    """

    def __init__(self, report: Mt5Report, metrics: Metrics):
        self.report = report
        self.metrics = metrics
        self.currency = metrics.currency
        self.page_number = 0
        self.canvas: Optional[pdfcanvas.Canvas] = None

    # -- veřejné API ---------------------------------------------------------

    def build(self, path: str) -> str:
        """Vygeneruje PDF do zadaného souboru a vrátí jeho cestu."""
        theme.register_fonts()
        charts.init_style()

        self.canvas = pdfcanvas.Canvas(path, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
        self.canvas.setTitle(f"Report obchodování · {self.metrics.period.label}")
        self.canvas.setAuthor(self.report.account.company or "MT5")
        self.canvas.setSubject(f"Obchodní report za období: {self.metrics.period.label}")

        shown = self._page_overview()
        if not self.metrics.is_empty:
            self._page_performance()
            self._page_details()
            # Strany podle strategie řadíme před seznam obchodů, který je
            # přílohou celého reportu; metriky strategie plní jen tehdy,
            # když je jich v období dost na rozdělení
            strategies = self.metrics.strategies
            if strategies:
                self._page_strategies()
                for index, strategy in enumerate(strategies, start=1):
                    self._page_strategy(strategy, index, len(strategies))
            self._pages_trades(start=shown)

        self.canvas.save()
        return path

    # -- základní stavební prvky --------------------------------------------

    def _new_page(self, title: str, subtitle: str = "", heading: Optional[str] = None) -> float:
        """
        Založí novou stranu s hlavičkou a vrátí souřadnici y pod hlavičkou.

        :param title: drobný verzálkový nadpis strany v hlavičce
        :param subtitle: doplňkový text vpravo pod obdobím
        :param heading: velký nadpis místo názvu účtu (např. název strategie);
            název účtu se pak přesune do řádku s údaji o účtu
        """
        if self.page_number:
            self.canvas.showPage()
        self.page_number += 1
        c = self.canvas

        # Podklad stránky
        c.setFillColor(_c(theme.PAGE))
        c.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, stroke=0, fill=1)

        # Tmavý pruh hlavičky přes celou šířku
        top = PAGE_HEIGHT - HEADER_HEIGHT
        c.setFillColor(_c(theme.DARK_SURFACE))
        c.rect(0, top, PAGE_WIDTH, HEADER_HEIGHT, stroke=0, fill=1)
        # Tenký akcentní proužek na spodní hraně hlavičky
        c.setFillColor(_c(theme.ACCENT))
        c.rect(0, top, PAGE_WIDTH, 2.2, stroke=0, fill=1)

        account = self.report.account
        c.setFillColor(_c(theme.DARK_INK_SECONDARY))
        self._tracked(MARGIN, top + HEADER_HEIGHT - 20, title.upper(), 7.2, 1.3)

        c.setFillColor(_c(theme.DARK_INK))
        c.setFont(theme.FONT_BOLD, 17)
        name = account.name or "Obchodní účet"
        c.drawString(MARGIN, top + HEADER_HEIGHT - 42,
                     self._clip(heading or name, theme.FONT_BOLD, 17, 420))

        c.setFillColor(_c(theme.DARK_INK_SECONDARY))
        c.setFont(theme.FONT_REGULAR, 7.5)
        # Číslo účtu se v reportu zobrazuje zamaskované, aby nebylo čitelné.
        # Nahrazuje-li velký nadpis název účtu, přidáme název sem.
        detail = " · ".join(filter(None, [
            name if heading else "",
            f"Účet {mask_account(account.account)}" if account.account else "",
            account.company,
        ]))
        c.drawString(MARGIN, top + HEADER_HEIGHT - 55,
                     self._clip(detail, theme.FONT_REGULAR, 7.5, 460))

        # Pravá strana hlavičky: období a doplňkový popis
        c.setFillColor(_c(theme.DARK_INK_SECONDARY))
        self._tracked(PAGE_WIDTH - MARGIN, top + HEADER_HEIGHT - 20, "OBDOBÍ", 7.2, 1.3, right=True)
        c.setFillColor(_c(theme.DARK_INK))
        c.setFont(theme.FONT_BOLD, 13)
        c.drawRightString(PAGE_WIDTH - MARGIN, top + HEADER_HEIGHT - 40,
                          self.metrics.period.label)
        if subtitle:
            c.setFillColor(_c(theme.DARK_INK_SECONDARY))
            c.setFont(theme.FONT_REGULAR, 7.5)
            c.drawRightString(PAGE_WIDTH - MARGIN, top + HEADER_HEIGHT - 55, subtitle)

        self._footer()
        return top - 12.0

    def _footer(self) -> None:
        """Vykreslí patičku s číslem strany a zdrojem dat."""
        c = self.canvas
        c.setStrokeColor(_c(theme.HAIRLINE))
        c.setLineWidth(0.5)
        c.line(MARGIN, FOOTER_HEIGHT + 6, PAGE_WIDTH - MARGIN, FOOTER_HEIGHT + 6)

        c.setFillColor(_c(theme.INK_MUTED))
        c.setFont(theme.FONT_REGULAR, 6.8)
        source = self.report.account.exported_at or datetime.now().strftime("%Y.%m.%d %H:%M")
        c.drawString(MARGIN, FOOTER_HEIGHT - 4,
                     f"Zdroj: historie obchodování MetaTrader 5 · export {source}")
        c.drawRightString(PAGE_WIDTH - MARGIN, FOOTER_HEIGHT - 4, f"Strana {self.page_number}")

    def _card(self, x: float, y: float, width: float, height: float,
              title: str = "",
              subtitle: Union[str, Sequence[str]] = "") -> Tuple[float, float, float, float]:
        """
        Vykreslí bílou kartu s volitelným titulkem a vrátí její vnitřní plochu.

        :param subtitle: podtitulek, nebo jeho varianty od nejpodrobnější;
            vykreslí se první, která se vejde do šířky karty
        :return: (x, y, šířka, výška) prostoru pro obsah karty
        """
        c = self.canvas
        c.setFillColor(_c(theme.CARD))
        c.setStrokeColor(_c(theme.HAIRLINE))
        c.setLineWidth(0.6)
        c.roundRect(x, y, width, height, 5, stroke=1, fill=1)

        padding = 10.0
        content_top = y + height - padding
        if title:
            c.setFillColor(_c(theme.INK))
            c.setFont(theme.FONT_BOLD, 8.6)
            c.drawString(x + padding, content_top - 8, title)
            content_top -= 13
            if subtitle:
                c.setFillColor(_c(theme.INK_MUTED))
                c.setFont(theme.FONT_REGULAR, 6.8)
                variants = [subtitle] if isinstance(subtitle, str) else subtitle
                c.drawString(x + padding, content_top - 6,
                             self._fit(variants, theme.FONT_REGULAR, 6.8, width - 2 * padding))
                content_top -= 10
            content_top -= 2
        return (x + padding, y + padding, width - 2 * padding, content_top - (y + padding))

    def _kpi(self, x: float, y: float, width: float, height: float,
             label: str, value: str, note: str = "",
             value_color: Optional[str] = None, accent: Optional[str] = None) -> None:
        """
        Vykreslí jednu KPI dlaždici.

        :param label: popisek ukazatele
        :param value: hlavní hodnota (velkým písmem)
        :param note: doplňující řádek pod hodnotou
        :param value_color: barva hodnoty (např. zisk/ztráta)
        :param accent: barva svislého proužku na levé hraně
        """
        c = self.canvas
        c.setFillColor(_c(theme.CARD))
        c.setStrokeColor(_c(theme.HAIRLINE))
        c.setLineWidth(0.6)
        c.roundRect(x, y, width, height, 5, stroke=1, fill=1)

        if accent:
            # Barevný proužek nesmí přesahovat zaoblený roh karty
            c.setFillColor(_c(accent))
            c.rect(x + 0.6, y + 5, 2.4, height - 10, stroke=0, fill=1)

        padding = 11.0
        c.setFillColor(_c(theme.INK_MUTED))
        self._tracked(x + padding, y + height - 15, label.upper(), 6.6, 0.7)

        c.setFillColor(_c(value_color or theme.INK))
        size = 16.0
        # Delší hodnoty zmenšíme, aby se vešly do dlaždice
        while size > 9 and c.stringWidth(value, theme.FONT_BOLD, size) > width - 2 * padding:
            size -= 0.5
        c.setFont(theme.FONT_BOLD, size)
        c.drawString(x + padding, y + height - 15 - size - 5, value)

        if note:
            c.setFillColor(_c(theme.INK_SECONDARY))
            c.setFont(theme.FONT_REGULAR, 6.8)
            c.drawString(x + padding, y + 9,
                         self._clip(note, theme.FONT_REGULAR, 6.8, width - 2 * padding))

    def _chart_card(self, x: float, y: float, width: float, height: float,
                    title: str, render: Callable[[Tuple[float, float]], bytes],
                    subtitle: Union[str, Sequence[str]] = "") -> None:
        """
        Vykreslí kartu s grafem.

        Graf se renderuje přímo v cílové velikosti (v palcích), takže velikost
        písma v grafu odpovídá velikosti písma v sazbě.
        """
        inner_x, inner_y, inner_w, inner_h = self._card(x, y, width, height, title, subtitle)
        if inner_w <= 0 or inner_h <= 0:
            return
        png = render((inner_w / 72.0, inner_h / 72.0))
        image = ImageReader(io.BytesIO(png))
        self.canvas.drawImage(image, inner_x, inner_y, inner_w, inner_h,
                              preserveAspectRatio=True, anchor="c", mask="auto")

    def _stat_rows(self, x: float, y: float, width: float, height: float,
                   rows: Sequence[Tuple[str, str, Optional[str]]]) -> None:
        """
        Vypíše seznam dvojic popisek/hodnota pod sebe s vlasovými oddělovači.

        :param rows: trojice (popisek, hodnota, barva hodnoty nebo None)
        """
        if not rows:
            return
        c = self.canvas
        line_height = height / len(rows)
        font_size = min(8.2, max(6.4, line_height * 0.42))
        for index, (label, value, color) in enumerate(rows):
            top = y + height - index * line_height
            baseline = top - line_height / 2 - font_size * 0.35
            c.setFillColor(_c(theme.INK_SECONDARY))
            c.setFont(theme.FONT_REGULAR, font_size)
            c.drawString(x, baseline, self._clip(label, theme.FONT_REGULAR, font_size, width * 0.62))
            c.setFillColor(_c(color or theme.INK))
            c.setFont(theme.FONT_BOLD, font_size)
            c.drawRightString(x + width, baseline, value)
            if index < len(rows) - 1:
                c.setStrokeColor(_c(theme.HAIRLINE))
                c.setLineWidth(0.4)
                c.line(x, top - line_height, x + width, top - line_height)

    # -- pomocné textové operace --------------------------------------------

    def _clip(self, text: str, font: str, size: float, max_width: float) -> str:
        """Zkrátí text s výpustkou tak, aby se vešel do zadané šířky."""
        if not text:
            return ""
        if self.canvas.stringWidth(text, font, size) <= max_width:
            return text
        ellipsis = "…"
        result = text
        while result and self.canvas.stringWidth(result + ellipsis, font, size) > max_width:
            result = result[:-1]
        return result + ellipsis

    def _fit(self, variants: Sequence[str], font: str, size: float, max_width: float) -> str:
        """
        Vybere první variantu textu, která se vejde do zadané šířky.

        Když se nevejde žádná, zkrátí poslední (nejstručnější) výpustkou, aby
        text nepřetekl přes okraj.

        :param variants: varianty textu od nejpodrobnější po nejstručnější
        """
        for text in variants:
            if self.canvas.stringWidth(text, font, size) <= max_width:
                return text
        return self._clip(variants[-1], font, size, max_width)

    def _tracked(self, x: float, y: float, text: str, size: float,
                 spacing: float = 1.1, right: bool = False) -> None:
        """
        Vypíše krátký verzálkový popisek s prostrkáním.

        Prostrkání zlepšuje čitelnost verzálek; nastavuje se přes setCharSpace,
        které se hned poté vrací zpět na nulu.
        """
        c = self.canvas
        # Prostrkání umí jen textový objekt, proto text kreslíme přes beginText.
        # Šířku s prostrkáním si musíme dopočítat kvůli zarovnání doprava.
        width = c.stringWidth(text, theme.FONT_REGULAR, size) + spacing * max(0, len(text) - 1)
        text_object = c.beginText(x - width if right else x, y)
        text_object.setFont(theme.FONT_REGULAR, size)
        text_object.setCharSpace(spacing)
        text_object.textOut(text)
        # Prostrkání zůstává v grafickém stavu PDF, proto ho hned vracíme na nulu
        text_object.setCharSpace(0)
        c.drawText(text_object)

    def _optional_money(self, value: float, available: bool) -> str:
        """Vrátí částku, nebo pomlčku, pokud pro ni v období nejsou podklady."""
        return money(value, self.currency) if available else "—"

    def _pl_color(self, value: float) -> str:
        """Barva textu podle znaménka hodnoty (zisk / ztráta / neutrální)."""
        if value > 0:
            return theme.PROFIT_TEXT
        if value < 0:
            return theme.LOSS_TEXT
        return theme.INK

    # -- strana 1: zhuštěný přehled -----------------------------------------

    def _page_overview(self) -> int:
        """
        Vykreslí úvodní dashboard – vše podstatné na jedné obrazovce.

        U denního reportu se místo tří doplňkových grafů vypíše rovnou seznam
        obchodů (nejvýše OVERVIEW_TRADE_LIMIT); pro jediný den jsou
        zajímavější než rozpady.

        :return: počet obchodů vypsaných na této straně (0, pokud žádné)
        """
        m = self.metrics
        top = self._new_page("Přehled obchodování", self._period_subtitle())

        if m.is_empty:
            self._draw_empty_notice(top)
            return 0

        content_width = PAGE_WIDTH - 2 * MARGIN
        bottom = FOOTER_HEIGHT + 14

        kpi_y = self._kpi_row(m, top)

        # --- prostřední pás: křivka zůstatku + souhrn ukazatelů ---
        middle_top = kpi_y - GUTTER
        daily = m.period.kind == "day"
        if daily:
            # Spodní pás dostane jen tolik místa, kolik seznam obchodů potřebuje;
            # počet řádků je omezen, aby zbylo místo pro křivku zůstatku
            # (z výšky karty se odvodí i počet vypsaných obchodů)
            listed = min(len(m.positions), OVERVIEW_TRADE_LIMIT)
            lower_height = max(120.0, _trade_card_height(listed))
        else:
            lower_height = LOWER_BAND_HEIGHT
        middle_height = middle_top - bottom - GUTTER - lower_height
        self._chart_with_stats(
            middle_top - middle_height, middle_height,
            "Vývoj zůstatku účtu",
            lambda size: charts.equity_chart(m, size),
            f"Počáteční {money(m.opening_balance, self.currency)} → "
            f"konečný {money(m.closing_balance, self.currency)}",
            self._overview_stats(),
        )

        # --- spodní pás ---
        if daily:
            return self._trade_table_card(MARGIN, bottom, content_width, lower_height, start=0)
        self._breakdown_cards(m, bottom, lower_height)
        return 0

    def _chart_with_stats(self, y: float, height: float, title: str,
                          render: Callable[[Tuple[float, float]], bytes], subtitle: str,
                          stats: Sequence[Tuple[str, str, Optional[str]]]) -> None:
        """
        Vykreslí prostřední pás dashboardu: široký graf vlevo a kartu
        „Klíčové ukazatele“ vpravo.

        :param y: spodní hrana pásu
        :param height: výška pásu
        :param title: titulek karty s grafem
        :param render: funkce, která vykreslí graf v zadané velikosti
        :param subtitle: podtitulek karty s grafem
        :param stats: řádky ukazatelů (popisek, hodnota, barva hodnoty)
        """
        content_width = PAGE_WIDTH - 2 * MARGIN
        chart_width = content_width * MAIN_CHART_RATIO
        self._chart_card(MARGIN, y, chart_width, height, title, render, subtitle=subtitle)
        inner = self._card(MARGIN + chart_width + GUTTER, y, content_width - chart_width - GUTTER,
                           height, "Klíčové ukazatele")
        self._stat_rows(*inner, stats)

    def _kpi_row(self, m: Metrics, top: float) -> float:
        """
        Vykreslí řadu KPI dlaždic pod hlavičku strany.

        :param m: metriky, ze kterých se dlaždice plní (účet nebo strategie)
        :param top: horní hrana řady
        :return: souřadnice y spodní hrany řady
        """
        content_width = PAGE_WIDTH - 2 * MARGIN
        kpi_height = 54.0
        kpis = self._overview_kpis(m)
        tile_width = (content_width - GUTTER * (len(kpis) - 1)) / len(kpis)
        kpi_y = top - kpi_height
        for index, (label, value, note, color, accent) in enumerate(kpis):
            self._kpi(MARGIN + index * (tile_width + GUTTER), kpi_y,
                      tile_width, kpi_height, label, value, note, color, accent)
        return kpi_y

    def _breakdown_cards(self, m: Metrics, y: float, height: float) -> None:
        """
        Vykreslí přes celou šířku trojici rozpadů: po časových úsecích,
        podle symbolu a podle směru obchodu.

        :param m: metriky, ze kterých se rozpady kreslí (účet nebo strategie)
        :param y: spodní hrana karet
        :param height: výška karet
        """
        content_width = PAGE_WIDTH - 2 * MARGIN
        third = (content_width - 2 * GUTTER) / 3
        self._chart_card(
            MARGIN, y, third, height,
            f"Výsledek po úsecích · {m.bucket_label.lower()}",
            lambda size: charts.bucket_chart(m, size),
        )
        self._chart_card(
            MARGIN + third + GUTTER, y, third, height,
            "Výsledek podle symbolu",
            lambda size: charts.symbol_chart(m, size),
            subtitle=f"{plural(len(m.by_symbol), 'obchodovaný symbol', 'obchodované symboly', 'obchodovaných symbolů')}",
        )
        self._chart_card(
            MARGIN + 2 * (third + GUTTER), y, third, height,
            "Dlouhé vs. krátké pozice",
            lambda size: charts.direction_chart(m, size),
        )

    def _period_subtitle(self, m: Optional[Metrics] = None) -> str:
        """
        Doplňkový text hlavičky: rozsah skutečné aktivity v období.

        :param m: metriky strategie; bez zadání se použijí metriky celého účtu
        """
        m = self.metrics if m is None else m
        if m.is_empty:
            return "bez obchodní aktivity"
        first = min(p.close_time for p in m.positions if p.close_time)
        last = max(p.close_time for p in m.positions if p.close_time)
        return (f"{plural(m.trades, 'obchod', 'obchody', 'obchodů')} · "
                f"{datetime_cs(first, with_time=False)} – {datetime_cs(last, with_time=False)}")

    def _overview_kpis(self, m: Metrics) -> List[Tuple[str, str, str, str, str]]:
        """
        Sestaví obsah KPI dlaždic.

        :param m: metriky účtu, nebo strategie (zhodnocení i pokles v % se
            pak vztahují k zůstatku účtu)
        """
        profit_color = self._pl_color(m.net_profit)
        return [
            ("Čistý zisk", signed_money(m.net_profit, self.currency),
             f"hrubý {compact_money(m.gross_profit)} / {compact_money(m.gross_loss)}",
             profit_color, theme.PROFIT if m.net_profit >= 0 else theme.LOSS),
            ("Zhodnocení", percent(m.return_pct, 2, signed=True),
             f"ze zůstatku {compact_money(m.opening_balance)}",
             profit_color, theme.PROFIT if m.net_profit >= 0 else theme.LOSS),
            ("Obchodů", cs_number(m.trades, 0),
             f"{plural(m.trading_days, 'den', 'dny', 'dnů')} · {cs_number(m.volume, 2)} lotů",
             theme.INK, theme.ACCENT),
            ("Win Rate", percent(m.win_rate, 1),
             f"{m.wins}× zisk / {m.losses}× ztráta",
             theme.INK, theme.SERIES[2]),
            ("RRR", rrr(m.payoff_ratio),
             f"prům. {compact_money(m.avg_win)} / {compact_money(m.avg_loss)}",
             theme.PROFIT_TEXT if (m.payoff_ratio or 0) >= 1 else theme.LOSS_TEXT,
             theme.SERIES[4]),
            ("Profit Factor", ratio(m.profit_factor),
             f"prům. obchod {money(m.expectancy, decimals=2)}",
             theme.PROFIT_TEXT if (m.profit_factor or 0) >= 1 else theme.LOSS_TEXT,
             theme.SERIES[6]),
            ("Maximální pokles", compact_money(m.max_drawdown, self.currency),
             f"{percent(m.max_drawdown_pct, 2)} · zotavení {ratio(m.recovery_factor)}",
             theme.LOSS_TEXT if m.max_drawdown else theme.INK, theme.SERIOUS),
        ]

    def _overview_stats(self) -> List[Tuple[str, str, Optional[str]]]:
        """Seznam klíčových ukazatelů zobrazený vedle křivky zůstatku."""
        m = self.metrics
        return [
            ("Konečný zůstatek", money(m.closing_balance, self.currency), theme.INK),
            ("Nejvyšší zůstatek", money(m.peak_balance, self.currency), None),
        ] + self._trade_stats(m)

    def _trade_stats(self, m: Metrics) -> List[Tuple[str, str, Optional[str]]]:
        """
        Ukazatele obchodů společné pro úvodní stranu i stranu strategie
        (průměry, extrémy, dny, série, doba obchodu, Sharpe, poplatky).

        :param m: metriky účtu nebo strategie
        """
        best_day = (f"{datetime_cs(m.best_day[0], with_time=False)} · "
                    f"{compact_money(m.best_day[1], self.currency)}") if m.best_day else "—"
        worst_day = (f"{datetime_cs(m.worst_day[0], with_time=False)} · "
                     f"{compact_money(m.worst_day[1], self.currency)}") if m.worst_day else "—"
        return [
            ("Průměrný zisk", self._optional_money(m.avg_win, bool(m.wins)),
             self._pl_color(m.avg_win)),
            ("Průměrná ztráta", self._optional_money(m.avg_loss, bool(m.losses)),
             self._pl_color(m.avg_loss)),
            ("Největší zisk", self._optional_money(m.largest_win, bool(m.wins)),
             self._pl_color(m.largest_win)),
            ("Největší ztráta", self._optional_money(m.largest_loss, bool(m.losses)),
             self._pl_color(m.largest_loss)),
            ("Nejlepší den", best_day, theme.PROFIT_TEXT if m.best_day and m.best_day[1] > 0 else None),
            ("Nejhorší den", worst_day, theme.LOSS_TEXT if m.worst_day and m.worst_day[1] < 0 else None),
            ("Nejdelší série zisků / ztrát",
             f"{m.max_consecutive_wins}× / {m.max_consecutive_losses}×", None),
            ("Průměrná doba obchodu", duration(m.avg_duration_minutes), None),
            ("Sharpeho poměr", ratio(m.sharpe_ratio), None),
            ("Poplatky a swapy", money(m.commission + m.swap, self.currency), None),
        ]

    def _draw_empty_notice(self, top: float) -> None:
        """Zobrazí informaci, že ve zvoleném období nebyl uzavřen žádný obchod."""
        c = self.canvas
        width = PAGE_WIDTH - 2 * MARGIN
        height = 116.0
        y = top - 60 - height
        self._card(MARGIN, y, width, height)

        c.setFillColor(_c(theme.INK))
        c.setFont(theme.FONT_BOLD, 15)
        c.drawCentredString(PAGE_WIDTH / 2, y + height - 42,
                            "Ve zvoleném období nebyl uzavřen žádný obchod")

        # Uživateli napovíme, jaký rozsah dat soubor vůbec obsahuje
        times = [p.close_time for p in self.report.positions if p.close_time]
        lines = [f"Zůstatek účtu k počátku období: {money(self.metrics.opening_balance, self.currency)}"]
        if times:
            lines.append(
                f"Soubor obsahuje {plural(len(times), 'obchod', 'obchody', 'obchodů')} "
                f"z období {datetime_cs(min(times), with_time=False)} – "
                f"{datetime_cs(max(times), with_time=False)}"
            )
        c.setFillColor(_c(theme.INK_SECONDARY))
        c.setFont(theme.FONT_REGULAR, 9)
        for index, line in enumerate(lines):
            c.drawCentredString(PAGE_WIDTH / 2, y + height - 66 - index * 15, line)

    # -- strana 2: analýza výkonnosti ---------------------------------------

    def _page_performance(self) -> None:
        """Podrobnější pohled na rizikový profil a strukturu obchodů."""
        m = self.metrics
        top = self._new_page("Analýza výkonnosti", self._period_subtitle())
        content_width = PAGE_WIDTH - 2 * MARGIN
        bottom = FOOTER_HEIGHT + 14

        lower_height = 190.0
        upper_height = top - bottom - GUTTER - lower_height
        upper_y = top - upper_height
        drawdown_width = content_width * 0.735
        risk_width = content_width - drawdown_width - GUTTER

        self._chart_card(
            MARGIN, upper_y, drawdown_width, upper_height,
            "Pokles zůstatku od lokálního maxima",
            lambda size: charts.drawdown_chart(m, size),
            subtitle=self._drawdown_subtitle(),
        )

        inner = self._card(MARGIN + drawdown_width + GUTTER, upper_y, risk_width,
                           upper_height, "Rizikový profil")
        self._stat_rows(*inner, self._risk_stats())

        third = (content_width - 2 * GUTTER) / 3
        if m.period.kind == "day":
            # Rozdělení výsledků ani dny v týdnu nedávají pro jediný den smysl,
            # proto sem přesouváme rozpady z úvodní strany
            self._breakdown_cards(m, bottom, lower_height)
            return

        self._chart_card(
            MARGIN, bottom, third, lower_height,
            "Rozdělení výsledků obchodů",
            lambda size: charts.distribution_chart(m, size),
            subtitle="Počet obchodů podle dosaženého výsledku",
        )
        self._chart_card(
            MARGIN + third + GUTTER, bottom, third, lower_height,
            "Výsledek podle dne v týdnu",
            lambda size: charts.weekday_chart(m, size),
            subtitle="Podle dne uzavření pozice",
        )
        self._chart_card(
            MARGIN + 2 * (third + GUTTER), bottom, third, lower_height,
            "Nejlepší a nejhorší obchody",
            lambda size: charts.top_trades_chart(m, size),
        )

    def _peak_label(self, value: float, moment: Optional[datetime],
                    instrumental: bool = False, with_moment: bool = True) -> str:
        """
        Popíše lokální maximum zůstatku pro podtitulek grafu poklesu.

        :param value: výše maxima
        :param moment: kdy zůstatek na maximu stál; None znamená, že maximem
            je počáteční zůstatek
        :param instrumental: sedmý pád („pod maximem“) místo druhého („od maxima“)
        :param with_moment: připojit datum a čas maxima
        """
        amount = money(value, self.currency)
        if moment is None:
            noun = "počátečním zůstatkem" if instrumental else "počátečního zůstatku"
            return f"{noun} {amount}"
        noun = "maximem" if instrumental else "maxima"
        if not with_moment:
            return f"{noun} {amount}"
        return f"{noun} {amount} z {datetime_cs(moment)}"

    def _drawdown_subtitle(self) -> List[str]:
        """
        Podtitulek grafu poklesu: maximální pokles včetně lokálního maxima,
        od kterého vznikl, a pokles na konci křivky.

        Faktor zotavení se sem už nevejde; je uveden v sousední kartě
        „Rizikový profil“.

        :return: varianty podtitulku od nejpodrobnější; karta vykreslí první,
            která se do ní vejde
        """
        m = self.metrics
        head = (f"Maximální pokles {money(m.max_drawdown, self.currency)} "
                f"({percent(m.max_drawdown_pct, 2)})")
        if m.max_drawdown > 0:
            head += " od " + self._peak_label(m.max_drawdown_peak, m.max_drawdown_peak_time)

        # Křivka končí na maximu – stačí údaj o maximálním poklesu
        if m.current_drawdown <= 0:
            return [head]
        tail = f"{head} · na konci {money(m.current_drawdown, self.currency)} pod "
        if m.peak_time == m.max_drawdown_peak_time:
            return [tail + "ním"]

        # Konec křivky se měří od jiného, pozdějšího maxima; kratší varianta
        # pro úzkou kartu vynechá jeho datum a čas
        return [tail + self._peak_label(m.peak_balance, m.peak_time, instrumental=True),
                tail + self._peak_label(m.peak_balance, m.peak_time, instrumental=True,
                                        with_moment=False)]

    def _risk_stats(self) -> List[Tuple[str, str, Optional[str]]]:
        """Ukazatele rizika zobrazené vedle křivky poklesu."""
        m = self.metrics
        # Průměrný denní výsledek počítáme jen ze dnů, kdy se skutečně obchodovalo
        daily_average = m.net_profit / m.trading_days if m.trading_days else 0.0
        return [
            ("Maximální pokles", money(m.max_drawdown, self.currency),
             theme.LOSS_TEXT if m.max_drawdown else None),
            ("Maximální pokles v %", percent(m.max_drawdown_pct, 2),
             theme.LOSS_TEXT if m.max_drawdown else None),
            ("Faktor zotavení", ratio(m.recovery_factor), None),
            ("Sharpeho poměr", ratio(m.sharpe_ratio), None),
            ("Nejvyšší zůstatek", money(m.peak_balance, self.currency), None),
            ("Konečný zůstatek", money(m.closing_balance, self.currency),
             self._pl_color(m.net_profit)),
            ("Nejdelší série ztrát",
             f"{m.max_consecutive_losses}× · {compact_money(m.max_consecutive_loss_amount, self.currency)}",
             theme.LOSS_TEXT if m.max_consecutive_losses else None),
            ("Nejdelší série zisků",
             f"{m.max_consecutive_wins}× · {compact_money(m.max_consecutive_win_amount, self.currency)}",
             theme.PROFIT_TEXT if m.max_consecutive_wins else None),
            ("Největší ztráta", self._optional_money(m.largest_loss, bool(m.losses)),
             self._pl_color(m.largest_loss)),
            ("Největší zisk", self._optional_money(m.largest_win, bool(m.wins)),
             self._pl_color(m.largest_win)),
            ("Průměrný denní výsledek", money(daily_average, self.currency),
             self._pl_color(daily_average)),
            ("Obchodních dnů", cs_number(m.trading_days, 0), None),
        ]

    # -- strana 3: podrobné ukazatele ---------------------------------------

    def _page_details(self) -> None:
        """Tabulkový přehled všech ukazatelů a výkonnosti podle symbolů."""
        m = self.metrics
        top = self._new_page("Podrobné ukazatele", self._period_subtitle())
        content_width = PAGE_WIDTH - 2 * MARGIN
        bottom = FOOTER_HEIGHT + 14
        height = top - bottom

        left_width = content_width * 0.42
        right_width = content_width - left_width - GUTTER

        # Levý sloupec: dvě karty s ukazateli pod sebou
        half = (height - GUTTER) / 2
        inner = self._card(MARGIN, top - half, left_width, half, "Výsledky a rizika")
        self._stat_rows(*inner, self._detail_stats_results())

        inner = self._card(MARGIN, bottom, left_width, half, "Struktura obchodů")
        self._stat_rows(*inner, self._detail_stats_structure())

        # Pravý sloupec: tabulka podle symbolů a graf průměrů.
        # Výška tabulky se řídí počtem symbolů, aby v kartě nezůstávalo prázdné místo.
        row_height = 15.0
        needed = 20 + 14 + 34 + row_height * (len(m.by_symbol) + 1)
        table_height = max(150.0, min(height - 120.0 - GUTTER, needed))
        chart_height = height - table_height - GUTTER
        table_x = MARGIN + left_width + GUTTER
        inner = self._card(table_x, top - table_height, right_width, table_height,
                           "Výkonnost podle symbolu",
                           subtitle=f"Seřazeno podle čistého výsledku · "
                                    f"{plural(len(m.by_symbol), 'symbol', 'symboly', 'symbolů')} "
                                    f"· částky v {self.currency}")
        self._symbol_table(*inner)

        self._chart_card(
            table_x, bottom, right_width, chart_height,
            "Průměrná velikost ziskového a ztrátového obchodu",
            lambda size: charts.win_loss_chart(m, size),
        )

    def _detail_stats_results(self) -> List[Tuple[str, str, Optional[str]]]:
        """Ukazatele výsledků a rizika pro stranu s detaily."""
        m = self.metrics
        return [
            ("Čistý zisk", signed_money(m.net_profit, self.currency), self._pl_color(m.net_profit)),
            ("Hrubý zisk", money(m.gross_profit, self.currency), self._pl_color(m.gross_profit)),
            ("Hrubá ztráta", money(m.gross_loss, self.currency), self._pl_color(m.gross_loss)),
            ("Provize", money(m.commission, self.currency), None),
            ("Swapy", money(m.swap, self.currency), None),
            ("Zhodnocení za období", percent(m.return_pct, 2, signed=True), self._pl_color(m.net_profit)),
            ("Počáteční zůstatek", money(m.opening_balance, self.currency), None),
            ("Konečný zůstatek", money(m.closing_balance, self.currency), None),
            ("Maximální pokles", money(m.max_drawdown, self.currency), theme.LOSS_TEXT),
            ("Maximální pokles v %", percent(m.max_drawdown_pct, 2), theme.LOSS_TEXT),
            ("Faktor zotavení", ratio(m.recovery_factor), None),
            ("Sharpeho poměr", ratio(m.sharpe_ratio), None),
        ]

    def _detail_stats_structure(self) -> List[Tuple[str, str, Optional[str]]]:
        """Ukazatele struktury obchodů pro stranu s detaily."""
        m = self.metrics
        long_stats = next((g for g in m.by_direction if g.key.startswith("Dlouhé")), None)
        short_stats = next((g for g in m.by_direction if g.key.startswith("Krátké")), None)
        return [
            ("Počet obchodů", cs_number(m.trades, 0), None),
            ("Ziskové obchody", f"{m.wins} · {percent(m.win_rate, 1)}",
             theme.PROFIT_TEXT if m.wins else None),
            ("Ztrátové obchody",
             f"{m.losses} · {percent(100.0 * m.losses / m.trades if m.trades else 0.0, 1)}",
             theme.LOSS_TEXT if m.losses else None),
            ("Profit Factor", ratio(m.profit_factor), None),
            ("Průměrný obchod", money(m.expectancy, self.currency), self._pl_color(m.expectancy)),
            ("Poměr zisk/ztráta (RRR)", rrr(m.payoff_ratio), None),
            ("Nejdelší série zisků",
             f"{m.max_consecutive_wins}× · {compact_money(m.max_consecutive_win_amount, self.currency)}",
             theme.PROFIT_TEXT if m.max_consecutive_wins else None),
            ("Nejdelší série ztrát",
             f"{m.max_consecutive_losses}× · {compact_money(m.max_consecutive_loss_amount, self.currency)}",
             theme.LOSS_TEXT if m.max_consecutive_losses else None),
            ("Dlouhé pozice (buy)",
             f"{long_stats.trades} · {percent(long_stats.win_rate, 0)}" if long_stats else "—", None),
            ("Krátké pozice (sell)",
             f"{short_stats.trades} · {percent(short_stats.win_rate, 0)}" if short_stats else "—", None),
            ("Zobchodovaný objem", f"{cs_number(m.volume, 2)} lotů", None),
            ("Průměrná doba obchodu", duration(m.avg_duration_minutes), None),
        ]

    def _symbol_table(self, x: float, y: float, width: float, height: float) -> None:
        """Vykreslí tabulku výkonnosti podle symbolu do zadané plochy."""
        groups = self.metrics.by_symbol
        if not groups:
            return
        headers = ["Symbol", "Obchodů", "Úspěšnost", "Loty",
                   "Hrubý zisk", "Hrubá ztráta", "Čistý výsledek"]
        weights = [0.16, 0.11, 0.13, 0.12, 0.16, 0.16, 0.16]
        aligns = ["left", "right", "right", "right", "right", "right", "right"]

        rows: List[List[Tuple[str, Optional[str]]]] = []
        for group in groups:
            rows.append([
                (group.key, None),
                (cs_number(group.trades, 0), None),
                (percent(group.win_rate, 0), None),
                (cs_number(group.volume, 2), None),
                (money(group.gross_profit, decimals=2),
                 theme.PROFIT_TEXT if group.gross_profit else None),
                (money(group.gross_loss, decimals=2),
                 theme.LOSS_TEXT if group.gross_loss else None),
                (signed_money(group.net, decimals=2), self._pl_color(group.net)),
            ])
        total = self.metrics
        footer = [
            ("Celkem", None),
            (cs_number(total.trades, 0), None),
            (percent(total.win_rate, 0), None),
            (cs_number(total.volume, 2), None),
            (money(total.gross_profit, decimals=2),
             theme.PROFIT_TEXT if total.gross_profit else None),
            (money(total.gross_loss, decimals=2),
             theme.LOSS_TEXT if total.gross_loss else None),
            (signed_money(total.net_profit, decimals=2), self._pl_color(total.net_profit)),
        ]
        self._table(x, y, width, height, headers, weights, aligns, rows, footer)

    # -- strany podle strategie (magic number) ------------------------------

    def _page_strategies(self) -> None:
        """
        Srovnávací strana všech strategií v období.

        Nahoře průběh kumulativního výsledku a výsledek podle strategie,
        dole tabulka výkonnosti. Výška tabulky se řídí počtem strategií;
        když se všechny nevejdou ani při zhuštěných řádcích, vypíší se jen
        ty nejlepší a podtitulek to uvede.
        """
        m = self.metrics
        strategies = m.strategies
        count = len(strategies)
        top = self._new_page(
            "Přehled strategií",
            f"{plural(count, 'strategie', 'strategie', 'strategií')} · {self._period_subtitle()}",
        )
        content_width = PAGE_WIDTH - 2 * MARGIN
        bottom = FOOTER_HEIGHT + 14
        height = top - bottom

        # Kolik řádků (strategie + souhrnný řádek) se do tabulky vůbec vejde
        max_table_height = height - GUTTER - STRATEGY_CHART_MIN_HEIGHT
        capacity = int((max_table_height - STRATEGY_TABLE_OVERHEAD) // STRATEGY_ROW_MIN_HEIGHT) - 1
        listed = strategies[:max(1, capacity)]
        needed = STRATEGY_TABLE_OVERHEAD + (len(listed) + 1) * STRATEGY_ROW_HEIGHT
        table_height = max(120.0, min(max_table_height, needed))
        chart_height = height - table_height - GUTTER
        chart_y = top - chart_height

        curves_width = content_width * MAIN_CHART_RATIO
        bars_width = content_width - curves_width - GUTTER
        self._chart_card(
            MARGIN, chart_y, curves_width, chart_height,
            "Kumulativní výsledek podle strategie",
            lambda size: charts.strategy_curves_chart(strategies, m.period, self.currency, size),
            subtitle="Součet čistých výsledků uzavřených obchodů od začátku období",
        )
        self._chart_card(
            MARGIN + curves_width + GUTTER, chart_y, bars_width, chart_height,
            "Výsledek podle strategie",
            lambda size: charts.strategy_chart(strategies, self.currency, size),
            subtitle=plural(count, "strategie", "strategie", "strategií"),
        )

        shown = (f"zobrazeno {len(listed)} nejlepších z {count} · "
                 if len(listed) < count else "")
        inner = self._card(
            MARGIN, bottom, content_width, table_height,
            "Výkonnost podle strategie",
            subtitle=[
                f"Seřazeno podle čistého výsledku · {shown}max. pokles z kumulativního "
                f"výsledku strategie · částky v {self.currency}",
                f"Seřazeno podle čistého výsledku · {shown}částky v {self.currency}",
            ],
        )
        self._strategy_table(*inner, listed)

    def _strategy_table(self, x: float, y: float, width: float, height: float,
                        strategies: Sequence[StrategyMetrics]) -> None:
        """
        Vykreslí tabulku výkonnosti strategií do zadané plochy.

        Souhrnný řádek nese hodnoty celého účtu – maximální pokles účtu proto
        není součtem poklesů strategií.

        :param strategies: strategie k vypsání (už seřazené)
        """
        headers = ["Strategie", "Obchodů", "Úspěšnost", "Profit Factor", "RRR",
                   "Prům. obchod", "Loty", "Max. pokles", "Hrubý zisk",
                   "Hrubá ztráta", "Čistý výsledek"]
        weights = [0.15, 0.07, 0.08, 0.09, 0.08, 0.09, 0.07, 0.09, 0.09, 0.09, 0.10]
        aligns = ["left"] + ["right"] * 10

        def row(label: str, m: Metrics) -> List[Tuple[str, Optional[str]]]:
            """Jeden řádek tabulky z metrik strategie nebo účtu."""
            return [
                (label, None),
                (cs_number(m.trades, 0), None),
                (percent(m.win_rate, 0), None),
                (ratio(m.profit_factor), None),
                (rrr(m.payoff_ratio), None),
                (signed_money(m.expectancy, decimals=2), self._pl_color(m.expectancy)),
                (cs_number(m.volume, 2), None),
                (money(m.max_drawdown, decimals=2),
                 theme.LOSS_TEXT if m.max_drawdown else None),
                (money(m.gross_profit, decimals=2),
                 theme.PROFIT_TEXT if m.gross_profit else None),
                (money(m.gross_loss, decimals=2),
                 theme.LOSS_TEXT if m.gross_loss else None),
                (signed_money(m.net_profit, decimals=2), self._pl_color(m.net_profit)),
            ]

        rows = [row(s.label, s.metrics) for s in strategies]
        self._table(x, y, width, height, headers, weights, aligns, rows,
                    footer=row("Celý účet", self.metrics))

    def _page_strategy(self, strategy: StrategyMetrics, index: int, count: int) -> None:
        """
        Kompaktní strana jedné strategie: KPI, kumulativní výsledek, klíčové
        ukazatele a rozpady podle času, symbolu a směru.

        :param strategy: strategie a její metriky
        :param index: pořadí strategie (od 1) – kvůli orientaci v reportu
        :param count: celkový počet strategií
        """
        m = strategy.metrics
        top = self._new_page(f"Strategie {index} z {count}", self._period_subtitle(m),
                             heading=strategy.label)
        bottom = FOOTER_HEIGHT + 14

        kpi_y = self._kpi_row(m, top)

        # Prostřední pás: kumulativní výsledek strategie + souhrn ukazatelů
        middle_top = kpi_y - GUTTER
        middle_height = middle_top - bottom - GUTTER - LOWER_BAND_HEIGHT
        self._chart_with_stats(
            middle_top - middle_height, middle_height,
            "Kumulativní výsledek strategie",
            lambda size: charts.equity_chart(m, size, relative=True),
            f"Součet čistých výsledků obchodů strategie · konečný "
            f"{signed_money(m.net_profit, self.currency)}",
            self._strategy_stats(m),
        )

        self._breakdown_cards(m, bottom, LOWER_BAND_HEIGHT)

    def _strategy_stats(self, m: Metrics) -> List[Tuple[str, str, Optional[str]]]:
        """
        Klíčové ukazatele strategie zobrazené vedle jejího kumulativního výsledku.

        Místo zůstatku (u strategie nemá smysl) uvádí podíl strategie na
        obchodech účtu a průměrný obchod.
        """
        total = self.metrics.trades
        share = 100.0 * m.trades / total if total else 0.0
        return [
            ("Podíl na obchodech účtu", f"{m.trades} z {total} · {percent(share, 0)}", None),
            ("Průměrný obchod", money(m.expectancy, self.currency), self._pl_color(m.expectancy)),
        ] + self._trade_stats(m)

    # -- strany se seznamem obchodů -----------------------------------------

    # -- seznam obchodů ------------------------------------------------------

    def _trade_columns(self) -> List[Tuple[str, float, str, TradeCell]]:
        """
        Sloupce tabulky obchodů: (hlavička, relativní šířka, zarovnání, obsah buňky).

        Obsah buňky je funkce pořadového čísla a pozice. Sloupce "Otevřeno"
        a "Uzavřeno" jsou širší kvůli času včetně vteřin; magic number se
        vypisuje surové (0 = ruční obchod) a jeho sloupec pojme až 15 číslic
        (EA často skládají magic number z data a času, např. 202611110801).
        Ceny a zisk mají šířku jen s malou rezervou nad záhlavím.
        """
        return [
            ("#", 0.032, "right", lambda number, p: (str(number), None)),
            ("Otevřeno", 0.118, "left",
             lambda number, p: (datetime_cs(p.open_time, with_seconds=True), None)),
            ("Uzavřeno", 0.118, "left",
             lambda number, p: (datetime_cs(p.close_time, with_seconds=True), None)),
            ("Magic", 0.100, "left", lambda number, p: (str(p.magic), None)),
            ("Symbol", 0.069, "left", lambda number, p: (p.symbol, None)),
            ("Směr", 0.051, "left",
             lambda number, p: ("Dlouhá" if p.direction == "buy" else "Krátká", None)),
            ("Objem", 0.051, "right", lambda number, p: (cs_number(p.volume, 2), None)),
            ("Otevírací cena", 0.080, "right", lambda number, p: (self._price(p.open_price), None)),
            ("Zavírací cena", 0.080, "right", lambda number, p: (self._price(p.close_price), None)),
            ("Provize", 0.060, "right", lambda number, p: (money(p.commission, decimals=2), None)),
            ("Swap", 0.056, "right", lambda number, p: (money(p.swap, decimals=2), None)),
            ("Zisk", 0.080, "right", lambda number, p: (money(p.gross_profit, decimals=2), None)),
            ("Výsledek", 0.081, "right",
             lambda number, p: (signed_money(p.net_profit, decimals=2), self._pl_color(p.net_profit))),
        ]

    def _sorted_positions(self) -> List[Position]:
        """Obchody období seřazené podle času uzavření."""
        return sorted(self.metrics.positions, key=lambda p: p.close_time or datetime.min)

    def _trade_table_card(self, x: float, y: float, width: float, height: float,
                          start: int) -> int:
        """
        Vykreslí kartu se seznamem obchodů od zadaného pořadí.

        Karta se zkrátí, pokud zbývá méně obchodů, než by se do ní vešlo.

        :return: počet obchodů vypsaných v kartě
        """
        positions = self._sorted_positions()
        capacity = max(1, int((height - TRADE_CARD_OVERHEAD) // TRADE_ROW_HEIGHT))
        chunk = positions[start:start + capacity]
        if not chunk:
            return 0

        card_height = min(height, _trade_card_height(len(chunk)))
        inner = self._card(
            x, y + height - card_height, width, card_height,
            "Uzavřené pozice",
            subtitle=f"Řazeno podle času uzavření · zobrazeno {start + 1}–"
                     f"{start + len(chunk)} z {len(positions)} · částky v {self.currency}",
        )
        headers, weights, aligns, cells = zip(*self._trade_columns())
        # Řádky číslujeme od pořadí prvního obchodu v kartě
        rows = [[cell(number, position) for cell in cells]
                for number, position in enumerate(chunk, start=start + 1)]
        self._table(*inner, headers, weights, aligns, rows, row_height=TRADE_ROW_HEIGHT)
        return len(chunk)

    def _pages_trades(self, start: int = 0) -> None:
        """
        Vypíše zbývající obchody období na samostatné strany.

        :param start: pořadí prvního nevypsaného obchodu (obchody vypsané už
            na úvodní straně se neopakují)
        """
        positions = self._sorted_positions()
        content_width = PAGE_WIDTH - 2 * MARGIN
        bottom = FOOTER_HEIGHT + 14

        index = start
        while index < len(positions):
            top = self._new_page("Seznam obchodů", self._period_subtitle())
            shown = self._trade_table_card(MARGIN, bottom, content_width, top - bottom, index)
            if not shown:
                break
            index += shown

    @staticmethod
    def _price(value: Optional[float]) -> str:
        """
        Naformátuje cenu instrumentu.

        Počet desetinných míst odvozujeme z hodnoty samotné, aby se cena
        nezaokrouhlila – měnové páry mají pět míst, páry s jenem tři,
        indexy a kovy dvě.
        """
        if value is None:
            return "—"
        decimals = 5
        for candidate in (2, 3, 5):
            if abs(round(value, candidate) - value) < 1e-9:
                decimals = candidate
                break
        return cs_number(value, decimals)

    # -- obecná tabulka ------------------------------------------------------

    def _table(self, x: float, y: float, width: float, height: float,
               headers: Sequence[str], weights: Sequence[float], aligns: Sequence[str],
               rows: Sequence[Sequence[Tuple[str, Optional[str]]]],
               footer: Optional[Sequence[Tuple[str, Optional[str]]]] = None,
               row_height: Optional[float] = None) -> None:
        """
        Vykreslí jednoduchou tabulku bez svislých linek.

        :param weights: relativní šířky sloupců (součet 1.0)
        :param aligns: zarovnání jednotlivých sloupců ('left' / 'right')
        :param rows: řádky jako dvojice (text, barva)
        :param footer: volitelný souhrnný řádek zvýrazněný tučně
        """
        c = self.canvas
        count = len(rows) + (1 if footer else 0)
        if count == 0:
            return

        header_height = 14.0
        available = height - header_height
        if row_height is None:
            row_height = min(15.0, max(9.0, available / max(count, 1)))
        font_size = min(7.4, max(5.6, row_height * 0.55))

        # Hranice sloupců podle relativních vah
        edges = [x]
        for weight in weights:
            edges.append(edges[-1] + width * weight)
        padding = 3.0

        def draw_row(values, top: float, font: str, size: float,
                     default_color: str, line: bool) -> None:
            """Vykreslí jeden řádek tabulky."""
            baseline = top - row_height + (row_height - size) / 2 + size * 0.18
            for column, (text, color) in enumerate(values):
                left, right = edges[column], edges[column + 1]
                c.setFillColor(_c(color or default_color))
                c.setFont(font, size)
                cell_width = right - left - 2 * padding
                clipped = self._clip(str(text), font, size, cell_width)
                if aligns[column] == "right":
                    c.drawRightString(right - padding, baseline, clipped)
                else:
                    c.drawString(left + padding, baseline, clipped)
            if line:
                c.setStrokeColor(_c(theme.HAIRLINE))
                c.setLineWidth(0.4)
                c.line(x, top - row_height, x + width, top - row_height)

        # Hlavička tabulky
        c.setFillColor(_c(theme.INK_MUTED))
        c.setFont(theme.FONT_BOLD, min(6.6, font_size))
        header_baseline = y + height - header_height + 4
        for column, title in enumerate(headers):
            left, right = edges[column], edges[column + 1]
            clipped = self._clip(title, theme.FONT_BOLD, min(6.6, font_size),
                                 right - left - 2 * padding)
            if aligns[column] == "right":
                c.drawRightString(right - padding, header_baseline, clipped)
            else:
                c.drawString(left + padding, header_baseline, clipped)
        c.setStrokeColor(_c(theme.AXIS))
        c.setLineWidth(0.6)
        c.line(x, y + height - header_height, x + width, y + height - header_height)

        # Datové řádky
        cursor = y + height - header_height
        for index, values in enumerate(rows):
            # Jemné pruhování zlepšuje čitelnost dlouhých tabulek
            if index % 2 == 1:
                c.setFillColor(_c(theme.PAGE))
                c.rect(x, cursor - row_height, width, row_height, stroke=0, fill=1)
            draw_row(values, cursor, theme.FONT_REGULAR, font_size,
                     theme.INK_SECONDARY, line=False)
            cursor -= row_height

        if footer:
            c.setStrokeColor(_c(theme.AXIS))
            c.setLineWidth(0.6)
            c.line(x, cursor, x + width, cursor)
            draw_row(footer, cursor, theme.FONT_BOLD, font_size, theme.INK, line=False)


def build_report(report: Mt5Report, metrics: Metrics, path: str) -> str:
    """Vygeneruje PDF report do zadaného souboru."""
    return ReportPdf(report, metrics).build(path)
