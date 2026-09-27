# Ozon Buyer MCP v0.2

Read-only MCP server for Ozon buyer-side scenarios.

## Tools

- `ozon_health()`
- `ozon_search(query, limit, sort, price_min, price_max)`
- `ozon_product(product, include_description)`
- `ozon_reviews(product, limit)`
- `ozon_get_price(product)`
- `ozon_compare(products)`
- `ozon_delivery(product)`

## Runtime

The service opens Chromium, passes the Ozon/Variti anti-bot page, then calls Ozon storefront composer-api from the browser page.

By default Chromium runs headed inside Xvfb (`OZON_HEADLESS=0`).

## Safety

v0.2 is read-only:
- no Ozon account login;
- no user cookies;
- no cart/favorites/orders;
- no operations that spend money.

## Docker

```bash
docker build -t ozon-buyer-mcp .
docker run -i --rm --init --shm-size=1g ozon-buyer-mcp
```

## Streamable HTTP

```bash
docker run --rm --init --shm-size=1g \
  -e OZON_TRANSPORT=streamable-http \
  -e OZON_PORT=8084 \
  -p 8084:8084 \
  ozon-buyer-mcp
```

MCP endpoint: `/mcp`.

## Railway note

Ozon may block datacenter/VPN IPs, so Railway can run the MCP transport successfully while live Ozon requests may still receive anti-bot/403 responses.
