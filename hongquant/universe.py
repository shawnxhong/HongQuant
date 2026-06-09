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
    options_underliers: dict[str, list[str]] = field(default_factory=dict)
    momentum_watchlist: list[str] = field(default_factory=list)
    fragility_clusters: dict[str, list[str]] = field(default_factory=dict)

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

    @property
    def options_core_tickers(self) -> list[str]:
        """Flat list of all options underliers, excluding vol (VIX)."""
        result = []
        for group, tickers in self.options_underliers.items():
            if group != "vol":
                result.extend(tickers)
        return sorted(set(result))

    @property
    def fragility_symbols(self) -> list[str]:
        """Flat, deduped list of every symbol across all fragility clusters."""
        result: list[str] = []
        for tickers in self.fragility_clusters.values():
            result.extend(tickers)
        return sorted(set(result))

    def cluster_of(self, symbol: str) -> str | None:
        """Return the cluster name a symbol belongs to, or None."""
        for name, tickers in self.fragility_clusters.items():
            if symbol in tickers:
                return name
        return None


_KNOWN_FIELDS = {f.name for f in Universe.__dataclass_fields__.values()}  # type: ignore[attr-defined]


def load_universe(path: Path | str = "configs/universe.yaml") -> Universe:
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return Universe(**{k: v for k, v in data.items() if k in _KNOWN_FIELDS and v is not None})
