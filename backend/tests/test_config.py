from pathlib import Path

import pytest
from pydantic import ValidationError

from repoman.config import Settings

SECRET = "x" * 32


def make(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": "postgresql+asyncpg://u:p@db/repoman",
        "storage_path": Path("/tmp/repoman"),
        "secret_key": SECRET,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_plain_postgres_url_uses_asyncpg_driver() -> None:
    assert make(database_url="postgresql://u:p@db/repoman").database_url == (
        "postgresql+asyncpg://u:p@db/repoman"
    )


def test_trusted_proxies_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPOMAN_DATABASE_URL", "postgresql://u:p@db/repoman")
    monkeypatch.setenv("REPOMAN_STORAGE_PATH", "/tmp/repoman")
    monkeypatch.setenv("REPOMAN_SECRET_KEY", SECRET)
    monkeypatch.setenv("REPOMAN_TRUSTED_PROXIES", "10.0.0.0/8, 192.168.1.10")
    assert Settings().trusted_proxies == ["10.0.0.0/8", "192.168.1.10"]  # type: ignore[call-arg]


def test_base_url_trailing_slash_and_empty() -> None:
    assert make(base_url="https://repo.company.local/").base_url == "https://repo.company.local"
    assert make(base_url="").base_url is None


def test_listen_parsing() -> None:
    settings = make(listen="127.0.0.1:9000")
    assert (settings.listen_host, settings.listen_port) == ("127.0.0.1", 9000)
    with pytest.raises(ValidationError):
        make(listen="9000")


def test_short_secret_key_rejected() -> None:
    with pytest.raises(ValidationError):
        make(secret_key="short")


def test_secrets_not_in_repr() -> None:
    text = repr(make())
    assert SECRET not in text
    assert "u:p@" not in text
