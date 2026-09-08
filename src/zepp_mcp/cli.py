"""Command-line setup and FastMCP launch entry point."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import re
import sys
from collections.abc import Callable, Sequence
from typing import Any

from zepp_mcp import __version__
from zepp_mcp.auth import PasswordAuthProvider, ZeppAuthError, ZeppCredentials
from zepp_mcp.client import ZeppClient
from zepp_mcp.config import (
    CREDENTIAL_ENV_NAMES,
    ConfigurationError,
    Settings,
    config_path,
    get_settings,
    load_config_values,
    make_settings,
    masked_config_values,
    reset_config,
    write_config,
)
from zepp_mcp.server import mcp

DEFAULT_BASE_URL = "https://api-mifit.zepp.com"
DEFAULT_COUNTRY_CODE = "US"
LoginFunc = Callable[[str, str, str, str], ZeppCredentials]


def main(argv: Sequence[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print(__version__)
        return

    command = args.command or "serve"
    try:
        if command == "setup":
            _run_setup(args)
        elif command == "config":
            _run_config(args)
        else:
            _run_server(args)
    except ConfigurationError as error:
        print(f"zepp-mcp: {error}", file=sys.stderr)
        raise SystemExit(2) from error
    except KeyboardInterrupt:
        raise SystemExit(130) from None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Self-hosted FastMCP server for Zepp/Amazfit")
    parser.set_defaults(transport="stdio", host="127.0.0.1", port=8000)
    parser.add_argument("--version", action="store_true", help="Show the installed version")
    subparsers = parser.add_subparsers(dest="command")

    serve = subparsers.add_parser("serve", help="Run the MCP server")
    serve.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    serve.add_argument("--host", default="127.0.0.1", help="HTTP bind address")
    serve.add_argument("--port", type=int, default=8000, help="HTTP port")

    setup = subparsers.add_parser("setup", help="Configure Zepp access interactively")
    setup.add_argument(
        "--auth",
        choices=("login", "token"),
        help="Authentication method; defaults to login for a new configuration",
    )
    setup.add_argument(
        "--region",
        choices=("auto", "eu", "us"),
        default="auto",
        help="Zepp login cluster (default: infer from country code)",
    )
    setup.add_argument(
        "--country-code",
        help="Account country as ISO-3166 alpha-2 code, for example DE or US",
    )
    setup.add_argument(
        "--base-url",
        help="Override the Zepp API base URL instead of using the detected regional host",
    )

    config = subparsers.add_parser("config", help="Inspect or remove local configuration")
    config_subparsers = config.add_subparsers(dest="config_command", required=True)
    config_subparsers.add_parser("show", help="Show local configuration with masked token")
    reset = config_subparsers.add_parser("reset", help="Remove local configuration")
    reset.add_argument("--yes", action="store_true", help="Skip confirmation")
    return parser


def _run_server(args: argparse.Namespace) -> None:
    try:
        get_settings()
    except ConfigurationError:
        missing_local_config = not config_path().exists()
        has_credential_environment = any(name in os.environ for name in CREDENTIAL_ENV_NAMES)
        if (
            missing_local_config
            and not has_credential_environment
            and sys.stdin.isatty()
            and sys.stdout.isatty()
        ):
            print("Zepp MCP is not configured yet. Starting setup…")
            _run_setup(
                argparse.Namespace(
                    auth=None,
                    base_url=None,
                    country_code=None,
                    region="auto",
                )
            )
            print("Setup completed. Start the server again from your MCP client.")
            return
        raise

    if args.transport == "stdio":
        mcp.run(transport="stdio", show_banner=False)
        return
    if not 1 <= args.port <= 65535:
        raise ConfigurationError("HTTP port must be between 1 and 65535")
    mcp.run(
        transport="http",
        host=args.host,
        port=args.port,
        show_banner=False,
    )


def _run_setup(
    args: argparse.Namespace,
    *,
    input_func: Callable[[str], str] = input,
    secret_input: Callable[[str], str] = getpass.getpass,
    verify: Callable[[Settings], dict[str, Any]] | None = None,
    login: LoginFunc | None = None,
) -> None:
    existing = load_config_values()
    values = dict(existing)
    default_auth = (
        "token" if existing.get("ZEPP_APP_TOKEN") and existing.get("ZEPP_USER_ID") else "login"
    )
    auth_mode = getattr(args, "auth", None) or _prompt_auth_mode(default_auth, input_func)

    if auth_mode == "login":
        _run_login_setup(
            args,
            values,
            existing,
            input_func=input_func,
            secret_input=secret_input,
            verify=verify,
            login=login,
        )
        return

    _run_token_setup(
        args,
        values,
        existing,
        input_func=input_func,
        secret_input=secret_input,
        verify=verify,
    )


def _run_login_setup(
    args: argparse.Namespace,
    values: dict[str, Any],
    existing: dict[str, Any],
    *,
    input_func: Callable[[str], str],
    secret_input: Callable[[str], str],
    verify: Callable[[Settings], dict[str, Any]] | None,
    login: LoginFunc | None,
) -> None:
    country_code = getattr(args, "country_code", None)
    if country_code:
        country_code = str(country_code).strip().upper()
    else:
        default_country = _guess_country_code()
        answer = input_func(f"Zepp account country code [{default_country}]: ").strip().upper()
        country_code = answer or default_country

    if len(country_code) != 2 or not country_code.isalpha():
        raise ConfigurationError("Country code must be a two-letter ISO code such as DE or US")

    account = input_func("Zepp account email or phone (phone in international format): ").strip()
    if not account:
        raise ConfigurationError("Zepp account is required for login authentication")
    password = secret_input("Zepp password (input hidden): ").strip()
    if not password:
        raise ConfigurationError("Zepp password is required for login authentication")

    region = str(getattr(args, "region", "auto") or "auto")
    try:
        credentials = (login or _authenticate_password)(account, password, region, country_code)
    except (ZeppAuthError, ValueError) as error:
        raise ConfigurationError(str(error)) from error
    finally:
        password = ""

    values["ZEPP_APP_TOKEN"] = credentials.app_token
    values["ZEPP_USER_ID"] = credentials.user_id
    values["ZEPP_BASE_URL"] = (
        getattr(args, "base_url", None)
        or credentials.api_base_url
        or existing.get("ZEPP_BASE_URL")
        or DEFAULT_BASE_URL
    )

    settings = make_settings(values)
    result = (verify or _verify_connection)(settings)
    target = write_config(settings)
    get_settings.cache_clear()
    print(f"Configuration saved to {target}")
    print(
        "Connected to Zepp as user "
        f"{result.get('user_id', settings.zepp_user_id)} via {settings.base_url}"
    )
    print(f"Authentication flow: {credentials.auth_flow}")
    print("The account password was used only for login and was not saved.")


def _run_token_setup(
    args: argparse.Namespace,
    values: dict[str, Any],
    existing: dict[str, Any],
    *,
    input_func: Callable[[str], str],
    secret_input: Callable[[str], str],
    verify: Callable[[Settings], dict[str, Any]] | None,
) -> None:
    default_url = getattr(args, "base_url", None) or str(
        existing.get("ZEPP_BASE_URL", DEFAULT_BASE_URL)
    )
    answer = input_func(f"Zepp API base URL [{default_url}]: ").strip()
    values["ZEPP_BASE_URL"] = answer or default_url

    existing_user_id = str(existing.get("ZEPP_USER_ID", ""))
    prompt = f"Zepp user ID [{existing_user_id}]: " if existing_user_id else "Zepp user ID: "
    user_id = input_func(prompt).strip()
    if user_id:
        values["ZEPP_USER_ID"] = user_id
    elif not existing_user_id:
        raise ConfigurationError("Zepp user ID is required")

    existing_token = existing.get("ZEPP_APP_TOKEN")
    token_prompt = "Zepp app token (input hidden)"
    if existing_token:
        token_prompt += " [press Enter to retain current token]"
    token = secret_input(f"{token_prompt}: ").strip()
    if token:
        values["ZEPP_APP_TOKEN"] = token
    elif not existing_token:
        raise ConfigurationError("Zepp app token is required")

    settings = make_settings(values)
    result = (verify or _verify_connection)(settings)
    target = write_config(settings)
    get_settings.cache_clear()
    print(f"Configuration saved to {target}")
    print(
        "Connected to Zepp as user "
        f"{result.get('user_id', settings.zepp_user_id)} via {settings.base_url}"
    )


def _prompt_auth_mode(default: str, input_func: Callable[[str], str]) -> str:
    answer = input_func(f"Authentication method [login/token] [{default}]: ").strip().lower()
    if not answer:
        return default
    if answer in {"login", "l"}:
        return "login"
    if answer in {"token", "t"}:
        return "token"
    raise ConfigurationError("Authentication method must be 'login' or 'token'")


def _guess_country_code() -> str:
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(name, "")
        match = re.search(r"[_-]([A-Za-z]{2})(?:[.@]|$)", value)
        if match:
            return match.group(1).upper()
    return DEFAULT_COUNTRY_CODE


def _run_config(args: argparse.Namespace) -> None:
    if args.config_command == "show":
        values = load_config_values()
        target = config_path()
        if not values:
            print(f"No local configuration exists at {target}")
            return
        print(f"Configuration file: {target}")
        print(json.dumps(masked_config_values(values), indent=2, sort_keys=True))
        return

    if args.config_command == "reset":
        if not args.yes:
            answer = input(f"Remove local configuration at {config_path()}? [y/N] ").strip().lower()
            if answer not in {"y", "yes"}:
                print("Configuration was not removed.")
                return
        removed = reset_config()
        get_settings.cache_clear()
        print("Configuration removed." if removed else "No local configuration exists.")


def _authenticate_password(
    account: str,
    password: str,
    region: str,
    country_code: str,
) -> ZeppCredentials:
    async def authenticate() -> ZeppCredentials:
        provider = PasswordAuthProvider(
            account,
            password,
            region=region,
            country_code=country_code,
        )
        return await provider.authenticate()

    return asyncio.run(authenticate())


def _verify_connection(settings: Settings) -> dict[str, Any]:
    async def check() -> dict[str, Any]:
        async with ZeppClient(settings) as client:
            return await client.check_connection()

    return asyncio.run(check())


if __name__ == "__main__":
    main()
