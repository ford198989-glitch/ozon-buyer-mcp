from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any
from urllib.parse import quote

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

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
        self._pw = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._ready = False
        self._lock = asyncio.Lock()

    async def _launch(self) -> None:
        self._pw = await async_playwright().start()
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
        )
        for marker in markers:
            if marker in title or marker in body[:5000]:
                return marker
        return None

    async def ensure_ready(self) -> None:
        if self._ready and self._page:
            return
        async with self._lock:
            if self._ready and self._page:
                return
            if not self._browser:
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

    async def search_dom(self, path: str, limit: int = 12) -> list[dict[str, Any]]:
        await self.ensure_ready()
        assert self._page is not None
        url = "https://www.ozon.ru" + path
        response = await self._page.goto(url, wait_until="domcontentloaded", timeout=self._nav_timeout_ms)
        await self._page.wait_for_timeout(max(4000, self._challenge_wait_ms // 2))

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

    async def fetch_json(self, path: str, retries: int = 1) -> dict[str, Any]:
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
        if self._context:
            await self._context.close()
        self._context = None
        if self._browser:
            await self._browser.close()
        self._browser = None
        if self._pw:
            await self._pw.stop()
        self._pw = None
