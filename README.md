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

The service is read-only: it does not perform login, cart, checkout, orders,
favorites or other write actions. An account can be signed in manually in the
dedicated Chrome profile after the MCP endpoint has been protected as below.

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

## Personal account prices

The local worker uses the dedicated Chrome profile at
`%USERPROFILE%\ozon-buyer-mcp-cdp-profile`. After the MCP endpoint is protected,
the owner can sign in to Ozon in that Chrome window. The worker then reads the
same rendered search pages and product data shown in that profile. Ozon login
codes, passwords, browser cookies, and the worker token must not be copied into
ChatGPT, GitHub, or Railway. The login session stays in the local Chrome profile.

Personal account access requires OAuth on the public MCP endpoint. For the
Railway `ozon-buyer-mcp-live` service, configure these variables before deploying
the protected build:

- `AUTH0_DOMAIN`: the Auth0 tenant domain, without `https://`;
- `AUTH0_AUDIENCE`: the canonical public MCP URL ending in `/mcp`;
- `AUTH0_REQUIRED_SCOPE`: a dedicated scope such as `ozon:read`;
- `AUTH0_ALLOWED_SUBJECT`: the exact Auth0 `sub` for the owner.

The Auth0 API must issue RS256 access tokens for that audience and scope, and
permit the ChatGPT connector's OAuth authorization-code + PKCE flow. On HTTP
startup, missing or partial auth configuration stops the service. Anonymous
requests to `/mcp` receive `401` with an OAuth discovery challenge. Product
arguments are restricted to Ozon product URLs or SKU values so tools cannot
navigate to account pages.

Rollout order: configure Auth0 and the owner allowlist, deploy the protected
MCP build, verify anonymous `401` and owner-authorized access, reconnect the
ChatGPT plugin with OAuth, then sign in to Ozon in the dedicated Chrome window.
Compare a product's price in that window with `ozon_get_price` for the same SKU.
Prices may still depend on the selected payment method and delivery conditions.

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
