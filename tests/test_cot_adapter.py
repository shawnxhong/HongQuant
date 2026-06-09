from __future__ import annotations

import pandas as pd

from hongquant.data.adapters import cot


def _synthetic(years: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Market_and_Exchange_Names": [
                "GOLD - COMMODITY EXCHANGE INC.",
                "GOLD - COMMODITY EXCHANGE INC.",
                "SILVER - COMMODITY EXCHANGE INC.",
            ],
            "Report_Date_as_YYYY-MM-DD": ["2026-05-27", "2026-06-03", "2026-06-03"],
            "M_Money_Positions_Long_All": [200_000, 220_000, 50_000],
            "M_Money_Positions_Short_All": [50_000, 40_000, 20_000],
        }
    )


def test_managed_money_net_is_long_minus_short(monkeypatch):
    monkeypatch.setattr(cot, "_fetch_disaggregated", _synthetic)
    s = cot.managed_money_net("GOLD")
    assert len(s) == 2
    assert s.iloc[-1] == 180_000  # 2026-06-03: 220k long - 40k short


def test_market_filter_selects_silver(monkeypatch):
    monkeypatch.setattr(cot, "_fetch_disaggregated", _synthetic)
    s = cot.managed_money_net("SILVER")
    assert len(s) == 1 and s.iloc[0] == 30_000


def test_missing_columns_degrades_to_empty(monkeypatch):
    monkeypatch.setattr(
        cot, "_fetch_disaggregated",
        lambda years: pd.DataFrame({"Market_and_Exchange_Names": ["GOLD"], "x": [1]}),
    )
    assert cot.managed_money_net("GOLD").empty


def test_fetch_failure_degrades_to_empty(monkeypatch):
    def boom(years):
        raise RuntimeError("no network")

    monkeypatch.setattr(cot, "_fetch_disaggregated", boom)
    assert cot.managed_money_net("GOLD").empty
