from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: str = Field("dev", alias="HONGQUANT_ENV")
    data_dir: Path = Field(Path("./data"), alias="HONGQUANT_DATA_DIR")
    log_level: str = Field("INFO", alias="HONGQUANT_LOG_LEVEL")

    alpaca_api_key: str | None = Field(None, alias="ALPACA_API_KEY")
    alpaca_api_secret: str | None = Field(None, alias="ALPACA_API_SECRET")
    alpaca_paper: bool = Field(True, alias="ALPACA_PAPER")

    ibkr_host: str = Field("127.0.0.1", alias="IBKR_HOST")
    ibkr_port: int = Field(7497, alias="IBKR_PORT")
    ibkr_client_id: int = Field(17, alias="IBKR_CLIENT_ID")
    ibkr_market_data_type: int = Field(1, alias="IBKR_MARKET_DATA_TYPE")

    edgar_user_agent: str = Field(
        "HongQuant research anon@example.com", alias="EDGAR_USER_AGENT"
    )

    fred_api_key: str | None = Field(None, alias="FRED_API_KEY")

    binance_api_key: str | None = Field(None, alias="BINANCE_API_KEY")
    binance_api_secret: str | None = Field(None, alias="BINANCE_API_SECRET")
    okx_api_key: str | None = Field(None, alias="OKX_API_KEY")
    okx_api_secret: str | None = Field(None, alias="OKX_API_SECRET")
    okx_api_passphrase: str | None = Field(None, alias="OKX_API_PASSPHRASE")
    coinbase_api_key: str | None = Field(None, alias="COINBASE_API_KEY")
    coinbase_api_secret: str | None = Field(None, alias="COINBASE_API_SECRET")

    polygon_api_key: str | None = Field(None, alias="POLYGON_API_KEY")
    options_data_provider: str = Field("yfinance", alias="OPTIONS_DATA_PROVIDER")
    fmp_api_key: str | None = Field(None, alias="FMP_API_KEY")
    finnhub_api_key: str | None = Field(None, alias="FINNHUB_API_KEY")
    tiingo_api_key: str | None = Field(None, alias="TIINGO_API_KEY")

    anthropic_api_key: str | None = Field(None, alias="ANTHROPIC_API_KEY")
    deepseek_api_key: str | None = Field(None, alias="DEEPSEEK_API_KEY")
    deepseek_model: str = Field("deepseek-chat", alias="DEEPSEEK_MODEL")
    openai_api_key: str | None = Field(None, alias="OPENAI_API_KEY")

    # Fragility radar — LLM narrative layer (consumes pre-computed features only)
    fragility_enable_llm: bool = Field(True, alias="FRAGILITY_ENABLE_LLM")
    fragility_llm_provider: str = Field("anthropic", alias="FRAGILITY_LLM_PROVIDER")
    fragility_llm_model: str = Field("claude-opus-4-8", alias="FRAGILITY_LLM_MODEL")
    anthropic_self_check_model: str | None = Field(None, alias="ANTHROPIC_SELF_CHECK_MODEL")

    # Liquidity Regime Monitor — advisory reaction-function LLM (default off:
    # the mechanical state machine and report never depend on it).
    lrm_enable_llm: bool = Field(False, alias="LRM_ENABLE_LLM")
    lrm_llm_model: str = Field("claude-opus-4-8", alias="LRM_LLM_MODEL")

    telegram_bot_token: str | None = Field(None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str | None = Field(None, alias="TELEGRAM_CHAT_ID")

    smtp_host: str | None = Field(None, alias="SMTP_HOST")
    smtp_port: int = Field(587, alias="SMTP_PORT")
    smtp_user: str | None = Field(None, alias="SMTP_USER")
    smtp_password: str | None = Field(None, alias="SMTP_PASSWORD")
    smtp_from: str | None = Field(None, alias="SMTP_FROM")
    smtp_to: str | None = Field(None, alias="SMTP_TO")  # comma-separated

    self_check_total_timeout_seconds: int = Field(300, alias="SELF_CHECK_TOTAL_TIMEOUT_SECONDS")
    self_check_source_timeout_seconds: int = Field(30, alias="SELF_CHECK_SOURCE_TIMEOUT_SECONDS")
    self_check_llm_timeout_seconds: int = Field(45, alias="SELF_CHECK_LLM_TIMEOUT_SECONDS")

    postgres_host: str = Field("localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(5432, alias="POSTGRES_PORT")
    postgres_db: str = Field("hongquant", alias="POSTGRES_DB")
    postgres_user: str = Field("hongquant", alias="POSTGRES_USER")
    postgres_password: str = Field("hongquant", alias="POSTGRES_PASSWORD")

    @property
    def parquet_root(self) -> Path:
        return self.data_dir / "parquet"

    @property
    def duckdb_path(self) -> Path:
        return self.data_dir / "hongquant.duckdb"

    @property
    def lancedb_path(self) -> Path:
        return self.data_dir / "lancedb"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
