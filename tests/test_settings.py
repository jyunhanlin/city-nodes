import pytest
from pydantic import ValidationError


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_KEY", '{"type":"test"}')
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("GITHUB_REPOSITORY", "user/repo")

    from settings import Settings

    s = Settings()
    assert s.google_service_account_key == '{"type":"test"}'
    assert s.github_token == "ghp_test"
    assert s.github_repository == "user/repo"


def test_settings_all_fields_have_defaults():
    from settings import Settings

    s = Settings(_env_file=None)
    assert s.google_service_account_key == ""
    assert s.github_token == ""
    assert s.github_repository == ""
