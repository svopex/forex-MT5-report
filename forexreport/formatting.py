"""
Jednotné formátování čísel, částek a časů podle českých zvyklostí.

Používá se v grafech i v PDF, aby byl report v obou vrstvách konzistentní.
Jako oddělovač tisíců je pevná (nezalomitelná) mezera, desetinným oddělovačem
je čárka.
"""

from __future__ import annotations

import re
from typing import Optional

NBSP = " "


def cs_number(value: float, decimals: int = 2) -> str:
    """
    Naformátuje číslo česky (mezera po tisících, desetinná čárka).

    Hodnoty, které se po zaokrouhlení rovnají nule, se vypisují bez znaménka –
    "-0,00" by v tabulce působilo jako chyba.
    """
    if round(value, decimals) == 0:
        value = abs(value)
    text = f"{value:,.{decimals}f}"
    return text.replace(",", NBSP).replace(".", ",")


def money(value: float, currency: str = "", decimals: int = 2) -> str:
    """Naformátuje peněžní částku, volitelně s kódem měny."""
    text = cs_number(value, decimals)
    return f"{text}{NBSP}{currency}" if currency else text


def signed_money(value: float, currency: str = "", decimals: int = 2) -> str:
    """Jako `money`, ale kladné hodnoty dostanou znaménko plus."""
    prefix = "+" if round(value, decimals) > 0 else ""
    return prefix + money(value, currency, decimals)


def percent(value: Optional[float], decimals: int = 1, signed: bool = False) -> str:
    """Naformátuje procenta; None vrací jako pomlčku."""
    if value is None:
        return "—"
    prefix = "+" if signed and value > 0 else ""
    return f"{prefix}{cs_number(value, decimals)}{NBSP}%"


def ratio(value: Optional[float], decimals: int = 2) -> str:
    """Naformátuje bezrozměrný poměr; None (např. dělení nulou) vrací jako pomlčku."""
    if value is None:
        return "—"
    return cs_number(value, decimals)


def duration(minutes: Optional[float]) -> str:
    """
    Převede dobu v minutách na čitelný tvar (dny / hodiny / minuty).

    Používá se pro průměrnou dobu držení pozice.
    """
    if minutes is None:
        return "—"
    total = int(round(minutes))
    if total < 60:
        return f"{total}{NBSP}min"
    hours, mins = divmod(total, 60)
    if hours < 24:
        return f"{hours}{NBSP}h {mins}{NBSP}min"
    days, hours = divmod(hours, 24)
    return f"{days}{NBSP}d {hours}{NBSP}h"


def datetime_cs(moment, with_time: bool = True) -> str:
    """Naformátuje datum (a čas) česky, bez úvodních nul u dne a měsíce."""
    if moment is None:
        return "—"
    text = f"{moment.day}.{NBSP}{moment.month}.{NBSP}{moment.year}"
    if with_time and hasattr(moment, "hour"):
        text += f" {moment.hour:02d}:{moment.minute:02d}"
    return text


def plural(count: int, one: str, few: str, many: str) -> str:
    """
    Vrátí počet se správně skloňovaným podstatným jménem.

    Čeština má tři tvary: 1 (den), 2–4 (dny) a 0 nebo 5+ (dnů).
    """
    if count == 1:
        form = one
    elif 2 <= count <= 4:
        form = few
    else:
        form = many
    return f"{count}{NBSP}{form}"


def rrr(value: Optional[float], decimals: int = 2) -> str:
    """
    Naformátuje poměr rizika a zisku ve tvaru "1 : 3".

    Vstupem je podíl průměrného zisku k průměrné ztrátě; výsledek se čte jako
    "na jednu jednotku rizika připadá tolik jednotek zisku". None vrací pomlčku.
    """
    if value is None:
        return "—"
    return f"1{NBSP}:{NBSP}{cs_number(value, decimals)}"


def compact_money(value: float, currency: str = "") -> str:
    """
    Naformátuje částku s přesností podle jejího řádu.

    Velké částky nepotřebují haléře, u malých by naopak zaokrouhlení na celé
    jednotky vyrobilo zavádějící nulu.
    """
    decimals = 0 if abs(value) >= 100 else 2
    return money(value, currency, decimals)


def mask_account(account: str) -> str:
    """
    Zamaskuje číslo účtu, aby v reportu nebylo čitelné.

    Z identifikátoru zůstane první a poslední znak, mezi ně přijdou tři
    hvězdičky; doplňující údaje v závorce (měna, server, typ účtu) se
    nemění. Velmi krátká čísla se zakryjí celá.

    >>> mask_account("498754 (USD, FTTrading-Server, demo, Hedge)")
    '4***4 (USD, FTTrading-Server, demo, Hedge)'
    """
    text = (account or "").strip()
    if not text:
        return ""
    # Číslo účtu je první slovo, za ním bývá závorka s měnou a serverem
    match = re.match(r"^(\S+)(.*)$", text, re.S)
    if not match:
        return text
    identifier, rest = match.group(1), match.group(2)
    masked = "***" if len(identifier) <= 3 else f"{identifier[0]}***{identifier[-1]}"
    return masked + rest
