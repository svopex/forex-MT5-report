"""
Vykreslení grafů reportu pomocí matplotlibu.

Každá funkce vrací PNG jako bajty (ReportLab je vkládá přes ImageReader).
Grafy záměrně používají tenké značky, vlasovou mřížku a přímé popisky jen tam,
kde nesou informaci – hustota popisků je největší zdroj nečitelnosti.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MaxNLocator

from . import theme
from .formatting import cs_number, plural, signed_money
from .metrics import GroupStats, Metrics, StrategyMetrics
from .mt5_parser import Position
from .periods import Period


# Výchozí rozlišení rastru vkládaného do PDF
DPI = 220


def init_style() -> None:
    """Nastaví globální styl matplotlibu podle motivu reportu."""
    family = theme.matplotlib_font_family()
    plt.rcParams.update({
        "font.family": family,
        "font.size": 8.5,
        "figure.facecolor": theme.SURFACE,
        "axes.facecolor": theme.SURFACE,
        "axes.edgecolor": theme.AXIS,
        "axes.labelcolor": theme.INK_SECONDARY,
        "axes.titlecolor": theme.INK,
        "axes.linewidth": 0.6,
        "axes.grid": True,
        "grid.color": theme.GRID,
        "grid.linewidth": 0.6,
        "grid.linestyle": "-",           # mřížka je vždy plná vlasová linka
        "xtick.color": theme.INK_MUTED,
        "ytick.color": theme.INK_MUTED,
        "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5,
        "legend.frameon": False,
        "legend.fontsize": 7.5,
        "savefig.facecolor": theme.SURFACE,
        "figure.autolayout": False,
    })


def _finish(fig) -> bytes:
    """Uzavře figuru a vrátí ji jako PNG v bajtech."""
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=DPI)
    plt.close(fig)
    return buffer.getvalue()


def _style_axes(ax, *, x_grid: bool = False, y_grid: bool = True) -> None:
    """Sjednotí vzhled os: bez horního a pravého rámečku, jen vlasová mřížka."""
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(theme.AXIS)
    ax.spines["bottom"].set_color(theme.AXIS)
    ax.grid(False)
    if y_grid:
        ax.grid(True, axis="y", zorder=0)
    if x_grid:
        ax.grid(True, axis="x", zorder=0)
    ax.set_axisbelow(True)


def _money_formatter(ax, axis: str = "y"):
    """
    Formátovač peněžní osy s přesností odvozenou od rozestupu popisků.

    Bez toho by se u malých rozsahů (např. pokles v řádu desetin) sousední
    popisky zaokrouhlily na stejné číslo a osa by měla dvakrát "0".
    """
    def fmt(value, _pos):
        ticks = ax.get_yticks() if axis == "y" else ax.get_xticks()
        if len(ticks) > 1:
            step = min(abs(b - a) for a, b in zip(ticks, ticks[1:]))
        else:
            step = abs(value) or 1.0
        if step >= 1:
            decimals = 0
        elif step >= 0.01:
            decimals = 2
        else:
            decimals = 4
        return cs_number(value, decimals)
    return FuncFormatter(fmt)


def _fmt_money(value: float, currency: str = "", decimals: Optional[int] = 2) -> str:
    """
    Naformátuje částku včetně měny.

    Při decimals=None se přesnost volí podle řádu hodnoty, aby se drobné
    částky nezobrazily jako nula.
    """
    if decimals is None:
        decimals = 0 if abs(value) >= 100 else 2
    text = cs_number(value, decimals)
    return f"{text} {currency}".strip()


def _series_decimals(values: Sequence[float]) -> int:
    """
    Zvolí jednotný počet desetinných míst pro celou sadu popisků.

    Přesnost se řídí největší hodnotou v sadě – kdyby ji každý popisek volil
    sám, sousední čísla by měla různý počet desetinných míst.
    """
    largest = max((abs(v) for v in values), default=0.0)
    return 0 if largest >= 100 else 2


def _category_limits(ax, count: int, minimum: int, horizontal: bool = False) -> None:
    """
    Rozšíří kategoriální osu tak, aby sloupce nebyly nepřiměřeně široké.

    Při jedné či dvou kategoriích by sloupec vyplnil celou plochu grafu, což
    působí jako chyba. Rozsah proto vycentrujeme na zadané minimum pozic.
    """
    if count <= 0:
        return
    span = max(count, minimum)
    center = (count - 1) / 2.0
    low, high = center - span / 2.0, center + span / 2.0
    if horizontal:
        ax.set_ylim(low, high)
    else:
        ax.set_xlim(low, high)


def _pl_colors(values: Sequence[float]) -> List[str]:
    """Přiřadí sloupcům stavovou barvu podle znaménka výsledku."""
    return [theme.PROFIT if v > 0 else (theme.LOSS if v < 0 else theme.INK_MUTED) for v in values]


def _date_label(value: float, _pos=None) -> str:
    """
    Popisek data ve tvaru "5. 8." bez úvodních nul.

    Datum sestavujeme ručně, protože formát "%-d" zná jen POSIX; na Windows
    by strftime skončil chybou "Invalid format string".
    """
    moment = mdates.num2date(value)
    return f"{moment.day}. {moment.month}."


def _date_locator(ax, period_kind: str) -> None:
    """Nastaví formát časové osy podle délky zobrazeného období."""
    if period_kind == "day":
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=8))
    elif period_kind in ("week", "month"):
        ax.xaxis.set_major_formatter(FuncFormatter(_date_label))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=9))
    else:
        ax.xaxis.set_major_formatter(FuncFormatter(_date_label))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=10))


# ---------------------------------------------------------------------------
# Jednotlivé grafy
# ---------------------------------------------------------------------------


def _step_series(curve: Sequence[Tuple[datetime, float]], end: datetime,
                 shift: float = 0.0) -> Tuple[List[datetime], List[float]]:
    """
    Rozloží křivku na časy a hodnoty pro schodový graf.

    Poslední bod protáhne do konce období, aby křivka nekončila "ve vzduchu"
    a křivky více řad končily ve stejném místě.

    :param curve: body (čas, hodnota) seřazené podle času
    :param end: konec období
    :param shift: hodnota odečtená od všech bodů (např. počáteční zůstatek)
    """
    times = [t for t, _ in curve]
    values = [v - shift for _, v in curve]
    if times and times[-1] < end:
        times.append(end)
        values.append(values[-1])
    return times, values


def equity_chart(metrics: Metrics, size: Tuple[float, float] = (7.6, 2.6),
                 relative: bool = False) -> bytes:
    """
    Vývoj zůstatku účtu v čase.

    Zůstatek se mění skokově při uzavření obchodu, proto schodová křivka.

    :param relative: místo zůstatku vykreslit kumulativní výsledek od nuly
        (používá se u strategie, kde zůstatek účtu nemá smysl)
    """
    fig, ax = plt.subplots(figsize=size, layout="constrained")
    # V relativním režimu odečteme počáteční zůstatek, křivka pak začíná na nule
    reference = 0.0 if relative else metrics.opening_balance
    quantity = "Výsledek" if relative else "Zůstatek"
    times, values = _step_series(metrics.equity_curve, metrics.period.end,
                                 shift=metrics.opening_balance if relative else 0.0)

    ax.fill_between(times, values, reference,
                    step="post", color=theme.ACCENT, alpha=0.10, linewidth=0, zorder=1)
    ax.plot(times, values, drawstyle="steps-post",
            color=theme.ACCENT, linewidth=1.8, zorder=3, label=quantity)
    # Referenční linie počátečního zůstatku (v relativním režimu nuly)
    ax.axhline(reference, color=theme.AXIS, linewidth=0.9, zorder=2)

    # Přímý popisek jen u koncové hodnoty – ostatní nese osa
    if times:
        end_color = theme.PROFIT_TEXT if values[-1] >= reference else theme.LOSS_TEXT
        ax.annotate(
            signed_money(values[-1], metrics.currency) if relative
            else _fmt_money(values[-1], metrics.currency),
            xy=(times[-1], values[-1]),
            xytext=(-4, 7), textcoords="offset points",
            ha="right", va="bottom", fontsize=8, fontweight="bold", color=end_color,
        )

    _style_axes(ax)
    _date_locator(ax, metrics.period.kind)
    ax.yaxis.set_major_formatter(_money_formatter(ax, "y"))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
    ax.set_ylabel(f"{quantity} ({metrics.currency})", fontsize=7.5)
    ax.margins(x=0.01, y=0.12)
    return _finish(fig)


def drawdown_chart(metrics: Metrics, size: Tuple[float, float] = (7.6, 1.7)) -> bytes:
    """Pokles zůstatku od posledního maxima (underwater křivka)."""
    fig, ax = plt.subplots(figsize=size, layout="constrained")
    times, values = _step_series(metrics.drawdown_curve, metrics.period.end)

    ax.fill_between(times, values, 0, step="post",
                    color=theme.LOSS, alpha=0.16, linewidth=0, zorder=1)
    ax.plot(times, values, drawstyle="steps-post", color=theme.LOSS, linewidth=1.4, zorder=3)
    ax.axhline(0, color=theme.AXIS, linewidth=0.9, zorder=2)

    # Popisek u nejhlubšího poklesu
    if values and min(values) < 0:
        index = min(range(len(values)), key=lambda i: values[i])
        # Podle polohy extrému volíme stranu popisku, aby nepřetekl mimo osy
        relative = index / max(1, len(values) - 1)
        align = "left" if relative < 0.15 else ("right" if relative > 0.85 else "center")
        offset_x = 3 if align == "left" else (-3 if align == "right" else 0)
        ax.annotate(
            f"max. pokles {_fmt_money(abs(values[index]), metrics.currency)} "
            f"({cs_number(metrics.max_drawdown_pct, 2)} %)",
            xy=(times[index], values[index]),
            xytext=(offset_x, -5), textcoords="offset points",
            ha=align, va="top", fontsize=7.5, color=theme.LOSS_TEXT,
        )

    _style_axes(ax)
    _date_locator(ax, metrics.period.kind)
    ax.yaxis.set_major_formatter(_money_formatter(ax, "y"))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=3))
    ax.set_ylabel(f"Pokles ({metrics.currency})", fontsize=7.5)
    ax.margins(x=0.01, y=0.25)
    return _finish(fig)


def bucket_chart(metrics: Metrics, size: Tuple[float, float] = (3.65, 2.2)) -> bytes:
    """Výsledek po časových úsecích (hodina / den / týden / měsíc podle období)."""
    groups = metrics.by_bucket
    fig, ax = plt.subplots(figsize=size, layout="constrained")
    labels = [g.key for g in groups]
    values = [g.net for g in groups]
    positions = range(len(groups))

    ax.bar(positions, values, width=0.55,
           color=_pl_colors(values), linewidth=0, zorder=3)
    ax.axhline(0, color=theme.AXIS, linewidth=0.9, zorder=2)

    _style_axes(ax)
    ax.set_xticks(list(positions))
    # U hustých os popisky prořídíme, aby se nepřekrývaly
    step = max(1, len(labels) // 12 + 1)
    ax.set_xticklabels(
        [label if i % step == 0 else "" for i, label in enumerate(labels)],
        rotation=45 if len(labels) > 6 else 0,
        ha="right" if len(labels) > 6 else "center",
    )
    ax.yaxis.set_major_formatter(_money_formatter(ax, "y"))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
    ax.set_ylabel(f"Výsledek ({metrics.currency})", fontsize=7.5)
    ax.margins(y=0.18)
    _category_limits(ax, len(groups), minimum=6)
    return _finish(fig)


def symbol_chart(metrics: Metrics, size: Tuple[float, float] = (3.65, 2.2),
                 limit: int = 10) -> bytes:
    """Čistý výsledek podle obchodovaného symbolu (nejvýraznější nahoře)."""
    return _net_bars_chart(metrics.by_symbol, metrics.currency, size, limit)


def strategy_chart(strategies: Sequence[StrategyMetrics], currency: str,
                   size: Tuple[float, float] = (3.65, 2.2), limit: int = 10) -> bytes:
    """Čistý výsledek podle strategie (magic number), nejlepší nahoře."""
    return _net_bars_chart([s.group for s in strategies], currency, size, limit)


def _net_bars_chart(source: Sequence[GroupStats], currency: str,
                    size: Tuple[float, float], limit: int) -> bytes:
    """
    Vodorovné sloupce čistého výsledku skupin (symbolů, strategií …).

    Zobrazí se nejvýše `limit` skupin s nejvýraznějším výsledkem; seřazené
    jsou tak, aby nejlepší skupina byla nahoře.

    :param source: souhrny skupin; popiskem osy je jejich klíč
    :param currency: měna účtu pro popisek osy
    """
    groups = sorted(source, key=lambda g: abs(g.net), reverse=True)[:limit]
    groups = sorted(groups, key=lambda g: g.net)

    fig, ax = plt.subplots(figsize=size, layout="constrained")
    labels = [g.key for g in groups]
    values = [g.net for g in groups]
    positions = range(len(groups))

    ax.barh(positions, values, height=0.5, color=_pl_colors(values), linewidth=0, zorder=3)
    ax.axvline(0, color=theme.AXIS, linewidth=0.9, zorder=2)

    # Přímé popisky hodnot u konce sloupce (vně, aby se nemohly oříznout)
    span = max((abs(v) for v in values), default=1.0) or 1.0
    decimals = _series_decimals(values)
    for index, value in enumerate(values):
        offset = span * 0.03
        ax.text(
            value + (offset if value >= 0 else -offset), index,
            _fmt_money(value, decimals=decimals),
            va="center", ha="left" if value >= 0 else "right",
            fontsize=7, color=theme.PROFIT_TEXT if value >= 0 else theme.LOSS_TEXT,
        )

    _style_axes(ax, x_grid=True, y_grid=False)
    ax.set_yticks(list(positions))
    ax.set_yticklabels(labels, fontsize=7.5, color=theme.INK_SECONDARY)
    ax.xaxis.set_major_formatter(_money_formatter(ax, "x"))
    ax.xaxis.set_major_locator(MaxNLocator(nbins=4))
    ax.set_xlabel(f"Výsledek ({currency})", fontsize=7.5)
    ax.margins(x=0.22)
    _category_limits(ax, len(groups), minimum=5, horizontal=True)
    return _finish(fig)


# Nejvyšší počet strategií s vlastní barvou v grafu průběhu; kategoriální
# paleta má jen osm slotů a necykluje se, zbytek se sloučí do "Ostatní"
MAX_STRATEGY_SERIES = len(theme.SERIES)


def _cumulative_curve(positions: Sequence[Position],
                      period: Period) -> List[Tuple[datetime, float]]:
    """
    Kumulativní čistý výsledek obchodů v čase, začínající nulou na začátku období.

    Používá se jen pro sloučenou řadu "Ostatní"; jednotlivé strategie mají
    křivku spočtenou už v metrikách. Obchody pocházejí z více strategií,
    proto je musíme znovu seřadit podle času uzavření.
    """
    curve: List[Tuple[datetime, float]] = [(period.start, 0.0)]
    total = 0.0
    for position in sorted(positions, key=lambda p: p.close_time or period.end):
        total += position.net_profit
        curve.append((position.close_time or period.end, total))
    return curve


def _strategy_series(strategies: Sequence[StrategyMetrics],
                     period: Period) -> List[Tuple[str, str, List, List[float]]]:
    """
    Připraví řady pro graf průběhu strategií.

    Barva patří strategii, ne jejímu pořadí podle výsledku: strategie se
    řadí podle magic number (neznámé na konec) a barvy se přidělují v pevném
    pořadí palety. Při více strategiích, než má paleta barev, si vlastní
    barvu ponechají ty s nejvýraznějším výsledkem a ostatní se sloučí do
    jedné šedé řady "Ostatní".

    :return: seznam čtveřic (popisek, barva, časy, hodnoty)
    """
    ordered = sorted(strategies, key=lambda s: s.magic_order)
    folded: List[StrategyMetrics] = []
    if len(ordered) > MAX_STRATEGY_SERIES:
        # Magic number je mezi strategiemi jedinečné, slouží proto jako klíč
        significant = sorted(ordered, key=lambda s: abs(s.metrics.net_profit), reverse=True)
        kept = {s.magic for s in significant[:MAX_STRATEGY_SERIES - 1]}
        folded = [s for s in ordered if s.magic not in kept]
        ordered = [s for s in ordered if s.magic in kept]

    series = []
    for index, strategy in enumerate(ordered):
        # Křivka zůstatku strategie začíná počátečním zůstatkem účtu;
        # po jeho odečtení zbude kumulativní výsledek strategie
        m = strategy.metrics
        times, values = _step_series(m.equity_curve, period.end, shift=m.opening_balance)
        series.append((strategy.label, theme.SERIES[index], times, values))
    if folded:
        merged = [p for s in folded for p in s.metrics.positions]
        times, values = _step_series(_cumulative_curve(merged, period), period.end)
        series.append((f"Ostatní ({len(folded)})", theme.INK_MUTED, times, values))
    return series


def strategy_curves_chart(strategies: Sequence[StrategyMetrics], period: Period,
                          currency: str, size: Tuple[float, float] = (7.6, 2.6)) -> bytes:
    """
    Kumulativní výsledek jednotlivých strategií v čase – jedna čára na strategii.

    Legenda je vždy nad grafem; při nejvýše čtyřech strategiích se konečná
    hodnota vypíše i přímo u konce čáry, pokud se popisky nepřekrývají.
    """
    series = _strategy_series(strategies, period)
    fig, ax = plt.subplots(figsize=size, layout="constrained")

    for label, color, times, values in series:
        ax.plot(times, values, drawstyle="steps-post", color=color, linewidth=1.6,
                solid_joinstyle="round", solid_capstyle="round", zorder=3, label=label)
    ax.axhline(0, color=theme.AXIS, linewidth=0.9, zorder=2)

    _style_axes(ax)
    _date_locator(ax, period.kind)
    ax.yaxis.set_major_formatter(_money_formatter(ax, "y"))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
    ax.set_ylabel(f"Výsledek ({currency})", fontsize=7.5)
    ax.margins(x=0.01, y=0.14)

    # Přímé popisky konečných hodnot: jen u malého počtu řad a jen tehdy,
    # když jsou konce čar dost daleko od sebe (jinak by se popisky slily
    # a identitu nese legenda)
    ends = sorted(values[-1] for _, _, _, values in series)
    low, high = ax.get_ylim()
    spacing = (high - low) * 0.07
    apart = all(b - a >= spacing for a, b in zip(ends, ends[1:]))
    if len(series) <= 4 and apart:
        left, right = ax.get_xlim()
        # Vpravo uvolníme místo, aby se popisky vešly za konec čar
        ax.set_xlim(left, right + (right - left) * 0.11)
        decimals = _series_decimals(ends)
        for _, _, times, values in series:
            ax.annotate(
                signed_money(values[-1], decimals=decimals),
                xy=(times[-1], values[-1]), xytext=(4, 0), textcoords="offset points",
                ha="left", va="center", fontsize=7.5, fontweight="bold",
                color=theme.PROFIT_TEXT if values[-1] >= 0 else theme.LOSS_TEXT,
            )

    # Legenda nad plochou grafu, aby nezakrývala čáry
    fig.legend(loc="outside upper left", ncol=min(len(series), 5), fontsize=7.5,
               handlelength=1.6, columnspacing=1.4, labelcolor=theme.INK_SECONDARY)
    return _finish(fig)


def _zero_aligned_bins(values: Sequence[float], target: int) -> List[float]:
    """
    Sestaví hranice intervalů histogramu zarovnané na nulu.

    Nula musí být hranicí intervalu, jinak by jeden sloupec obsahoval zároveň
    ziskové i ztrátové obchody a jeho barva by lhala.
    """
    if not values:
        return [0.0, 1.0]
    low, high = min(values), max(values)
    span = max(abs(low), abs(high)) or 1.0
    width = span / max(1, target // 2)
    edges: List[float] = [0.0]
    cursor = 0.0
    while cursor < high + width:
        cursor += width
        edges.append(cursor)
    cursor = 0.0
    while cursor > low - width:
        cursor -= width
        edges.insert(0, cursor)
    return edges


def distribution_chart(metrics: Metrics, size: Tuple[float, float] = (3.65, 2.2)) -> bytes:
    """Rozdělení výsledků jednotlivých obchodů (histogram)."""
    results = metrics.trade_results
    fig, ax = plt.subplots(figsize=size, layout="constrained")
    bins = _zero_aligned_bins(results, target=min(18, max(6, len(results) // 3)))

    counts, edges, patches = ax.hist(results, bins=bins, linewidth=1.2,
                                     edgecolor=theme.SURFACE, zorder=3)
    # Barva podle toho, na které straně nuly interval leží
    for patch, left, right in zip(patches, edges[:-1], edges[1:]):
        middle = (left + right) / 2
        patch.set_facecolor(theme.PROFIT if middle > 0 else theme.LOSS)
    ax.axvline(0, color=theme.AXIS, linewidth=0.9, zorder=4)

    _style_axes(ax)
    ax.xaxis.set_major_formatter(_money_formatter(ax, "x"))
    ax.xaxis.set_major_locator(MaxNLocator(nbins=5))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=4, integer=True))
    ax.set_xlabel(f"Výsledek obchodu ({metrics.currency})", fontsize=7.5)
    ax.set_ylabel("Počet obchodů", fontsize=7.5)
    ax.margins(x=0.02)
    return _finish(fig)


def weekday_chart(metrics: Metrics, size: Tuple[float, float] = (3.65, 2.2)) -> bytes:
    """Výsledek podle dne v týdnu, kdy byl obchod uzavřen."""
    groups = metrics.by_weekday
    fig, ax = plt.subplots(figsize=size, layout="constrained")
    labels = [g.key[:2] for g in groups]
    values = [g.net for g in groups]
    positions = range(len(groups))

    ax.bar(positions, values, width=0.5, color=_pl_colors(values), linewidth=0, zorder=3)
    ax.axhline(0, color=theme.AXIS, linewidth=0.9, zorder=2)

    # Nad sloupcem uvádíme počet obchodů – doplňuje informaci, kterou osa nenese
    span = max((abs(v) for v in values), default=1.0) or 1.0
    for index, group in enumerate(groups):
        value = group.net
        ax.text(
            index, value + (span * 0.06 if value >= 0 else -span * 0.06),
            f"{group.trades}×",
            ha="center", va="bottom" if value >= 0 else "top",
            fontsize=7, color=theme.INK_MUTED,
        )

    _style_axes(ax)
    ax.set_xticks(list(positions))
    ax.set_xticklabels(labels, fontsize=7.5, color=theme.INK_SECONDARY)
    ax.yaxis.set_major_formatter(_money_formatter(ax, "y"))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
    ax.set_ylabel(f"Výsledek ({metrics.currency})", fontsize=7.5)
    ax.margins(y=0.28)
    _category_limits(ax, len(groups), minimum=5)
    return _finish(fig)


def direction_chart(metrics: Metrics, size: Tuple[float, float] = (3.65, 2.2)) -> bytes:
    """Porovnání dlouhých a krátkých pozic – výsledek a úspěšnost."""
    groups = metrics.by_direction
    fig, ax = plt.subplots(figsize=size, layout="constrained")
    labels = [f"{g.key}\n{plural(g.trades, 'obchod', 'obchody', 'obchodů')} · "
              f"úspěšnost {g.win_rate:.0f} %" for g in groups]
    values = [g.net for g in groups]
    positions = range(len(groups))

    ax.barh(positions, values, height=0.34, color=_pl_colors(values), linewidth=0, zorder=3)
    ax.axvline(0, color=theme.AXIS, linewidth=0.9, zorder=2)

    span = max((abs(v) for v in values), default=1.0) or 1.0
    decimals = _series_decimals(values)
    for index, value in enumerate(values):
        offset = span * 0.04
        ax.text(
            value + (offset if value >= 0 else -offset), index,
            _fmt_money(value, decimals=decimals),
            va="center", ha="left" if value >= 0 else "right",
            fontsize=7.5, fontweight="bold",
            color=theme.PROFIT_TEXT if value >= 0 else theme.LOSS_TEXT,
        )

    _style_axes(ax, x_grid=True, y_grid=False)
    ax.set_yticks(list(positions))
    ax.set_yticklabels(labels, fontsize=7.5, color=theme.INK_SECONDARY)
    ax.xaxis.set_major_formatter(_money_formatter(ax, "x"))
    ax.xaxis.set_major_locator(MaxNLocator(nbins=4))
    ax.set_xlabel(f"Výsledek ({metrics.currency})", fontsize=7.5)
    ax.margins(x=0.28)
    _category_limits(ax, len(groups), minimum=3, horizontal=True)
    return _finish(fig)


def top_trades_chart(metrics: Metrics, size: Tuple[float, float] = (3.65, 2.2),
                     count: int = 5) -> bytes:
    """Nejlepší a nejhorší jednotlivé obchody v období."""
    ordered = sorted(metrics.positions, key=lambda p: p.net_profit)
    worst = ordered[:count]
    best = ordered[-count:]
    # Při malém počtu obchodů se množiny mohou překrývat – ponecháme unikátní
    selection = {p.ticket: p for p in worst}
    selection.update({p.ticket: p for p in best})
    chosen = sorted(selection.values(), key=lambda p: p.net_profit)

    fig, ax = plt.subplots(figsize=size, layout="constrained")
    labels = [f"{p.symbol} {p.direction}" for p in chosen]
    values = [p.net_profit for p in chosen]
    positions = range(len(chosen))

    ax.barh(positions, values, height=0.5, color=_pl_colors(values), linewidth=0, zorder=3)
    ax.axvline(0, color=theme.AXIS, linewidth=0.9, zorder=2)

    span = max((abs(v) for v in values), default=1.0) or 1.0
    decimals = _series_decimals(values)
    for index, value in enumerate(values):
        offset = span * 0.03
        ax.text(
            value + (offset if value >= 0 else -offset), index,
            _fmt_money(value, decimals=decimals),
            va="center", ha="left" if value >= 0 else "right",
            fontsize=7, color=theme.PROFIT_TEXT if value >= 0 else theme.LOSS_TEXT,
        )

    _style_axes(ax, x_grid=True, y_grid=False)
    ax.set_yticks(list(positions))
    ax.set_yticklabels(labels, fontsize=7, color=theme.INK_SECONDARY)
    ax.xaxis.set_major_formatter(_money_formatter(ax, "x"))
    ax.xaxis.set_major_locator(MaxNLocator(nbins=4))
    ax.set_xlabel(f"Výsledek obchodu ({metrics.currency})", fontsize=7.5)
    ax.margins(x=0.22)
    _category_limits(ax, len(chosen), minimum=5, horizontal=True)
    return _finish(fig)


def win_loss_chart(metrics: Metrics, size: Tuple[float, float] = (3.65, 2.2)) -> bytes:
    """
    Struktura obchodů: podíl ziskových a ztrátových a jejich průměrná velikost.

    Místo koláče používáme dva doplňující se pohledy na jedné ose – podíl
    a průměrnou velikost obchodu, aby graf nesl víc než jediné číslo.
    """
    fig, ax = plt.subplots(figsize=size, layout="constrained")
    values = [metrics.avg_win, metrics.avg_loss]
    labels = [
        f"Průměrný zisk\n{plural(metrics.wins, 'ziskový obchod', 'ziskové obchody', 'ziskových obchodů')}",
        f"Průměrná ztráta\n{plural(metrics.losses, 'ztrátový obchod', 'ztrátové obchody', 'ztrátových obchodů')}",
    ]

    ax.barh([0, 1], values, height=0.34, color=[theme.PROFIT, theme.LOSS],
            linewidth=0, zorder=3)
    ax.axvline(0, color=theme.AXIS, linewidth=0.9, zorder=2)

    span = max((abs(v) for v in values), default=1.0) or 1.0
    decimals = _series_decimals(values)
    for index, value in enumerate(values):
        offset = span * 0.04
        ax.text(
            value + (offset if value >= 0 else -offset), index,
            _fmt_money(value, decimals=decimals),
            va="center", ha="left" if value >= 0 else "right",
            fontsize=7.5, fontweight="bold",
            color=theme.PROFIT_TEXT if value >= 0 else theme.LOSS_TEXT,
        )

    _style_axes(ax, x_grid=True, y_grid=False)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(labels, fontsize=7.5, color=theme.INK_SECONDARY)
    ax.xaxis.set_major_formatter(_money_formatter(ax, "x"))
    ax.xaxis.set_major_locator(MaxNLocator(nbins=4))
    ax.set_xlabel(f"Velikost obchodu ({metrics.currency})", fontsize=7.5)
    ax.margins(x=0.28)
    _category_limits(ax, 2, minimum=3, horizontal=True)
    return _finish(fig)
