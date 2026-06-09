from __future__ import annotations

import json
from datetime import date

from hongquant.fragility.score import compute_fragility
from hongquant.fragility.systemic import gate_from_values
from hongquant.fragility.types import PillarScore
from hongquant.llm import client
from hongquant.llm.agents import fragility_redteam


def _score():
    return compute_fragility(
        "NVDA", date(2026, 6, 9), gate=gate_from_values(nfci=0.3), cluster="ai_semis",
        pillar_a=PillarScore(0.9), pillar_b=PillarScore(0.8), pillar_c=PillarScore(0.7),
    )


def test_client_is_noop_without_api_key(monkeypatch):
    class _S:
        fragility_enable_llm = True
        fragility_llm_provider = "anthropic"
        anthropic_api_key = None
        fragility_llm_model = "claude-opus-4-8"

    monkeypatch.setattr(client, "get_settings", lambda: _S())
    assert client.is_enabled() is False
    assert client.complete("system", "user") is None


def test_brief_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr(fragility_redteam.client, "is_enabled", lambda: False)
    assert fragility_redteam.brief([_score()], gate=gate_from_values()) is None


def test_brief_feeds_only_computed_numbers(monkeypatch):
    """The model is handed a DATA block built from the pipeline's numbers, with the
    anti-hallucination rule in the system prompt — it never sources figures itself."""
    calls: list[tuple[str, str]] = []

    def fake_complete(system, user, **kwargs):
        calls.append((system, user))
        return "BRIEFING"

    monkeypatch.setattr(fragility_redteam.client, "is_enabled", lambda: True)
    monkeypatch.setattr(fragility_redteam.client, "complete", fake_complete)

    s = _score()
    out = fragility_redteam.brief([s], gate=gate_from_values(nfci=0.3), today=date(2026, 6, 9))
    assert out == "BRIEFING"

    # First call is the Bull's Advocate: its user payload is exactly "DATA:\n<json>".
    bull_system, bull_user = calls[0]
    assert "ABSOLUTE RULE" in bull_system          # anti-hallucination guardrail present
    assert bull_user.startswith("DATA:\n")
    data = json.loads(bull_user[len("DATA:\n"):])
    flagged = data["flagged_instruments"]
    assert flagged[0]["symbol"] == "NVDA"
    assert flagged[0]["fragility_score_0_100"] == s.score   # pipeline's number, verbatim
    assert flagged[0]["pillar_A_extension_0_1"] == s.pillar_a
