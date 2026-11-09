import asyncio
import json
import pytest
from ozon_buyer_mcp.delivery import ranked_delivery_candidates
from ozon_buyer_mcp.service import OzonService

def page(**states):
    return {"widgetStates": {name+"-1-default-1": json.dumps(value) for name, value in states.items()}}

@pytest.mark.parametrize("month", "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split())
def test_all_months(month):
    result = ranked_delivery_candidates([page(webDelivery={"title": f"Доставим 12 {month}"})])
    assert len(result) == 1 and f"12 {month}" in result[0]

def test_navigation_feedback_recommendations_do_not_block_product_dates():
    data = page(catalogMenu={"text": "Доставка от 1 часа завтра"},
                footer={"text": "Доставка"},
                webFeedbackForm={"text": "Информация о доставке"},
                webRecommendations={"text": "Доставка завтра"},
                webDelivery={"title": "В пункт выдачи", "date": "10 ноября"})
    result = ranked_delivery_candidates([data])
    assert len(result) == 1 and result[0].startswith("webDelivery:")
    assert "10 ноября" in result[0]

@pytest.mark.parametrize("date", ["Сегодня", "Завтра", "Послезавтра", "Во вторник", "12–14 декабря"])
def test_relative_and_range(date):
    assert ranked_delivery_candidates([page(webDelivery={"text": date})])

def test_reject_unknown_date_and_tracking_only_dates():
    assert ranked_delivery_candidates([page(webDelivery={"title": "Условия доставки", "trackingInfo":{"text":"Завтра"}})]) == []
    assert ranked_delivery_candidates([page(catalogMenu={"text": "Завтра"})]) == []
    assert ranked_delivery_candidates([ValueError("offline"), {}, {"widgetStates":{"webDelivery-x":"{"}}]) == []

def test_deduplicate_pages_and_rank_current_seller():
    a = page(webDelivery={"title":"Завтра", "seller":"Другой", "sku":"999999"})
    b = page(webDelivery={"title":"12 ноября", "seller":"Магазин", "sku":"123456"})
    result = ranked_delivery_candidates([a,b,b], sku="123456", seller="Магазин")
    assert len(result) == 2 and "12 ноября" in result[0]
    assert "[sku]" in result[0] and "[seller]" in result[0]

def test_service_uses_filtered_candidates_even_with_page_failures():
    class Browser:
        async def fetch_json(self, path, **kwargs):
            if "layout_page_index=4" in path:
                raise RuntimeError("page unavailable")
            return page(webGallery={"sku":"123456"}, catalogMenu={"text":"Доставка от 1 часа"},
                        webDelivery={"text":"Завтра"})
    result = asyncio.run(OzonService(Browser()).delivery("123456"))
    assert result.candidates == ["webDelivery: Завтра"]


def test_search_summary_accepts_november_not_just_september():
    from ozon_buyer_mcp.service import _summary_from_dom
    item = _summary_from_dom({'sku':'123456', 'title':'Товар', 'text':'Доставка 14 ноября'})
    assert '14 ноября' in item.discount_text
