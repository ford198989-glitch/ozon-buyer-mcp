from __future__ import annotations
import asyncio
from urllib.parse import quote
from .browser import OzonBrowser
from .models import CompareItem, CompareResponse, DeliveryResponse, PriceResponse, ProductDetails, ReviewsResponse, SearchResponse
from .parsers import delivery_candidates, parse_details, parse_reviews, parse_search, product_path

_SORT_MAP = {"popular":"", "price":"price", "price_desc":"price_desc", "rating":"rating", "new":"new", "discount":"discount"}

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
        result=parse_search(await self.browser.fetch_json(path), query=query, sort=sort, limit=limit)
        result.note="Buyer-side data comes from Ozon storefront composer-api and can vary by region/session."
        return result

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
        path=product_path(product)
        return DeliveryResponse(product=product,candidates=delivery_candidates(await self.browser.fetch_json(path)))

    async def compare(self, products: list[str]) -> CompareResponse:
        cleaned=[str(x).strip() for x in products if str(x).strip()]
        if not 2 <= len(cleaned) <= 6: raise ValueError("products must contain from 2 to 6 SKU/URL values")
        details=await asyncio.gather(*(self.product(x,include_description=False) for x in cleaned))
        return CompareResponse(count=len(details),items=[CompareItem(
            sku=d.sku,title=d.title,price_rub=d.price_rub,regular_price_rub=d.regular_price_rub,
            old_price_rub=d.old_price_rub,rating=d.rating,reviews=d.reviews,seller=d.seller.name if d.seller else None,
            available=d.available,url=d.url,characteristics=d.characteristics) for d in details])
