"""Application configuration loaded from environment variables."""

from decimal import Decimal
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """All configuration is pulled from environment variables or .env file."""

    # --- Auth ---
    dashboard_password: str = Field(default="changeme")
    secret_key: str = Field(default="dev-secret-key-change-in-production")

    # --- Database ---
    database_url: str = Field(
        default="mysql+aiomysql://tradingagents_user:password@localhost:3306/tradingagents_db"
    )
    database_url_sync: str = Field(
        default="mysql+pymysql://tradingagents_user:password@localhost:3306/tradingagents_db"
    )

    # --- DeepSeek / LLM ---
    openai_api_key: str = Field(default="")
    deepseek_api_key: str = Field(default="")
    deepseek_base_url: str = Field(default="https://api.deepseek.com")
    deep_think_model: str = Field(default="deepseek-v4-pro")
    quick_think_model: str = Field(default="deepseek-v4-flash")

    # --- Cost Protection ---
    daily_cost_cap_usd: Decimal = Field(default=Decimal("10.00"))
    monthly_cost_cap_usd: Decimal = Field(default=Decimal("100.00"))

    # --- Alpha Vantage ---
    alpha_vantage_api_key: str = Field(default="")

    # --- TradingAgents Framework ---
    max_debate_rounds: int = Field(default=2)
    max_risk_discuss_rounds: int = Field(default=1)

    # --- Cron ---
    cron_hour: int = Field(default=7)
    cron_minute: int = Field(default=0)
    cron_timezone: str = Field(default="America/New_York")

    # --- Server ---
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


# Singleton instance
settings = Settings()
