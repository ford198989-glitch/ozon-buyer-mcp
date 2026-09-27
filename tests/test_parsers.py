import json
from ozon_buyer_mcp.parsers import clean_url, parse_details, parse_reviews, parse_search, price_to_number, product_path

def _page(**widgets):
    return {"widgetStates": {f"{name}-1-default-1": json.dumps(value) for name, value in widgets.items()}}

def test_price_to_number():
    assert price_to_number("53 022 ₽") == 53022
    assert price_to_number("нет") is None

def test_product_path():
    assert product_path("1185261285") == "/product/1185261285/"
    assert product_path("https://www.ozon.ru/product/foo-1185261285/?at=x") == "/product/foo-1185261285/"

def test_clean_url():
    assert clean_url("/product/a-123456/?at=x") == "https://www.ozon.ru/product/a-123456/"

def test_parse_search():
    item={"sku":1185261285,"action":{"link":"/product/demo-1185261285/?at=x"},"mainState":[
        {"type":"priceV2","priceV2":{"price":[{"textStyle":"PRICE","text":"1 234 ₽"},{"textStyle":"ORIGINAL_PRICE","text":"1 500 ₽"}],"discount":"-18%"}},
        {"id":"name","textDS":{"text":"Тестовый товар"}},
        {"labelListV2":{"items":[{"type":"icon","icon":{"name":"ic_s_star"}},{"type":"text","text":{"text":"4,8"}},{"type":"text","text":{"text":"321 отзыв"}}]}}]}
    r=parse_search(_page(tileGridDesktop={"items":[item]}),query="тест",sort="popular",limit=10)
    assert r.count==1 and r.items[0].sku=="1185261285" and r.items[0].price_rub==1234 and r.items[0].rating==4.8

def test_parse_details():
    base=_page(webProductHeading={"title":"Товар"},webPrice={"cardPrice":"999 ₽","price":"1 099 ₽","originalPrice":"1 500 ₽","isAvailable":True},
               webGallery={"sku":"123456789","coverImage":"https://img/1.jpg","images":[{"src":"https://img/2.jpg"}]},
               webCurrentSeller={"sellerCell":{"centerBlock":{"title":{"text":"Продавец"}},"common":{"action":{"link":"/seller/demo-1/"}}},
                                 "rating":{"title":{"text":"4,9"}}})
    r=parse_details(base,{})
    assert r.sku=="123456789" and r.price_rub==999 and r.available is True and r.seller.name=="Продавец"

def test_parse_reviews():
    p=_page(webListReviews={"reviews":[{"author":{"title":"Иван"},"publishedAt":1704067200,"isItemPurchased":True,
                                            "content":{"score":5,"comment":"Хорошо","positive":"Быстро","negative":""}}]})
    r=parse_reviews(p)
    assert r.count==1 and r.reviews[0].author=="Иван" and r.reviews[0].score==5 and r.reviews[0].purchased is True
