from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pytest

import zepp_mcp.cli as cli
from zepp_mcp.auth import ZeppCredentials
from zepp_mcp.config import Settings


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
