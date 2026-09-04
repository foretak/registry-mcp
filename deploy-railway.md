# Deploying registry-mcp on Railway

Companion to `deploy.md` (the Ubuntu/Docker Compose/Caddy path). This is the
Railway path: no Caddy, no manual TLS — Railway terminates HTTPS and injects
`PORT` itself. Config-as-code lives in `railway.toml` at the repo root
(builder, healthcheck, restart policy, region/replica count); this doc is
the command sequence that goes with it.

Commands below use the `railway` CLI (`railway --version` to confirm it's
installed and `railway whoami` to confirm you're logged in). Everything
here is a **new-project, single-service** setup — one API service, one
volume, no database service.

## 0. Region and cost expectations

- **Region: `europe-west4` (Amsterdam / "EU West")** — the Railway region
  closest to Norway. This is already pinned in `railway.toml` under
  `[deploy.multiRegionConfig.europe-west4-drams3a]` (Railway's full region
  identifier), alongside `numReplicas = 1`.
- **Why exactly 1 replica, always**: the SQLite cache (`DECISIONS.md`
  D-006) is a single file on a single Railway volume. SQLite has no
  multi-writer coordination across processes on different machines — two
  replicas writing `cache.sqlite3` concurrently risk `database is locked`
  errors and corrupt reads. Do not raise `numReplicas` (or add a second
  region) without first moving the cache to a shared store.
- **Cost**: the Hobby plan is $5/month and *includes* $5 of usage credit,
  so a small always-on service (this one: no background workers, modest
  RAM) plus a small volume often lands close to or within that credit.
  Volume storage is billed separately at **$0.15/GB/month** on top of
  compute — a 1 GB volume (plenty for a SQLite cache of company lookups)
  is about $0.15/month. Get current numbers from
  <https://railway.com/pricing> before committing, since Railway's pricing
  page is the source of truth, not this doc.
- **Sleep-on-idle ("Serverless")**: off by default. Railway *can* sleep a
  service after ~10 minutes with no outbound traffic and wake it on the
  next request, which would reduce compute cost further — but the first
  request after a sleep pays a cold-start, which is a bad trade for an MCP
  server a client expects to respond to promptly. Leave it off (Settings →
  Deploy → Serverless) unless you specifically want the savings and can
  live with occasional cold starts.

## 1. Create and link the project

From the repo root (`/home/farge/registry-mcp`), with `railway.toml` and
the `Dockerfile` already committed:

```bash
railway init --name registry-mcp
```

This creates a new Railway project and links the current directory to its
default environment (`railway status` confirms). `railway init` already
links your working directory to the project it creates, so `railway link`
below is normally redundant right after `init` — it's here for the case
where you're re-cloning this repo on another machine, or the project was
created some other way (e.g. the Railway dashboard) and you need to attach
this checkout to it:

```bash
railway link
```

(Follow the prompts: workspace, project, environment.)

## 2. First deploy (creates the service)

Railway doesn't have a service to attach a volume or variables to until
something is deployed, so deploy once first:

```bash
railway up --detach
```

Watch it build (`railway logs --build`) — it should print `Using detected
Dockerfile!` and use the settings from `railway.toml` (Dockerfile builder,
`/health` healthcheck). This first deploy will come up **without** the
volume or the app's required env vars, so `/health` will pass (it doesn't
touch the cache) but company lookups will fail until step 3 is done and a
redeploy happens.

## 3. Add the persistent volume

```bash
railway volume add --mount-path /app/data
```

Mounts a volume at `/app/data` inside the container — the same path the
Dockerfile already creates and `chown`s for the `app` user, and where
`REGISTRY_MCP_CACHE_PATH=/app/data/cache.sqlite3` points. If you have more
than one service in the project, disambiguate with `--service <name>` (the
service name defaults to the repo directory name, `registry-mcp`, for a
project created via `railway up`/`init` from this checkout).

Attaching a volume triggers a redeploy on its own so the mount takes
effect — no separate restart needed, but see step 5.

## 4. Set environment variables

```bash
railway variable set \
  REGISTRY_MCP_CONTACT_EMAIL=you@example.com \
  REGISTRY_MCP_ADMIN_KEY="$(openssl rand -hex 32)" \
  REGISTRY_MCP_CACHE_PATH=/app/data/cache.sqlite3 \
  RAILWAY_RUN_UID=0
```

