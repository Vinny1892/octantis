"""Application configuration via Pydantic BaseSettings."""

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RedpandaSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDPANDA_", extra="ignore")

    brokers: str = "localhost:9092"
    topic: str = "otel-infra-events"
    group_id: str = "octantis-agent"
    security_protocol: str = "PLAINTEXT"
    sasl_mechanism: str | None = None
    sasl_username: str | None = None
    sasl_password: str | None = None

    @property
    def broker_list(self) -> list[str]:
        return [b.strip() for b in self.brokers.split(",")]


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LLM_", extra="ignore")

    provider: Literal["anthropic", "openrouter"] = "anthropic"
    model: str = "claude-sonnet-4-6"
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    max_tokens: int = 2048
    temperature: float = 0.1

    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        extra="ignore",
        populate_by_name=True,
    )


class PrometheusSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PROMETHEUS_", extra="ignore")

    url: str = "http://prometheus:9090"
    timeout: int = 30


class KubernetesSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="K8S_", extra="ignore")

    in_cluster: bool = False
    kubeconfig: str | None = None


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
    """Controls the pre-LLM filtering, batching, and sampling pipeline."""

    model_config = SettingsConfigDict(env_prefix="PIPELINE_", extra="ignore")

    # Pre-filter thresholds
    cpu_threshold: float = 75.0          # % — pass if CPU >= this
    memory_threshold: float = 80.0       # % — pass if memory >= this
    error_rate_threshold: float = 0.01   # req/s — pass if error rate >= this
    # Comma-separated regex patterns for known-benign sources/logs to always drop
    benign_patterns: str = ""
    # Comma-separated event types to allow (empty = allow all)
    allowed_event_types: str = ""

    # Batcher
    batch_window_seconds: float = 30.0
    batch_max_size: int = 20

    # Sampler cooldown
    sampler_cooldown_seconds: float = 300.0  # 5 min default
    sampler_max_entries: int = 1000

    @property
    def benign_patterns_list(self) -> list[str]:
        return [p.strip() for p in self.benign_patterns.split(",") if p.strip()]

    @property
    def allowed_event_types_list(self) -> list[str]:
        return [t.strip() for t in self.allowed_event_types.split(",") if t.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: str = "INFO"
    min_severity_to_notify: Literal["CRITICAL", "MODERATE", "LOW", "NOT_A_PROBLEM"] = (
        "MODERATE"
    )

    redpanda: RedpandaSettings = Field(default_factory=RedpandaSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    prometheus: PrometheusSettings = Field(default_factory=PrometheusSettings)
    kubernetes: KubernetesSettings = Field(default_factory=KubernetesSettings)
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
