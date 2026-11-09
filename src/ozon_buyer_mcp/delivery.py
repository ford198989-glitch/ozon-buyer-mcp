"""Bounded delivery contexts, never global navigation or recommendation text."""
from __future__ import annotations

import json
import re
from typing import Any

MONTHS = r"января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря"
DATE = re.compile(
    rf"\b(?:сегодня|завтра|послезавтра|\d{{1,2}}\s*(?:[–—-]\s*\d{{1,2}}\s*)?(?:{MONTHS})|"
    r"понедельник|вторник|сред[ау]|четверг|пятниц[ау]|суббот[ау]|воскресенье)\b",
    re.I,
)
CONTEXT = re.compile(r"достав|получ|курьер|пункт выдачи|самовывоз|\bпвз\b", re.I)
# Restrict to offer/delivery widgets. Arbitrary page strings contain promotions,
# reviews, footer links and other sellers' recommended products.
WIDGET = re.compile(r"(?:delivery|deliver|shipping|logistic|pickup|webCurrentSeller|webSeller|webPrice|webAddToCart)", re.I)
SKIP_KEYS = {"trackingInfo", "action", "link", "url", "deeplink", "image", "icon", "sku", "id"}

def _texts(node: Any, depth: int = 0):
    if depth > 16:
        return
    if isinstance(node, str):
        clean = re.sub(r"<[^>]*>", " ", node)
        clean = re.sub(r"\s+", " ", clean).strip()
        if clean and not re.match(r"^(?:https?://|ozon://|/)", clean):
            yield clean
    elif isinstance(node, list):
        for value in node[:200]:
            yield from _texts(value, depth + 1)
    elif isinstance(node, dict):
        for key, value in list(node.items())[:200]:
            if key not in SKIP_KEYS:
                yield from _texts(value, depth + 1)

def ranked_delivery_candidates(pages, *, sku=None, seller="", price=None, limit=40):
    found = {}
    for page_index, page in enumerate(pages):
        if not isinstance(page, dict):
            continue
        states = page.get("widgetStates")
        if not isinstance(states, dict):
            continue
        for key, raw in states.items():
            name = str(key).split("-", 1)[0]
            if not WIDGET.search(name):
                continue
            try:
                obj = json.loads(raw) if isinstance(raw, str) else raw
            except (ValueError, TypeError):
                continue
            strings = list(dict.fromkeys(_texts(obj)))[:300]
            # Dates split across adjacent labels ("10" / "ноября") still work.
            text = " ".join(strings)
            if not DATE.search(text):
                continue
            if not CONTEXT.search(text) and not re.search(r"deliver|shipping|logistic|pickup", name, re.I):
                continue
            # Match only complete identifiers/amounts, not arbitrary substrings.
            encoded = json.dumps(obj, ensure_ascii=False)
            sku_match = bool(sku and re.search(rf"(?<!\d){re.escape(str(sku))}(?!\d)", encoded))
            seller_match = bool(seller and seller.casefold() in text.casefold())
            price_match = bool(price and re.search(rf"(?<!\d){re.escape(str(price))}(?!\d)", encoded))
            score = 8 * sku_match + 4 * seller_match + 2 * price_match + (page_index == 0)
            for match in DATE.finditer(text):
                snippet = text[max(0, match.start()-120):match.end()+180].strip()
                identity = (name, snippet)
                prefix = name + (" [sku]" if sku_match else "") + (" [seller]" if seller_match else "")
                candidate = f"{prefix}: {snippet}"
                if identity not in found or score > found[identity][0]:
                    found[identity] = (score, candidate)
    return [value[1] for value in sorted(found.values(), key=lambda x: -x[0])[:limit]]

