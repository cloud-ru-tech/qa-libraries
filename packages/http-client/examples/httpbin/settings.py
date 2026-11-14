"""httpbin demo environment settings."""

import os

BASE_URL = os.getenv("HTTPBIN_BASE_URL", "http://localhost:8080")

DEMO_USER = "demo"
DEMO_PASSWORD = "s3cret"  # noqa: S105
DEMO_API_KEY = "demo-api-key-42"

CLIENT_NAME = "httpbin-demo"
CLIENT_VERSION = "1.0.0"

# Glom masking paths. The first two lines mask the request body,
# the rest mask the echoed body and headers in the httpbin response.
# The library masks common secrets (authorization, token, password, ...) itself.
SANITIZE_KEYS: tuple[str, ...] = (
    "user.password",
    "items.*.token",
    "json.user.password",
    "json.items.*.token",
    "headers.Authorization",
    "headers.X-Api-Key",
    # httpbin puts the raw request body in data as a single string. Masking works
    # on parsed structures and does not inspect strings, so mask this entire field
    # to prevent secrets from leaking into logs through it.
    "data",
)
