"""Authentication providers for the reverse-engineered Zepp/Huami login flows."""

from __future__ import annotations

import urllib.parse
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

LEGACY_REGISTRATION_URL = "https://api-user.huami.com/registrations/{account}/tokens"
LEGACY_ACCOUNT_LOGIN_URL = "https://account.huami.com/v2/client/login"
SUCCESS_REDIRECT = "https://s3-us-west-2.amazonaws.com/hm-registration/successsignin.html"

# Reverse-engineered from current Zepp clients/community implementations.
# Keep the metadata isolated here because Zepp may change it without notice.
_ZEPP_AES_KEY = b"xeNtBVqzDc6tuNTh"
_ZEPP_AES_IV = b"MAAAYAAAAAAAAABg"
_ZEPP_APP_NAME = "com.huami.midong"
_ZEPP_APP_VERSION = "9.12.5"
_ZEPP_BUILD = "151689"
_ZEPP_USER_AGENT = "Zepp/9.12.5 (Pixel 4; Android 12; Density/2.75)"

_EU_COUNTRIES = frozenset(
    {
        "AT",
        "BE",
        "BG",
        "CH",
        "CY",
        "CZ",
        "DE",
        "DK",
        "EE",
        "ES",
        "FI",
        "FR",
        "GB",
        "GR",
        "HR",
        "HU",
        "IE",
        "IS",
        "IT",
        "LI",
        "LT",
        "LU",
        "LV",
        "MT",
        "NL",
        "NO",
        "PL",
        "PT",
        "RO",
        "SE",
        "SI",
        "SK",
        "UK",
    }
)


@dataclass(frozen=True, slots=True)
class ZeppCredentials:
    """Long-lived credentials returned by a Zepp authentication provider."""

    app_token: str
    user_id: str
    country_code: str | None = None
    api_base_url: str | None = None
    auth_flow: str = "token"

    def __post_init__(self) -> None:
        if not self.app_token:
            raise ValueError("app_token must not be empty")
        if not self.user_id:
            raise ValueError("user_id must not be empty")


class ZeppAuthError(RuntimeError):
    """Raised when Zepp authentication fails."""


class ZeppAuthRejected(ZeppAuthError):
    """Raised when credentials are explicitly rejected."""


class ZeppAuthRateLimited(ZeppAuthError):
    """Raised when Zepp rate-limits authentication."""


class AuthProvider(Protocol):
    """Small interface for interchangeable credential providers."""

    async def authenticate(self) -> ZeppCredentials:
        """Return usable long-lived Zepp credentials."""


class StaticTokenAuthProvider:
    """Provider for an already known app token and user ID."""

    def __init__(
        self,
        app_token: str,
        user_id: str,
        *,
        api_base_url: str | None = None,
        country_code: str | None = None,
    ) -> None:
        self._credentials = ZeppCredentials(
            app_token=app_token.strip(),
            user_id=user_id.strip(),
            api_base_url=api_base_url,
            country_code=country_code,
            auth_flow="token",
        )

    async def authenticate(self) -> ZeppCredentials:
        return self._credentials


@dataclass(frozen=True, slots=True)
class _ModernCluster:
    name: str
    token_url: str
    login_url: str
    api_base_url: str
    cloud_region: str
    country_hint: str


_MODERN_CLUSTERS = {
    "eu": _ModernCluster(
        name="eu",
        token_url="https://api-user-de2.zepp.com/v2/registrations/tokens",
        login_url="https://api-mifit-de2.zepp.com/v2/client/login",
        api_base_url="https://api-mifit-de2.zepp.com",
        cloud_region="eu-central-1",
        country_hint="DE",
    ),
    "us": _ModernCluster(
        name="us",
        token_url="https://api-user-us2.zepp.com/v2/registrations/tokens",
        login_url="https://api-mifit-us2.zepp.com/v2/client/login",
        api_base_url="https://api-mifit-us2.zepp.com",
        cloud_region="us-west-2",
        country_hint="US",
    ),
}


