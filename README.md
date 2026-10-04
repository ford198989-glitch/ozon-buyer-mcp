# Price Hunter MCP v0.6.0

Read-only buyer-side Price Hunter for ChatGPT. It compares Ozon, Wildberries, Yandex Market, Megamarket, Avito and ordinary web stores through the same local Chrome profile; Ozon product details/reviews remain available.

## Production status (2026-10-04)

The protected v0.6.0 build is deployed on Railway. Both production services — `ozon-buyer-mcp-live` and `ozon-worker-relay` — are online. The ChatGPT connector **Ozon Buyer MCP Personal** still uses Auth0 OAuth with the existing `ozon:read` scope name for backward compatibility, although the service now covers multiple marketplaces and web stores.

The owner manually signs in to Ozon in the dedicated Chrome profile on their Windows PC when personal Ozon prices are needed. Other marketplace and web searches use the same local Chrome profile and rendered pages. An earlier end-to-end check of SKU `2568217536` matched the prices shown in that Chrome window (380 RUB with Ozon Card, 420 RUB without) at the time of the check; those numbers are only a historical validation example.

The Windows connector must be running for live marketplace/web requests. The old anonymous ChatGPT connector is incompatible with the protected `/mcp` endpoint and receives `401`.

## Current production architecture

```
ChatGPT
  -> public MCP on Railway
  -> private relay on Railway
  -> Windows PC connector
  -> ordinary externally launched Google Chrome (CDP 127.0.0.1:9222)
  -> Ozon / Wildberries / Yandex Market / Megamarket / Avito / web stores
```

This architecture is intentional: marketplace anti-bot and regional/session-dependent pricing are more reliably handled through the user's ordinary local Chrome than by direct Railway/datacenter requests. Railway orchestrates jobs; the local connector performs the browser work.

## Buyer tools

- `ozon_health()`
- `ozon_search(query, limit, sort, price_min, price_max)`
- `ozon_product(product, include_description)`
- `ozon_reviews(product, limit)`
- `ozon_get_price(product)`
- `ozon_delivery(product)`
- `ozon_compare(products)`
- `market_search(query, marketplaces, limit_per_market)` — searches any subset of Ozon, Wildberries, Yandex Market, Megamarket, Avito and ordinary web stores
- `market_compare(query, marketplaces, limit_per_market)` — returns the cheapest relevant offer per source and the best overall price
- `best_buy(query, sources, limit_per_source, include_avito)` — Price Hunter mode: exact-model matching, best new offer, separate Avito result, savings vs Ozon

The service is read-only: it does not perform login, cart, checkout, orders,
favorites or other write actions. Sign-in to Ozon happens manually in the
dedicated Chrome window, outside the MCP tools.

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
6. long-polls the Railway relay and executes marketplace/web browser jobs locally.

Expected console status:

```
External Chrome CDP: OK
Local worker: OK
Railway relay: OK
CONNECTED. Waiting for Ozon requests from ChatGPT...
```

Keep the connector window open while ChatGPT is using Price Hunter. Since v0.4.1 the connector automatically restarts the external Chrome when a new job arrives after it was closed, and the local worker reconnects to a fresh CDP/page. If the connector itself is closed, run `START_OZON_MCP.cmd` again. The Ozon login persists in the dedicated local Chrome profile unless that session expires or the profile is cleared.

## Network requirement

The relay host is:

`ozon-worker-relay-production.up.railway.app`

If the PC cannot reach it directly, route **only this exact relay domain** through the router/VPN.

Do **not** route marketplace sites through the relay VPN rule. The intended setup is to route only the relay hostname if necessary; Ozon/Wildberries/Yandex Market/Megamarket/Avito/web stores should use the normal local Internet connection unless the user's own network policy requires otherwise.

## Security

- Publicly reachable MCP requires a valid Auth0 user access token with audience equal to the MCP URL, the `ozon:read` scope, and the configured owner subject. Anonymous access returns `401`.
- Relay and local worker require bearer tokens.
- No worker token is committed to GitHub.
- The one-click launcher stores the token only on the Windows machine via DPAPI.
- Dedicated Chrome profile: `%USERPROFILE%\ozon-buyer-mcp-cdp-profile`.
- Local worker binds only to `127.0.0.1:8765`.
- Chrome CDP binds only to `127.0.0.1:9222`.

## Personal account prices

