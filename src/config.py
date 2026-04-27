from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class _CsvAwareEnvSource(EnvSettingsSource):
    """Env source that passes comma-separated strings raw for list[int] fields.

    pydantic-settings tries to JSON-decode complex types before the field
    validator fires.  Bypassing JSON decoding for admin_tg_ids lets the
    ``_split_csv`` validator handle the ``"111,222,333"`` format.
    """

    def prepare_field_value(
        self,
        field_name: str,
        field: FieldInfo,
        value: Any,
        value_is_complex: bool,
    ) -> Any:
        if field_name == "admin_tg_ids" and isinstance(value, str):
            return value
        return super().prepare_field_value(field_name, field, value, value_is_complex)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        env_ignore_empty=True,
    )

    bot_token: str
    bot_username: str = "GrancviBot"
    app_bot_token: str = ""  # @grancviWebBot — TMA launcher; empty until provisioned
    app_bot_username: str = "grancviWebBot"
    # Public TMA URL — used in WebAppInfo buttons sent by the bot.
    tma_url: str = "https://app.grancvi.am"
    database_url: str
    redis_url: str
    # CORS allowlist for FastAPI. Include the TMA origin(s) + localhost
    # dev. Override in prod via env var API_CORS_ORIGINS as a JSON list:
    #   API_CORS_ORIGINS=["https://app.grancvi.am"]
    api_cors_origins: list[str] = Field(
        default_factory=lambda: [
            "https://app.grancvi.am",
            "https://grancvi.am",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )
    # Env var accepts comma-separated integers: "111,222,333"
    admin_tg_ids: list[int] = Field(default_factory=list)
    log_level: str = "INFO"
    sentry_dsn: str | None = None
    default_timezone: str = "Asia/Yerevan"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            _CsvAwareEnvSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )

    @field_validator("admin_tg_ids", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                return []
            return [int(x.strip()) for x in stripped.split(",") if x.strip()]
        if isinstance(v, int):
            return [v]
        return v


settings = Settings()
