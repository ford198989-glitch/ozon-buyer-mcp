from __future__ import annotations
import asyncio
import json
import re
from urllib.parse import quote
from .browser import OzonBrowser
from .models import CompareItem, CompareResponse, DeliveryResponse, PriceResponse, ProductDetails, ProductSummary, ReviewsResponse, SearchResponse
from .parsers import delivery_candidates, parse_details, parse_reviews, product_path, price_to_number

_SORT_MAP = {"popular":"", "price":"price", "price_desc":"price_desc", "rating":"rating", "new":"new", "discount":"discount"}

def _summary_from_dom(card: dict) -> ProductSummary:
    text = str(card.get("text") or "")
    prices = [price_to_number(x) for x in re.findall(r"(\d[\d\s\u00a0]{1,12})\s*₽", text)]
    prices = [p for p in prices if p]
    price = prices[0] if prices else None
    old = next((p for p in prices[1:] if price and p > price), None)

    rating = None
    reviews = None
    m = re.search(r"([1-5][\.,]\d)\s+([\d\s]+)\s*(?:отзыв|отзывов|оцен)", text, re.I)
    if m:
        try:
            rating = float(m.group(1).replace(",", "."))
        except ValueError:
            pass
        reviews = price_to_number(m.group(2))

    delivery_text = None
    dm = re.search(
        r"(.{0,90}(?:достав\w*|завтра|послезавтра|сегодня|"
        r"\b(?:28|29)\s+сентябр\w*|"
        r"понедельник|вторник|сред[ау]|четверг|пятниц|суббот|воскресень).{0,130})",
        text,
        re.I,
    )
    if dm:
        delivery_text = re.sub(r"\s+", " ", dm.group(1)).strip()

    title = str(card.get("title") or "").strip() or None
    if not title:
        lines = [x.strip() for x in re.split(r"[\r\n]+", text) if x.strip()]
        title = next((x for x in lines if "₽" not in x and len(x) >= 8), None)

    return ProductSummary(
        sku=str(card.get("sku") or ""),
        title=title,
        url=str(card.get("url") or "") or None,
        price_rub=price,
        regular_price_rub=price,
        old_price_rub=old,
        discount_text=delivery_text,
        rating=rating,
        reviews=reviews,
        image=str(card.get("image") or "") or None,
    )

