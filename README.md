# Price Hunter MCP v0.6.2

Read-only buyer-side Price Hunter for ChatGPT. It compares Ozon, Wildberries, Yandex Market, Megamarket, Avito and ordinary web stores through the same local Chrome profile; Ozon product details/reviews remain available.

## Expansion from Ozon to Price Hunter

The original Ozon-only integration gained Wildberries and Yandex Market in v0.5.0, then Megamarket, Avito and web-store discovery in v0.6.0. v0.6.1 and v0.6.2 improve parser reliability, deadlines, price extraction and relevance selection. The repository and authenticated live health both identify the current release as v0.6.2.

| Source | Identifier | Implemented capability | Practical limitation |
| --- | --- | --- | --- |
| Ozon | `ozon` | Search, product details, reviews, prices, delivery and comparison; participates in cross-source search | Personal prices require manual sign-in in the dedicated Chrome profile |
| Wildberries | `wildberries` / `wb` | Rendered search cards and cross-source comparison | Fields depend on the current page layout and account/region |
| Yandex Market | `yandex_market` / `yandex` / `market` | Rendered search cards and cross-source comparison | Seller, promotion and payment conditions must be checked on the linked offer |
| Megamarket | `megamarket` / `mega` | Rendered search cards and cross-source comparison | CAPTCHA may require manual interaction in Chrome |
| Avito | `avito` / `авито` | Listing discovery; separate `best_avito_offer` | Condition is reported as unknown; listings are excluded from the new-goods winner |
| Web stores | `web` / `internet` / `интернет` | Yandex Search discovers external store pages; JSON-LD or rendered page data supplies prices | Only 3–5 candidate pages are inspected per call; this is not an exhaustive Internet search |

The added sources support discovery and price comparison. Detailed product/review/delivery tools remain Ozon-specific. Cross-source offers may contain price, old price, title, URL, rating, review count, seller, image and delivery text; unavailable fields are `null`. Searches run sequentially in the same Windows Chrome profile. Per-source failures are returned in `errors`, and successful sources can still contribute results; an empty result does not establish that a product is unavailable everywhere.

Examples with the current tool schema:

```python
market_search(query="Genau Stride X", marketplaces=["ozon", "wb", "yandex_market"], limit_per_market=6)
market_compare(query="Genau Stride X", marketplaces=["ozon", "wb", "yandex_market", "megamarket", "web"])
best_buy(query="Genau Stride X", sources=["ozon", "wb", "yandex_market", "web"], limit_per_source=6, include_avito=False)
```

Omitting the source list searches all six sources. Public per-source limits are clamped to 1–20. `market_search` returns `offers`, `cheapest` and `errors`; `market_compare` returns `by_market`, `best_offer` and the price spread between selected source offers; `best_buy` returns `best_new_offer`, `best_avito_offer`, `best_ozon_offer`, `by_source` and `savings_vs_ozon_rub`. Savings describe the inspected results, not a guaranteed market-wide minimum. Restart `START_OZON_MCP.cmd` after a code update so the local worker understands the new marketplace jobs.

## Production status (2026-10-05)

The protected v0.6.2 build is deployed on Railway at commit `07aae6273cd5ca1cbc0539dca93d363153d354af`. The `ozon-buyer-mcp-live` deployment and `ozon-worker-relay` are in Railway's `SUCCESS` state; the OAuth-connected **Ozon Buyer MCP Personal** connector returned `ozon_health.version = 0.6.2` on 2026-10-05. This health check does not establish that the Windows connector is currently online or that a particular marketplace search succeeds. The connector still uses the existing Auth0 `ozon:read` scope name for backward compatibility, although the service now covers multiple marketplaces and web stores.

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

Some ChatGPT connections retain an older tool schema and do not show the three multi-market tools. On those connections, call `ozon_search(query="Genau Stride X", sort="best_buy")`, `sort="market_compare"`, or `sort="market_search"` to invoke the corresponding mode across the default sources. The `limit` parameter becomes the per-source limit (capped at 20). These modes ignore `price_min` and `price_max`; use the dedicated tools when their schema is available. Reconnecting the plugin or opening a new chat may refresh the tool list.

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

Since the deployed `07aae62` change, `market_search.cheapest` is selected only from exact matches or offers with relevance at least `0.65`. `market_compare` applies the same gate to each source; a source with no qualifying priced offer has `best_offer: null`. The service no longer labels an unrelated cheap result as the best match. Where bounded card text has explicit RUB amounts, the parser uses its first amount as the current price and a later higher amount as the old price; otherwise it uses the worker's structured price. Verify the selected offer on its product page before purchase.


## Price Hunter (v0.6.0)

`best_buy` is intended for exact product/model shopping. It keeps short model tokens such as `X` and numeric/alphanumeric model identifiers such as `S50`, so similarly named products are less likely to be mixed together.

Default sources are Ozon, Wildberries, Yandex Market, Megamarket, Avito and ordinary web stores. Avito is reported separately so used/second-hand listings do not automatically beat new retail offers.

The generic `web` source discovers candidate stores through Yandex Search, then opens a limited number of product pages in the local Chrome profile. It excludes the separately handled marketplace domains, prefers JSON-LD Product/Offer prices (`high` confidence), and falls back to rendered price elements or body text (`medium` confidence). Confidence describes the extraction method; it does not verify the seller, currency, stock, item condition or final checkout price.

`best_buy` normally accepts priced offers with an exact token/model match or relevance at least `0.68`, excluding `low` confidence. If there are no qualifying new-goods offers, the current code falls back to priced new-source offers with relevance at least `0.55`; that fallback does not repeat the confidence exclusion. `by_source` continues to use the stricter filter, so a fallback winner can coexist with an empty strict result for its source. Within accepted candidates the lowest price wins; an exact match is not separately ranked ahead of every weaker candidate. Marketplace and web offers are classified as new by source, rather than by inspecting their actual condition. Always check model, condition, currency and offer terms on the linked page.

Example:

`best_buy("Genau Stride X")`

The response includes the best new offer, best Avito offer (if enabled), best Ozon offer, savings versus Ozon, and the best matching result per source.


## Reliability fixes in v0.6.1

- fixed the embedded JavaScript newline-regex bug that broke Wildberries and Yandex Market parsing with `Invalid regular expression: missing /`;
- added fast CAPTCHA/robot-page detection for marketplace and web searches so blocked sources fail cleanly instead of stalling the whole comparison;
- bounded marketplace/web navigation times and web candidate depth so one slow source cannot occupy the single Windows browser worker for minutes;
- aligned local-worker, relay and MCP request deadlines to avoid late `/result` 404 responses after the caller has already timed out.

Megamarket may still present an interactive CAPTCHA. The service does not bypass it; solve it manually in the dedicated Chrome window if that source is needed.

## Current release summary

- Version: `0.6.2`
- Production MCP commit: `07aae6273cd5ca1cbc0539dca93d363153d354af`
- Production MCP: Railway `SUCCESS`; authenticated `ozon_health` returned version `0.6.2` on 2026-10-05
- Production relay: Railway `SUCCESS` on 2026-10-05
- Local worker: auto-updates from `main` when `START_OZON_MCP.cmd` is restarted
- Canonical Yandex Disk documentation: `/ChatGPT/Ozon Buyer MCP/README.md`


## v0.6.2 price parsing fix

Marketplace and web parsers now treat a price element as one monetary value instead of concatenating every digit from a DOM block. This fixes inflated prices on Yandex Market, Megamarket and web stores when a price node contains current/old prices, bonuses or decimals. JSON-LD decimal prices such as `17600.00` are parsed as 17600 RUB rather than 1760000.
