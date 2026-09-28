# Ozon Buyer MCP v0.4.1

Read-only MCP server for buyer-side Ozon research from ChatGPT.

## Current production architecture

```
ChatGPT
  -> public MCP on Railway
  -> private relay on Railway
  -> Windows PC connector
  -> ordinary externally launched Google Chrome (CDP 127.0.0.1:9222)
  -> Ozon
```

This architecture is intentional: direct Railway/datacenter requests and Playwright-launched browsers are commonly blocked by Ozon, while an ordinary Chrome process on the user's PC works reliably.

## Buyer tools

- `ozon_health()`
- `ozon_search(query, limit, sort, price_min, price_max)`
- `ozon_product(product, include_description)`
- `ozon_reviews(product, limit)`
- `ozon_get_price(product)`
- `ozon_delivery(product)`
- `ozon_compare(products)`

The service is read-only: no login, cart, checkout, orders, favorites or other write actions.

## Windows quick start

Download and run:

`START_OZON_MCP.cmd`

On first launch it asks for the worker token. The token is **not** stored in GitHub or Yandex Disk; Windows stores it locally using DPAPI. Later launches are one-click.

The launcher automatically:

1. downloads the latest repo to `%USERPROFILE%\ozon-buyer-mcp-local`;
2. finds installed Google Chrome;
3. starts an external Chrome with CDP on `127.0.0.1:9222` and a dedicated profile;
4. installs/updates the local Python package;
5. starts the local worker on `127.0.0.1:8765`;
6. long-polls the Railway relay and executes Ozon browser jobs locally.

Expected console status:

```
External Chrome CDP: OK
Local worker: OK
Railway relay: OK
CONNECTED. Waiting for Ozon requests from ChatGPT...
```

Keep the connector window open while ChatGPT is using Ozon. Since v0.4.1 the connector automatically restarts the external Chrome if it is closed, and the local worker reconnects to a fresh CDP/page instead of retaining a dead Playwright target.

## Network requirement

The relay host is:

`ozon-worker-relay-production.up.railway.app`

If the PC cannot reach it directly, route **only this exact relay domain** through the router/VPN.

Do **not** route `ozon.ru` through VPN. Ozon should use the normal local Internet connection.

## Security

- Public MCP remains read-only.
- Relay and local worker require bearer tokens.
- No worker token is committed to GitHub.
- The one-click launcher stores the token only on the Windows machine via DPAPI.
- Dedicated Chrome profile: `%USERPROFILE%\ozon-buyer-mcp-cdp-profile`.
- Local worker binds only to `127.0.0.1:8765`.
- Chrome CDP binds only to `127.0.0.1:9222`.

If a token was ever exposed in chat/logs/scripts, rotate it in Railway and run the launcher again after deleting `%USERPROFILE%\ozon-buyer-mcp-local\.worker-token.dpapi`.

## Delivery-date caveat

Ozon pages can contain dates for several sellers/alternate offers at once. Search snippets are useful for discovery, but a delivery date should be treated as confirmed only when it is tied to the exact offer/seller shown to the user.

## Railway

MCP endpoint:

`https://ozon-buyer-mcp-live-production.up.railway.app/mcp`

Relay health endpoint:

`https://ozon-worker-relay-production.up.railway.app/health`

Main MCP service uses the relay instead of accessing Ozon directly.

## Troubleshooting

If ChatGPT reports that the local worker is offline:

1. run `START_OZON_MCP.cmd`;
2. keep the connector console open;
3. keep the external Chrome window open;
4. check that the console reaches `CONNECTED`.

If relay connection fails, verify the exact relay-domain VPN route. If Ozon itself fails, verify that `ozon.ru` is **not** routed through the VPN.
