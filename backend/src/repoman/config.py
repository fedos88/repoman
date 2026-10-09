"""Bootstrap configuration from environment variables (REPOMAN_*).

Only process-level settings live here. Repositories, users, roles, LDAP and
system defaults are configured through the REST API and stored in the database.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REPOMAN_", extra="ignore")

    database_url: str = Field(repr=False)
    storage_path: Path
    secret_key: str = Field(min_length=32, repr=False)

    listen: str = "0.0.0.0:8000"
    base_url: str | None = None
    trusted_proxies: Annotated[list[str], NoDecode] = Field(default_factory=list)
    log_level: str = "INFO"

    # First administrator, created on startup when there is no active admin.
    admin_user: str = "admin"
    admin_password: SecretStr | None = None

    @field_validator("admin_password", mode="before")
    @classmethod
    def _empty_password_is_unset(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("admin_user")
    @classmethod
    def _normalize_admin_user(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("database_url")
    @classmethod
    def _use_asyncpg_driver(cls, value: str) -> str:
        for prefix in ("postgresql://", "postgres://"):
            if value.startswith(prefix):
                return "postgresql+asyncpg://" + value.removeprefix(prefix)
        return value

    @field_validator("trusted_proxies", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().rstrip("/")
        return value or None

    @field_validator("listen")
    @classmethod
    def _check_listen(cls, value: str) -> str:
        host, sep, port = value.rpartition(":")
        if not sep or not host or not port.isdigit():
            raise ValueError("expected HOST:PORT")
        return value

    @property
    def listen_host(self) -> str:
        return self.listen.rpartition(":")[0]

    @property
    def listen_port(self) -> int:
        return int(self.listen.rpartition(":")[2])


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
