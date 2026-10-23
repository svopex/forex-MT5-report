"""
Výpočet obchodních metrik nad vyfiltrovanou množinou pozic.

Za jeden obchod se považuje jedna uzavřená pozice; jeho výsledek je čistý,
tedy včetně provize a swapu (`Position.net_profit`). Součet čistých výsledků
proto odpovídá změně zůstatku účtu za dané období.
"""

from __future__ import annotations

import math
import statistics
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from .mt5_parser import Mt5Report, Position
from .periods import Period


@dataclass
class GroupStats:
    """Souhrn za skupinu obchodů (symbol, směr, den v týdnu, časové okno …)."""

    key: str
    trades: int = 0
    wins: int = 0
    losses: int = 0
    net: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    volume: float = 0.0

    @property
    def win_rate(self) -> float:
        """Podíl ziskových obchodů v procentech."""
        return 100.0 * self.wins / self.trades if self.trades else 0.0

    @property
    def profit_factor(self) -> Optional[float]:
        """Poměr hrubého zisku ke hrubé ztrátě; None, pokud nebyla žádná ztráta."""
        if self.gross_loss == 0:
            return None
        return self.gross_profit / abs(self.gross_loss)


@dataclass
class Metrics:
    """Kompletní sada metrik reportu za zvolené období."""

    period: Period
    currency: str = "USD"

    # Základní počty
    trades: int = 0
    wins: int = 0
    losses: int = 0
    breakeven: int = 0

    # Výsledky
    net_profit: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    commission: float = 0.0
    swap: float = 0.0
    volume: float = 0.0

    # Zůstatek
    opening_balance: float = 0.0
    closing_balance: float = 0.0
    peak_balance: float = 0.0
    # Okamžik, kdy zůstatek naposledy stál na svém maximu (None = maximem je
    # počáteční zůstatek)
    peak_time: Optional[datetime] = None

    # Rozšířené ukazatele
    largest_win: float = 0.0
    largest_loss: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    # Lokální maximum zůstatku, od kterého se měří maximální pokles, a jeho čas
    # (None = maximem je počáteční zůstatek)
    max_drawdown_peak: float = 0.0
    max_drawdown_peak_time: Optional[datetime] = None
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    max_consecutive_win_amount: float = 0.0
    max_consecutive_loss_amount: float = 0.0
    sharpe_ratio: Optional[float] = None
    avg_duration_minutes: Optional[float] = None
    trading_days: int = 0
    best_day: Optional[Tuple[date, float]] = None
    worst_day: Optional[Tuple[date, float]] = None

    # Rozpady
    by_symbol: List[GroupStats] = field(default_factory=list)
    by_direction: List[GroupStats] = field(default_factory=list)
    by_weekday: List[GroupStats] = field(default_factory=list)
    by_bucket: List[GroupStats] = field(default_factory=list)   # časová osa (den/týden/měsíc)
    bucket_label: str = "Den"

    # Podklady pro grafy
    equity_curve: List[Tuple[datetime, float]] = field(default_factory=list)
    drawdown_curve: List[Tuple[datetime, float]] = field(default_factory=list)
    trade_results: List[float] = field(default_factory=list)
    positions: List[Position] = field(default_factory=list)

    # ---- odvozené vlastnosti -------------------------------------------------

    @property
    def win_rate(self) -> float:
        """Úspěšnost v procentech (ziskové obchody / všechny obchody)."""
        return 100.0 * self.wins / self.trades if self.trades else 0.0

    @property
    def profit_factor(self) -> Optional[float]:
        """Profit factor: hrubý zisk / hrubá ztráta."""
        if self.gross_loss == 0:
            return None
        return self.gross_profit / abs(self.gross_loss)

    @property
    def expectancy(self) -> float:
        """Průměrný výnos na jeden obchod."""
        return self.net_profit / self.trades if self.trades else 0.0

    @property
    def payoff_ratio(self) -> Optional[float]:
        """
        Poměr průměrného zisku k průměrné ztrátě (RRR).

        Bez ziskového nebo bez ztrátového obchodu poměr nelze určit – chybí
        vzorek jedné ze stran – a vrací se None.
        """
        if not self.avg_loss or not self.avg_win:
            return None
        return self.avg_win / abs(self.avg_loss)

    @property
    def return_pct(self) -> float:
        """Zhodnocení počátečního zůstatku za období v procentech."""
        if not self.opening_balance:
            return 0.0
        return 100.0 * self.net_profit / self.opening_balance

    @property
    def recovery_factor(self) -> Optional[float]:
        """Poměr čistého zisku k maximálnímu poklesu."""
        if self.max_drawdown <= 0:
            return None
        return self.net_profit / self.max_drawdown

    @property
    def current_drawdown(self) -> float:
        """
        Pokles zůstatku po posledním obchodu od nejvyššího dosaženého zůstatku.

        Zaokrouhluje se na haléře, aby zbytky součtu v plovoucí čárce
        nevypadaly jako pokles.
        """
        return round(self.peak_balance - self.closing_balance, 2)

    @property
    def is_empty(self) -> bool:
        """True, pokud za období nebyl uzavřen žádný obchod."""
        return self.trades == 0


