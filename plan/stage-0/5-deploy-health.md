# Bite 5: Bare deploy, `/health` at the public URL

## For you

**What already exists.** The gateway already has a `/health` page that needs no login. There's no Dockerfile, no server and no domain.

**What's being built.** About 40 lines of config: a Dockerfile, which packages the gateway; a `compose.yaml`, which runs it; and a Caddyfile, which sets up the proxy that handles HTTPS. Together they make a public HTTPS address that shows only `/health`. The server holds no API keys, so nothing on it can spend money.

**Your input** (write under each one):

1. Which server: Hetzner (about €10 a month), Oracle Always Free, or something else?
   - Your answer:
2. Approve Docker?
   - Your answer:
3. Approve Caddy?
   - Your answer:
4. Which domain or subdomain should the public address use?
   - Your answer:

---

**Goal:** a public HTTPS address answers `GET /health` with 200, so deploying can't fail in the last week.
**Builder:** Claude, with you doing the account and DNS steps. **After:** bite 1 and Open #7 (VPS cost). **Budget:** about 40 lines of config.

**Blocked on you:**
- Open #7: choose Hetzner (about €10 a month), Oracle Always Free, or something else.
- New dependencies: Docker (packages the gateway so it runs the same everywhere) and a reverse proxy such as Caddy. A reverse proxy sits in front of the app and handles HTTPS. Both need your OK, then entries in `DEPENDENCIES.md`.
- A domain or subdomain for the URL.

**Safety:**
- The box holds no provider keys, so nothing on it can spend money.
- The proxy exposes only `/health`, and port 8000 is never published.
- If the API is ever exposed later, it needs `AI_OS_TOKEN`, HTTPS and a spend cap first.

**Write the tests first:**
- Locally, `docker compose up` makes `/health` return 200 through the proxy, and `/api/llm/chat` through the proxy returns 404.
- From your laptop, `curl https://<domain>/health` returns 200.
- Check that the gateway starts with no keys. If it won't, the plan comes back to you rather than me adding keys.

**Build:**
- One `gateway/Dockerfile`, following I17.
- A `compose.yaml` with the gateway on the internal network only. Inside the container, uvicorn listens on `0.0.0.0`, which means "all addresses inside the container"; `main.py` stays on 127.0.0.1 for local runs.
- A Caddyfile that serves only `/health`.

**Done when:** the public `curl` returns 200 and the API path doesn't answer from outside.
**Out of scope:** the bot, the scheduler and Litestream on the box (Stage 3), and grader access (Open #9).
