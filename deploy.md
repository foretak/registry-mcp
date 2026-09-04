# Deploying registry-mcp on a fresh Ubuntu 24.04 VPS

These are the exact commands to take a brand-new Ubuntu 24.04 server to a
running instance behind Caddy with automatic HTTPS.

## 1. Point DNS at the server

Before starting, create an `A` (and `AAAA`, if you have an IPv6 address)
record for the domain you'll use, pointing at the VPS's public IP. Caddy
needs this to issue a certificate later.

## 2. Update the system and create a deploy user (optional but recommended)

```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo adduser deploy
sudo usermod -aG sudo deploy
su - deploy
```

The rest of the commands assume you are logged in as this (or any
non-root, sudo-capable) user.

## 3. Install Docker Engine and the Compose plugin

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Allow running docker without sudo (log out and back in for this to apply)
sudo usermod -aG docker "$USER"
```

Log out and back in (or run `newgrp docker`) so the group change takes
effect, then confirm:

```bash
docker --version
docker compose version
```

## 4. Configure the firewall

```bash
sudo apt-get install -y ufw
sudo ufw allow OpenSSH
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
sudo ufw status
```

## 5. Clone the repository

```bash
sudo mkdir -p /opt/registry-mcp
sudo chown "$USER":"$USER" /opt/registry-mcp
git clone https://github.com/foretak/registry-mcp.git /opt/registry-mcp
cd /opt/registry-mcp
```

## 6. Configure environment variables

```bash
cp .env.example .env
nano .env   # set REGISTRY_MCP_CONTACT_EMAIL, REGISTRY_MCP_ADMIN_KEY, REGISTRY_MCP_DOMAIN
```

Generate a strong admin key if you don't already have one:

```bash
openssl rand -hex 32
```

## 7. Build and start the stack

```bash
docker compose up --build -d
```

This builds the `api` image, starts it, and starts `caddy`, which will
automatically request a TLS certificate for `REGISTRY_MCP_DOMAIN` from
Let's Encrypt on first request.

## 8. Verify it's running

```bash
docker compose ps
curl -sS https://<your-domain>/health   # through Caddy, from anywhere
```

That should return a healthy response. If it fails, give Caddy a minute
to finish the ACME challenge and check its logs (below). See "Smoke
test" below for the full set of checks (T13 ran all of these against a
local `REGISTRY_MCP_DOMAIN=localhost` stack; the corrections below come
from that run).

> The `api` container does not publish a host port by itself (only
> `expose: "8080"`, reachable from `caddy` over the compose network) — the
> `curl http://localhost:8080/health` "direct to the api container" step
> from an earlier draft of this doc does not work as written on a fresh
> checkout; go through Caddy, or `docker compose exec api curl -fsS
> http://localhost:8080/health` from inside the container.

## 9. View logs

```bash
docker compose logs -f            # all services
docker compose logs -f api        # just the API
docker compose logs -f caddy      # just Caddy / TLS issuance
```

## 10. Updating to a new version

```bash
cd /opt/registry-mcp
git pull
docker compose up --build -d
```

This rebuilds only what changed and restarts affected services with no
manual downtime steps required. To also prune old, now-unused images:

```bash
docker image prune -f
```

## Testing this locally (no VPS, no real domain)

`REGISTRY_MCP_DOMAIN=localhost` makes Caddy skip Let's Encrypt entirely and
issue a certificate from its own internal CA instead — you get real HTTPS
with no DNS and no public IP, at the cost of every client needing to trust
(or ignore) that internal CA. `curl` needs `-k` (`--insecure`); an MCP
client needs its TLS verification turned off (below); a browser will show a
"not secure" warning you click through.

```bash
cp .env.example .env
# Edit .env:
#   REGISTRY_MCP_DOMAIN=localhost
#   REGISTRY_MCP_ADMIN_KEY=localtest        (or anything — this is a throwaway instance)
#   REGISTRY_MCP_CONTACT_EMAIL=hello@example.test
docker compose up --build -d
```

**If ports 80/443 are already taken on this machine** (or, as on a
rootless Docker install, not bindable at all — `cannot expose privileged
port 80` / `bind: permission denied` from the daemon even though nothing
else is listening on it), use the checked-in override
`docker-compose.local.yml`, which remaps Caddy's `80`/`443` to `8080`/`8443`
on the host:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build -d
```

Every URL in the smoke test below becomes `https://localhost:8443/...`
instead of `https://localhost/...` when using this override.

## Smoke test

