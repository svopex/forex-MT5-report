"""
Rozbor a vyhodnocení parametru období (`all`, `year=`, `month=`, `week=`, `day=`).

Období se vždy vyhodnocuje vůči datům v souboru, nikoli vůči systémovému datu –
hodnota `last` proto znamená poslední období, ve kterém proběhl nějaký obchod.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional, Sequence


# Podporované druhy období
PERIOD_KINDS = ("all", "year", "month", "week", "day")

# Nápověda zobrazovaná při chybném zadání
PERIOD_HELP = """Podporované hodnoty parametru období:
  all              celé obchodní období obsažené v souboru
  year=2026        kalendářní rok
  year=last        poslední rok s obchodní aktivitou
  month=202608     kalendářní měsíc ve tvaru RRRRMM
  month=last       poslední měsíc s obchodní aktivitou
  week=20260825    týden (pondělí-neděle), do kterého spadá zadaný den RRRRMMDD
  week=last        poslední týden s obchodní aktivitou
  day=20260825     jeden den ve tvaru RRRRMMDD
  day=last         poslední den s obchodní aktivitou"""


class PeriodError(ValueError):
    """Chyba v zadání parametru období."""


@dataclass(frozen=True)
class PeriodSpec:
    """Rozparsovaný parametr období: druh a jeho hodnota ('last' nebo číselný kód)."""

    kind: str
    value: str = ""

    def __str__(self) -> str:
        return self.kind if self.kind == "all" else f"{self.kind}={self.value}"


@dataclass(frozen=True)
class Period:
    """
    Konkrétní vyhodnocené období.

    :param start: začátek intervalu (včetně)
    :param end: konec intervalu (včetně, s časem 23:59:59)
    :param kind: druh období
    :param label: popisek pro hlavičku reportu
    :param short_label: krátký popisek pro název souboru
    """

    start: datetime
    end: datetime
    kind: str
    label: str
    short_label: str

    def contains(self, moment: Optional[datetime]) -> bool:
        """Zjistí, zda daný okamžik spadá do období."""
        if moment is None:
            return False
        return self.start <= moment <= self.end

    @property
    def days(self) -> int:
        """Počet kalendářních dnů, které období pokrývá."""
        return (self.end.date() - self.start.date()).days + 1


# ---------------------------------------------------------------------------
# Parsování parametru
# ---------------------------------------------------------------------------


def parse_period(raw: str) -> PeriodSpec:
    """
    Rozparsuje parametr období z příkazové řádky.

    Akceptuje i tvar bez rovnítka pro `all` a je tolerantní k velikosti písmen
    a oddělovačům v datech (2026-08-25 i 20260825).
    """
    text = (raw or "").strip().lower()
    if not text:
        raise PeriodError("Období nebylo zadáno.\n" + PERIOD_HELP)

    if text == "all":
        return PeriodSpec("all")

    if "=" not in text:
        raise PeriodError(
            f"Neznámý parametr období '{raw}'.\n" + PERIOD_HELP
        )

    kind, _, value = text.partition("=")
    kind = kind.strip()
    value = value.strip().replace("-", "").replace(".", "").replace("/", "")

    if kind not in PERIOD_KINDS:
        raise PeriodError(f"Neznámý druh období '{kind}'.\n" + PERIOD_HELP)
    if kind == "all":
        return PeriodSpec("all")
    if not value:
        raise PeriodError(f"Chybí hodnota u parametru '{kind}'.\n" + PERIOD_HELP)

    if value != "last":
        expected = {"year": 4, "month": 6, "week": 8, "day": 8}[kind]
        if not re.fullmatch(rf"\d{{{expected}}}", value):
            hint = {"year": "RRRR", "month": "RRRRMM", "week": "RRRRMMDD", "day": "RRRRMMDD"}[kind]
            raise PeriodError(
                f"Hodnota '{value}' u parametru '{kind}' nemá očekávaný tvar {hint}.\n"
                + PERIOD_HELP
            )
        # Smysluplnost data ověříme hned, ať se kvůli překlepu zbytečně nečte celý sešit
        if kind == "month":
            month = int(value[4:])
            if not 1 <= month <= 12:
                raise PeriodError(f"Měsíc '{value[4:]}' není platný (očekává se 01–12).")
        elif kind in ("week", "day"):
            _parse_day_value(value)
    return PeriodSpec(kind, value)


# ---------------------------------------------------------------------------
# Vyhodnocení období vůči datům
# ---------------------------------------------------------------------------

_MONTH_NAMES = [
    "leden", "únor", "březen", "duben", "květen", "červen",
    "červenec", "srpen", "září", "říjen", "listopad", "prosinec",
]


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    """Vrátí hranice jednoho dne (00:00:00 až 23:59:59)."""
    return (
        datetime.combine(day, datetime.min.time()),
        datetime.combine(day, datetime.max.time()).replace(microsecond=0),
    )


def _fmt(day: date) -> str:
    """Formátuje datum česky (bez úvodních nul)."""
    return f"{day.day}. {day.month}. {day.year}"


def resolve_period(spec: PeriodSpec, timestamps: Sequence[datetime]) -> Period:
    """
    Vyhodnotí parametr období vůči časovým razítkům obchodů.

    :param spec: rozparsovaný parametr
    :param timestamps: časy uzavření obchodů (alespoň jeden)
    :raises PeriodError: pokud data neobsahují žádný obchod
    """
    stamps: List[datetime] = sorted(t for t in timestamps if t is not None)
    if not stamps:
        raise PeriodError("Soubor neobsahuje žádné uzavřené obchody, report nelze sestavit.")

    first, last = stamps[0], stamps[-1]

    if spec.kind == "all":
        start, _ = _day_bounds(first.date())
        _, end = _day_bounds(last.date())
        return Period(
            start=start,
            end=end,
            kind="all",
            label=f"Celé období · {_fmt(first.date())} – {_fmt(last.date())}",
            short_label="cele-obdobi",
        )

    if spec.kind == "year":
        year = last.year if spec.value == "last" else int(spec.value)
        start, _ = _day_bounds(date(year, 1, 1))
        _, end = _day_bounds(date(year, 12, 31))
        return Period(start, end, "year", f"Rok {year}", f"rok-{year}")

    if spec.kind == "month":
        if spec.value == "last":
            year, month = last.year, last.month
        else:
            year, month = int(spec.value[:4]), int(spec.value[4:])
            if not 1 <= month <= 12:
                raise PeriodError(f"Měsíc '{spec.value[4:]}' není platný (očekává se 01–12).")
        last_day = calendar.monthrange(year, month)[1]
        start, _ = _day_bounds(date(year, month, 1))
        _, end = _day_bounds(date(year, month, last_day))
        return Period(
            start, end, "month",
            f"{_MONTH_NAMES[month - 1].capitalize()} {year}",
            f"mesic-{year}{month:02d}",
        )

    if spec.kind == "week":
        anchor = last.date() if spec.value == "last" else _parse_day_value(spec.value)
        monday = anchor - timedelta(days=anchor.weekday())
        sunday = monday + timedelta(days=6)
        start, _ = _day_bounds(monday)
        _, end = _day_bounds(sunday)
        iso_year, iso_week, _ = monday.isocalendar()
        return Period(
            start, end, "week",
            f"{iso_week}. týden {iso_year} · {_fmt(monday)} – {_fmt(sunday)}",
            f"tyden-{iso_year}W{iso_week:02d}",
        )

    # spec.kind == "day"
    day = last.date() if spec.value == "last" else _parse_day_value(spec.value)
    start, end = _day_bounds(day)
    weekday = ["pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle"][day.weekday()]
    return Period(
        start, end, "day",
        f"{_fmt(day)} ({weekday})",
        f"den-{day.strftime('%Y%m%d')}",
    )


def _parse_day_value(value: str) -> date:
    """Převede hodnotu RRRRMMDD na datum, s hlášením chyby v češtině."""
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError as exc:
        raise PeriodError(f"Datum '{value}' není platné (očekává se tvar RRRRMMDD).") from exc
