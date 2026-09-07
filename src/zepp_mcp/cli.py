"""Command-line setup and FastMCP launch entry point."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sys
from collections.abc import Callable, Sequence
from typing import Any

from zepp_mcp import __version__
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
        "--base-url",
        help=f"Zepp API base URL (default: {DEFAULT_BASE_URL})",
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
            _run_setup(argparse.Namespace(base_url=None))
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
) -> None:
    existing = load_config_values()
    values = dict(existing)

    default_url = args.base_url or str(existing.get("ZEPP_BASE_URL", DEFAULT_BASE_URL))
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


def _verify_connection(settings: Settings) -> dict[str, Any]:
    async def check() -> dict[str, Any]:
        async with ZeppClient(settings) as client:
            return await client.check_connection()

    return asyncio.run(check())


if __name__ == "__main__":
    main()
