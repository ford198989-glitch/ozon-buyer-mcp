from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from urllib.parse import quote

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

_HOME = "https://www.ozon.ru/"
_API = "https://www.ozon.ru/api/composer-api.bx/page/json/v2?url="


class OzonUpstreamError(RuntimeError):
    pass


class OzonBrowser:
    def __init__(self, headless: bool | None = None) -> None:
        self._headless = (os.getenv("OZON_HEADLESS", "0") == "1") if headless is None else headless
        self._challenge_wait_ms = int(os.getenv("OZON_CHALLENGE_WAIT_MS", "12000"))
        self._nav_timeout_ms = int(os.getenv("OZON_BROWSER_TIMEOUT_MS", "90000"))
        self._pw = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._ready = False
        self._lock = asyncio.Lock()

    async def _launch(self) -> None:
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=self._headless,
            args=[
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
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="ru-RU",
        )

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
            await self._page.goto(_HOME, wait_until="domcontentloaded", timeout=self._nav_timeout_ms)
            await self._page.wait_for_timeout(self._challenge_wait_ms)
            title = (await self._page.title()).lower()
            if any(x in title for x in ("antibot", "ограничен", "доступ ограничен")):
                raise OzonUpstreamError(f"Ozon anti-bot challenge not passed: {title!r}")
            self._ready = True

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
