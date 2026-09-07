"""Runtime configuration and local credential handling for Zepp MCP."""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from platformdirs import user_config_dir
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, SecretStr, ValidationError

APP_NAME = "zepp-mcp"
CONFIG_FILENAME = "config.json"
CREDENTIAL_ENV_NAMES = ("ZEPP_APP_TOKEN", "ZEPP_USER_ID")
OPTIONAL_ENV_NAMES = (
    "ZEPP_BASE_URL",
    "ZEPP_REQUEST_TIMEOUT_MS",
    "ZEPP_APP_NAME",
    "ZEPP_APP_PLATFORM",
)
ALL_ENV_NAMES = CREDENTIAL_ENV_NAMES + OPTIONAL_ENV_NAMES


class ConfigurationError(RuntimeError):
    """Raised when Zepp MCP configuration is missing, invalid, or unsafe."""


class Settings(BaseModel):
    """Validated Zepp API settings.

    Configuration is loaded only from the explicit local config file and process
    environment. The MCP never auto-loads a .env file.
    """

    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)

    zepp_app_token: SecretStr = Field(alias="ZEPP_APP_TOKEN", min_length=1)
    zepp_user_id: str = Field(alias="ZEPP_USER_ID", min_length=1)
    zepp_base_url: AnyHttpUrl = Field(default="https://api-mifit.zepp.com", alias="ZEPP_BASE_URL")
    zepp_request_timeout_ms: int = Field(
        default=20_000,
        ge=1_000,
        le=300_000,
        alias="ZEPP_REQUEST_TIMEOUT_MS",
    )
    zepp_app_name: str = Field(default="com.xiaomi.hm.health", alias="ZEPP_APP_NAME")
    zepp_app_platform: str = Field(default="web", alias="ZEPP_APP_PLATFORM")

    @property
    def base_url(self) -> str:
        return str(self.zepp_base_url).rstrip("/")

    @property
    def timeout_seconds(self) -> float:
        return self.zepp_request_timeout_ms / 1000

    def as_config_values(self) -> dict[str, Any]:
        return {
            "ZEPP_APP_TOKEN": self.zepp_app_token.get_secret_value(),
            "ZEPP_USER_ID": self.zepp_user_id,
            "ZEPP_BASE_URL": str(self.zepp_base_url),
            "ZEPP_REQUEST_TIMEOUT_MS": self.zepp_request_timeout_ms,
            "ZEPP_APP_NAME": self.zepp_app_name,
            "ZEPP_APP_PLATFORM": self.zepp_app_platform,
        }


def config_path() -> Path:
    return Path(user_config_dir(APP_NAME, appauthor=False)) / CONFIG_FILENAME


def load_config_values(path: Path | None = None) -> dict[str, Any]:
    target = path or config_path()
    if not target.exists():
        return {}
    if target.is_symlink():
        raise ConfigurationError(f"Refusing symlinked configuration file: {target}")
    _require_safe_permissions(target)
    try:
        decoded = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigurationError(f"Could not read configuration file {target}: {error}") from error
    if not isinstance(decoded, dict):
        raise ConfigurationError(f"Configuration file {target} must contain a JSON object")
    return {name: decoded[name] for name in ALL_ENV_NAMES if name in decoded}


def write_config(settings: Settings, path: Path | None = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        target.parent.chmod(0o700)

    serialized = json.dumps(settings.as_config_values(), indent=2, sort_keys=True) + "\n"
    temporary_name: str | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            if os.name != "nt":
                os.chmod(temporary.name, 0o600)
            temporary.write(serialized)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, target)
        temporary_name = None
        if os.name != "nt":
            target.chmod(0o600)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
    return target


def reset_config(path: Path | None = None) -> bool:
    target = path or config_path()
    if not target.exists():
        return False
    if target.is_symlink():
        raise ConfigurationError(f"Refusing symlinked configuration file: {target}")
    target.unlink()
    return True


def make_settings(values: Mapping[str, Any]) -> Settings:
    try:
        return Settings.model_validate(values)
    except ValidationError as error:
        raise ConfigurationError(f"Invalid Zepp configuration: {error}") from error


def masked_config_values(values: Mapping[str, Any]) -> dict[str, Any]:
    displayed = {name: values[name] for name in ALL_ENV_NAMES if name in values}
    token = displayed.get("ZEPP_APP_TOKEN")
    if isinstance(token, str):
        displayed["ZEPP_APP_TOKEN"] = _mask_token(token)
    return displayed


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    values = load_config_values()
    environment = {name: os.environ[name] for name in ALL_ENV_NAMES if name in os.environ}
    credential_overrides = [name for name in CREDENTIAL_ENV_NAMES if name in environment]
    if credential_overrides and len(credential_overrides) != len(CREDENTIAL_ENV_NAMES):
        raise ConfigurationError(
            "ZEPP_APP_TOKEN and ZEPP_USER_ID must be supplied together when using "
            "environment overrides."
        )
    values.update(environment)
    if not values:
        raise ConfigurationError(
            "Zepp MCP is not configured. Run 'zepp-mcp setup' in a terminal first."
        )
    return make_settings(values)


def _require_safe_permissions(path: Path) -> None:
    if os.name == "nt":
        return
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ConfigurationError(
            f"Configuration file {path} has unsafe permissions {mode:03o}; expected 600."
        )


def _mask_token(token: str) -> str:
    if len(token) <= 8:
        return "*" * len(token)
    return f"{token[:4]}…{token[-4:]}"
