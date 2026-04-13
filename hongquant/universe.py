"""Load the configs/universe.yaml watchlist."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Universe:
    us_sector_etfs: list[str] = field(default_factory=list)
    us_broad_etfs: list[str] = field(default_factory=list)
    us_factor_etfs: list[str] = field(default_factory=list)
    us_commodity_etfs: list[str] = field(default_factory=list)
    us_stocks_watchlist: list[str] = field(default_factory=list)
    crypto_spot: list[str] = field(default_factory=list)
    fred_series: list[str] = field(default_factory=list)

    @property
    def all_us_tickers(self) -> list[str]:
        return sorted(
            set(
                self.us_sector_etfs
                + self.us_broad_etfs
                + self.us_factor_etfs
                + self.us_commodity_etfs
                + self.us_stocks_watchlist
            )
        )


def load_universe(path: Path | str = "configs/universe.yaml") -> Universe:
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return Universe(**{k: v for k, v in data.items() if v is not None})