# ---------------------------------------------------------------------------
# Pomocné funkce
# ---------------------------------------------------------------------------

WEEKDAY_NAMES = ["Pondělí", "Úterý", "Středa", "Čtvrtek", "Pátek", "Sobota", "Neděle"]
_MONTH_SHORT = ["led", "úno", "bře", "dub", "kvě", "čvn", "čvc", "srp", "zář", "říj", "lis", "pro"]


def filter_positions(positions: Sequence[Position], period: Period) -> List[Position]:
    """
    Vybere pozice uzavřené v daném období.

    Rozhoduje čas uzavření – realizovaný zisk patří do období, kdy byl realizován.
    """
    return [p for p in positions if period.contains(p.close_time)]


def _bucket_key(moment: datetime, granularity: str) -> Tuple[str, datetime]:
    """
    Vrátí popisek a řadicí klíč časového koše podle zvolené granularity.

    :param granularity: 'hour', 'day', 'week' nebo 'month'
    """
    if granularity == "hour":
        start = moment.replace(minute=0, second=0, microsecond=0)
        return f"{start.hour:02d}:00", start
    if granularity == "day":
        start = datetime.combine(moment.date(), datetime.min.time())
        return f"{moment.day}. {moment.month}.", start
    if granularity == "week":
        monday = moment.date() - timedelta(days=moment.weekday())
        start = datetime.combine(monday, datetime.min.time())
        iso_week = monday.isocalendar()[1]
        return f"{iso_week}. týd.", start
    # month
    start = datetime(moment.year, moment.month, 1)
    return f"{_MONTH_SHORT[moment.month - 1]} {moment.year % 100:02d}", start


def choose_granularity(period: Period) -> Tuple[str, str]:
    """
    Zvolí vhodné dělení časové osy podle délky období.

    Vrací dvojici (granularita, popisek osy).
    """
    if period.kind == "day":
        return "hour", "Hodina uzavření"
    if period.kind == "week":
        return "day", "Den"
    if period.kind == "month":
        return "day", "Den"
    if period.kind == "year":
        return "month", "Měsíc"
    # Celé období – podle skutečného rozsahu
    span = period.days
    if span <= 14:
        return "day", "Den"
    if span <= 120:
        return "week", "Týden"
    return "month", "Měsíc"


def _accumulate(group: GroupStats, position: Position) -> None:
    """Přičte jednu pozici do souhrnu skupiny."""
    net = position.net_profit
    group.trades += 1
    group.net += net
    group.volume += position.volume
    if net > 0:
        group.wins += 1
        group.gross_profit += net
    elif net < 0:
        group.losses += 1
        group.gross_loss += net


def _group_by(positions: Sequence[Position], key_func) -> "OrderedDict[str, GroupStats]":
    """Obecné seskupení pozic podle klíče vráceného funkcí `key_func`."""
    groups: "OrderedDict[str, GroupStats]" = OrderedDict()
    for position in positions:
        key = key_func(position)
        if key not in groups:
            groups[key] = GroupStats(key=key)
        _accumulate(groups[key], position)
    return groups


def _consecutive(results: Sequence[float]) -> Tuple[int, int, float, float]:
    """
    Najde nejdelší série ziskových a ztrátových obchodů.

    Vrací (max výher v řadě, max proher v řadě, částka nejlepší série,
    částka nejhorší série).
    """
    best_wins = best_losses = 0
    best_win_amount = best_loss_amount = 0.0
    run_wins = run_losses = 0
    run_win_amount = run_loss_amount = 0.0

    for value in results:
        if value > 0:
            run_wins += 1
            run_win_amount += value
            run_losses = 0
            run_loss_amount = 0.0
            if run_wins > best_wins:
                best_wins, best_win_amount = run_wins, run_win_amount
        elif value < 0:
            run_losses += 1
            run_loss_amount += value
            run_wins = 0
            run_win_amount = 0.0
            if run_losses > best_losses:
                best_losses, best_loss_amount = run_losses, run_loss_amount
        else:
            # Nulový obchod sérii přerušuje
            run_wins = run_losses = 0
            run_win_amount = run_loss_amount = 0.0

    return best_wins, best_losses, best_win_amount, best_loss_amount


