# Price Hunter MCP: Linux/Acer migration — 2026-10-13

## Current deployment

Price Hunter 0.6.2 now runs on the owner's Linux Acer host. The former Railway MCP/relay services and account were retired. The MCP server, private browser-job relay and worker are colocated; the worker uses an ordinary installed Chrome under a systemd/Xvfb service. A locked desktop does not stop this service. Windows launch scripts remain optional compatibility tools and are no longer required by this Acer deployment.

```text
ChatGPT -> authenticated HTTPS MCP -> Linux relay -> Linux native worker
        -> local Chrome CDP -> marketplace rendered pages
```

The canonical public MCP path is `/ozon/mcp` on HTTPS 443, with the owner's private origin configured externally. Set resource URL and Auth0 audience to that exact path; `ozon:read` remains the required scope. Supported `offline_access`, Allow Offline Access and the path/discovery layer let compatible clients renew credentials. Controlled short-expiry tests observed successful refresh and real protected calls; normal access-token lifetimes were restored. A continuous 24-hour test was not performed.

## Browser and reliability changes

- Dedicated Chrome profile, manual owner sign-in, Xvfb virtual display, loopback-only CDP 9222.
- Chrome supervised by `acer-ozon-browser.service`; browser worker connects to this existing browser rather than opening a second profile instance.
- Native worker polls the local relay. Title extraction uses the actual product DOM instead of a generic marketplace page title; code/fixture checks and a real product-price read were recorded.
- Quiesced same-host profile backup and Chrome restarts/cold boots passed. Cross-OS keyring/cookie portability was not established.
- Public HTTPS path-layer supports canonical resource metadata/authorization on `/ozon/mcp`.

## Function checks and limits

After source Railway retirement, an authenticated `market_search` restricted to Ozon returned two rendered offers with `errors={}`. A product-price read and owner login/restart checks were performed separately. This does not revalidate every marketplace, every personal promotion or an Internet-wide minimum price. Prices/delivery depend on page, account and region; a person must verify the linked offer before purchasing.

The existing six source adapters and tool semantics remain documented in the main README. Ozon tools remain read-only: no cart, checkout, orders, favorites, payment or automatic login. Existing owner authorization and JWT signature/issuer/audience/expiry/scope checks remain.

## Operator checks

```bash
systemctl is-active acer-ozon-browser.service
systemctl is-enabled acer-ozon-browser.service
curl --fail --max-time 15 "$MCP_PUBLIC_ORIGIN/ozon/healthz"
```

Use the deployment's real health routing and protected MCP tool to verify access; an accessible health page alone does not prove authorization or rendered search. Store worker/relay/Auth0 values only in private host settings. Never publish profile, cookies, tokens, credentials or remote browser ports. Changes to source documentation do not rebuild the deployed images automatically.

## Recovery

Capture profile only while its browser owner is quiesced; restore to a separate directory first and verify SQLite/file integrity. Preserve relay settings, the correct existing native profile and keyring. Restore one browser and one worker, then verify protected health and an actual rendered query. Do not turn recovery into a purchase or introduce a second Chrome on the same profile.

Private infrastructure inventory, exact origin and recovery hashes are maintained in the owner's private MCP documentation and Yandex Disk migration package. This public document contains no personal infrastructure credentials or private backup data.
