from __future__ import annotations
import asyncio
import os
from mcp.server import MCPServer
from .browser import OzonBrowser
from .service import OzonService

VERSION = "0.2.1"
mcp = MCPServer("ozon-buyer")
browser = OzonBrowser()
service = OzonService(browser)

@mcp.tool()
async def ozon_health() -> dict:
    return {
        "ok": True,
        "version": VERSION,
        "mode": "buyer-read-only",
        "writes_enabled": False,
        "orders_enabled": False,
        "account_login": False,
        "transport": os.getenv("OZON_TRANSPORT", "stdio"),
        "headless": os.getenv("OZON_HEADLESS", "0") == "1",
    }

@mcp.tool()
async def ozon_search(query: str, limit: int = 12, sort: str = "popular",
                      price_min: int | None = None, price_max: int | None = None) -> dict:
    return (await service.search(query, limit, sort, price_min, price_max)).model_dump()

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