Run these against a stack started as above. (T13 ran the `:8443` form,
since 80/443 were unavailable in that environment; commands below show the
plain-port form — drop in `:8443` if you're using the override.)

```bash
# REST + static discovery routes, all through Caddy/TLS
curl -k https://localhost/health
curl -k https://localhost/v1/NO/company/923609016
curl -k https://localhost/llms.txt
curl -k https://localhost/server.json
curl -k https://localhost/
curl -k https://localhost/status          # public status page, see below

# MCP over HTTPS — note the trailing slash, see "MCP and the trailing
# slash" below
claude mcp add registry-mcp-docker --transport http https://localhost/mcp/
claude mcp list      # should show "registry-mcp-docker ... ✔ Connected"
claude mcp remove registry-mcp-docker

# Or drive it directly with fastmcp, bypassing the CLI:
uv run python -c "
import asyncio
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

async def main():
    transport = StreamableHttpTransport('https://localhost/mcp/', verify=False)
    async with Client(transport) as client:
        print([t.name for t in await client.list_tools()])

asyncio.run(main())
"

# Persistence: restart the stack, then look the same company up again —
# `cached` must be true and `fetched_at` must be the *same* timestamp as
# before the restart (proves the SQLite file survived on the named volume,
# not just an in-process cache).
docker compose restart
curl -k https://localhost/v1/NO/company/923609016   # cached: true, same fetched_at

docker compose down -v   # tear down when done; confirm with `docker ps -a`
```

Actual results from the T13 run (2026-09-04, `:8443` override, abbreviated):

| Check | Result |
|---|---|
| `GET /health` | `200` `{"status":"ok","version":"0.1.0","countries":["NO"]}` |
| `GET /v1/NO/company/923609016` | `200`, full `CompanyReport` (EQUINOR ASA) |
| `GET /llms.txt` | `200`, text |
| `GET /server.json` | `200`, JSON |
| `GET /` | `200`, HTML homepage |
| `GET /status` | `200`, HTML — version `0.1.0`, countries `NO`, upstream `reachable`, cache rows `1` |
| MCP `tools/list` (`claude mcp add --transport http .../mcp/` then `claude mcp list`) | `✔ Connected`, 5 tools |
| Restart + re-lookup | `cached: true`, `fetched_at` identical to the pre-restart value — persisted on the `registry-data` volume |

## Corrections found while verifying this doc (T13)

- **Dockerfile only copied `.venv` and `src` into the runtime image**
  (flagged in `REVIEW.md`'s T04 note). `static/` and the root `server.json`
  were missing, so `/`, `/llms.txt`, `/llms-full.txt` and `/server.json`
  404'd in a real container while working fine under `uv run uvicorn`
  locally. Fixed: the Dockerfile now also `COPY`s `/app/static` and
  `/app/server.json` from the builder stage into `/app/static` and
  `/app/server.json` in the runtime stage, and sets
  `REGISTRY_MCP_STATIC_DIR=/app/static` explicitly (`api/main.py`'s
  `_static_dir()`/`_server_json_path()` heuristic would in fact have found
  them at `/app` on its own, since that's the repo-root fallback — the env
  var is set anyway so the routes keep working even if that heuristic
  changes).
- **Step 8's "direct to the api container" `curl http://localhost:8080/health`
  never worked**: `docker-compose.yml`'s `api` service only `expose`s port
  8080 to other containers on the compose network, it never `ports:`-publishes
  it to the host. Removed that line from step 8; `docker compose exec api
  curl -fsS http://localhost:8080/health` is the real equivalent if you need
  to check the container without going through Caddy.
- **Ports 80/443 are not always available to Docker**: on a rootless Docker
  install in particular, binding them can fail with `cannot expose
  privileged port 80` even when nothing else is listening on them. Added
  `docker-compose.local.yml` (an explicit `-f` override, not autoloaded) that
  remaps Caddy to `8080`/`8443`, plus the "Testing this locally" section
  above.
- **MCP and the trailing slash**: `mcp.http_app(path="/")` is mounted at
  `/mcp` in `api/main.py`; a `POST /mcp` (no trailing slash) is a Starlette
  `Mount` redirect — a `307` to `/mcp/` — confirmed independent of Caddy/TLS
  (same 307 hitting the `api` container directly over plain HTTP). Some
  clients (`fastmcp`'s `StreamableHttpTransport`, tested here) do not follow
  that redirect for a `POST` and fail with a bare `MCPError`; `claude mcp
  add` does follow it and connects fine either way. Always give the MCP URL
  with a trailing slash (`https://localhost/mcp/`) to avoid depending on a
  client's redirect handling — this doc's examples above do. Not fixed in
  `api/main.py` itself (out of T13's file ownership; `api/main.py`'s only
  T13 edit is the one `status_router` import + include line) — worth a
  one-line fix for whoever next touches that mount (`redirect_slashes=False`
  on the `Mount`, or mount at `/mcp/` instead of `/mcp`).
- **`fastmcp.client.transports.StreamableHttpTransport(url, verify=False)`**
  is the option to skip TLS verification against Caddy's internal CA
  certificate without installing it system-wide — used for the MCP check
  above instead of trusting the CA. `httpx`'s own `verify=False` also works
  if you build the transport by hand.

## Troubleshooting

- **Certificate not issuing**: confirm DNS actually resolves to this
  server (`dig +short <your-domain>`) and that ports 80/443 are open
  (`sudo ufw status`, and check your cloud provider's firewall/security
  group too).
- **`docker compose` not found**: you likely installed the old standalone
  `docker-compose` (with a hyphen) instead of the plugin; re-run step 3.
- **Cache/data not persisting across restarts**: confirm the `api`
  service is writing to `/app/data` (backed by the `registry-data` named
  volume) — check with `docker volume inspect registry-mcp_registry-data`.
