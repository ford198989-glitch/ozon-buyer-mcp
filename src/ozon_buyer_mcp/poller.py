from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from .browser import OzonBrowser

RELAY_URL = (os.getenv("OZON_RELAY_URL") or "").strip().rstrip("/")
TOKEN = (os.getenv("OZON_WORKER_TOKEN") or "").strip()
browser = OzonBrowser()


def _request_sync(method: str, path: str, payload: dict[str, Any] | None = None, timeout: int = 40) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        RELAY_URL + path,
        data=data,
        method=method,
        headers={
            "authorization": f"Bearer {TOKEN}",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


async def _request(method: str, path: str, payload: dict[str, Any] | None = None, timeout: int = 40) -> dict[str, Any]:
    return await asyncio.to_thread(_request_sync, method, path, payload, timeout)


async def execute(job: dict[str, Any]) -> dict[str, Any]:
    op = str(job.get("op") or "")
    payload = job.get("payload") or {}
    try:
        if op == "search-dom":
            items = await browser.search_dom(str(payload.get("path") or ""), limit=int(payload.get("limit") or 12))
            return {"ok": True, "items": items}
        if op == "market-search-dom":
            items = await browser.market_search_dom(
                str(payload.get("marketplace") or ""),
                str(payload.get("query") or ""),
                limit=int(payload.get("limit") or 12),
            )
            return {"ok": True, "items": items}
        if op == "fetch-json":
            data = await browser.fetch_json(str(payload.get("path") or ""), retries=int(payload.get("retries") or 1))
            return {"ok": True, "data": data}
        return {"ok": False, "error": f"unsupported operation: {op}"}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


async def run() -> None:
    if not RELAY_URL or not TOKEN:
        raise RuntimeError("OZON_RELAY_URL and OZON_WORKER_TOKEN are required")
    print(f"Marketplace local worker connected to relay: {RELAY_URL}", flush=True)
    print("Keep this window open while using marketplace search in ChatGPT.", flush=True)
    while True:
        try:
            answer = await _request("GET", "/next", timeout=35)
            job = answer.get("job")
            if not job:
                continue
            response = await execute(job)
            await _request("POST", "/result", {"id": job.get("id"), "response": response}, timeout=40)
        except urllib.error.HTTPError as exc:
            print(f"Relay HTTP {exc.code}; retrying...", flush=True)
            await asyncio.sleep(3)
        except Exception as exc:
            print(f"Relay error: {exc}; retrying...", flush=True)
            await asyncio.sleep(3)


def main() -> None:
    try:
        asyncio.run(run())
    finally:
        try:
            asyncio.run(browser.close())
        except Exception:
            pass


if __name__ == "__main__":
    main()
