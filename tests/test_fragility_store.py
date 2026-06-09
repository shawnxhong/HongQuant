from __future__ import annotations

from datetime import date

from hongquant.fragility import store
from hongquant.fragility.score import compute_fragility, rank_and_flag
from hongquant.fragility.systemic import gate_from_values
from hongquant.fragility.types import PillarScore


def _scores(asof, base=0.9):
    gate = gate_from_values()
    out = [
        compute_fragility(sym, asof, gate=gate, cluster="ai_semis",
                          pillar_a=PillarScore(base), pillar_b=PillarScore(base),
                          pillar_c=PillarScore(base))
        for sym in ("NVDA", "AMD")
    ]
    rank_and_flag(out)
    return out


def test_write_then_read_history_round_trip(tmp_path):
    d1 = date(2026, 6, 8)
    store.write_scores(_scores(d1), asof=d1, root=tmp_path)
    hist = store.read_history("NVDA", before=date(2026, 6, 9), root=tmp_path)
    assert not hist.empty
    assert d1 in hist.index


def test_read_history_excludes_before_date(tmp_path):
    d1 = date(2026, 6, 8)
    store.write_scores(_scores(d1), asof=d1, root=tmp_path)
    # asking for history strictly before d1 should be empty
    assert store.read_history("NVDA", before=d1, root=tmp_path).empty


def test_prior_bands_reads_latest_prior_run(tmp_path):
    store.write_scores(_scores(date(2026, 6, 6), base=0.2), asof=date(2026, 6, 6), root=tmp_path)
    store.write_scores(_scores(date(2026, 6, 8), base=0.9), asof=date(2026, 6, 8), root=tmp_path)
    bands = store.prior_bands(date(2026, 6, 9), root=tmp_path)
    assert bands.get("NVDA") == "Critical"  # from the 6/8 run, not 6/6


def test_cold_start_is_empty(tmp_path):
    assert store.read_history("NVDA", root=tmp_path).empty
    assert store.prior_bands(date(2026, 6, 9), root=tmp_path) == {}
