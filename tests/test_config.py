from __future__ import annotations

import os
import stat

import pytest

from zepp_mcp.config import (
    ConfigurationError,
    Settings,
    load_config_values,
    make_settings,
    masked_config_values,
    write_config,
)


def test_settings_defaults() -> None:
    settings = make_settings({"ZEPP_APP_TOKEN": "secret-token", "ZEPP_USER_ID": "123"})
    assert settings.base_url == "https://api-mifit.zepp.com"
    assert settings.zepp_app_platform == "web"
    assert settings.zepp_app_name == "com.xiaomi.hm.health"


def test_masked_token_does_not_expose_full_secret() -> None:
    masked = masked_config_values({"ZEPP_APP_TOKEN": "abcdefghijkl", "ZEPP_USER_ID": "123"})
    assert masked["ZEPP_APP_TOKEN"] == "abcd…ijkl"
    assert "abcdefghijkl" not in str(masked)


def test_write_and_load_config(tmp_path) -> None:
    path = tmp_path / "config.json"
    settings = Settings.model_validate({"ZEPP_APP_TOKEN": "secret-token", "ZEPP_USER_ID": "123"})
    write_config(settings, path)
    loaded = load_config_values(path)
    assert loaded["ZEPP_APP_TOKEN"] == "secret-token"
    assert loaded["ZEPP_USER_ID"] == "123"
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_load_rejects_unsafe_permissions(tmp_path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX permissions test")
    path = tmp_path / "config.json"
    path.write_text('{"ZEPP_APP_TOKEN":"secret","ZEPP_USER_ID":"123"}')
    path.chmod(0o644)
    with pytest.raises(ConfigurationError, match="unsafe permissions"):
        load_config_values(path)
