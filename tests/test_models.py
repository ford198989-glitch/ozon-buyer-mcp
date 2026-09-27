from ozon_buyer_mcp.models import ProductSummary, SearchResponse


def test_models_roundtrip():
    item = ProductSummary(
        sku="1",
        title="Test",
        url="https://www.ozon.ru/product/1",
        price_rub=123,
    )
    out = SearchResponse(query="x", items=[item], count=1).model_dump()
    assert out["items"][0]["price_rub"] == 123
    assert out["items"][0]["sku"] == "1"