class PasswordAuthProvider:
    """Exchange a Zepp account/password for an app token and user ID.

    The password is only held in memory for the duration of ``authenticate``.
    The provider first tries the current regional encrypted Zepp flow and falls
    back to the historical Huami registration flow when the regional protocol
    is unavailable. Explicit credential rejection and rate limiting do not
    trigger a second password attempt.
    """

    def __init__(
        self,
        account: str,
        password: str,
        *,
        region: str = "auto",
        country_code: str = "US",
        timeout_seconds: float = 30.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        account = account.strip()
        password = password.strip()
        region = region.strip().lower()
        country_code = country_code.strip().upper()

        if not account:
            raise ValueError("account must not be empty")
        if not password:
            raise ValueError("password must not be empty")
        if region not in {"auto", "eu", "us"}:
            raise ValueError("region must be one of: auto, eu, us")
        if len(country_code) != 2 or not country_code.isalpha():
            raise ValueError("country_code must be an ISO-3166 alpha-2 code")

        self._account = account
        self._password = password
        self._region = region
        self._country_code = country_code
        self._timeout_seconds = timeout_seconds
        self._http_client = http_client

    async def authenticate(self) -> ZeppCredentials:
        if self._http_client is not None:
            return await self._authenticate_with_client(self._http_client)

        async with httpx.AsyncClient(
            timeout=self._timeout_seconds,
            headers={"User-Agent": _ZEPP_USER_AGENT},
        ) as client:
            return await self._authenticate_with_client(client)

    async def _authenticate_with_client(self, client: httpx.AsyncClient) -> ZeppCredentials:
        cluster = _MODERN_CLUSTERS[self._resolved_region()]
        modern_error: Exception | None = None

        try:
            return await self._modern_login(client, cluster)
        except (ZeppAuthRejected, ZeppAuthRateLimited):
            raise
        except (ZeppAuthError, httpx.HTTPError) as error:
            modern_error = error

        try:
            return await self._legacy_login(client)
        except (ZeppAuthRejected, ZeppAuthRateLimited):
            raise
        except (ZeppAuthError, httpx.HTTPError) as legacy_error:
            modern_name = type(modern_error).__name__ if modern_error is not None else "unknown"
            raise ZeppAuthError(
                "Zepp login failed via both the regional and legacy authentication flows "
                f"(regional={modern_name}, legacy={type(legacy_error).__name__}). "
                "Check the account/password and retry with --region eu or --region us if needed."
            ) from legacy_error

    def _resolved_region(self) -> str:
        if self._region != "auto":
            return self._region
        return "eu" if self._country_code in _EU_COUNTRIES else "us"

    async def _modern_login(
        self,
        client: httpx.AsyncClient,
        cluster: _ModernCluster,
    ) -> ZeppCredentials:
        access_token, country_code = await self._modern_access_token(client, cluster)
        payload = await self._modern_exchange(client, cluster, access_token, country_code)
        return _credentials_from_login_payload(
            payload,
            country_code=country_code,
            api_base_url=cluster.api_base_url,
            auth_flow=f"zepp-v2-{cluster.name}",
        )

    async def _modern_access_token(
        self,
        client: httpx.AsyncClient,
        cluster: _ModernCluster,
    ) -> tuple[str, str]:
        country_code = self._country_code or cluster.country_hint
        body = _encrypt_modern_form(
            {
                "emailOrPhone": self._account,
                "state": "REDIRECTION",
                "client_id": "HuaMi",
                "password": self._password,
                "redirect_uri": SUCCESS_REDIRECT,
                "region": cluster.cloud_region,
                "token": ["access", "refresh"],
                "country_code": country_code,
            }
        )
        response = await client.post(
            cluster.token_url,
            content=body,
            follow_redirects=False,
            headers={
                "app_name": _ZEPP_APP_NAME,
                "appname": _ZEPP_APP_NAME,
                "cv": f"{_ZEPP_BUILD}_{_ZEPP_APP_VERSION}",
                "v": "2.0",
                "appplatform": "android_phone",
                "vb": "202509151347",
                "vn": _ZEPP_APP_VERSION,
                "x-hm-ekv": "1",
                "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                "user-agent": _ZEPP_USER_AGENT,
            },
        )
        return _extract_access_token(response, country_code)

    async def _modern_exchange(
        self,
        client: httpx.AsyncClient,
        cluster: _ModernCluster,
        access_token: str,
        country_code: str,
    ) -> dict[str, Any]:
        response = await client.post(
            cluster.login_url,
            data={
                "code": access_token,
                "device_id": str(uuid.uuid4()),
                "device_model": "android_phone",
                "app_version": _ZEPP_APP_VERSION,
                "dn": (
                    "api-mifit.zepp.com,api-user.zepp.com,api-watch.zepp.com,"
                    "app-analytics.zepp.com,auth.zepp.com,api-analytics.zepp.com"
                ),
                "third_name": "huami",
                "source": f"com.huami.watch.hmwatchmanager:{_ZEPP_APP_VERSION}:{_ZEPP_BUILD}",
                "app_name": _ZEPP_APP_NAME,
                "country_code": country_code,
                "grant_type": "access_token",
                "allow_registration": "false",
                "lang": "en",
                "countryState": _country_state(country_code),
            },
            follow_redirects=True,
            headers={
                "app_name": "com.huami.webapp",
                "appname": "com.huami.webapp",
                "origin": "https://user.zepp.com",
                "referer": "https://user.zepp.com/",
                "accept": "application/json, text/plain, */*",
                "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
        )
        _raise_for_auth_status(response, "regional Zepp login")
        return _json_object(response, "regional Zepp login")

    async def _legacy_login(self, client: httpx.AsyncClient) -> ZeppCredentials:
        encoded_account = urllib.parse.quote(self._account, safe="")
        response = await client.post(
            LEGACY_REGISTRATION_URL.format(account=encoded_account),
            data={
                "state": "REDIRECTION",
                "client_id": "HuaMi",
                "password": self._password,
                "redirect_uri": SUCCESS_REDIRECT,
                "region": "us-west-2",
                "token": "access",
                "country_code": self._country_code,
                "json_response": "true",
                "name": self._account,
            },
            follow_redirects=False,
            headers={
                "app_name": "com.xiaomi.hm.health",
                "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
        )
        access_token, country_code = _extract_access_token(response, self._country_code)

        login_response = await client.post(
            LEGACY_ACCOUNT_LOGIN_URL,
            data={
                "app_name": "com.xiaomi.hm.health",
                "app_version": "4.0.9",
                "code": access_token,
                "country_code": country_code,
                "device_id": "02:00:00:00:00:00",
                "device_model": "android_phone",
                "dn": (
                    "account.huami.com,api-user.huami.com,api-watch.huami.com,"
                    "api-analytics.huami.com,app-analytics.huami.com,api-mifit.huami.com"
                ),
                "grant_type": "access_token",
                "third_name": "huami",
                "allow_registration": "false",
            },
            follow_redirects=True,
        )
        _raise_for_auth_status(login_response, "legacy Huami login")
        payload = _json_object(login_response, "legacy Huami login")
        return _credentials_from_login_payload(
            payload,
            country_code=country_code,
            api_base_url=None,
            auth_flow="huami-legacy",
        )


def _encrypt_modern_form(values: dict[str, Any]) -> bytes:
    encoded = urllib.parse.urlencode(values, doseq=True).encode()
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(encoded) + padder.finalize()
    encryptor = Cipher(algorithms.AES(_ZEPP_AES_KEY), modes.CBC(_ZEPP_AES_IV)).encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def _extract_access_token(response: httpx.Response, country_hint: str) -> tuple[str, str]:
    if response.status_code == 429:
        raise ZeppAuthRateLimited(
            "Zepp rate-limited the login request (HTTP 429). Wait a few minutes before retrying."
        )
    if response.status_code == 401:
        raise ZeppAuthRejected("Zepp rejected the account credentials (HTTP 401).")

    access: str | None = None
    country_code = country_hint

    if 200 <= response.status_code < 300:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            raw_access = payload.get("access")
            if raw_access not in (None, ""):
                access = str(raw_access)
            raw_country = payload.get("country_code")
            if raw_country not in (None, ""):
                country_code = str(raw_country).upper()

    location = response.headers.get("location")
    if not access and location:
        params = _parse_redirect_params(location)
        raw_access = params.get("access")
        if raw_access:
            access = raw_access
        raw_country = params.get("country_code")
        if raw_country:
            country_code = raw_country.upper()
        raw_error = params.get("error")
        if raw_error in {"401", "unauthorized", "invalid_grant"}:
            raise ZeppAuthRejected("Zepp rejected the account credentials.")

    if not access:
        raise ZeppAuthError(
            f"Zepp token endpoint did not return an access token (HTTP {response.status_code})."
        )
    return access, country_code


def _parse_redirect_params(location: str) -> dict[str, str]:
    parsed = urllib.parse.urlparse(location)
    combined: dict[str, str] = {}
    for source in (parsed.query, parsed.fragment.lstrip("?")):
        if not source:
            continue
        for key, values in urllib.parse.parse_qs(source, keep_blank_values=True).items():
            if values:
                combined[key] = values[0]
    return combined


def _raise_for_auth_status(response: httpx.Response, step: str) -> None:
    if response.status_code == 429:
        raise ZeppAuthRateLimited(
            f"{step} was rate-limited (HTTP 429). Wait a few minutes before retrying."
        )
    if response.status_code in {401, 403}:
        raise ZeppAuthRejected(f"{step} rejected the supplied credentials.")
    if not 200 <= response.status_code < 300:
        raise ZeppAuthError(f"{step} failed with HTTP {response.status_code}.")


def _json_object(response: httpx.Response, step: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as error:
        raise ZeppAuthError(f"{step} returned invalid JSON.") from error
    if not isinstance(payload, dict):
        raise ZeppAuthError(f"{step} returned a non-object JSON response.")
    return {str(key): value for key, value in payload.items()}


def _credentials_from_login_payload(
    payload: dict[str, Any],
    *,
    country_code: str,
    api_base_url: str | None,
    auth_flow: str,
) -> ZeppCredentials:
    raw_token_info = payload.get("token_info")
    if not isinstance(raw_token_info, dict):
        message = payload.get("message") or payload.get("error")
        suffix = f": {message}" if isinstance(message, str) and message else ""
        raise ZeppAuthError(f"Zepp login did not return token_info{suffix}")

    app_token = raw_token_info.get("app_token")
    user_id = raw_token_info.get("user_id")
    if app_token in (None, "") or user_id in (None, ""):
        raise ZeppAuthError("Zepp login did not return both app_token and user_id.")

    return ZeppCredentials(
        app_token=str(app_token),
        user_id=str(user_id),
        country_code=country_code,
        api_base_url=api_base_url,
        auth_flow=auth_flow,
    )


def _country_state(country_code: str) -> str:
    return {
        "AT": "AT-9",
        "BE": "BE-BRU",
        "DE": "DE-BE",
        "ES": "ES-MD",
        "FR": "FR-IDF",
        "GB": "GB-ENG",
        "IT": "IT-MI",
        "NL": "NL-NH",
        "PL": "PL-MZ",
        "UK": "GB-ENG",
        "US": "US-NY",
    }.get(country_code.upper(), "US-NY")
