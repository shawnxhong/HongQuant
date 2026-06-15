"""Weekly external dependency self-check.

This module is intentionally separate from Prefect flows: it probes small,
cheap samples from each configured external dependency, records latency, and
optionally sends a concise Telegram + email summary. It does not write to the
data lake or run full production flows.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import smtplib
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pandas as pd

from ..config import get_settings
from ..email import send_email
from ..logging import setup_logging

Status = str


@dataclass
class CheckResult:
    name: str
    category: str
    required: bool
    status: Status
    latency_ms: int | None = None
    message: str = ""
    missing_env: list[str] = field(default_factory=list)
    exception_type: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "PASS" or (not self.required and self.status in {"WARN", "SKIP"})


@dataclass
class SelfCheckReport:
    overall_status: Status
    started_at: str
    elapsed_seconds: float
    checks: list[CheckResult]
    thresholds: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_status": self.overall_status,
            "started_at": self.started_at,
            "elapsed_seconds": self.elapsed_seconds,
            "checks": [asdict(c) for c in self.checks],
            "thresholds": self.thresholds,
        }


def _has(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _setting(name: str, default: Any = None) -> Any:
    return getattr(get_settings(), name, default)


def _missing_result(
    name: str,
    category: str,
    *,
    required: bool,
    missing_env: list[str],
) -> CheckResult:
    return CheckResult(
        name=name,
        category=category,
        required=required,
        status="FAIL" if required else "SKIP",
        message="missing required environment variable(s)" if required else "not configured",
        missing_env=missing_env,
    )


def timed_check(
    name: str,
    category: str,
    required: bool,
    func: Callable[[], str],
    *,
    timeout_seconds: int,
) -> CheckResult:
    start = time.perf_counter()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(func)
    try:
        message = future.result(timeout=timeout_seconds)
    except concurrent.futures.TimeoutError:
        executor.shutdown(wait=False, cancel_futures=True)
        return CheckResult(
            name=name,
            category=category,
            required=required,
            status="FAIL" if required else "WARN",
            latency_ms=int((time.perf_counter() - start) * 1000),
            message=f"timed out after {timeout_seconds}s",
            exception_type="TimeoutError",
        )
    except Exception as exc:
        executor.shutdown(wait=False, cancel_futures=True)
        return CheckResult(
            name=name,
            category=category,
            required=required,
            status="FAIL" if required else "WARN",
            latency_ms=int((time.perf_counter() - start) * 1000),
            message=str(exc)[:300],
            exception_type=type(exc).__name__,
        )
    finally:
        if future.done():
            executor.shutdown(wait=False)
    latency = int((time.perf_counter() - start) * 1000)
    return CheckResult(
        name=name,
        category=category,
        required=required,
        status="PASS",
        latency_ms=latency,
        message=message[:300],
    )


def _check_fred() -> str:
    from ..data.adapters.fred import fetch_series

    df = fetch_series(["DGS2"])
    if df.empty:
        raise RuntimeError("FRED DGS2 returned no rows")
    latest = pd.to_datetime(df["ts"]).max().date()
    return f"DGS2 rows={len(df)}, latest={latest}"


def _check_yfinance_ohlcv() -> str:
    from ..data.adapters.yfinance_ import fetch_ohlcv

    start = (datetime.now(tz=UTC) - timedelta(days=10)).date().isoformat()
    df = fetch_ohlcv(["SPY"], start=start, interval="1d")
    if df.empty:
        raise RuntimeError("SPY OHLCV returned no rows")
    return f"SPY bars={len(df)}"


def _check_defillama() -> str:
    from ..liquidity.adapters.defillama import fetch_stablecoin_mcap

    s = fetch_stablecoin_mcap(days=30)
    if s.empty:
        raise RuntimeError("stablecoin market cap returned no rows")
    return f"stablecoin rows={len(s)}, latest={max(s.index)}"


def _check_cot() -> str:
    from ..data.adapters.cot import managed_money_net

    s = managed_money_net("GOLD", years=1)
    if s.empty:
        raise RuntimeError("GOLD COT managed money net returned no rows")
    return f"GOLD COT rows={len(s)}, latest={max(s.index)}"


def _check_edgar() -> str:
    from ..data.adapters.edgar import list_filings

    filings = list_filings("AAPL", limit=3)
    if not filings:
        raise RuntimeError("AAPL filings returned no rows")
    return f"AAPL filings={len(filings)}, latest={filings[0].filed_at.date()}"


def _check_alpaca() -> str:
    from ..data.adapters.alpaca import fetch_ohlcv

    start = datetime.now(tz=UTC) - timedelta(days=10)
    df = fetch_ohlcv(["SPY"], start=start, interval="1d")
    if df.empty:
        raise RuntimeError("Alpaca SPY bars returned no rows")
    return f"SPY bars={len(df)}"


def _check_ccxt_public() -> str:
    from ..data.adapters.ccxt_ import fetch_ohlcv

    start = datetime.now(tz=UTC) - timedelta(hours=6)
    df = fetch_ohlcv(["BTC/USDT"], start=start, interval="1h", exchange="binance", page_limit=20)
    if df.empty:
        raise RuntimeError("Binance BTC/USDT returned no rows")
    return f"BTC/USDT bars={len(df)}"



def _first_spy_option_expiry() -> date:
    import yfinance as yf

    options = list(getattr(yf.Ticker("SPY"), "options", []) or [])
    if options:
        return date.fromisoformat(options[0])
    from ..options.expiries import front_friday

    return front_friday(datetime.now(tz=UTC).date())


def _check_yfinance_options() -> str:
    from ..options.adapters.yfinance_options import fetch_chain_snapshot
    df = fetch_chain_snapshot("SPY", expirations=[_first_spy_option_expiry()])
    if df.empty:
        raise RuntimeError("yfinance SPY options returned no rows")
    return f"SPY contracts={len(df)}"


def _check_polygon_options() -> str:
    from ..options.adapters.polygon_options import fetch_chain_snapshot
    df = fetch_chain_snapshot("SPY", expirations=[_first_spy_option_expiry()])
    if df.empty:
        raise RuntimeError("Polygon SPY options returned no rows")
    return f"SPY contracts={len(df)}"


def _check_ibkr_options() -> str:
    from ..options.adapters.ibkr_options import fetch_chain_snapshot
    df = fetch_chain_snapshot("SPY", expirations=[_first_spy_option_expiry()])
    if df.empty:
        raise RuntimeError("IBKR SPY options returned no rows")
    return f"SPY contracts={len(df)}"


def _check_anthropic() -> str:
    import anthropic

    model = _setting("anthropic_self_check_model") or _setting("fragility_llm_model")
    client = anthropic.Anthropic(api_key=_setting("anthropic_api_key"))
    resp = client.messages.create(
        model=model,
        max_tokens=8,
        system="Return exactly: pong",
        messages=[{"role": "user", "content": "ping"}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    if "pong" not in text.lower():
        raise RuntimeError(f"unexpected Anthropic response: {text[:80]}")
    return f"model={model}"


def _check_deepseek() -> str:
    payload = {
        "model": _setting("deepseek_model", "deepseek-chat"),
        "messages": [
            {"role": "system", "content": "Return exactly: pong"},
            {"role": "user", "content": "ping"},
        ],
        "max_tokens": 8,
        "temperature": 0,
    }
    resp = httpx.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {_setting('deepseek_api_key')}"},
        json=payload,
        timeout=float(_setting("self_check_llm_timeout_seconds", 45)),
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"].strip()
    if "pong" not in text.lower():
        raise RuntimeError(f"unexpected DeepSeek response: {text[:80]}")
    return f"model={_setting('deepseek_model', 'deepseek-chat')}"


def _send_telegram_summary(text: str) -> bool:
    if not _setting("telegram_bot_token") or not _setting("telegram_chat_id"):
        return False
    url = f"https://api.telegram.org/bot{_setting('telegram_bot_token')}/sendMessage"
    resp = httpx.post(
        url,
        data={"chat_id": _setting("telegram_chat_id"), "text": text, "parse_mode": "Markdown"},
        timeout=10.0,
    )
    resp.raise_for_status()
    return True


def _check_telegram_config() -> str:
    return "Telegram config present"


def _check_smtp_login() -> str:
    if not all([
        _setting("smtp_host"),
        _setting("smtp_user"),
        _setting("smtp_password"),
        _setting("smtp_from"),
        _setting("smtp_to"),
    ]):
        raise RuntimeError("SMTP is not fully configured")
    recipients = [r.strip() for r in (_setting("smtp_to") or "").split(",") if r.strip()]
    if not recipients:
        raise RuntimeError("SMTP_TO has no recipients")
    with smtplib.SMTP(_setting("smtp_host"), _setting("smtp_port", 587), timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.login(_setting("smtp_user"), _setting("smtp_password"))
    return f"SMTP login ok, recipients={len(recipients)}"


def _selected_options_check(provider: str) -> tuple[str, Callable[[], str]]:
    if provider == "polygon":
        return "options_polygon", _check_polygon_options
    if provider == "ibkr":
        return "options_ibkr", _check_ibkr_options
    return "options_yfinance", _check_yfinance_options


def _build_checks(strict_optional: bool) -> list[tuple[str, str, bool, Callable[[], str], list[str]]]:
    provider = (_setting("options_data_provider", "yfinance") or "yfinance").lower()
    checks: list[tuple[str, str, bool, Callable[[], str], list[str]]] = [
        ("fred", "data", True, _check_fred, ["FRED_API_KEY"]),
        ("yfinance_ohlcv", "data", True, _check_yfinance_ohlcv, []),
        ("defillama", "data", True, _check_defillama, []),
        ("cot_gold", "data", True, _check_cot, []),
        ("edgar", "data", True, _check_edgar, ["EDGAR_USER_AGENT"]),
        ("anthropic", "llm", True, _check_anthropic, ["ANTHROPIC_API_KEY"]),
        ("deepseek", "llm", True, _check_deepseek, ["DEEPSEEK_API_KEY"]),
        ("telegram_config", "notify", True, _check_telegram_config, ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]),
        (
            "smtp_login",
            "notify",
            True,
            _check_smtp_login,
            ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "SMTP_TO"],
        ),
    ]
    opt_name, opt_func = _selected_options_check(provider)
    opt_missing = ["POLYGON_API_KEY"] if provider == "polygon" else []
    checks.append((opt_name, "data", True, opt_func, opt_missing))

    optional_required = strict_optional
    checks.extend(
        [
            ("alpaca", "data", optional_required, _check_alpaca, ["ALPACA_API_KEY", "ALPACA_API_SECRET"]),
            ("ccxt_binance_public", "data", optional_required, _check_ccxt_public, []),
        ]
    )
    if provider != "polygon":
        checks.append(("options_polygon", "data", optional_required, _check_polygon_options, ["POLYGON_API_KEY"]))
    if provider != "ibkr" and strict_optional:
        checks.append(("options_ibkr", "data", True, _check_ibkr_options, []))
    return checks


def _missing_env_for(names: list[str]) -> list[str]:
    values = {
        "FRED_API_KEY": _setting("fred_api_key"),
        "EDGAR_USER_AGENT": _setting("edgar_user_agent"),
        "ANTHROPIC_API_KEY": _setting("anthropic_api_key"),
        "DEEPSEEK_API_KEY": _setting("deepseek_api_key"),
        "SMTP_HOST": _setting("smtp_host"),
        "SMTP_USER": _setting("smtp_user"),
        "SMTP_PASSWORD": _setting("smtp_password"),
        "SMTP_FROM": _setting("smtp_from"),
        "SMTP_TO": _setting("smtp_to"),
        "ALPACA_API_KEY": _setting("alpaca_api_key"),
        "ALPACA_API_SECRET": _setting("alpaca_api_secret"),
        "POLYGON_API_KEY": _setting("polygon_api_key"),
        "TELEGRAM_BOT_TOKEN": _setting("telegram_bot_token"),
        "TELEGRAM_CHAT_ID": _setting("telegram_chat_id"),
    }
    return [name for name in names if not _has(values.get(name))]


def run_weekly_self_check(
    *,
    send_notifications: bool = True,
    strict_optional: bool = False,
) -> SelfCheckReport:
    setup_logging()
    started = datetime.now(tz=UTC)
    total_start = time.perf_counter()
    checks: list[CheckResult] = []

    for name, category, required, func, env_names in _build_checks(strict_optional):
        missing = _missing_env_for(env_names)
        if missing:
            checks.append(_missing_result(name, category, required=required, missing_env=missing))
            continue
        timeout = (
            _setting("self_check_llm_timeout_seconds", 45)
            if category == "llm"
            else _setting("self_check_source_timeout_seconds", 30)
        )
        checks.append(timed_check(name, category, required, func, timeout_seconds=timeout))

    elapsed = time.perf_counter() - total_start
    total_timeout = _setting("self_check_total_timeout_seconds", 300)
    total_timed_out = elapsed > total_timeout
    required_failed = any(c.required and c.status != "PASS" for c in checks)
    overall = "FAIL" if required_failed or total_timed_out else "PASS"
    if total_timed_out:
        checks.append(
            CheckResult(
                name="total_runtime",
                category="runtime",
                required=True,
                status="FAIL",
                latency_ms=int(elapsed * 1000),
                message=f"total runtime exceeded {total_timeout}s",
            )
        )

    report = SelfCheckReport(
        overall_status=overall,
        started_at=started.isoformat(),
        elapsed_seconds=round(elapsed, 3),
        checks=checks,
        thresholds={
            "source_timeout_seconds": _setting("self_check_source_timeout_seconds", 30),
            "llm_timeout_seconds": _setting("self_check_llm_timeout_seconds", 45),
            "total_timeout_seconds": total_timeout,
        },
    )

    if send_notifications:
        _deliver_summary(report)
    return report


def _status_counts(checks: list[CheckResult]) -> dict[str, int]:
    counts = {"PASS": 0, "WARN": 0, "FAIL": 0, "SKIP": 0}
    for c in checks:
        counts[c.status] = counts.get(c.status, 0) + 1
    return counts


def render_summary(report: SelfCheckReport) -> str:
    counts = _status_counts(report.checks)
    lines = [
        f"*HongQuant Weekly Self-Check: {report.overall_status}*",
        f"Started: {report.started_at}",
        f"Elapsed: {report.elapsed_seconds:.1f}s",
        f"Checks: PASS {counts['PASS']} | WARN {counts['WARN']} | FAIL {counts['FAIL']} | SKIP {counts['SKIP']}",
    ]
    problem_checks = [c for c in report.checks if c.status in {"FAIL", "WARN", "SKIP"}]
    if problem_checks:
        lines.append("")
        lines.append("*Attention*")
        for c in problem_checks[:12]:
            req = "required" if c.required else "optional"
            missing = f" missing={','.join(c.missing_env)}" if c.missing_env else ""
            lines.append(f"- {c.status} {c.name} ({req}): {c.message}{missing}")
        if len(problem_checks) > 12:
            lines.append(f"- ... {len(problem_checks) - 12} more")
    slow = [
        c
        for c in report.checks
        if c.latency_ms is not None
        and math.isfinite(c.latency_ms)
        and c.status == "PASS"
        and c.latency_ms > 0
    ]
    if slow:
        top = sorted(slow, key=lambda c: c.latency_ms or 0, reverse=True)[:5]
        lines.append("")
        lines.append("*Slowest PASS checks*")
        for c in top:
            lines.append(f"- {c.name}: {(c.latency_ms or 0) / 1000:.1f}s")
    return "\n".join(lines)


def _deliver_summary(report: SelfCheckReport) -> None:
    text = render_summary(report)
    telegram = timed_check(
        "telegram_send",
        "notify",
        True,
        lambda: "sent" if _send_telegram_summary(text) else "not sent",
        timeout_seconds=15,
    )
    report.checks.append(telegram)
    subject = f"[HongQuant Self-Check: {report.overall_status}] {datetime.now(tz=UTC).date()}"
    email_ok = send_email(subject, text)
    report.checks.append(
        CheckResult(
            name="email_send",
            category="notify",
            required=True,
            status="PASS" if email_ok else "FAIL",
            message="sent" if email_ok else "send_email returned False",
        )
    )
    if telegram.status != "PASS" or not email_ok:
        report.overall_status = "FAIL"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="HongQuant weekly external dependency self-check")
    p.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    p.add_argument("--no-notify", action="store_true", help="Do not send Telegram/email summary")
    p.add_argument(
        "--strict-optional",
        action="store_true",
        help="Treat optional data sources as required",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    report = run_weekly_self_check(
        send_notifications=not args.no_notify,
        strict_optional=args.strict_optional,
    )
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, default=str))
    else:
        print(render_summary(report))
    return 0 if report.overall_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
