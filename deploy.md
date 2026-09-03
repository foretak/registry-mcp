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
curl -sS http://localhost:8080/health   # direct to the api container, from inside the host
curl -sS https://<your-domain>/health   # through Caddy, from anywhere
```

Both should return a healthy response. If the HTTPS check fails, give
Caddy a minute to finish the ACME challenge and check its logs (below).

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
