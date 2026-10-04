from __future__ import annotations
import asyncio
import json
import re
from urllib.parse import quote
from .browser import OzonBrowser
from .marketplaces import NEW_GOODS_MARKETPLACES, normalize_marketplaces
from .models import CompareItem, CompareResponse, DeliveryResponse, MarketplaceOffer, MarketplaceSearchResponse, PriceResponse, ProductDetails, ProductSummary, ReviewsResponse, SearchResponse
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

def _match_metrics(query: str, text: str | None) -> tuple[float, bool]:
    q_all = re.findall(r"[a-zа-яё0-9]+", str(query or "").lower())
    t = set(re.findall(r"[a-zа-яё0-9]+", str(text or "").lower()))
    q = {
        x for x in q_all
        if len(x) > 1 or re.fullmatch(r"[a-z0-9]", x)
    }
    if not q:
        return 0.0, False

    overlap = len(q & t) / len(q)
    normalized_query = " ".join(q_all)
    normalized_text = " ".join(re.findall(r"[a-zа-яё0-9]+", str(text or "").lower()))
    if normalized_query and normalized_query in normalized_text:
        overlap = min(1.0, overlap + 0.2)

    model_tokens = {
        x for x in q
        if any(ch.isdigit() for ch in x)
        or (len(x) <= 2 and re.fullmatch(r"[a-z0-9]+", x))
    }
    exact = q.issubset(t) or (
        bool(model_tokens)
        and model_tokens.issubset(t)
        and overlap >= 0.75
    )
    return round(overlap, 3), exact


def _query_relevance(query: str, title: str | None) -> float:
    return _match_metrics(query, title)[0]


