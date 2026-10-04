from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from .marketplaces import market_search_url, normalize_marketplace

_HOME = "https://www.ozon.ru/"
_API = "https://www.ozon.ru/api/composer-api.bx/page/json/v2?url="


class OzonUpstreamError(RuntimeError):
    pass


def _proxy_config() -> dict[str, str] | None:
    server = (os.getenv("OZON_PROXY_SERVER") or "").strip()
    if not server:
        return None
    if "://" not in server:
        server = "http://" + server

    proxy: dict[str, str] = {"server": server}
    username = os.getenv("OZON_PROXY_USERNAME")
    password = os.getenv("OZON_PROXY_PASSWORD")
    bypass = os.getenv("OZON_PROXY_BYPASS")
    if username:
        proxy["username"] = username
    if password:
        proxy["password"] = password
    if bypass:
        proxy["bypass"] = bypass
    return proxy


class OzonBrowser:
    def __init__(self, headless: bool | None = None) -> None:
        self._headless = (os.getenv("OZON_HEADLESS", "0") == "1") if headless is None else headless
        self._challenge_wait_ms = int(os.getenv("OZON_CHALLENGE_WAIT_MS", "12000"))
        self._nav_timeout_ms = int(os.getenv("OZON_BROWSER_TIMEOUT_MS", "90000"))
        self._proxy = _proxy_config()
        self._chrome_profile_dir = (os.getenv("OZON_CHROME_PROFILE_DIR") or "").strip()
        self._browser_channel = (os.getenv("OZON_BROWSER_CHANNEL") or "").strip()
        self._cdp_url = (os.getenv("OZON_CDP_URL") or "").strip()
        self._remote_worker_url = (os.getenv("OZON_REMOTE_WORKER_URL") or "").strip().rstrip("/")
        self._remote_worker_token = (os.getenv("OZON_REMOTE_WORKER_TOKEN") or "").strip()
        self._pw = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._ready = False
        self._lock = asyncio.Lock()

    def _page_is_alive(self) -> bool:
        if not self._ready or self._page is None:
            return False
        try:
            if self._page.is_closed():
                return False
            if self._browser is not None and not self._browser.is_connected():
                return False
        except Exception:
            return False
        return True

    @staticmethod
    def _is_target_closed_error(exc: Exception) -> bool:
        text = f"{type(exc).__name__}: {exc}".lower()
        markers = (
            "targetclosederror",
            "target page, context or browser has been closed",
            "browser has been closed",
            "page has been closed",
            "context has been closed",
            "connection closed",
        )
        return any(marker in text for marker in markers)

    async def _launch(self) -> None:
        self._pw = await async_playwright().start()

        # Best local mode: attach to a Chrome process started independently
        # of Playwright. Playwright does not control Chrome's launch flags.
        if self._cdp_url:
            self._browser = await self._pw.chromium.connect_over_cdp(self._cdp_url)
            contexts = self._browser.contexts
            if not contexts:
                raise OzonUpstreamError("Chrome CDP connected but no browser context is available")
            self._context = contexts[0]
            return

        # Local Windows mode can use the user's real installed Chrome with a
        # dedicated persistent profile. This is closer to a normal browser
        # session than Playwright's bundled Chromium and keeps Ozon cookies.
        if self._chrome_profile_dir:
            kwargs: dict[str, Any] = {
                "user_data_dir": self._chrome_profile_dir,
                "headless": self._headless,
                "viewport": {"width": 1920, "height": 1080},
                "locale": "ru-RU",
                "timezone_id": "Europe/Moscow",
                "args": ["--disable-blink-features=AutomationControlled"],
                "ignore_default_args": ["--enable-automation"],
            }
            if self._browser_channel:
                kwargs["channel"] = self._browser_channel
            if self._proxy:
                kwargs["proxy"] = self._proxy
            self._context = await self._pw.chromium.launch_persistent_context(**kwargs)
            self._browser = None
            return

        launch_kwargs: dict[str, Any] = {
            "headless": self._headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--mute-audio",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
                "--disable-background-networking",
            ],
        }
        if self._browser_channel:
            launch_kwargs["channel"] = self._browser_channel
        if self._proxy:
            launch_kwargs["proxy"] = self._proxy

        self._browser = await self._pw.chromium.launch(**launch_kwargs)
        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="ru-RU",
            timezone_id="Europe/Moscow",
        )

    async def _blocked_reason(self, page: Page) -> str | None:
        title = (await page.title()).lower()
        body = (await page.locator("body").inner_text(timeout=5000)).lower()
        markers = (
            "antibot",
            "доступ ограничен",
            "доступ временно ограничен",
            "подозрительная активность",
            "access denied",
            "forbidden",
            "captcha",
            "капча",
            "вы не робот",
            "не робот",
            "проверка браузера",
            "проверка безопасности",
        )
        for marker in markers:
            if marker in title or marker in body[:5000]:
                return marker
        return None

    async def ensure_ready(self) -> None:
        if self._page_is_alive():
            return
        async with self._lock:
            if self._page_is_alive():
                return

            # A previously healthy CDP/page can disappear when the user closes
            # the external Chrome window or its tab. Drop every cached handle
            # before reconnecting so Playwright never reuses a dead target.
            if self._ready or self._page is not None or self._context is not None or self._browser is not None or self._pw is not None:
                await self.close()

            try:
                if not self._context:
                    await self._launch()
                assert self._context is not None
                self._page = await self._context.new_page()
                response = await self._page.goto(_HOME, wait_until="domcontentloaded", timeout=self._nav_timeout_ms)
                await self._page.wait_for_timeout(self._challenge_wait_ms)
                reason = await self._blocked_reason(self._page)
                if reason:
                    raise OzonUpstreamError(f"Ozon page blocked: {reason}")
                if response and response.status >= 400:
                    raise OzonUpstreamError(f"Ozon home page returned HTTP {response.status}")
                self._ready = True
            except Exception:
                await self.close()
                raise

    async def _goto_with_recovery(self, url: str, wait_ms: int):
        for attempt in range(2):
            try:
                await self.ensure_ready()
                assert self._page is not None
                response = await self._page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=min(self._nav_timeout_ms, 60000),
                )
                await self._page.wait_for_timeout(wait_ms)
                return response
            except Exception as exc:
                if attempt == 0 and self._is_target_closed_error(exc):
                    await self.close()
                    continue
                raise
        raise OzonUpstreamError("Browser target recovery failed")

    def _remote_post_sync(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._remote_worker_url or not self._remote_worker_token:
            raise OzonUpstreamError("Remote Ozon worker is not fully configured")
        operation = endpoint.strip("/")
        body = json.dumps({"op": operation, "payload": payload}).encode("utf-8")
        req = urllib.request.Request(
            self._remote_worker_url + "/submit",
            data=body,
            method="POST",
            headers={
                "content-type": "application/json",
                "authorization": f"Bearer {self._remote_worker_token}",
            },
        )
        try:
            # Keep the outer MCP->relay timeout longer than the local worker and relay
            # deadlines. This prevents abandoned jobs whose late /result then becomes 404.
            remote_timeout = max(130, self._nav_timeout_ms // 1000 + 20)
            with urllib.request.urlopen(req, timeout=remote_timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("error")
            except Exception:
                detail = None
            raise OzonUpstreamError(detail or f"Remote worker returned HTTP {exc.code}") from exc
        except Exception as exc:
            raise OzonUpstreamError(f"Remote worker request failed: {exc}") from exc
        if not data.get("ok"):
            raise OzonUpstreamError(str(data.get("error") or "Remote worker failed"))
        return data

    async def _remote_post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self._remote_post_sync, endpoint, payload)

    async def search_dom(self, path: str, limit: int = 12) -> list[dict[str, Any]]:
        if self._remote_worker_url:
            data = await self._remote_post("/search-dom", {"path": path, "limit": limit})
            return list(data.get("items") or [])

        url = "https://www.ozon.ru" + path
        response = await self._goto_with_recovery(
            url,
            wait_ms=max(4000, self._challenge_wait_ms // 2),
        )
        assert self._page is not None

        reason = await self._blocked_reason(self._page)
        if reason:
            raise OzonUpstreamError(f"Ozon search page blocked: {reason}")
        if response and response.status >= 400:
            raise OzonUpstreamError(f"Ozon search page returned HTTP {response.status}")

        for _ in range(3):
            await self._page.evaluate("window.scrollBy(0, Math.max(window.innerHeight, 900))")
            await self._page.wait_for_timeout(800)

        raw: list[dict[str, Any]] = await self._page.evaluate(
            """(limit) => {
              const out = [];
              const seen = new Set();

              const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
              const productAnchors = Array.from(document.querySelectorAll('a[href*="/product/"]'));

              for (const a of productAnchors) {
                const href = a.href || "";
                const m = href.match(/\/product\/[^/?]*?(\d{6,})(?:\/|\?|$)/);
                if (!m) continue;
                const sku = m[1];
                if (seen.has(sku)) continue;

                let node = a;
                let bestText = clean(a.innerText);
                for (let i = 0; i < 7 && node && node.parentElement; i++) {
                  node = node.parentElement;
                  const t = clean(node.innerText);
                  if (t.length >= 20 && t.length <= 1800 && /₽/.test(t)) {
                    bestText = t;
                    break;
                  }
                }

                let title = clean(a.innerText);
                if (!title || title.length < 5 || /₽/.test(title)) {
                  const img = node?.querySelector?.("img") || a.querySelector("img");
                  const alt = clean(img?.getAttribute?.("alt"));
                  if (alt && alt.length > title.length) title = alt;
                }

                const img = node?.querySelector?.("img") || a.querySelector("img");
                const image = img ? (img.currentSrc || img.src || "") : "";

                out.push({sku, url: href.split("?")[0], title, text: bestText, image});
                seen.add(sku);
                if (out.length >= limit * 3) break;
              }

              const ld = [];
              for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
                try { ld.push(JSON.parse(s.textContent || "{}")); } catch (_) {}
              }
              return {cards: out, ld};
            }""",
            max(1, min(limit, 30)),
        )

        cards = list(raw.get("cards") or [])
        # Keep JSON-LD around as a fallback source if Ozon changes card markup.
        for obj in raw.get("ld") or []:
            items = obj.get("itemListElement") if isinstance(obj, dict) else None
            if not isinstance(items, list):
                continue
            for entry in items:
                item = entry.get("item") if isinstance(entry, dict) else None
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "")
                match = re.search(r"/product/[^/?]*?(\d{6,})(?:/|\?|$)", url)
                if not match:
                    continue
                cards.append({
                    "sku": match.group(1),
                    "url": url.split("?", 1)[0],
                    "title": str(item.get("name") or ""),
                    "text": "",
                    "image": str(item.get("image") or ""),
                    "ld": item,
                })

        dedup: dict[str, dict[str, Any]] = {}
        for card in cards:
            sku = str(card.get("sku") or "")
            if not sku:
                continue
            prev = dedup.get(sku)
            if not prev or len(str(card.get("text") or "")) > len(str(prev.get("text") or "")):
                dedup[sku] = card
        return list(dedup.values())[:limit]

    async def market_search_dom(self, marketplace: str, query: str, limit: int = 12) -> list[dict[str, Any]]:
        market = normalize_marketplace(marketplace)
        limit = max(1, min(int(limit), 30))

        if market == "ozon":
            path = f"/search/?text={quote(str(query or '').strip())}&from_global=true"
            return await self.search_dom(path, limit=limit)

        if self._remote_worker_url:
            data = await self._remote_post(
                "/market-search-dom",
                {"marketplace": market, "query": query, "limit": limit},
            )
            return list(data.get("items") or [])

        if market == "web":
            return await self._web_search_dom(query, limit=limit)

        await self.ensure_ready()
        assert self._context is not None
        page = await self._context.new_page()
        try:
            url = market_search_url(market, query)
            response = await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=min(self._nav_timeout_ms, 30000),
            )
            await page.wait_for_timeout(max(2500, min(self._challenge_wait_ms // 3, 4000)))

            for _ in range(3):
                await page.evaluate("window.scrollBy(0, Math.max(window.innerHeight, 900))")
                await page.wait_for_timeout(650)

            if response and response.status >= 400:
                raise OzonUpstreamError(
                    f"{market} search page returned HTTP {response.status}"
                )

            title = (await page.title()).lower()
            body = (await page.locator("body").inner_text(timeout=10000)).lower()
            blocked_markers = (
                "access denied",
                "доступ ограничен",
                "доступ временно ограничен",
                "подозрительная активность",
                "captcha",
                "капча",
                "проверка браузера",
                "хотим проверить",
                "вы не робот",
                "не робот",
                "проверка безопасности",
            )
            if any(x in title or x in body[:6000] for x in blocked_markers):
                raise OzonUpstreamError(f"{market} search page is blocked")

            items = await page.evaluate(
                """({marketplace, limit}) => {
                  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
                  const num = (s) => {
                    const d = String(s || "").replace(/[^0-9]/g, "");
                    return d ? Number(d) : null;
                  };
                  const prices = (s) => Array.from(
                    String(s || "").matchAll(/(\d[\d\s\u00a0]{1,12})\s*₽/g)
                  ).map((m) => num(m[1])).filter(Boolean);
                  const ratingAndReviews = (s) => {
                    const t = clean(s);
                    const m = t.match(/([1-5](?:[\.,]\d)?)\s+([\d\s\u00a0]+)\s*(?:оцен|отзыв)/i);
                    return {
                      rating: m ? Number(m[1].replace(",", ".")) : null,
                      reviews: m ? num(m[2]) : null,
                    };
                  };
                  const delivery = (s) => {
                    const t = clean(s);
                    const m = t.match(/(.{0,55}(?:сегодня|завтра|послезавтра|достав\w*|получ\w*|\d{1,2}\s+(?:октябр|ноябр|декабр|январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр)\w*).{0,90})/i);
                    return m ? clean(m[1]) : null;
                  };

                  let anchors = [];
                  if (marketplace === "wildberries") {
                    anchors = Array.from(document.querySelectorAll(
                      'a[href*="/catalog/"][href*="/detail.aspx"]'
                    ));
                  } else if (marketplace === "avito") {
                    anchors = Array.from(document.querySelectorAll(
                      'a[data-marker="item-title"], a[itemprop="url"]'
                    ));
                  } else if (marketplace === "megamarket") {
                    anchors = Array.from(document.querySelectorAll(
                      'a[href*="/catalog/details/"], a[href*="/catalog/"]'
                    ));
                  } else {
                    anchors = Array.from(document.querySelectorAll(
                      'a[href*="/card/"], a[href*="/product--"], a[href*="/product/"]'
                    ));
                  }

                  const out = [];
                  const seen = new Set();

                  for (const a of anchors) {
                    const href = a.href || "";
                    if (!href) continue;

                    let productId = null;
                    if (marketplace === "wildberries") {
                      const m = href.match(/\/catalog\/(\d+)\/detail\.aspx/i);
                      productId = m ? m[1] : null;
                    } else if (marketplace === "avito") {
                      const m = href.match(/_(\d{6,})(?:\?|$)/);
                      productId = m ? m[1] : null;
                    } else {
                      try {
                        const u = new URL(href);
                        productId = u.searchParams.get("sku") || u.searchParams.get("uniqueId");
                        if (!productId) {
                          const m = u.pathname.match(/(?:-|\/)(\d{5,})(?:\/|$)/);
                          productId = m ? m[1] : null;
                        }
                      } catch (_) {}
                    }
                    const key = productId || href.split("?")[0];
                    if (seen.has(key)) continue;

                    let node = a;
                    let text = clean(a.innerText);
                    for (let i = 0; i < 8 && node && node.parentElement; i++) {
                      node = node.parentElement;
                      const t = clean(node.innerText);
                      if (t.length >= 20 && t.length <= 2600 && /₽/.test(t)) {
                        text = t;
                        break;
                      }
                    }
                    if (!/₽/.test(text)) continue;

                    let selector = '[data-auto="snippet-price-current"], [data-auto="price-value"], [data-zone-name="price"]';
                    if (marketplace === "wildberries") {
                      selector = '.price__lower-price, ins.price__lower-price, [class*="price__lower-price"]';
                    } else if (marketplace === "avito") {
                      selector = '[itemprop="price"], [data-marker="item-price"]';
                    } else if (marketplace === "megamarket") {
                      selector = '[class*="price"], [data-test*="price"], [data-qa*="price"]';
                    }
                    const directPriceNode = node?.querySelector?.(selector);
                    const allPrices = prices(text);
                    const directPrice = num(
                      directPriceNode?.getAttribute?.("content") ||
                      directPriceNode?.innerText
                    );
                    const price = directPrice || allPrices[0] || null;
                    if (!price) continue;
                    const oldPrice = allPrices.find((p) => p > price) || null;

                    let titleSelectors = ['[data-auto="snippet-title"]', 'h3', 'h2'];
                    if (marketplace === "wildberries") {
                      titleSelectors = ['.product-card__name', '.product-card__brand', '[class*="product-card__name"]'];
                    } else if (marketplace === "avito") {
                      titleSelectors = ['[data-marker="item-title"]', '[itemprop="name"]', 'h3'];
                    } else if (marketplace === "megamarket") {
                      titleSelectors = ['[class*="title"]', '[data-test*="title"]', 'h3', 'h2'];
                    }

                    const titleParts = [];
                    for (const sel of titleSelectors) {
                      const t = clean(node?.querySelector?.(sel)?.innerText);
                      if (t && t.length <= 300 && !titleParts.includes(t)) titleParts.push(t);
                    }
                    const img = node?.querySelector?.("img") || a.querySelector("img");
                    const alt = clean(img?.getAttribute?.("alt"));
                    let productTitle = titleParts.join(" / ");
                    if ((!productTitle || productTitle.length < 5) && alt) productTitle = alt;
                    if (!productTitle || /₽/.test(productTitle)) productTitle = clean(a.innerText);
                    if (!productTitle || /₽/.test(productTitle)) {
                      const lines = String(text || "").split(/\\n+/).map(clean).filter(Boolean);
                      productTitle = lines.find((x) => !/₽/.test(x) && x.length >= 5 && x.length <= 240) || null;
                    }

                    const rr = ratingAndReviews(text);
                    out.push({
                      product_id: productId,
                      title: productTitle,
                      url: href.split("?")[0],
                      price_rub: price,
                      old_price_rub: oldPrice,
                      rating: rr.rating,
                      reviews: rr.reviews,
                      delivery_text: delivery(text),
                      seller: null,
                      image: img ? (img.currentSrc || img.src || "") : "",
                      condition: marketplace === "avito" ? "unknown" : "new",
                      price_confidence: directPrice ? "high" : "medium",
                      text,
                    });
                    seen.add(key);
                    if (out.length >= limit) break;
                  }
                  return out;
                }""",
                {"marketplace": market, "limit": limit},
            )
            return list(items or [])[:limit]
        finally:
            try:
                await page.close()
            except Exception:
                pass

    async def _web_search_dom(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        await self.ensure_ready()
        assert self._context is not None

        search_page = await self._context.new_page()
        try:
            response = await search_page.goto(
                market_search_url("web", query),
                wait_until="domcontentloaded",
                timeout=min(self._nav_timeout_ms, 20000),
            )
            await search_page.wait_for_timeout(max(1800, min(self._challenge_wait_ms // 4, 3000)))
            if response and response.status >= 400:
                raise OzonUpstreamError(f"web search returned HTTP {response.status}")

            search_title = (await search_page.title()).lower()
            search_body = (await search_page.locator("body").inner_text(timeout=7000)).lower()
            if any(marker in search_title or marker in search_body[:5000] for marker in (
                "captcha", "капча", "вы не робот", "не робот",
                "подозрительная активность", "проверка браузера",
            )):
                raise OzonUpstreamError("web search page is blocked")

            candidates = await search_page.evaluate(
                """(limit) => {
                  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
                  const blocked = [
                    "yandex.ru", "ya.ru", "ozon.ru", "wildberries.ru",
                    "market.yandex.ru", "megamarket.ru", "avito.ru"
                  ];
                  const out = [];
                  const seen = new Set();
                  for (const a of Array.from(document.querySelectorAll('a[href^="http"]'))) {
                    let u;
                    try { u = new URL(a.href); } catch (_) { continue; }
                    const host = u.hostname.replace(/^www\./, "").toLowerCase();
                    if (blocked.some((x) => host === x || host.endsWith("." + x))) continue;
                    const text = clean(a.innerText);
                    if (!text || text.length < 4 || text.length > 280) continue;
                    const key = u.origin + u.pathname;
                    if (seen.has(key)) continue;
                    seen.add(key);
                    out.push({url: a.href, title: text, host});
                    if (out.length >= limit * 3) break;
                  }
                  return out;
                }""",
                max(1, min(limit, 10)),
            )
        finally:
            try:
                await search_page.close()
            except Exception:
                pass

        offers: list[dict[str, Any]] = []
        candidate_budget = max(3, min(limit, 5))
        for candidate in list(candidates or [])[:candidate_budget]:
            if len(offers) >= limit:
                break
            page = await self._context.new_page()
            try:
                response = await page.goto(
                    str(candidate.get("url") or ""),
                    wait_until="domcontentloaded",
                    timeout=min(self._nav_timeout_ms, 10000),
                )
                if response and response.status >= 400:
                    continue
                await page.wait_for_timeout(1200)
                raw = await page.evaluate(
                    """() => {
                      const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
                      const num = (v) => {
                        const d = String(v ?? "").replace(/[^0-9]/g, "");
                        return d ? Number(d) : null;
                      };
                      const rub = (s) => {
                        const m = String(s || "").match(/(\d[\d\s\u00a0]{1,12})\s*₽/);
                        return m ? num(m[1]) : null;
                      };
                      const walk = (node, found=[]) => {
                        if (!node || found.length > 20) return found;
                        if (Array.isArray(node)) {
                          for (const x of node) walk(x, found);
                          return found;
                        }
                        if (typeof node !== "object") return found;
                        const type = node["@type"];
                        const types = Array.isArray(type) ? type : [type];
                        if (types.some((x) => String(x).toLowerCase() === "product")) found.push(node);
                        for (const v of Object.values(node)) {
                          if (typeof v === "object") walk(v, found);
                        }
                        return found;
                      };

                      const products = [];
                      for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
                        try { walk(JSON.parse(s.textContent || "{}"), products); } catch (_) {}
                      }

                      for (const p of products) {
                        const offers = Array.isArray(p.offers) ? p.offers[0] : p.offers;
                        const agg = p.aggregateRating || {};
                        const price = num(
                          offers?.price ??
                          offers?.lowPrice ??
                          offers?.priceSpecification?.price
                        );
                        if (price) {
                          return {
                            title: clean(p.name || document.querySelector("h1")?.innerText || document.title),
                            price_rub: price,
                            old_price_rub: null,
                            rating: Number(agg.ratingValue) || null,
                            reviews: num(agg.reviewCount || agg.ratingCount),
                            image: Array.isArray(p.image) ? p.image[0] : (p.image || ""),
                            price_confidence: "high",
                          };
                        }
                      }

                      const priceSelectors = [
                        '[itemprop="price"]',
                        'meta[property="product:price:amount"]',
                        'meta[property="og:price:amount"]',
                        '[data-price]',
                        '[class*="price"]'
                      ];
                      let price = null;
                      for (const sel of priceSelectors) {
                        const el = document.querySelector(sel);
                        if (!el) continue;
                        price = num(
                          el.getAttribute?.("content") ||
                          el.getAttribute?.("data-price") ||
                          el.innerText
                        );
                        if (price && price >= 50) break;
                      }
                      if (!price) {
                        const body = clean(document.body?.innerText || "");
                        price = rub(body);
                      }
                      if (!price) return null;
                      return {
                        title: clean(document.querySelector("h1")?.innerText || document.title),
                        price_rub: price,
                        old_price_rub: null,
                        rating: null,
                        reviews: null,
                        image: document.querySelector('meta[property="og:image"]')?.content || "",
                        price_confidence: "medium",
                      };
                    }"""
                )
                if not isinstance(raw, dict) or not raw.get("price_rub"):
                    continue
                raw["product_id"] = None
                raw["url"] = page.url
                raw["seller"] = str(candidate.get("host") or "")
                raw["delivery_text"] = None
                raw["condition"] = "new"
                offers.append(raw)
            except Exception:
                continue
            finally:
                try:
                    await page.close()
                except Exception:
                    pass
        return offers[:limit]

    async def delivery_dom(self, path: str) -> list[str]:
        if self._remote_worker_url:
            data = await self._remote_post("/delivery-dom", {"path": path})
            return list(data.get("candidates") or [])

        url = "https://www.ozon.ru" + path
        response = await self._goto_with_recovery(
            url,
            wait_ms=max(5000, self._challenge_wait_ms // 2),
        )
        assert self._page is not None

        reason = await self._blocked_reason(self._page)
        if reason:
            raise OzonUpstreamError(f"Ozon product page blocked: {reason}")
        if response and response.status >= 400:
            raise OzonUpstreamError(f"Ozon product page returned HTTP {response.status}")

        body = await self._page.locator("body").inner_text(timeout=10000)
        lines = [re.sub(r"\s+", " ", line).strip() for line in body.splitlines()]
        trigger = re.compile(
            r"(достав|завтра|послезавтра|сегодня|пвз|пункт выдачи|курьер|"
            r"сентябр|октябр|ноябр|декабр|январ|феврал|март|апрел|ма[йя]|июн|июл|август)",
            re.I,
        )
        out: list[str] = []
        for i, line in enumerate(lines):
            if not line or not trigger.search(line):
                continue
            start = max(0, i - 1)
            end = min(len(lines), i + 2)
            snippet = " | ".join(x for x in lines[start:end] if x)
            if 3 <= len(snippet) <= 300 and snippet not in out:
                out.append(snippet)
            if len(out) >= 20:
                break
        return out

    async def fetch_json(self, path: str, retries: int = 1) -> dict[str, Any]:
        if self._remote_worker_url:
            data = await self._remote_post("/fetch-json", {"path": path, "retries": retries})
            result = data.get("data")
            if not isinstance(result, dict):
                raise OzonUpstreamError("Remote worker returned invalid JSON payload")
            return result

        for attempt in range(retries + 1):
            try:
                await self.ensure_ready()
                assert self._page is not None
                target = _API + quote(path, safe="")
                body = await self._page.evaluate(
                    """async (url) => {
                      const r = await fetch(url, {headers: {accept: 'application/json'}});
                      return {status: r.status, text: await r.text()};
                    }""",
                    target,
                )
                status = int(body.get("status", 0))
                if status != 200:
                    if status in (307, 403) and attempt < retries:
                        await self.close()
                        continue
                    raise OzonUpstreamError(f"Ozon returned HTTP {status}")
                return json.loads(body["text"])
            except Exception:
                if attempt < retries:
                    await self.close()
                    continue
                raise
        raise OzonUpstreamError("Ozon request failed")

    async def close(self) -> None:
        self._ready = False
        self._page = None

        # When attached over CDP, Chrome is an externally managed process.
        # Disconnect Playwright without closing the user's Chrome/context.
        if self._cdp_url:
            self._context = None
            self._browser = None
            if self._pw:
                try:
                    await self._pw.stop()
                except Exception:
                    pass
            self._pw = None
            return

        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
        self._context = None
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        self._browser = None
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
        self._pw = None
