"""Параметры демо-стенда httpbin."""

import os

BASE_URL = os.getenv("HTTPBIN_BASE_URL", "http://localhost:8080")

DEMO_USER = "demo"
DEMO_PASSWORD = "s3cret"  # noqa: S105
DEMO_API_KEY = "demo-api-key-42"

CLIENT_NAME = "httpbin-demo"
CLIENT_VERSION = "1.0.0"

# Пути glom для маскирования. Первые две строки закрывают тело запроса,
# остальные — эхо этого же тела и заголовков в ответе httpbin.
# Типовые секреты (authorization, token, password, ...) библиотека маскирует сама.
SANITIZE_KEYS: tuple[str, ...] = (
    "user.password",
    "items.*.token",
    "json.user.password",
    "json.items.*.token",
    "headers.Authorization",
    "headers.X-Api-Key",
    # httpbin кладёт в data сырое тело запроса одной строкой. Маскирование работает
    # по разобранной структуре и внутрь строки не заглядывает, поэтому такое поле
    # закрывается только целиком — иначе секрет утечёт в лог через него.
    "data",
)
