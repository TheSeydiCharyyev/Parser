from __future__ import annotations

from urllib.parse import urlparse

from django.core.exceptions import ValidationError


def validate_http_url_allow_internal(value: str) -> None:
    """Валидация URL для подписок.

    В dev/демо нам нужны внутренние адреса вида http://backend:8000/..., поэтому
    валидатор не требует TLD, а проверяет только схему и наличие host.
    """

    try:
        parsed = urlparse((value or "").strip())
    except Exception:
        raise ValidationError("Введите правильный URL.")

    if parsed.scheme not in {"http", "https"}:
        raise ValidationError("Введите правильный URL.")
    if not parsed.netloc:
        raise ValidationError("Введите правильный URL.")