def _sharpe(daily_returns: Sequence[float]) -> Optional[float]:
    """
    Sharpeho poměr z denních výnosů (bezrizikovou sazbu uvažujeme nulovou).

    Výsledek je anualizovaný přes 252 obchodních dnů. Vrací None, pokud není
    dost dat nebo je rozptyl nulový.
    """
    if len(daily_returns) < 2:
        return None
    mean = statistics.fmean(daily_returns)
    stdev = statistics.stdev(daily_returns)
    if stdev == 0:
        return None
    return (mean / stdev) * math.sqrt(252)


# ---------------------------------------------------------------------------
# Hlavní výpočet
# ---------------------------------------------------------------------------


def compute_metrics(report: Mt5Report, period: Period) -> Metrics:
    """
    Spočítá všechny metriky reportu za zvolené období.

    :param report: načtený export z MT5
    :param period: vyhodnocené období
    """
    selected = filter_positions(report.positions, period)
    metrics = Metrics(period=period, currency=report.account.currency or "USD")
    metrics.positions = selected

    # Počáteční zůstatek období = počáteční kapitál + vše realizované před obdobím
    # (včetně vkladů a výběrů, které mohly proběhnout dříve).
    opening = report.initial_balance
    for position in report.positions:
        if position.close_time and position.close_time < period.start:
            opening += position.net_profit
    for deal in report.deposits[1:]:
        if deal.time and deal.time < period.start:
            opening += deal.profit
    metrics.opening_balance = opening

    if not selected:
        metrics.closing_balance = opening
        metrics.peak_balance = opening
        metrics.bucket_label = choose_granularity(period)[1]
        return metrics

    results = [p.net_profit for p in selected]
    metrics.trade_results = results
    metrics.trades = len(selected)
    metrics.wins = sum(1 for v in results if v > 0)
    metrics.losses = sum(1 for v in results if v < 0)
    metrics.breakeven = metrics.trades - metrics.wins - metrics.losses

    metrics.net_profit = sum(results)
    metrics.gross_profit = sum(v for v in results if v > 0)
    metrics.gross_loss = sum(v for v in results if v < 0)
    metrics.commission = sum(p.commission for p in selected)
    metrics.swap = sum(p.swap for p in selected)
    metrics.volume = sum(p.volume for p in selected)

    wins = [v for v in results if v > 0]
    losses = [v for v in results if v < 0]
    # Nejlepší obchod hledáme jen mezi ziskovými – jinak by se při samých
    # ztrátách jako "největší zisk" vykázala nejmenší ztráta
    metrics.largest_win = max(wins) if wins else 0.0
    metrics.largest_loss = min(losses) if losses else 0.0
    metrics.avg_win = statistics.fmean(wins) if wins else 0.0
    metrics.avg_loss = statistics.fmean(losses) if losses else 0.0

    (metrics.max_consecutive_wins, metrics.max_consecutive_losses,
     metrics.max_consecutive_win_amount, metrics.max_consecutive_loss_amount) = _consecutive(results)

    durations = [p.duration_minutes for p in selected if p.duration_minutes is not None]
    metrics.avg_duration_minutes = statistics.fmean(durations) if durations else None

    # Křivka zůstatku a pokles od lokálního maxima; výchozím maximem je
    # počáteční zůstatek (čas None)
    balance = opening
    peak = opening
    peak_time: Optional[datetime] = None
    equity: List[Tuple[datetime, float]] = [(period.start, balance)]
    drawdown: List[Tuple[datetime, float]] = [(period.start, 0.0)]
    max_dd = 0.0
    max_dd_pct = 0.0
    max_dd_peak = opening
    max_dd_peak_time: Optional[datetime] = None
    for position in selected:
        balance += position.net_profit
        moment = position.close_time or period.end
        # Při vyrovnání maxima posuneme i jeho čas – pokles začíná až od
        # posledního okamžiku, kdy zůstatek na maximu stál
        if balance >= peak:
            peak = balance
            peak_time = moment
        dd = peak - balance
        dd_pct = 100.0 * dd / peak if peak else 0.0
        # Spolu s nejhlubším poklesem si pamatujeme maximum, od kterého vznikl
        if dd > max_dd:
            max_dd = dd
            max_dd_peak = peak
            max_dd_peak_time = peak_time
        max_dd_pct = max(max_dd_pct, dd_pct)
        equity.append((moment, balance))
        drawdown.append((moment, -dd))
    metrics.equity_curve = equity
    metrics.drawdown_curve = drawdown
    metrics.closing_balance = balance
    metrics.peak_balance = peak
    metrics.peak_time = peak_time
    metrics.max_drawdown = max_dd
    metrics.max_drawdown_pct = max_dd_pct
    metrics.max_drawdown_peak = max_dd_peak
    metrics.max_drawdown_peak_time = max_dd_peak_time

    # Denní výnosy pro Sharpeho poměr a nej/nejhorší den
    daily: "OrderedDict[date, float]" = OrderedDict()
    for position in selected:
        if position.close_time:
            day = position.close_time.date()
            daily[day] = daily.get(day, 0.0) + position.net_profit
    metrics.trading_days = len(daily)
    if daily:
        best = max(daily.items(), key=lambda item: item[1])
        worst = min(daily.items(), key=lambda item: item[1])
        metrics.best_day, metrics.worst_day = best, worst
        # Denní výnos jako procento zůstatku na začátku období
        base = opening if opening else 1.0
        metrics.sharpe_ratio = _sharpe([value / base for value in daily.values()])

    # Rozpady
    metrics.by_symbol = sorted(
        _group_by(selected, lambda p: p.symbol or "—").values(),
        key=lambda g: g.net,
        reverse=True,
    )
    direction_labels = {"buy": "Dlouhé (buy)", "sell": "Krátké (sell)"}
    metrics.by_direction = list(
        _group_by(selected, lambda p: direction_labels.get(p.direction, p.direction)).values()
    )

    weekday_groups = _group_by(
        selected,
        lambda p: WEEKDAY_NAMES[p.close_time.weekday()] if p.close_time else "—",
    )
    # Dny v týdnu chceme v přirozeném pořadí, ne v pořadí výskytu
    metrics.by_weekday = [weekday_groups[name] for name in WEEKDAY_NAMES if name in weekday_groups]

    granularity, bucket_label = choose_granularity(period)
    metrics.bucket_label = bucket_label
    bucket_order: Dict[str, datetime] = {}

    def bucket_key(position: Position) -> str:
        moment = position.close_time or period.start
        label, order = _bucket_key(moment, granularity)
        bucket_order[label] = order
        return label

    buckets = _group_by(selected, bucket_key)
    ordered = sorted(buckets.values(), key=lambda g: bucket_order[g.key])
    metrics.by_bucket = _fill_gaps(ordered, bucket_order, granularity)

    return metrics