def _market_offer_from_raw(marketplace: str, query: str, item: dict) -> MarketplaceOffer:
    title = str(item.get("title") or "") or None
    relevance, exact_match = _match_metrics(query, title)
    return MarketplaceOffer(
        marketplace=marketplace,
        product_id=str(item.get("product_id") or "") or None,
        title=title,
        url=str(item.get("url") or "") or None,
        price_rub=item.get("price_rub") if isinstance(item.get("price_rub"), int) else None,
        old_price_rub=item.get("old_price_rub") if isinstance(item.get("old_price_rub"), int) else None,
        rating=float(item["rating"]) if isinstance(item.get("rating"), (int, float)) else None,
        reviews=int(item["reviews"]) if isinstance(item.get("reviews"), (int, float)) else None,
        delivery_text=str(item.get("delivery_text") or "") or None,
        seller=str(item.get("seller") or "") or None,
        image=str(item.get("image") or "") or None,
        relevance=relevance,
        exact_match=exact_match,
        condition=str(item.get("condition") or "") or ("unknown" if marketplace == "avito" else "new"),
        price_confidence=str(item.get("price_confidence") or "") or "medium",
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

    async def marketplace_search(
        self,
        query: str,
        marketplaces: list[str] | None = None,
        limit_per_market: int = 8,
    ) -> MarketplaceSearchResponse:
        query = str(query or "").strip()
        if not query:
            raise ValueError("query is required")
        markets = normalize_marketplaces(marketplaces)
        limit_per_market = max(1, min(int(limit_per_market), 20))
        offers: list[MarketplaceOffer] = []
        errors: dict[str, str] = {}

        for market in markets:
            try:
                if market == "ozon":
                    result = await self.search(query, limit=limit_per_market)
                    for item in result.items:
                        match_text = " ".join(
                            x for x in [item.title, item.discount_text] if x
                        )
                        relevance, exact_match = _match_metrics(query, match_text)
                        offers.append(MarketplaceOffer(
                            marketplace="ozon",
                            product_id=item.sku,
                            title=item.title,
                            url=item.url,
                            price_rub=item.price_rub,
                            old_price_rub=item.old_price_rub,
                            rating=item.rating,
                            reviews=item.reviews,
                            delivery_text=item.discount_text,
                            image=item.image,
                            relevance=relevance,
                            exact_match=exact_match,
                            condition="new",
                            price_confidence="high",
                        ))
                else:
                    items = await self.browser.market_search_dom(
                        market,
                        query,
                        limit=limit_per_market,
                    )
                    offers.extend(
                        _market_offer_from_raw(market, query, item)
                        for item in items
                        if isinstance(item, dict)
                    )
            except Exception as exc:
                errors[market] = f"{type(exc).__name__}: {exc}"

        offers.sort(
            key=lambda x: (
                -(x.relevance or 0.0),
                x.price_rub if x.price_rub is not None else 10**12,
            )
        )
        priced = [
            x for x in offers
            if x.price_rub is not None and x.marketplace != "avito"
        ]
        exact_priced = [x for x in priced if x.exact_match]
        relevant_priced = [x for x in priced if (x.relevance or 0.0) >= 0.65]
        cheapest = min(
            exact_priced or relevant_priced or priced,
            key=lambda x: x.price_rub or 10**12,
            default=None,
        )

        return MarketplaceSearchResponse(
            query=query,
            marketplaces=markets,
            count=len(offers),
            offers=offers,
            cheapest=cheapest,
            errors=errors,
            note=(
                "Marketplace results are read from rendered pages in the local Chrome profile. "
                "Prices, delivery and availability may depend on account and region."
            ),
        )

    async def compare_marketplaces(
        self,
        query: str,
        marketplaces: list[str] | None = None,
        limit_per_market: int = 8,
    ) -> dict:
        result = await self.marketplace_search(
            query=query,
            marketplaces=marketplaces,
            limit_per_market=limit_per_market,
        )
        by_market = []
        best_prices: list[int] = []
        for market in result.marketplaces:
            candidates = [
                x for x in result.offers
                if x.marketplace == market
                and x.price_rub is not None
                and (x.relevance or 0.0) >= 0.45
            ]
            if not candidates:
                candidates = [
                    x for x in result.offers
                    if x.marketplace == market and x.price_rub is not None
                ]
            best = min(candidates, key=lambda x: x.price_rub or 10**12, default=None)
            if best and best.price_rub is not None:
                best_prices.append(best.price_rub)
            by_market.append({
                "marketplace": market,
                "best_offer": best.model_dump() if best else None,
            })

        best_offer = result.cheapest.model_dump() if result.cheapest else None
        savings = (
            max(best_prices) - min(best_prices)
            if len(best_prices) >= 2
            else None
        )
        return {
            "query": result.query,
            "best_offer": best_offer,
            "by_market": by_market,
            "offers_checked": result.count,
            "savings_vs_most_expensive_market_rub": savings,
            "errors": result.errors,
            "note": result.note,
        }

    async def best_buy(
        self,
        query: str,
        sources: list[str] | None = None,
        limit_per_source: int = 6,
        include_avito: bool = True,
    ) -> dict:
        markets = normalize_marketplaces(sources)
        if not include_avito:
            markets = [x for x in markets if x != "avito"]
        result = await self.marketplace_search(
            query=query,
            marketplaces=markets,
            limit_per_market=limit_per_source,
        )

        def acceptable(x: MarketplaceOffer) -> bool:
            if x.price_rub is None:
                return False
            if x.price_confidence == "low":
                return False
            return x.exact_match or (x.relevance or 0.0) >= 0.68

        new_offers = [
            x for x in result.offers
            if x.marketplace in NEW_GOODS_MARKETPLACES and acceptable(x)
        ]
        avito_offers = [
            x for x in result.offers
            if x.marketplace == "avito" and acceptable(x)
        ]

        if not new_offers:
            new_offers = [
                x for x in result.offers
                if x.marketplace in NEW_GOODS_MARKETPLACES
                and x.price_rub is not None
                and (x.relevance or 0.0) >= 0.55
            ]

        best_new = min(
            new_offers,
            key=lambda x: x.price_rub or 10**12,
            default=None,
        )
        best_avito = min(
            avito_offers,
            key=lambda x: x.price_rub or 10**12,
            default=None,
        )

        by_source = []
        for market in result.marketplaces:
            candidates = [
                x for x in result.offers
                if x.marketplace == market and acceptable(x)
            ]
            best = min(
                candidates,
                key=lambda x: x.price_rub or 10**12,
                default=None,
            )
            by_source.append({
                "source": market,
                "best_offer": best.model_dump() if best else None,
            })

        ozon_candidates = [
            x for x in new_offers if x.marketplace == "ozon"
        ]
        best_ozon = min(
            ozon_candidates,
            key=lambda x: x.price_rub or 10**12,
            default=None,
        )
        savings_vs_ozon = None
        if (
            best_new and best_new.price_rub is not None
            and best_ozon and best_ozon.price_rub is not None
        ):
            savings_vs_ozon = best_ozon.price_rub - best_new.price_rub

        return {
            "query": query,
            "best_new_offer": best_new.model_dump() if best_new else None,
            "best_avito_offer": best_avito.model_dump() if best_avito else None,
            "best_ozon_offer": best_ozon.model_dump() if best_ozon else None,
            "savings_vs_ozon_rub": savings_vs_ozon,
            "by_source": by_source,
            "offers_checked": result.count,
            "errors": result.errors,
            "rules": {
                "avito_separate_from_new": True,
                "minimum_relevance": 0.68,
                "exact_model_match_preferred": True,
                "low_confidence_prices_excluded": True,
            },
            "note": (
                "Best new offer excludes Avito. Web-store prices are taken from "
                "structured product data or rendered pages and should be verified "
                "on the linked product page before purchase."
            ),
        }

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
                sku_match = str(product) in text or (details.sku and str(details.sku) in text)

                for m in trigger.finditer(text):
                    a = max(0, m.start() - 220)
                    b = min(len(text), m.end() + 260)
                    snippet = re.sub(r"\\[nrt]+|\s+", " ", text[a:b]).strip()
                    prefix = f"{widget_key}"
                    if sku_match:
                        prefix += " [sku]"
                    if seller_match:
                        prefix += " [seller]"
                    if price_match:
                        prefix += " [price]"
                    candidate = f"{prefix}: {snippet}"
                    score = (
                        (8 if sku_match else 0)
                        + (4 if seller_match else 0)
                        + (2 if price_match else 0)
                        + (1 if page_index == 0 else 0)
                    )
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
