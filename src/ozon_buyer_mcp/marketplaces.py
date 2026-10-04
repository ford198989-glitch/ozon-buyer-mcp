from __future__ import annotations

from urllib.parse import quote


SUPPORTED_MARKETPLACES = (
    "ozon",
    "wildberries",
    "yandex_market",
    "megamarket",
    "avito",
    "web",
)

NEW_GOODS_MARKETPLACES = (
    "ozon",
    "wildberries",
    "yandex_market",
    "megamarket",
    "web",
)

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
    "mega": "megamarket",
    "megamarket": "megamarket",
    "megamarket.ru": "megamarket",
    "авито": "avito",
    "avito": "avito",
    "avito.ru": "avito",
    "internet": "web",
    "интернет": "web",
    "web": "web",
    "all_web": "web",
}


def normalize_marketplace(value: str) -> str:
    key = str(value or "").strip().lower()
    market = _ALIASES.get(key)
    if not market:
        raise ValueError(
            "marketplace must be one of: "
            + ", ".join(SUPPORTED_MARKETPLACES)
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
    if market == "megamarket":
        return f"https://megamarket.ru/catalog/?q={q}"
    if market == "avito":
        return f"https://www.avito.ru/all?q={q}"
    if market == "web":
        # Yandex documents the desktop query endpoint with the text parameter.
        return f"https://yandex.ru/search/?text={q}%20%D0%BA%D1%83%D0%BF%D0%B8%D1%82%D1%8C%20%D1%86%D0%B5%D0%BD%D0%B0"
    return f"https://www.ozon.ru/search/?text={q}&from_global=true"
