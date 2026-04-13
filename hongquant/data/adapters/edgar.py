"""SEC EDGAR adapter — filings + XBRL company facts."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ...config import get_settings


@dataclass
class Filing:
    ticker: str
    form: str
    filed_at: pd.Timestamp
    accession: str
    url: str


def _ensure_identity() -> None:
    from edgar import set_identity

    set_identity(get_settings().edgar_user_agent)


def list_filings(
    ticker: str,
    *,
    forms: tuple[str, ...] = ("10-K", "10-Q", "8-K"),
    limit: int = 40,
) -> list[Filing]:
    """List recent filings for a ticker. Network call."""
    from edgar import Company

    _ensure_identity()
    company = Company(ticker)
    filings = company.get_filings(form=list(forms))
    out: list[Filing] = []
    for f in filings[:limit]:
        out.append(
            Filing(
                ticker=ticker,
                form=f.form,
                filed_at=pd.Timestamp(f.filing_date, tz="UTC"),
                accession=f.accession_no,
                url=f.homepage_url,
            )
        )
    return out


def fetch_company_facts(ticker: str) -> pd.DataFrame:
    """Return the us-gaap companyfacts table (long form).

    Columns: ticker, taxonomy, concept, unit, fiscal_year, fiscal_period, filed, value, form.
    """
    from edgar import Company

    _ensure_identity()
    company = Company(ticker)
    facts = company.get_facts()
    if facts is None:
        return pd.DataFrame()
    df = facts.to_pandas() if hasattr(facts, "to_pandas") else pd.DataFrame(facts)
    df["ticker"] = ticker
    return df