def _fill_gaps(groups: List[GroupStats], order: Dict[str, datetime],
               granularity: str) -> List[GroupStats]:
    """
    Doplní chybějící časové koše prázdnými záznamy.

    Bez toho by sloupcový graf spojil nesousedící období vedle sebe a vzbudil
    dojem souvislé řady (např. chybějící týden bez obchodů).
    """
    if len(groups) < 2:
        return groups

    steps = {
        "hour": timedelta(hours=1),
        "day": timedelta(days=1),
        "week": timedelta(days=7),
    }
    filled: List[GroupStats] = []
    for index, group in enumerate(groups):
        filled.append(group)
        if index + 1 >= len(groups):
            break
        current = order[group.key]
        following = order[groups[index + 1].key]
        # Měsíce mají proměnnou délku, proto se posouvají zvlášť
        if granularity == "month":
            cursor = current
            while True:
                year, month = cursor.year + (cursor.month // 12), cursor.month % 12 + 1
                cursor = datetime(year, month, 1)
                if cursor >= following:
                    break
                filled.append(GroupStats(key=_bucket_key(cursor, granularity)[0]))
            continue
        step = steps[granularity]
        cursor = current + step
        # Pojistka proti neúměrně dlouhé řadě prázdných košů
        while cursor < following and len(filled) < 400:
            filled.append(GroupStats(key=_bucket_key(cursor, granularity)[0]))
            cursor += step
    return filled
