"""
Načtení historie obchodování z CSV, které v MetaTraderu 5 vytváří skript
mql5/ExportHistory.mq5 (soubor ReportHistory-<účet>.csv).

Soubor je v UTF-8 s oddělovačem středník a má dvě části oddělené prázdným
řádkem – údaje o účtu ve tvaru klíč;hodnota a tabulku všech obchodů (deals)
účtu včetně vkladů a výběrů:

    # forex-MT5-report – historie obchodů z MetaTraderu 5
    format;1
    login;498754
    ...
    exported;2026.11.11 16:05:12

    time;deal;order;position;type;entry;symbol;volume;price;sl;tp;commission;fee;swap;profit;magic;comment
    2026.07.03 02:20:37;27520449;0;0;balance;in;;0;0;0;0;0;0;0;15000;0;Deposit

Uzavřené pozice se sestaví z obchodů podle čísla pozice (Position ID).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

# Verze formátu, kterou zapisuje ExportHistory.mq5 (řádek "format;1")
SUPPORTED_FORMAT = "1"

# Sloupce tabulky obchodů, které aplikace čte (ostatní jsou jen informativní)
_REQUIRED_COLUMNS = {
    "time", "deal", "position", "type", "entry", "symbol", "volume", "price",
    "commission", "fee", "swap", "profit", "magic",
}

# Typy obchodů, které nemění zůstatek účtu (kredit, zrušené obchody); ostatní
# neobchodní typy (vklad, výběr, korekce, bonus, úroky, poplatky…) se
# počítají jako pohyb zůstatku 'balance'
_NO_BALANCE_TYPES = {"credit", "buy_canceled", "sell_canceled"}

# Zbytkový objem, pod kterým se pozice považuje za uzavřenou (chyba zaokrouhlení)
_VOLUME_EPSILON = 1e-8


# ---------------------------------------------------------------------------
# Datové struktury
# ---------------------------------------------------------------------------


@dataclass
class Position:
    """Jedna uzavřená pozice (kompletní obchod od otevření po uzavření)."""

    ticket: str
    symbol: str
    direction: str                 # 'buy' / 'sell'
    volume: float                  # objem v lotech
    open_time: Optional[datetime]
    close_time: Optional[datetime]
    open_price: Optional[float]
    close_price: Optional[float]
    commission: float              # provize včetně poplatků (fee) všech obchodů pozice
    swap: float
    gross_profit: float            # zisk bez poplatků
    magic: int                     # magic number obchodu, který pozici otevřel (0 = ruční)

    @property
    def net_profit(self) -> float:
        """Čistý výsledek obchodu včetně provize a swapu."""
        return self.gross_profit + self.commission + self.swap

    @property
    def duration_minutes(self) -> Optional[float]:
        """Doba držení pozice v minutách; None, pokud chybí některý čas."""
        if not self.open_time or not self.close_time:
            return None
        return (self.close_time - self.open_time).total_seconds() / 60.0

    @property
    def is_win(self) -> bool:
        return self.net_profit > 0

    @property
    def is_loss(self) -> bool:
        return self.net_profit < 0


@dataclass
class Deal:
    """Jeden obchod (deal) z historie účtu, včetně vkladů a výběrů."""

    time: datetime
    ticket: int
    position: str                  # číslo pozice; u neobchodních pohybů "0"
    symbol: str
    deal_type: str                 # 'buy' / 'sell' / 'balance'
    entry: str                     # 'in' / 'out' / 'inout' / 'out_by'
    volume: float
    price: float
    commission: float
    fee: float
    swap: float
    profit: float
    magic: int


@dataclass
class AccountInfo:
    """Identifikační údaje účtu z hlavičky exportu."""

    name: str = ""
    account: str = ""              # např. "498754 (USD, FTTrading-Server, demo, Hedge)"
    company: str = ""
    exported_at: str = ""
    currency: str = ""


@dataclass
class Mt5Report:
    """Kompletní obsah načteného exportu."""

    account: AccountInfo
    # Počáteční kapitál účtu: první vklad, bez něj zůstatek před prvním obchodem
    initial_balance: float
    positions: List[Position] = field(default_factory=list)
    deals: List[Deal] = field(default_factory=list)
    source_file: str = ""

    @property
    def deposits(self) -> List[Deal]:
        """Všechny nebchodní pohyby na účtu (vklady, výběry, korekce)."""
        return [d for d in self.deals if d.deal_type == "balance"]


# ---------------------------------------------------------------------------
# Načtení CSV
# ---------------------------------------------------------------------------


def load_report(path: str) -> Mt5Report:
    """
    Načte CSV ze skriptu ExportHistory.mq5 a vrátí strukturovaná data.

    :param path: cesta k souboru ReportHistory-<účet>.csv
    :raises ValueError: soubor nelze přečíst nebo nemá očekávaný formát
    """
    # Jiný soubor (typicky export XLSX nebo HTML přímo z MetaTraderu) se pozná
    # podle chybějící verze formátu nebo podle toho, že není textem v UTF-8
    not_export = (
        f"Soubor {path} není export ze skriptu ExportHistory ve formátu verze "
        f"{SUPPORTED_FORMAT}. Export XLSX či HTML z MetaTraderu 5 se nepodporuje – "
        "historii vyexportujte aktuální verzí skriptu ExportHistory (mql5/ExportHistory.mq5)."
    )
    try:
        # utf-8-sig snese i BOM, který přidá Excel při uložení jako "CSV UTF-8";
        # řádky s komentářem (#) přeskočíme
        with open(path, encoding="utf-8-sig", newline="") as handle:
            rows = [row for row in csv.reader(handle, delimiter=";")
                    if not (row and row[0].startswith("#"))]
    except UnicodeDecodeError as exc:
        raise ValueError(not_export) from exc
    except (OSError, csv.Error) as exc:
        raise ValueError(f"Soubor {path} se nepodařilo přečíst: {exc}") from exc

    # Údaje o účtu končí prvním prázdným řádkem, za ním je tabulka obchodů
    separator = next((i for i, row in enumerate(rows) if not any(cell.strip() for cell in row)),
                     len(rows))
    meta = {row[0].strip().lower(): row[1].strip() for row in rows[:separator] if len(row) >= 2}
    if meta.get("format") != SUPPORTED_FORMAT:
        raise ValueError(not_export)
    table = [row for row in rows[separator + 1:] if any(row)]
    if not table:
        raise ValueError(f"V souboru {path} chybí tabulka obchodů.")

    header = [name.strip().lower() for name in table[0]]
    missing = _REQUIRED_COLUMNS - set(header)
    if missing:
        raise ValueError(f"V souboru {path} chybí sloupce: {', '.join(sorted(missing))}.")

    try:
        deals = [_parse_deal(dict(zip(header, row))) for row in table[1:]]
    except (ValueError, KeyError) as exc:
        raise ValueError(f"Soubor {path} obsahuje neplatný řádek obchodu: {exc}") from exc
    deals = sorted((deal for deal in deals if deal is not None), key=lambda d: (d.time, d.ticket))

    # Počáteční kapitál = první vklad; když v historii chybí (historie nezačíná
    # od založení účtu), odvodí se ze zůstatku při exportu minus všechny změny
    balance_before_first_deal = _to_float(meta.get("balance", "")) - sum(
        deal.profit + deal.commission + deal.fee + deal.swap for deal in deals)
    initial_balance = next((deal.profit for deal in deals if deal.deal_type == "balance"),
                           balance_before_first_deal)

    return Mt5Report(
        account=_parse_account(meta),
        initial_balance=initial_balance,
        positions=_build_positions(deals),
        deals=deals,
        source_file=path,
    )


def _parse_account(meta: Dict[str, str]) -> AccountInfo:
    """
    Sestaví údaje o účtu z hlavičky CSV.

    Řetězec účtu má stejný tvar jako v hlavičce reportu MetaTraderu:
    "498754 (USD, FTTrading-Server, demo, Hedge)".
    """
    details = [meta.get(key, "") for key in ("currency", "server", "trade_mode", "margin_mode")]
    details = [value for value in details if value]
    login = meta.get("login", "")
    return AccountInfo(
        name=meta.get("name", ""),
        account=f"{login} ({', '.join(details)})" if details else login,
        company=meta.get("company", ""),
        exported_at=meta.get("exported", ""),
        currency=meta.get("currency", ""),
    )


def _parse_deal(row: Dict[str, str]) -> Optional[Deal]:
    """
    Převede řádek tabulky na obchod.

    Typy bez vlivu na zůstatek (kredit, zrušené obchody) vrací jako None,
    ostatní neobchodní typy sjednotí na 'balance'.
    """
    deal_type = row["type"].strip().lower()
    if deal_type in _NO_BALANCE_TYPES:
        return None
    if deal_type not in ("buy", "sell"):
        deal_type = "balance"
    return Deal(
        # Čas je ve tvaru MT5 "RRRR.MM.DD HH:MM:SS"; fromisoformat je výrazně
        # rychlejší než strptime, stačí nahradit tečky v datu pomlčkami
        time=datetime.fromisoformat(row["time"].strip().replace(".", "-")),
        ticket=int(row["deal"]),
        position=row["position"].strip(),
        symbol=row["symbol"].strip(),
        deal_type=deal_type,
        entry=row["entry"].strip().lower(),
        volume=_to_float(row["volume"]),
        price=_to_float(row["price"]),
        commission=_to_float(row["commission"]),
        fee=_to_float(row["fee"]),
        swap=_to_float(row["swap"]),
        profit=_to_float(row["profit"]),
        magic=int(row["magic"]),
    )


def _to_float(text: str) -> float:
    """Převede číslo z CSV (desetinná tečka); prázdná hodnota je 0."""
    text = (text or "").strip()
    return float(text) if text else 0.0


# ---------------------------------------------------------------------------
# Sestavení pozic z obchodů
# ---------------------------------------------------------------------------


@dataclass
class _OpenTrade:
    """
    Rozpracovaná pozice při procházení obchodů.

    Sčítá objemy, ceny vážené objemem a peněžní složky všech obchodů pozice.
    """

    ticket: str
    symbol: str
    direction: str
    magic: int
    open_time: datetime
    open_volume: float = 0.0
    open_value: float = 0.0        # součet objem × cena vstupů
    close_volume: float = 0.0
    close_value: float = 0.0       # součet objem × cena výstupů
    close_time: Optional[datetime] = None
    commission: float = 0.0
    swap: float = 0.0
    profit: float = 0.0

    @property
    def remaining(self) -> float:
        """Dosud neuzavřený objem."""
        return self.open_volume - self.close_volume

    def add_entry(self, deal: Deal, volume: float) -> None:
        """Započítá vstup (otevření nebo navýšení pozice) o daném objemu."""
        self.open_volume += volume
        self.open_value += volume * deal.price

    def add_exit(self, deal: Deal, volume: float) -> None:
        """Započítá výstup (částečné nebo úplné uzavření) o daném objemu."""
        self.close_volume += volume
        self.close_value += volume * deal.price
        self.close_time = deal.time

    def add_money(self, deal: Deal) -> None:
        """Přičte peněžní složky obchodu; poplatek (fee) se počítá do provize."""
        self.commission += deal.commission + deal.fee
        self.swap += deal.swap
        self.profit += deal.profit

    def to_position(self) -> Position:
        """Vytvoří z uzavřeného obchodu pozici s průměrnými cenami."""
        return Position(
            ticket=self.ticket,
            symbol=self.symbol,
            direction=self.direction,
            volume=self.open_volume,
            open_time=self.open_time,
            close_time=self.close_time,
            open_price=self.open_value / self.open_volume if self.open_volume else None,
            close_price=self.close_value / self.close_volume if self.close_volume else None,
            commission=self.commission,
            swap=self.swap,
            gross_profit=self.profit,
            magic=self.magic,
        )


def _build_positions(deals: List[Deal]) -> List[Position]:
    """
    Sestaví uzavřené pozice z obchodů seskupených podle čísla pozice.

    Hedge účet: pozice = vstupní obchod(y) + výstupní obchod(y). Netting účet
    může pozici jedním obchodem otočit ('inout'); ten uzavře dosavadní objem
    a zbytek otevře jako novou pozici se stejným číslem (ticket s příponou).
    Pozice, které ještě nejsou úplně uzavřené, se vynechají.
    """
    open_trades: Dict[str, _OpenTrade] = {}
    segments: Dict[str, int] = {}
    positions: List[Position] = []

    def start_trade(deal: Deal, volume: float) -> _OpenTrade:
        # Další úseky téže pozice (po otočení) dostanou do čísla příponu "-2", "-3"…,
        # aby byl ticket v reportu jednoznačný
        segments[deal.position] = segments.get(deal.position, 0) + 1
        count = segments[deal.position]
        ticket = deal.position if count == 1 else f"{deal.position}-{count}"
        trade = _OpenTrade(ticket, deal.symbol, deal.deal_type, deal.magic, deal.time)
        trade.add_entry(deal, volume)
        open_trades[deal.position] = trade
        return trade

    for deal in deals:
        if deal.deal_type not in ("buy", "sell") or deal.position in ("", "0"):
            continue
        trade = open_trades.get(deal.position)

        # Vstup do pozice: nová pozice, nebo navýšení otevřené
        if deal.entry == "in":
            if trade is None:
                trade = start_trade(deal, deal.volume)
            else:
                trade.add_entry(deal, deal.volume)
            trade.add_money(deal)
            continue
        # Výstup bez známého vstupu (historie začíná uprostřed pozice) nelze sestavit
        if trade is None:
            continue

        # Výstup: uzavře nejvýše zbývající objem; u otočení ('inout') zbytek
        # objemu otevře novou pozici opačného směru
        closing = min(deal.volume, trade.remaining)
        trade.add_exit(deal, closing)
        trade.add_money(deal)
        if trade.remaining <= _VOLUME_EPSILON:
            positions.append(trade.to_position())
            del open_trades[deal.position]
        reversed_volume = deal.volume - closing
        if deal.entry == "inout" and reversed_volume > _VOLUME_EPSILON:
            start_trade(deal, reversed_volume)

    return sorted(positions, key=lambda p: p.close_time or datetime.min)
