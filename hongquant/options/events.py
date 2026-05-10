"""Event calendar: FOMC, CPI, NFP, earnings, OpEx markers."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import yaml

from .expiries import front_friday, is_opex_week, is_triple_witching_week, next_friday
from .types import Event

_CONFIGS = Path(__file__).parent.parent.parent / "configs"


def _load_fomc(year: int) -> list[date]:
    path = _CONFIGS / "fomc_meetings.yaml"
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return [date.fromisoformat(d) for d in data.get(year, [])]


def _load_bls(kind: str, year: int) -> list[date]:
    path = _CONFIGS / "bls_release_schedule.yaml"
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    entries = data.get(kind, {}).get(year, [])
    return [date.fromisoformat(row[0]) for row in entries]


def _earnings_dates(tickers: list[str], week_start: date, week_end: date) -> list[Event]:
    events: list[Event] = []
    try:
        import yfinance as yf  # lazy import

        for ticker in tickers:
            try:
                cal = yf.Ticker(ticker).calendar
                if cal is None:
                    continue
                # calendar is a dict with 'Earnings Date' key (list of Timestamps)
                for ts in cal.get("Earnings Date", []):
                    ed = ts.date() if hasattr(ts, "date") else ts
                    if isinstance(ed, date) and week_start <= ed <= week_end:
                        events.append(Event(date=ed, kind="EARNINGS", label=f"{ticker} earnings", importance="MEDIUM"))
            except Exception:
                continue
    except ImportError:
        pass
    return events


class EventCalendar:
    def __init__(
        self,
        *,
        momentum_watchlist: list[str] | None = None,
        configs_dir: Path | None = None,
    ) -> None:
        self._watchlist = momentum_watchlist or []
        if configs_dir:
            global _CONFIGS
            _CONFIGS = configs_dir

    def events_this_week(self, today: date) -> list[Event]:
        """Return all notable events in the week containing front_friday(today)."""
        ff = front_friday(today)
        # Week window: the Monday before the front Friday through the Friday
        week_start = ff - timedelta(days=ff.weekday())  # Monday
        week_end = ff

        events: list[Event] = []

        # FOMC dates overlapping this week
        for yr in {week_start.year, week_end.year}:
            for d in _load_fomc(yr):
                if week_start <= d <= week_end:
                    events.append(Event(date=d, kind="FOMC", label="FOMC announcement", importance="HIGH"))

        # CPI dates
        for yr in {week_start.year, week_end.year}:
            for d in _load_bls("cpi", yr):
                if week_start <= d <= week_end:
                    events.append(Event(date=d, kind="CPI", label="CPI release", importance="HIGH"))

        # NFP dates
        for yr in {week_start.year, week_end.year}:
            for d in _load_bls("nfp", yr):
                if week_start <= d <= week_end:
                    events.append(Event(date=d, kind="NFP", label="Employment Situation (NFP)", importance="HIGH"))

        # Monthly OpEx / Triple Witching markers
        if is_triple_witching_week(today):
            events.append(Event(date=ff, kind="TRIPLE_WITCHING", label="Triple Witching", importance="HIGH"))
        elif is_opex_week(today):
            events.append(Event(date=ff, kind="MONTHLY_OPEX", label="Monthly OpEx", importance="MEDIUM"))

        # Next-Friday OpEx markers (already looking at second expiry)
        nf = next_friday(today)
        nf_today_proxy = nf - timedelta(days=7)
        if is_triple_witching_week(nf_today_proxy):
            events.append(Event(date=nf, kind="TRIPLE_WITCHING", label="Triple Witching (next Fri)", importance="MEDIUM"))
        elif is_opex_week(nf_today_proxy):
            events.append(Event(date=nf, kind="MONTHLY_OPEX", label="Monthly OpEx (next Fri)", importance="LOW"))

        # Earnings in the watchlist
        if self._watchlist:
            events.extend(_earnings_dates(self._watchlist, week_start, week_end + timedelta(days=7)))

        return sorted(events, key=lambda e: (e.date, e.kind))

    def event_importance_score(self, today: date) -> float:
        """Return a 0-1 event risk score for this week."""
        events = self.events_this_week(today)
        score = 0.0
        for e in events:
            if e.kind in ("FOMC",):
                score = max(score, 0.9)
            elif e.kind in ("CPI", "NFP"):
                score = max(score, 0.6)
            elif e.kind == "TRIPLE_WITCHING":
                score = max(score, 0.5)
            elif e.kind == "MONTHLY_OPEX":
                score = max(score, 0.3)
            elif e.kind == "EARNINGS":
                score = max(score, 0.2)
        return min(score, 1.0)
