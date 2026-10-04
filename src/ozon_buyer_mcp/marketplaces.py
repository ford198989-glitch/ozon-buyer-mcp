from __future__ import annotations

from urllib.parse import quote


SUPPORTED_MARKETPLACES = ("ozon", "wildberries", "yandex_market")

_ALIASES = {
    "ozon": "ozon",
    "wb": "wildberries",
    "wildberries": "wildberries",
    "wildberry": "wildberries",
    "wildberries.ru": "wildberries",
    "yandex": "yandex_market",
    "market": "yandex_market",
    "yandex_market": "yandex_market",
    "yandex-market": "yandex_market",
    "market.yandex.ru": "yandex_market",
}


def normalize_marketplace(value: str) -> str:
    key = str(value or "").strip().lower()
    market = _ALIASES.get(key)
    if not market:
        raise ValueError(
            "marketplace must be one of: ozon, wildberries, yandex_market"
        )
    return market


def normalize_marketplaces(values: list[str] | None) -> list[str]:
    raw = values or list(SUPPORTED_MARKETPLACES)
    out: list[str] = []
    for value in raw:
        market = normalize_marketplace(value)
        if market not in out:
            out.append(market)
    if not out:
        raise ValueError("at least one marketplace is required")
    return out


def market_search_url(marketplace: str, query: str) -> str:
    market = normalize_marketplace(marketplace)
    q = quote(str(query or "").strip())
    if not q:
        raise ValueError("query is required")
    if market == "wildberries":
        return f"https://www.wildberries.ru/catalog/0/search.aspx?search={q}"
    if market == "yandex_market":
        return f"https://market.yandex.ru/search?text={q}"
    return f"https://www.ozon.ru/search/?text={q}&from_global=true"
