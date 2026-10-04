from ozon_buyer_mcp.marketplaces import (
    market_search_url,
    normalize_marketplace,
    normalize_marketplaces,
)
from ozon_buyer_mcp.models import MarketplaceOffer, MarketplaceSearchResponse


def test_marketplace_aliases():
    assert normalize_marketplace("wb") == "wildberries"
    assert normalize_marketplace("Wildberries") == "wildberries"
    assert normalize_marketplace("yandex") == "yandex_market"
    assert normalize_marketplace("market.yandex.ru") == "yandex_market"
    assert normalize_marketplaces(None) == ["ozon", "wildberries", "yandex_market"]


def test_market_search_urls():
    assert "wildberries.ru/catalog/0/search.aspx?search=" in market_search_url("wb", "Genau Stride X")
    assert "market.yandex.ru/search?text=" in market_search_url("yandex", "Genau Stride X")
    assert "ozon.ru/search/?text=" in market_search_url("ozon", "Genau Stride X")


def test_marketplace_models_roundtrip():
    offer = MarketplaceOffer(
        marketplace="wildberries",
        product_id="123",
        title="Test",
        price_rub=1000,
        relevance=1.0,
    )
    out = MarketplaceSearchResponse(
        query="Test",
        marketplaces=["wildberries"],
        count=1,
        offers=[offer],
        cheapest=offer,
    ).model_dump()
    assert out["cheapest"]["price_rub"] == 1000
    assert out["offers"][0]["marketplace"] == "wildberries"