The local worker uses the dedicated Chrome profile at
`%USERPROFILE%\ozon-buyer-mcp-cdp-profile`. The owner signs in to Ozon in that Chrome window. The worker then reads the
same rendered search pages and product data shown in that profile. Ozon login
codes, passwords, browser cookies, and the worker token must not be copied into
ChatGPT, GitHub, or Railway. The login session stays in the local Chrome profile.

The production Railway `ozon-buyer-mcp-live` service has OAuth configured through Auth0. Its configuration uses these variable names (never publish their values):

- `AUTH0_DOMAIN`: the Auth0 tenant domain, without `https://`;
- `AUTH0_AUDIENCE`: the canonical public MCP URL ending in `/mcp`;
- `AUTH0_REQUIRED_SCOPE`: a dedicated scope such as `ozon:read`;
- `AUTH0_ALLOWED_SUBJECT`: the exact Auth0 `sub` for the owner.

The Auth0 API issues RS256 access tokens for that audience and scope, and
permits the ChatGPT connector's OAuth authorization-code + PKCE flow. On HTTP
startup, missing or partial auth configuration stops the service. Anonymous
requests to `/mcp` receive `401` with an OAuth discovery challenge. Product
arguments are restricted to Ozon product URLs or SKU values so tools cannot
navigate to account pages.

To use the live release: run `START_OZON_MCP.cmd` and wait for `CONNECTED`; sign in to Ozon manually in the Chrome window if needed; use the OAuth-connected **Ozon Buyer MCP Personal** connector in ChatGPT. Check `ozon_health`, then call `ozon_get_price` with an Ozon product URL or SKU. Compare with the same product in that Chrome profile. Prices may depend on payment method and delivery conditions. `ozon_health.account_login` is a static capability flag and does **not** report whether the Chrome profile is signed in.

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
3. check that the console reaches `CONNECTED`;
4. let the connector restart Chrome on the next job, or restart the connector if it exited.

If relay connection fails, verify the exact relay-domain VPN route. If Ozon itself fails, verify that `ozon.ru` is **not** routed through the VPN.

If ChatGPT receives `401`, reconnect **Ozon Buyer MCP Personal** through Auth0 and check the owner account and `ozon:read` grant. A successful relay `/health` response alone does not verify OAuth access to `/mcp` or a live worker. If prices appear generic, confirm Ozon sign-in in the dedicated Chrome profile and compare the exact SKU in that same window.



## Multi-market search (v0.5.0+)

Cross-market discovery uses the same privacy model as the original Ozon integration: Railway never logs in to marketplaces directly. The local Windows connector opens rendered public/search pages in the dedicated Chrome profile and returns only bounded product fields needed for comparison.

Supported marketplace identifiers:

- `ozon`
- `wildberries` (alias: `wb`)
- `yandex_market` (aliases: `yandex`, `market`)
- `megamarket` (alias: `mega`)
- `avito` (alias: `авито`) — kept separate from new-goods winner
- `web` (aliases: `internet`, `интернет`) — discovers prices from ordinary web stores via Yandex search and validates product pages

Example workflow:

1. call `market_compare("Genau Stride X")`;
2. inspect the best matching offer from each marketplace;
3. compare price, rating, review count and delivery text;
4. open the returned product URL before purchase.

Marketplace pages are dynamic. Prices and delivery can depend on region, account, promotions and payment method. Cross-market matching uses token/model relevance and exact-model preference, so exact model names produce the most reliable price comparison.


## Price Hunter (v0.6.0)

`best_buy` is intended for exact product/model shopping. It keeps short model tokens such as `X` and numeric/alphanumeric model identifiers such as `S50`, so similarly named products are less likely to be mixed together.

Default sources are Ozon, Wildberries, Yandex Market, Megamarket, Avito and ordinary web stores. Avito is reported separately so used/second-hand listings do not automatically beat new retail offers.

The generic `web` source discovers candidate stores through Yandex Search, then opens a limited number of product pages in the local Chrome profile. It prefers JSON-LD Product/Offer prices and falls back to rendered page price elements. Every web result includes price-confidence metadata; low-confidence prices are excluded from `best_buy`.

Example:

`best_buy("Genau Stride X")`

The response includes the best new offer, best Avito offer (if enabled), best Ozon offer, savings versus Ozon, and the best matching result per source.


## Current release summary

- Version: `0.6.0`
- Production commit: `ccfaa5ead34e5f428583ccc5533106b1d2907ba2`
- Production MCP: online
- Production relay: online
- Local worker: auto-updates from `main` when `START_OZON_MCP.cmd` is restarted
- Canonical Yandex Disk documentation: `/ChatGPT/Ozon Buyer MCP/README.md`