class OzonService:
    def __init__(self, browser: OzonBrowser) -> None:
        self.browser = browser

    async def search(self, query: str, limit: int = 12, sort: str = "popular",
                     price_min: int | None = None, price_max: int | None = None) -> SearchResponse:
        query=query.strip()
        if not query: raise ValueError("query is required")
        if sort not in _SORT_MAP: raise ValueError(f"sort must be one of: {', '.join(_SORT_MAP)}")
        limit=max(1,min(limit,30))
        path=f"/search/?text={quote(query)}&from_global=true"
        if _SORT_MAP[sort]: path += f"&sorting={_SORT_MAP[sort]}"
        if price_min is not None or price_max is not None:
            low=max(0,int(price_min or 0)); high=max(low,int(price_max or 99_999_999))
            path += f"&currency_price={low}.000%3B{high}.000"

        cards = await self.browser.search_dom(path, limit=limit)
        items = [_summary_from_dom(card) for card in cards]
        items = [item for item in items if item.sku]

        if price_min is not None:
            items = [x for x in items if x.price_rub is None or x.price_rub >= price_min]
        if price_max is not None:
            items = [x for x in items if x.price_rub is None or x.price_rub <= price_max]

        return SearchResponse(
            query=query,
            sort=sort,
            count=len(items),
            items=items[:limit],
            note="Search data was read from the rendered Ozon web page; no direct composer-api request was used.",
        )

    async def product(self, product: str, include_description: bool = True) -> ProductDetails:
        path=product_path(product)
        if include_description:
            base,page2=await asyncio.gather(self.browser.fetch_json(path),
                self.browser.fetch_json(f"{path}?layout_container=pdpPage2column&layout_page_index=2"))
        else:
            base=await self.browser.fetch_json(path); page2={}
        return parse_details(base,page2)

    async def reviews(self, product: str, limit: int = 10) -> ReviewsResponse:
        path=product_path(product)
        return parse_reviews(await self.browser.fetch_json(f"{path}reviews/"), limit=max(1,min(limit,50)))

    async def price(self, product: str) -> PriceResponse:
        d=await self.product(product, include_description=False)
        return PriceResponse(sku=d.sku,title=d.title,price_rub=d.price_rub,regular_price_rub=d.regular_price_rub,
                             old_price_rub=d.old_price_rub,available=d.available,url=d.url)

    async def delivery(self, product: str) -> DeliveryResponse:
        path = product_path(product)
        details = await self.product(product, include_description=False)
        seller_name = (details.seller.name if details.seller else "") or ""
        price_text = str(details.price_rub or "")

        paths = [path]
        paths += [
            f"{path}?layout_container=pdpPage2column&layout_page_index={i}"
            for i in range(1, 7)
        ]
        pages = await asyncio.gather(
            *(self.browser.fetch_json(p, retries=1) for p in paths),
            return_exceptions=True,
        )

        trigger = re.compile(
            r"(?:достав\w*|сегодня|завтра|послезавтра|"
            r"\b\d{1,2}\s+(?:сентябр\w*|октябр\w*))",
            re.I,
        )
        found = []
        scored = []

        for page_index, page in enumerate(pages):
            if not isinstance(page, dict):
                continue
            for widget_key, raw in (page.get("widgetStates") or {}).items():
                try:
                    obj = json.loads(raw) if isinstance(raw, str) else raw
                    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
                except Exception:
                    text = str(raw)
                if not trigger.search(text):
                    continue

                lower = text.lower()
                seller_match = bool(seller_name and seller_name.lower() in lower)
                price_match = bool(price_text and price_text in text)

                for m in trigger.finditer(text):
                    a = max(0, m.start() - 220)
                    b = min(len(text), m.end() + 260)
                    snippet = re.sub(r"\\[nrt]+|\s+", " ", text[a:b]).strip()
                    prefix = f"{widget_key}"
                    if seller_match:
                        prefix += " [seller]"
                    if price_match:
                        prefix += " [price]"
                    candidate = f"{prefix}: {snippet}"
                    score = (4 if seller_match else 0) + (2 if price_match else 0) + (1 if page_index == 0 else 0)
                    if candidate not in found:
                        found.append(candidate)
                        scored.append((score, candidate))

        scored.sort(key=lambda x: x[0], reverse=True)
        candidates = [x[1] for x in scored[:40]]

        if not candidates:
            for page in pages:
                if isinstance(page, dict):
                    for item in delivery_candidates(page, limit=40):
                        if item not in candidates:
                            candidates.append(item)

        return DeliveryResponse(
            product=product,
            candidates=candidates[:40],
            note=(
                f"Delivery contexts are ranked for the current product seller={seller_name!r} "
                f"and price={details.price_rub!r}; dates may still include alternate offers if Ozon "
                "stores seller and delivery widgets separately."
            ),
        )

    async def compare(self, products: list[str]) -> CompareResponse:
        cleaned=[str(x).strip() for x in products if str(x).strip()]
        if not 2 <= len(cleaned) <= 6: raise ValueError("products must contain from 2 to 6 SKU/URL values")
        details=await asyncio.gather(*(self.product(x,include_description=False) for x in cleaned))
        return CompareResponse(count=len(details),items=[CompareItem(
            sku=d.sku,title=d.title,price_rub=d.price_rub,regular_price_rub=d.regular_price_rub,
            old_price_rub=d.old_price_rub,rating=d.rating,reviews=d.reviews,seller=d.seller.name if d.seller else None,
            available=d.available,url=d.url,characteristics=d.characteristics) for d in details])
