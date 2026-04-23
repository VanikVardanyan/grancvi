# TMA Deployment Runbook (Epic 11)

Adding API + app-launcher bot + static web frontend on top of the
existing `@GrancviBot` deployment. **Does not** modify the existing
`app` container.

## DNS (done)

A records on `jampord.am`:
- `api.jampord.am` → `94.130.149.91`
- `app.jampord.am` → `94.130.149.91`

Verify: `dig +short api.jampord.am` → `94.130.149.91`.

## One-time host setup (on VPS, run as `root`)

### 1. Install nginx + certbot

```bash
apt update
apt install -y nginx certbot python3-certbot-nginx
systemctl enable --now nginx
```

### 2. Drop the two nginx server blocks

```bash
install -o root -g root -m 0644 \
    /opt/tg-bot/deploy/nginx/api.conf \
    /etc/nginx/sites-available/api.jampord.am

install -o root -g root -m 0644 \
    /opt/tg-bot/deploy/nginx/app.conf \
    /etc/nginx/sites-available/app.jampord.am

ln -s /etc/nginx/sites-available/api.jampord.am /etc/nginx/sites-enabled/
ln -s /etc/nginx/sites-available/app.jampord.am /etc/nginx/sites-enabled/

# Placeholder static until the React build is deployed:
mkdir -p /var/www/jampord-app
install -o root -g root -m 0644 \
    /opt/tg-bot/deploy/web-dist-placeholder/index.html \
    /var/www/jampord-app/index.html
chown -R www-data:www-data /var/www/jampord-app

nginx -t
systemctl reload nginx
```

### 3. Issue SSL certificates

```bash
certbot --nginx -d api.jampord.am -d app.jampord.am \
    --non-interactive --agree-tos -m <your-email>
```

Certbot rewrites the server blocks above to add the HTTPS listener and
redirect HTTP→HTTPS. Cert auto-renewal is installed as a systemd timer
(`systemctl list-timers | grep certbot`).

Verify:
- `curl -sI https://app.jampord.am` → 200 OK with HTML
- `curl -s https://api.jampord.am/v1/health` → (after Step 4 deploys) `{"status":"ok"}`

## Container deployment

The following happens during each `docker compose … up -d` (including
the initial one that brings up the new services):

### 4. Bring up new containers without touching `app`

From `/opt/tg-bot` on VPS as `deploy`:

```bash
cd /opt/tg-bot
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d api app_bot
```

**Not** `--build` in the normal path — CI builds the image. But on the
very first run, or after `Dockerfile` changes, use `--build`.

Compose only recreates services whose definition changed. The existing
`app` container stays running, unaffected.

Verify:
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
# api         Up (healthy)
# app_bot     Up
# app         Up (healthy)  ← unchanged
curl http://localhost:8000/v1/health   # {"status":"ok"}
```

### 5. Point `@grancviWebBot` at the TMA URL (one-time, in BotFather)

```
/mybots → @grancviWebBot → Configure Mini App → Set url → https://app.jampord.am
```

Also set the bot button that opens the app from the chat:

```
/mybots → @grancviWebBot → Menu Button → Configure menu button
  text: "Записаться"
  url: https://app.jampord.am
```

## Frontend deploy (until CI is set up)

The React app lives in a sibling repo `grancvi-web`. Local build + scp:

```bash
# in grancvi-web/
pnpm build
scp -i ~/.ssh/grancvi-deploy -r dist/* \
    deploy@94.130.149.91:/var/www/jampord-app/
```

Or push to a branch and run a simple SSH deploy action (later task).

## Rollback

If something breaks only the new services:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml stop api app_bot
# existing app keeps running
```

To remove the new services entirely, revert the compose files and
`docker compose … up -d` — compose prunes the removed services.

Nginx blocks disable via:

```bash
rm /etc/nginx/sites-enabled/api.jampord.am /etc/nginx/sites-enabled/app.jampord.am
systemctl reload nginx
```
