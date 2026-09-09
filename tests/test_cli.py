from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pytest

import zepp_mcp.cli as cli
from zepp_mcp.auth import ZeppCredentials
from zepp_mcp.client import ZeppApiError
from zepp_mcp.config import ConfigurationError, Settings


def test_no_command_defaults_to_stdio_server(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(cli, "_run_server", lambda args: captured.update(vars(args)))

    cli.main([])

    assert captured["transport"] == "stdio"
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8000


def test_login_setup_persists_only_derived_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    answers = iter(["DE", "person@example.com"])

    monkeypatch.setattr(cli, "load_config_values", lambda: {})

    def fake_write(settings: Settings) -> Path:
        captured["written"] = settings
        return Path("/tmp/zepp-mcp-config.json")

    monkeypatch.setattr(cli, "write_config", fake_write)

    def fake_login(
        account: str,
        password: str,
        region: str,
        country_code: str,
    ) -> ZeppCredentials:
        captured["login_args"] = (account, password, region, country_code)
        return ZeppCredentials(
            app_token="derived-token",
            user_id="42",
            country_code="DE",
            api_base_url="https://api-mifit-de2.zepp.com",
            auth_flow="test-login",
        )

    def fake_verify(settings: Settings) -> dict[str, Any]:
        captured["verified"] = settings
        return {"connected": True, "user_id": "42"}

    cli._run_setup(
        argparse.Namespace(
            auth="login",
            base_url=None,
            country_code=None,
            region="auto",
        ),
        input_func=lambda prompt: next(answers),
        secret_input=lambda prompt: "test-value",
        verify=fake_verify,
        login=fake_login,
    )

    assert captured["login_args"] == ("person@example.com", "test-value", "auto", "DE")
    settings = captured["written"]
    assert isinstance(settings, Settings)
    assert settings.zepp_user_id == "42"
    assert settings.zepp_app_token.get_secret_value() == "derived-token"
    assert settings.base_url == "https://api-mifit-de2.zepp.com"
    assert "person@example.com" not in settings.as_config_values().values()
    assert "test-value" not in settings.as_config_values().values()


def test_verify_connection_wraps_api_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings.model_validate({"ZEPP_APP_TOKEN": "test-token", "ZEPP_USER_ID": "42"})

    class FailingClient:
        async def __aenter__(self) -> FailingClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def check_connection(self) -> dict[str, Any]:
            raise ZeppApiError("endpoint unavailable")

    monkeypatch.setattr(cli, "ZeppClient", lambda _settings: FailingClient())

    with pytest.raises(ConfigurationError, match="Could not verify Zepp access"):
        cli._verify_connection(settings)
