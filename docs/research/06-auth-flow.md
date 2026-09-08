# Zepp authentication flow

## Scope

This document records the authentication approach implemented for the first testable MCP release.
Zepp does not publish a supported public API, so every flow below is reverse-engineered and can
change without notice.

The implementation goal is deliberately narrow: obtain the long-lived `apptoken` and numeric user
ID required by the read-only Zepp API client, without persisting the account password.

## Sources reviewed

### EvanCooke/zepp-export

Repository: <https://github.com/EvanCooke/zepp-export>

Its API reference documents traffic captured from Zepp iOS v10.0.6 in February 2026 and confirms the
current regional data hosts:

- global: `https://api-mifit.huami.com`
- US: `https://api-mifit-us2.zepp.com`
- Europe: `https://api-mifit-de2.zepp.com`

It also confirms the normal API request headers used by this project: `apptoken`, `appPlatform: web`
and `appname: com.xiaomi.hm.health`.

### CristiPerciun/garmin-sync-server

Repository: <https://github.com/CristiPerciun/garmin-sync-server>

`mi_fitness_sync.py` contains a newer regional Zepp login implementation. The relevant observations
are:

- regional token endpoints at `api-user-de2.zepp.com` and `api-user-us2.zepp.com`;
- corresponding login endpoints at `api-mifit-de2.zepp.com` and `api-mifit-us2.zepp.com`;
- an AES-CBC encrypted registration body signalled by `x-hm-ekv: 1`;
- the access token is returned through the redirect URL;
- the regional `/v2/client/login` exchange returns `token_info.app_token` and `token_info.user_id`.

The fixed encryption key/IV and app metadata are implementation details of this private protocol and
must be treated as unstable.

### vamostibor03/zepp-health-agent

Repository: <https://github.com/vamostibor03/zepp-health-agent>

`watchdata/zepp_client.py` implements the historical Huami two-step login:

1. account/password -> access token through `api-user.huami.com/registrations/.../tokens`;
2. access token -> `app_token` + `user_id` through `account.huami.com/v2/client/login`.

It also explicitly warns that the login endpoint is rate limited and recommends token mode when an
existing app token is available.

### rolandsz/Mi-Fit-and-Zepp-workout-exporter

Repository: <https://github.com/rolandsz/Mi-Fit-and-Zepp-workout-exporter>

Its authentication module uses the Zepp/Huami privacy web page in a browser and extracts the
`apptoken` cookie after interactive login. This remains a useful conceptual fallback, but the MCP
currently avoids adding Playwright/browser installation as a runtime dependency.

## Implemented provider model

Authentication is isolated in `src/zepp_mcp/auth.py` behind a small provider protocol.

Two providers exist initially:

- `StaticTokenAuthProvider` for an already-known app token and user ID;
- `PasswordAuthProvider` for one-time account/password exchange during `zepp-mcp setup`.

The rest of the API client remains token-based. This is intentional: password login is a credential
bootstrap mechanism, not a requirement for every MCP server process.

## Password login sequence

The provider first resolves a regional cluster. With `region=auto`, EU-like country codes select the
European `de2` cluster and other country codes select `us2`. Users can force `--region eu` or
`--region us` if the account was created on a different cluster.

The normal sequence is:

1. Encrypt the registration form using the protocol expected by the current Zepp v2 token endpoint.
2. POST to the regional `/v2/registrations/tokens` endpoint.
3. Parse the access token and country code from the redirect response.
4. Exchange that access token at the regional `/v2/client/login` endpoint.
5. Extract `token_info.app_token` and `token_info.user_id`.
6. Use the regional API host returned by the provider as `ZEPP_BASE_URL` unless the user explicitly
   supplied `--base-url`.
7. Verify the token through the existing `/users/-/profile` call before writing local configuration.

If the regional protocol is unavailable or returns an unexpected non-authentication error, setup
falls back to the historical Huami registration/login sequence. An explicit authentication rejection
or HTTP 429 does not trigger a second password attempt.

## Credential handling

The account password is accepted through hidden terminal input and is never written to the config
file. Successful setup persists only the data required for later read-only API access:

- `ZEPP_APP_TOKEN`
- `ZEPP_USER_ID`
- `ZEPP_BASE_URL`
- non-secret client settings already used by the MCP

The config file keeps the existing `0600` permission requirement on POSIX systems.

Authentication exceptions intentionally avoid including response bodies, passwords, or returned
access/app tokens in error messages.

## Failure modes

Expected failure categories are:

- invalid account/password;
- account assigned to a different regional cluster;
- HTTP 429 rate limiting;
- Zepp changing app metadata, encryption parameters, endpoints, or expected headers;
- network/DNS/TLS failure;
- a successful login returning a token that is not accepted by the selected API host.

The setup command preserves manual token mode as the recovery path:

```text
zepp-mcp setup --auth token
```

## Why not store email/password for automatic refresh?

The current app token normally survives across many MCP invocations, while the password is a much
more sensitive credential. Persisting the password would increase risk and tightly couple every
server startup to an unstable login protocol. The safer initial model is bootstrap once, verify the
returned app token, then run the MCP entirely with token credentials.

If future testing shows that tokens expire too frequently, refresh/login can be added as another
provider with explicit opt-in credential storage or OS keyring support rather than silently changing
the current security model.
