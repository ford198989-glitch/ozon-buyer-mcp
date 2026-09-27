from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from .models import Description, ProductDetails, ProductSummary, Review, ReviewsResponse, SearchResponse, Seller


def price_to_number(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    digits = re.sub(r"[^0-9]", "", value)
    return int(digits) if digits else None


def clean_url(link: str | None) -> str | None:
    if not link:
        return None
    path = str(link).split("?", 1)[0]
    if path.startswith("http"):
        return path
    if not path.startswith("/"):
        path = "/" + path
    return "https://www.ozon.ru" + path


def product_path(product: str) -> str:
    raw = str(product or "").strip()
    if not raw:
        raise ValueError("product is required")
    if raw.startswith(("http://", "https://")):
        return urlparse(raw).path.rstrip("/") + "/"
    if raw.startswith("/product/"):
        return raw.rstrip("/") + "/"
    if raw.isdigit():
        return f"/product/{raw}/"
    return f"/product/{raw.strip('/')}/"


def _widget_name(key: str) -> str:
    return str(key).split("-", 1)[0]


def widget(page: dict[str, Any], name: str) -> dict[str, Any] | None:
    for key, raw in (page.get("widgetStates") or {}).items():
        if _widget_name(key) != name:
            continue
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def widgets(page: dict[str, Any], name: str) -> list[dict[str, Any]]:
    out = []
    for key, raw in (page.get("widgetStates") or {}).items():
        if _widget_name(key) != name:
            continue
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue
        if isinstance(parsed, dict):
            out.append(parsed)
    return out


def _parse_search_item(item: dict[str, Any]) -> ProductSummary | None:
    states = item.get("mainState") if isinstance(item.get("mainState"), list) else []
    price_block = next((s.get("priceV2") for s in states if s.get("type") == "priceV2"), None)
    prices = price_block.get("price", []) if isinstance(price_block, dict) else []
    price = price_to_number(next((x.get("text") for x in prices if x.get("textStyle") == "PRICE"), None))
    old = price_to_number(next((x.get("text") for x in prices if x.get("textStyle") == "ORIGINAL_PRICE"), None))
    title = None
    for state in states:
        if state.get("id") == "name":
            title = (state.get("textDS") or {}).get("text")
            break
    url = clean_url((item.get("action") or {}).get("link"))
    sku = str(item.get("sku") or item.get("id") or "")
    if not sku or price is None:
        return None
    rating = None
    reviews = None
    for state in states:
        labels = state.get("labelListV2")
        if not isinstance(labels, dict) or "ic_s_star" not in json.dumps(labels):
            continue
        texts = [(x.get("text") or {}).get("text") for x in labels.get("items", []) if x.get("type") == "text"]
        if texts:
            try:
                rating = float(str(texts[0]).replace(",", "."))
            except Exception:
                pass
        if len(texts) > 1:
            reviews = price_to_number(texts[1])
        break
    return ProductSummary(
        sku=sku,
        title=title,
        url=url,
        price_rub=price,
        regular_price_rub=price,
        old_price_rub=old if old and old > price else None,
        discount_text=str(price_block.get("discount")) if isinstance(price_block, dict) and price_block.get("discount") else None,
        rating=rating,
        reviews=reviews,
    )


def parse_search(page: dict[str, Any], query: str, sort: str, limit: int = 12) -> SearchResponse:
    grid = widget(page, "tileGridDesktop") or {}
    items = []
    for raw in grid.get("items", []):
        if not isinstance(raw, dict):
            continue
        parsed = _parse_search_item(raw)
        if parsed:
            items.append(parsed)
        if len(items) >= limit:
            break
    return SearchResponse(query=query, sort=sort, count=len(items), items=items)


def _score(page: dict[str, Any]) -> tuple[float | None, int | None]:
    data = widget(page, "webSingleProductScore") or widget(page, "webReviewProductScore") or {}
    text = str(data.get("text") or json.dumps(data, ensure_ascii=False))
    m = re.search(r"(\d[\.,]\d)", text)
    rating = float(m.group(1).replace(",", ".")) if m else None
    m2 = re.search(r"(\d[\d\s]*)\s*отзыв", text, re.I)
    return rating, price_to_number(m2.group(1)) if m2 else None


def _seller(page: dict[str, Any]) -> Seller | None:
    data = widget(page, "webCurrentSeller") or {}
    cell = data.get("sellerCell") or {}
    name = (((cell.get("centerBlock") or {}).get("title") or {}).get("text"))
    if not name:
        return None
    rtxt = (((data.get("rating") or {}).get("title") or {}).get("text"))
    try:
        rating = float(str(rtxt).replace(",", ".")) if rtxt else None
    except Exception:
        rating = None
    link = ((((cell.get("common") or {}).get("action") or {}).get("link")))
    return Seller(name=name, rating=rating, url=clean_url(link))


def parse_details(base_page: dict[str, Any], page2: dict[str, Any] | None = None) -> ProductDetails:
    heading = widget(base_page, "webProductHeading") or {}
    price = widget(base_page, "webPrice") or {}
    gallery = widget(base_page, "webGallery") or {}
    sku = str(gallery.get("sku") or "") or None
    images = []
    if gallery.get("coverImage"):
        images.append(str(gallery["coverImage"]))
    for image in gallery.get("images", []):
        src = image.get("src") if isinstance(image, dict) else image
        if isinstance(src, str):
            images.append(src)
    rating, reviews = _score(base_page)
    return ProductDetails(
        sku=sku,
        title=heading.get("title"),
        url=f"https://www.ozon.ru/product/{sku}/" if sku else None,
        price_rub=price_to_number(price.get("cardPrice")) or price_to_number(price.get("price")),
        regular_price_rub=price_to_number(price.get("price")),
        old_price_rub=price_to_number(price.get("originalPrice")),
        available=price.get("isAvailable") if isinstance(price.get("isAvailable"), bool) else None,
        rating=rating,
        reviews=reviews,
        seller=_seller(base_page),
        images=list(dict.fromkeys(images))[:10],
        description=Description(),
    )


def _unix_date(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(int(value), UTC).date().isoformat()
    except Exception:
        return None


def parse_reviews(page: dict[str, Any], limit: int = 10) -> ReviewsResponse:
    data = widget(page, "webListReviews") or {}
    raw_reviews = data.get("reviews") or data.get("items") or []
    out = []
    for raw in raw_reviews[:limit]:
        if not isinstance(raw, dict):
            continue
        content = raw.get("content") or {}
        author = raw.get("author") or {}
        out.append(Review(
            author=author.get("title"),
            score=content.get("score") if isinstance(content.get("score"), (int, float)) else None,
            comment=str(content.get("comment") or ""),
            pros=str(content.get("positive") or ""),
            cons=str(content.get("negative") or ""),
            date=_unix_date(raw.get("publishedAt") or raw.get("createdAt")),
            purchased=raw.get("isItemPurchased") if isinstance(raw.get("isItemPurchased"), bool) else None,
            has_photos=bool(content.get("photos")),
        ))
    rating, total = _score(page)
    return ReviewsResponse(rating=rating, total_reviews=total, count=len(out), reviews=out)


def delivery_candidates(page: dict[str, Any], limit: int = 8) -> list[str]:
    trigger = re.compile(r"(достав|получ|сегодня|завтра|пункт выдачи|пвз)", re.I)
    found: list[str] = []

    def walk(node: Any) -> None:
        if len(found) >= limit:
            return
        if isinstance(node, str):
            clean = re.sub(r"\s+", " ", node).strip()
            if 3 <= len(clean) <= 180 and trigger.search(clean):
                found.append(clean)
        elif isinstance(node, list):
            for x in node:
                walk(x)
        elif isinstance(node, dict):
            for x in node.values():
                walk(x)

    for raw in (page.get("widgetStates") or {}).values():
        try:
            walk(json.loads(raw) if isinstance(raw, str) else raw)
        except Exception:
            continue
    return list(dict.fromkeys(found))[:limit]
