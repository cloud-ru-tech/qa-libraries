# Pitfalls

Non-obvious behaviour that costs time when you hit it unprepared.

## A sync/async mismatch sends unauthenticated requests, silently

`IAM_Auth` overrides only `sync_auth_flow`; `IAM_AsyncAuth` overrides only `async_auth_flow`. Everything else falls back to `httpx.Auth`, whose default `auth_flow` yields the request unchanged.

So passing `IAM_Auth` to an `httpx.AsyncClient` (or `IAM_AsyncAuth` to a sync one) raises nothing, issues no token, and touches no header. The request goes out bare and the service answers 401 — which looks like an expired key, not like wiring.

```python
# WRONG — no Authorization header, no exception, no log line
async with httpx.AsyncClient(auth=IAM_Auth("kid", "secret", iam_client)) as client:
    await client.get("https://api.example.com/data")
```

The IAM client must match too: `IAM_Auth` needs `IAM_HttpClient` or `IAM_OpenID_HttpClient`, `IAM_AsyncAuth` needs the async twins. That half is caught statically — the constructors are typed with `IAM_SyncClientT` / `IAM_AsyncClientT`, so mypy flags it. The client-side mismatch is not typed at all: `httpx.Client(auth=...)` accepts any `Auth`.

When debugging a 401, check the outgoing request's headers before checking the key.

## Tokens are keyed by `key_id` alone

`store.get(key_id)` / `store.set(key_id, token)` — nothing about the IAM host or API is part of the key. One shared store plus two auth objects using the same key against different IAM endpoints (public API and OpenID, or two environments) means they overwrite each other's tokens and hand each other's tokens out.

This is fine and intentional for the normal case — one key, one IAM. If you do need two, give each auth object its own store instance.

## A custom store must round-trip `expires_at` exactly

`Token` is a frozen dataclass, so equality compares both `access_token` and `expires_at`. The 401 path uses that: it re-reads the store and only goes back to IAM when the stored token still equals the one the service just rejected.

A store that loses precision — truncating microseconds, dropping the timezone, storing a Unix integer — returns a token that is *unequal* to the rejected one. The refresh then concludes "someone else already renewed it" and retries with the same dead access token. The retry fails, and the caller sees a plain 401 with no clue why.

Serialize `expires_at` with `.isoformat()` and restore it with `datetime.fromisoformat()`, or keep the full `datetime` in a store that supports it.

## Two 401s in a row surface as a response, not an exception

The auth retries exactly once. If the second attempt is also rejected, that 401 response is returned to the caller like any other response — `IAM_Error` is only raised when *IAM itself* fails, never when the business service rejects the token.

Verified behaviour for a service that answers 401 unconditionally: 2 requests to the service, 2 token issues, final status 401.

So an invalid key pair does not throw. `raise_for_status()` or an explicit status check is still your job.

## Only 401 triggers a refresh

403 and 419 do not. A service that answers 403 for an expired token keeps getting the stale one until it expires on its own clock. If you are integrating with such a service, that is a service-side quirk to raise with its owners — do not wrap this auth in a retry loop to paper over it.

## Streaming request bodies are read into memory

The auth flow calls `request.read()` / `await request.aread()` before sending, because a body consumed by the first attempt would be empty on the 401 retry. A multi-gigabyte upload through an authorized client is therefore fully buffered.

For large uploads, get the token first and send the stream through a client without this auth attached.

## The async store is awaited while the lock is held

Both `_get_token` and `_refresh_token` hold the auth object's lock across the store call and the IAM call. That is what makes concurrent callers issue one token instead of N — but it also means a slow store stalls every coroutine sharing that auth object, not just the one that triggered it.

Keep store implementations cheap, and give them their own timeout.

## `expires_in: 0` means a new token per request

The safety margin is `min(30s, lifetime / 2)`, so a zero or negative `expires_in` produces a token whose `expires_at` is already in the past. Nothing loops or fails — the auth simply issues a fresh token on every single request. If IAM traffic looks unreasonable, check what `expires_in` it is actually returning.

For a 10-second token the margin shrinks to 5 seconds and the token stays usable, as intended.

## `AuthData` discards everything it does not declare

`scope`, `token_type`, `refresh_token` and any other field IAM returns are dropped during parsing. There is no passthrough dict. If a caller needs one of those, it has to be added as a field on `AuthData` in this library.

## False alarms when reading the code

- Canonical class names follow CapWords (`IamAuth`, `IamOpenIdHttpClient`). Legacy names such as
  `IAM_Auth` and `IAM_OpenID_HttpClient` remain aliases; they do not require disabling Ruff naming checks.
- `store if store is not None else InMemoryAuthStore()` is deliberately not `store or InMemoryAuthStore()`. A store wrapping an empty collection can be falsey, and the short form would silently throw it away.
- `AuthData.__post_init__` type-checks its own fields, which looks redundant next to the annotations. It is not: the values come straight from `response.json()`, so a proxy or an error page can put anything there.
- `IAM_InvalidJsonResponseError` reports only the status and content type, never the body — unlike `IAM_AuthError`. That asymmetry is intentional: it fires on a *successful* IAM response, whose body contains a live access token.
