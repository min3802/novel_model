from __future__ import annotations

from typing import Final


COUNTRY_TO_LOCALE: Final[dict[str, str]] = {
    "\uc77c\ubcf8": "ko_ja",
    "\ubbf8\uad6d": "ko_en_us",
    "\uc911\uad6d": "ko_zh_cn",
    "\ud0dc\uad6d": "ko_th_th",
}

LOCALE_TO_COUNTRY: Final[dict[str, str]] = {locale: country for country, locale in COUNTRY_TO_LOCALE.items()}


def resolve_locale_for_country(country: str) -> str | None:
    return COUNTRY_TO_LOCALE.get((country or "").strip())


def resolve_country_for_locale(locale: str) -> str | None:
    return LOCALE_TO_COUNTRY.get((locale or "").strip())
