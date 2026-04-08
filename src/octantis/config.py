"""Application configuration via Pydantic BaseSettings."""

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class OTLPSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OTLP_", extra="ignore")

    grpc_port: int = 4317
    http_port: int = 4318
    grpc_enabled: bool = True
    http_enabled: bool = True
    queue_max_size: int = 1000


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LLM_", extra="ignore")

    provider: Literal["anthropic", "openrouter", "bedrock"] = "anthropic"
    model: str = "claude-sonnet-4-6"
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    aws_region_name: str | None = Field(default=None, alias="AWS_REGION_NAME")
    max_tokens: int = 2048
    temperature: float = 0.1

    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        extra="ignore",
        populate_by_name=True,
    )


class GrafanaMCPSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GRAFANA_MCP_", extra="ignore")

    url: str | None = None
    api_key: str | None = None


class K8sMCPSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="K8S_MCP_", extra="ignore")

    url: str | None = None


class InvestigationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INVESTIGATION_", extra="ignore")

    model: str | None = Field(default=None, alias="LLM_INVESTIGATION_MODEL")
    max_queries: int = 10
    timeout_seconds: int = 60
    query_timeout_seconds: int = 10

    model_config = SettingsConfigDict(
        env_prefix="INVESTIGATION_",
        extra="ignore",
        populate_by_name=True,
    )


class MetricsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="METRICS_", extra="ignore")

    port: int = 9090
    enabled: bool = True


class SlackSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SLACK_", extra="ignore")

    webhook_url: str | None = None
    bot_token: str | None = None
    channel: str = "#infra-alerts"

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url or self.bot_token)


class DiscordSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DISCORD_", extra="ignore")

    webhook_url: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)


class PipelineSettings(BaseSettings):
    """Controls the trigger filter and fingerprint cooldown pipeline."""

    model_config = SettingsConfigDict(env_prefix="PIPELINE_", extra="ignore")

    # Trigger filter thresholds
    cpu_threshold: float = 75.0  # % — pass if CPU >= this
    memory_threshold: float = 80.0  # % — pass if memory >= this
    error_rate_threshold: float = 0.01  # req/s — pass if error rate >= this
    # Comma-separated regex patterns for known-benign sources/logs to always drop
    benign_patterns: str = ""

    # Fingerprint cooldown
    cooldown_seconds: float = 300.0  # 5 min default
    cooldown_max_entries: int = 1000

    @property
    def benign_patterns_list(self) -> list[str]:
        return [p.strip() for p in self.benign_patterns.split(",") if p.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: str = "INFO"
    language: Literal["en", "pt-br"] = "en"
    min_severity_to_notify: Literal["CRITICAL", "MODERATE", "LOW", "NOT_A_PROBLEM"] = "MODERATE"

    otlp: OTLPSettings = Field(default_factory=OTLPSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    grafana_mcp: GrafanaMCPSettings = Field(default_factory=GrafanaMCPSettings)
    k8s_mcp: K8sMCPSettings = Field(default_factory=K8sMCPSettings)
    investigation: InvestigationSettings = Field(default_factory=InvestigationSettings)
    metrics: MetricsSettings = Field(default_factory=MetricsSettings)
    slack: SlackSettings = Field(default_factory=SlackSettings)
    discord: DiscordSettings = Field(default_factory=DiscordSettings)
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"log_level must be one of {valid}")
        return upper


# Singleton
settings = Settings()