**`RAILWAY_RUN_UID=0` is required, not optional** (found on the real first
deploy, 2026-09-04): Railway mounts the volume owned by root, so the
Dockerfile's non-root `app` user cannot open `/app/data/cache.sqlite3` —
every cache read/write and every `log_call` fails silently (by design,
D-006), which shows up as `cached: false` on repeated lookups and
`total_calls: 0` in `/v1/stats`, with `sqlite3.OperationalError: unable to
open database file` in `railway logs`. Setting `RAILWAY_RUN_UID=0` makes
Railway start the container as root; the variable triggers a redeploy on
its own. (The Compose/Caddy path is unaffected — Docker named volumes
inherit the image's `chown`.)

(`railway variable` is the canonical command; `variables`, `vars`, and
`var` are all accepted aliases, so `railway variables set ...` — as you
might expect from `deploy.md`'s Compose `.env` — works identically.)

Replace `you@example.com` with a real address (sent as part of the
User-Agent header on upstream Brønnøysundregistrene requests, D-006/`.env.example`)
and keep the generated `REGISTRY_MCP_ADMIN_KEY` somewhere safe — it's the
shared secret for the admin-only `/stats` and dashboard endpoints. Unlike
the Compose deploy, there is no `REGISTRY_MCP_DOMAIN` variable to set here:
that one only exists to tell Caddy what certificate to request, and Railway
handles TLS itself.

Setting variables triggers a deploy by default (pass `--skip-deploys` to
each `variable set` call if you'd rather batch several changes and deploy
once yourself — then run step 5 manually).

## 5. Redeploy so the volume + variables are live together

```bash
railway up --detach
```

or, to redeploy the same build without rebuilding:

```bash
railway redeploy
```

Confirm the deploy is healthy:

```bash
railway logs --lines 50
```

You should see the `uvicorn` startup lines and the healthcheck path
(`/health`) passing — Railway won't cut over traffic to the new deployment
until `/health` responds successfully (default timeout 300s, configurable
via `healthcheckTimeout` in `railway.toml` or the `RAILWAY_HEALTHCHECK_TIMEOUT_SEC`
variable).

## 6. Get a Railway-provided HTTPS domain

```bash
railway domain
```

This generates and prints a `*.up.railway.app` (or similar) domain with a
free, auto-renewed TLS certificate — no DNS of your own required. Verify:

```bash
curl -sS https://<generated-domain>.up.railway.app/health
```

## 7. Custom domain: `api.<your-domain>`

```bash
railway domain api.<your-domain>
```

This both creates the custom domain on the service and prints the DNS
record(s) you need to add — a **CNAME** for `api` pointing at the target
Railway gives you, plus a **TXT** record for domain verification (Railway
requires both; see `railway domain status` below to re-check them anytime).
At your DNS provider:

- Add a `CNAME` record: host `api`, value = the target Railway printed
  (something like `<something>.up.railway.app` or a Railway-specific
  target — use exactly what the command output shows, don't guess it).
- Add the `TXT` record Railway printed, exactly as shown, for verification.

Then poll status until it's active and the certificate is issued:

```bash
railway domain status api.<your-domain>
```

DNS propagation and certificate issuance can take anywhere from a minute
to a few hours depending on your DNS provider's TTL — same caveat as the
Let's Encrypt step in `deploy.md`.

## 8. Smoke test (adapted from `deploy.md`)

Once `api.<your-domain>` (or the `*.up.railway.app` domain, if you're
skipping the custom domain) resolves and has a valid certificate, no `-k`
/ insecure flags are needed — this is a real, publicly trusted cert, not
Caddy's internal CA:

```bash
curl https://api.<your-domain>/health
curl https://api.<your-domain>/v1/NO/company/923609016
curl https://api.<your-domain>/llms.txt
curl https://api.<your-domain>/server.json
curl https://api.<your-domain>/
curl https://api.<your-domain>/status

# MCP over HTTPS — deploy.md's T13 run found a POST to /mcp (no trailing
# slash) 307-redirects to /mcp/, and some clients don't follow that
# redirect on a POST. `claude mcp add` does follow it, but give the URL
# with a trailing slash anyway to avoid depending on a client's redirect
# handling:
claude mcp add registry-mcp --transport http https://api.<your-domain>/mcp/
claude mcp list      # should show "registry-mcp ... ✔ Connected"
claude mcp remove registry-mcp
```

Persistence check (proves the SQLite file survived on the volume, not just
an in-process cache) — same idea as `deploy.md`'s restart test, done here
with a redeploy since there's no `docker compose restart` on Railway:

```bash
curl https://api.<your-domain>/v1/NO/company/923609016   # note fetched_at
railway redeploy -y
curl https://api.<your-domain>/v1/NO/company/923609016   # cached: true, same fetched_at
```

## 9. Logs and redeploying after future changes

```bash
railway logs                       # stream live deploy logs
railway logs --lines 100           # last 100 lines, no streaming
railway logs --since 1h            # last hour
railway logs --build               # build logs for the most recent build
railway logs --http --status ">=400"   # HTTP access logs, errors only
```

To ship a code change:

```bash
git pull   # or however this checkout gets the new commit
railway up --detach
```

To redeploy the exact same build (e.g. after only a variable/volume
change, or to force a restart):

```bash
railway redeploy
```

`railway redeploy --from-source` pulls and deploys the latest commit from
the connected source instead of re-running the existing build artifact —
useful if the service is connected to a GitHub repo for autodeploys rather
than deployed via `railway up` from a local checkout.

## Troubleshooting

- **Healthcheck failing / deploy stuck "unhealthy"**: `railway logs
  --deployment` on the failing deployment. Most likely cause after this
  setup is a missing `REGISTRY_MCP_CACHE_PATH` directory — the Dockerfile
  creates `/app/data` and the volume mounts over it, so this should already
  work; if it doesn't, `railway volume list` / `railway service` to check
  the volume is actually attached to this service.
- **`database is locked` errors**: someone raised `numReplicas` above 1
  (or added a second region) despite the note in `railway.toml`. Put it
  back to 1.
- **Custom domain never verifies**: `railway domain status api.<your-domain>`
  restates the exact CNAME/TXT values expected — diff them against what's
  actually at your DNS provider (`dig CNAME api.<your-domain>`, `dig TXT
  api.<your-domain>`).
- **Company lookups fail but `/health` is fine**: `/health` doesn't touch
  the cache or upstream registry, so it passing is not proof the volume or
  `REGISTRY_MCP_CONTACT_EMAIL`/`REGISTRY_MCP_CACHE_PATH` variables are set.
  `railway variable list` to confirm they're present on this service.
