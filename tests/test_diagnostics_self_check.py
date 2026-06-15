from __future__ import annotations

import json

from hongquant.diagnostics import weekly_self_check as w


class _Settings:
    log_level = "INFO"
    options_data_provider = "yfinance"
    fred_api_key = "fred-key"
    edgar_user_agent = "HongQuant test user@example.com"
    anthropic_api_key = "anthropic-secret"
    anthropic_self_check_model = "claude-haiku-4-5"
    fragility_llm_model = "claude-opus-4-8"
    deepseek_api_key = "deepseek-secret"
    deepseek_model = "deepseek-chat"
    telegram_bot_token = "telegram-secret"
    telegram_chat_id = "chat-id"
    smtp_host = "smtp.example.com"
    smtp_port = 587
    smtp_user = "user@example.com"
    smtp_password = "smtp-secret"
    smtp_from = "from@example.com"
    smtp_to = "to@example.com"
    alpaca_api_key = None
    alpaca_api_secret = None
    polygon_api_key = None
    self_check_total_timeout_seconds = 300
    self_check_source_timeout_seconds = 3
    self_check_llm_timeout_seconds = 3


def _patch_settings(monkeypatch, settings=None):
    monkeypatch.setattr(w, "get_settings", lambda: settings or _Settings())
    monkeypatch.setattr(w, "setup_logging", lambda: None)


def _patch_successful_required_checks(monkeypatch):
    for name in (
        "_check_fred",
        "_check_yfinance_ohlcv",
        "_check_defillama",
        "_check_cot",
        "_check_edgar",
        "_check_anthropic",
        "_check_deepseek",
        "_check_telegram_config",
        "_check_smtp_login",
        "_check_yfinance_options",
        "_check_ccxt_public",
    ):
        monkeypatch.setattr(w, name, lambda name=name: f"{name} ok")


def test_missing_required_env_fails_without_calling_network(monkeypatch):
    class Missing(_Settings):
        fred_api_key = None
        deepseek_api_key = None

    _patch_settings(monkeypatch, Missing())
    _patch_successful_required_checks(monkeypatch)

    report = w.run_weekly_self_check(send_notifications=False)

    assert report.overall_status == "FAIL"
    failed = {c.name: c for c in report.checks if c.status == "FAIL"}
    assert failed["fred"].missing_env == ["FRED_API_KEY"]
    assert failed["deepseek"].missing_env == ["DEEPSEEK_API_KEY"]


def test_optional_sources_skip_when_unconfigured(monkeypatch):
    _patch_settings(monkeypatch)
    _patch_successful_required_checks(monkeypatch)

    report = w.run_weekly_self_check(send_notifications=False)

    assert report.overall_status == "PASS"
    skipped = {c.name for c in report.checks if c.status == "SKIP"}
    assert "alpaca" in skipped
    assert "options_polygon" in skipped


def test_selected_polygon_provider_requires_polygon_key(monkeypatch):
    class PolygonSelected(_Settings):
        options_data_provider = "polygon"
        polygon_api_key = None

    _patch_settings(monkeypatch, PolygonSelected())
    _patch_successful_required_checks(monkeypatch)

    report = w.run_weekly_self_check(send_notifications=False)

    assert report.overall_status == "FAIL"
    polygon = next(c for c in report.checks if c.name == "options_polygon")
    assert polygon.required is True
    assert polygon.status == "FAIL"
    assert polygon.missing_env == ["POLYGON_API_KEY"]


def test_strict_optional_promotes_optional_missing_to_failure(monkeypatch):
    _patch_settings(monkeypatch)
    _patch_successful_required_checks(monkeypatch)

    report = w.run_weekly_self_check(send_notifications=False, strict_optional=True)

    assert report.overall_status == "FAIL"
    alpaca = next(c for c in report.checks if c.name == "alpaca")
    assert alpaca.required is True
    assert alpaca.status == "FAIL"


def test_notifications_are_sent_when_enabled(monkeypatch):
    sent = {"telegram": 0, "email": 0}

    _patch_settings(monkeypatch)
    _patch_successful_required_checks(monkeypatch)
    monkeypatch.setattr(w, "_send_telegram_summary", lambda text: sent.__setitem__("telegram", sent["telegram"] + 1) or True)
    monkeypatch.setattr(w, "send_email", lambda subject, body: sent.__setitem__("email", sent["email"] + 1) or True)

    report = w.run_weekly_self_check(send_notifications=True)

    assert report.overall_status == "PASS"
    assert sent == {"telegram": 1, "email": 1}
    assert any(c.name == "telegram_send" and c.status == "PASS" for c in report.checks)
    assert any(c.name == "email_send" and c.status == "PASS" for c in report.checks)


def test_report_json_does_not_include_secret_values(monkeypatch):
    _patch_settings(monkeypatch)
    _patch_successful_required_checks(monkeypatch)

    report = w.run_weekly_self_check(send_notifications=False)
    payload = json.dumps(report.to_dict())

    assert "deepseek-secret" not in payload
    assert "anthropic-secret" not in payload
    assert "smtp-secret" not in payload
    assert "telegram-secret" not in payload


def test_render_summary_includes_problem_checks():
    report = w.SelfCheckReport(
        overall_status="FAIL",
        started_at="2026-06-15T00:00:00+00:00",
        elapsed_seconds=1.2,
        checks=[
            w.CheckResult("fred", "data", True, "FAIL", message="missing", missing_env=["FRED_API_KEY"]),
            w.CheckResult("alpaca", "data", False, "SKIP", message="not configured"),
        ],
        thresholds={"source_timeout_seconds": 30, "llm_timeout_seconds": 45, "total_timeout_seconds": 300},
    )

    text = w.render_summary(report)

    assert "HongQuant Weekly Self-Check: FAIL" in text
    assert "FRED_API_KEY" in text
    assert "alpaca" in text
