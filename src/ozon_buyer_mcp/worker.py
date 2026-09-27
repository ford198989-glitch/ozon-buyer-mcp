from __future__ import annotations

import asyncio
import os
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
import uvicorn

from .browser import OzonBrowser, OzonUpstreamError

browser = OzonBrowser()
TOKEN = (os.getenv("OZON_WORKER_TOKEN") or "").strip()


def _authorized(request: Request) -> bool:
    if not TOKEN:
        return False
    return request.headers.get("authorization", "") == f"Bearer {TOKEN}"


async def health(request: Request) -> JSONResponse:
    if not _authorized(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    return JSONResponse({"ok": True, "worker": "ozon-local", "headless": os.getenv("OZON_HEADLESS", "0") == "1"})


async def search_dom(request: Request) -> JSONResponse:
    if not _authorized(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    data = await request.json()
    path = str(data.get("path") or "")
    limit = max(1, min(int(data.get("limit") or 12), 30))
    try:
        items = await browser.search_dom(path, limit=limit)
        return JSONResponse({"ok": True, "items": items})
    except OzonUpstreamError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=502)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status_code=500)


async def fetch_json(request: Request) -> JSONResponse:
    if not _authorized(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    data = await request.json()
    path = str(data.get("path") or "")
    retries = max(0, min(int(data.get("retries") or 1), 2))
    try:
        result = await browser.fetch_json(path, retries=retries)
        return JSONResponse({"ok": True, "data": result})
    except OzonUpstreamError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=502)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status_code=500)


async def shutdown() -> None:
    await browser.close()


app = Starlette(
    routes=[
        Route("/health", health, methods=["GET"]),
        Route("/search-dom", search_dom, methods=["POST"]),
        Route("/fetch-json", fetch_json, methods=["POST"]),
    ],
    on_shutdown=[shutdown],
)


def main() -> None:
    if not TOKEN:
        raise RuntimeError("OZON_WORKER_TOKEN is required")
    uvicorn.run(
        app,
        host=os.getenv("OZON_WORKER_HOST", "127.0.0.1"),
        port=int(os.getenv("OZON_WORKER_PORT", "8765")),
        log_level="info",
    )


if __name__ == "__main__":
    main()
