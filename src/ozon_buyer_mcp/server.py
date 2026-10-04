from __future__ import annotations
import asyncio
import os
from mcp.server import MCPServer
from .auth import auth_config, mcp_auth_options
from .browser import OzonBrowser
from .service import OzonService
from . import __version__
_transport = os.getenv("OZON_TRANSPORT", "stdio")
_auth_options = mcp_auth_options(auth_config()) if _transport in {"http", "streamable-http"} else {}
mcp = MCPServer("ozon-buyer", **_auth_options)
browser = OzonBrowser()
service = OzonService(browser)

@mcp.tool()
async def ozon_health() -> dict:
    return {
        "ok": True,
        "version": __version__,
        "mode": "buyer-read-only",
        "writes_enabled": False,
        "orders_enabled": False,
        "account_login": False,
        "transport": os.getenv("OZON_TRANSPORT", "stdio"),
        "headless": os.getenv("OZON_HEADLESS", "0") == "1",
        "proxy_enabled": bool((os.getenv("OZON_PROXY_SERVER") or "").strip()),
        "remote_worker_enabled": bool((os.getenv("OZON_REMOTE_WORKER_URL") or "").strip()),
        "marketplaces": ["ozon", "wildberries", "yandex_market", "megamarket", "avito", "web"],
    }

@mcp.tool()
async def ozon_search(query: str, limit: int = 12, sort: str = "popular",
                      price_min: int | None = None, price_max: int | None = None) -> dict:
    # Backward-compatible bridge for ChatGPT connectors that still expose the
    # pre-v0.5 frozen tool snapshot. The schema already accepts an arbitrary
    # string for `sort`, so these modes unlock the newer multi-market tools
    # without requiring the connector to be recreated first.
    compat_mode = str(sort or "popular").strip().lower()
    compat_limit = max(1, min(int(limit), 20))
    if compat_mode in {"best_buy", "best", "price_hunter"}:
        return await service.best_buy(
            query=query,
            sources=None,
            limit_per_source=compat_limit,
            include_avito=True,
        )
    if compat_mode in {"market_compare", "compare_all"}:
        return await service.compare_marketplaces(
            query=query,
            marketplaces=None,
            limit_per_market=compat_limit,
        )
    if compat_mode in {"market_search", "all_markets"}:
        return (
            await service.marketplace_search(
                query=query,
                marketplaces=None,
                limit_per_market=compat_limit,
            )
        ).model_dump()
    return (await service.search(query, limit, sort, price_min, price_max)).model_dump()

@mcp.tool()
async def market_search(query: str, marketplaces: list[str] | None = None, limit_per_market: int = 8) -> dict:
    return (await service.marketplace_search(query, marketplaces, limit_per_market)).model_dump()

@mcp.tool()
async def market_compare(query: str, marketplaces: list[str] | None = None, limit_per_market: int = 8) -> dict:
    return await service.compare_marketplaces(query, marketplaces, limit_per_market)

@mcp.tool()
async def best_buy(query: str, sources: list[str] | None = None, limit_per_source: int = 6, include_avito: bool = True) -> dict:
    return await service.best_buy(query, sources, limit_per_source, include_avito)

@mcp.tool()
async def ozon_product(product: str, include_description: bool = True) -> dict:
    return (await service.product(product, include_description=include_description)).model_dump()

@mcp.tool()
async def ozon_reviews(product: str, limit: int = 10) -> dict:
    return (await service.reviews(product, limit=limit)).model_dump()

@mcp.tool()
async def ozon_get_price(product: str) -> dict:
    return (await service.price(product)).model_dump()

@mcp.tool()
async def ozon_delivery(product: str) -> dict:
    return (await service.delivery(product)).model_dump()

@mcp.tool()
async def ozon_compare(products: list[str]) -> dict:
    return (await service.compare(products)).model_dump()

def main() -> None:
    transport = os.getenv("OZON_TRANSPORT", "stdio")
    kwargs = {}
    if transport in {"http", "streamable-http"}:
        transport = "streamable-http"
        kwargs = {
            "host": os.getenv("OZON_HOST", "0.0.0.0"),
            "port": int(os.getenv("PORT", os.getenv("OZON_PORT", "8084"))),
            "streamable_http_path": os.getenv("OZON_MCP_PATH", "/mcp"),
            "json_response": True,
            "stateless_http": True,
        }
    try:
        mcp.run(transport=transport, **kwargs)
    finally:
        try:
            asyncio.run(browser.close())
        except RuntimeError:
            pass

if __name__ == "__main__":
    main()
