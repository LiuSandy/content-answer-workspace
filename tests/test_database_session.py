import pytest

from app.platform.database.session import _build_database_url


def _clear_database_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for name in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"):
        monkeypatch.delenv(name, raising=False)


def test_database_url_uses_required_split_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_database_env(monkeypatch)
    monkeypatch.setenv("DB_HOST", "db.example")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_USER", "app")
    monkeypatch.setenv("DB_PASSWORD", "secret")
    monkeypatch.setenv("DB_NAME", "workspace")

    assert (
        _build_database_url()
        == "postgresql+asyncpg://app:secret@db.example:5432/workspace"
    )


def test_database_url_fails_when_split_configuration_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_database_env(monkeypatch)
    monkeypatch.setenv("DB_HOST", "db.example")

    with pytest.raises(RuntimeError, match="DB_PORT"):
        _build_database_url()


def test_database_url_prefers_full_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_database_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgresql://app:secret@db.example/workspace")

    assert (
        _build_database_url()
        == "postgresql+asyncpg://app:secret@db.example/workspace"
    )
