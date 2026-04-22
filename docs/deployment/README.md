# Deployment Runbook

VPS: Hetzner CAX11, Ubuntu 24.04 (ARM64), IP зафиксирован в GitHub Secrets (`SSH_HOST`).

## First-time setup

1. **Create VM in Hetzner Cloud**: CAX11, Ubuntu 24.04, NBG1, привязать свой SSH-ключ.
2. **Verify SSH as root:**
   ```bash
   ssh root@<IP>
   ```
3. **Run bootstrap** (скачивает себя из main):
   ```bash
   curl -fsSL https://raw.githubusercontent.com/VanikVardanyan/grancvi/main/scripts/bootstrap-vps.sh | bash
   ```
   Скрипт идемпотентный: повторный запуск безопасен.
4. **Create `.env`:**
   ```bash
   sudo -u deploy cp /opt/tg-bot/.env.prod.example /opt/tg-bot/.env
   sudo -u deploy nano /opt/tg-bot/.env
   ```
   Заполнить: `BOT_TOKEN`, `ADMIN_TG_IDS`, `SENTRY_DSN`, `POSTGRES_PASSWORD` (`openssl rand -base64 24`), и синхронно обновить `DATABASE_URL`.
5. **First build & start** (под `deploy`):
   ```bash
   sudo -u deploy bash -c 'cd /opt/tg-bot && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build'
   ```
6. **Verify health:**
   ```bash
   sudo -u deploy docker compose -f /opt/tg-bot/docker-compose.yml -f /opt/tg-bot/docker-compose.prod.yml ps
   sudo -u deploy docker inspect tg-bot-app-1 --format='{{.State.Health.Status}}'
   ```
   Через 60–90 секунд статус должен быть `healthy`.

## Deploy key for CI

1. **On your Mac:**
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/grancvi-deploy -N '' -C 'grancvi-deploy'
   ```
2. **Append pub key on VPS** (as root или через любого пользователя с доступом):
   ```bash
   cat ~/.ssh/grancvi-deploy.pub | ssh root@<IP> 'cat >> /home/deploy/.ssh/authorized_keys'
   ```
3. **Verify login as deploy** (должно пустить без пароля):
   ```bash
   ssh -i ~/.ssh/grancvi-deploy deploy@<IP> 'echo ok'
   ```
4. **GitHub repo Settings → Secrets and variables → Actions → New repository secret**:
   - `SSH_HOST` = `<VPS IPv4>`
   - `SSH_USER` = `deploy`
   - `SSH_PRIVATE_KEY` = вывод `cat ~/.ssh/grancvi-deploy` (включая `-----BEGIN OPENSSH PRIVATE KEY-----` и `-----END OPENSSH PRIVATE KEY-----`)

## Secrets reference

### GitHub Actions secrets (repo Settings → Secrets)

| Name | Value |
|---|---|
| `SSH_HOST` | VPS IPv4 |
| `SSH_USER` | `deploy` |
| `SSH_PRIVATE_KEY` | приватный ключ deploy-only, без пароля |

### `/opt/tg-bot/.env` on VPS

| Key | Notes |
|---|---|
| `BOT_TOKEN` | @BotFather |
| `ADMIN_TG_IDS` | Telegram user id мастера (через запятую) |
| `SENTRY_DSN` | sentry.io → Project → Settings → Client Keys |
| `LOG_LEVEL` | `INFO` |
| `POSTGRES_USER` | `botik` |
| `POSTGRES_PASSWORD` | `openssl rand -base64 24` |
| `POSTGRES_DB` | `botik` |
| `DATABASE_URL` | `postgresql+asyncpg://botik:${POSTGRES_PASSWORD}@postgres:5432/botik` |
| `REDIS_URL` | `redis://redis:6379/0` |
| `DEFAULT_TIMEZONE` | `Asia/Yerevan` |

## Day-to-day operations

### Change a secret (e.g. rotate bot token)

```bash
ssh deploy@<IP>
cd /opt/tg-bot
nano .env     # edit
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d   # recreate app only
```

### Rollback last release

**Preferred (via git):**
```bash
# on your Mac
git revert <sha> && git push origin main
# CI auto-deploys the revert in ~2 min
```

**Emergency (directly on VPS):**
```bash
ssh deploy@<IP>
cd /opt/tg-bot
git reset --hard <old-sha>
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```
(Риск: если потом запушишь новый коммит, CI накатит свежий `origin/main` поверх ручного отката.)

### Access psql

```bash
ssh deploy@<IP>
cd /opt/tg-bot
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec postgres psql -U botik botik
```

### Tail logs

```bash
ssh deploy@<IP>
cd /opt/tg-bot
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f --tail 300 app
```

### Restart only app (preserving db/redis state)

```bash
ssh deploy@<IP>
cd /opt/tg-bot
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build app
```

### Check healthcheck

```bash
ssh deploy@<IP>
docker inspect tg-bot-app-1 --format='{{.State.Health.Status}}'
docker inspect tg-bot-app-1 --format='{{json .State.Health}}' | jq
```

## Troubleshooting

**App unhealthy forever:**
- `docker compose logs --tail 300 app` — есть ли Python traceback?
- `docker compose exec app python /app/scripts/healthcheck.py` — что падает? (Обычно — токен неверный или нет интернета.)

**Миграции падают при старте:**
- `docker compose logs app | head -50` — ищи `alembic` ошибки.
- Rollback коммита с миграцией, push.

**Deploy workflow красный:**
- GitHub Actions → Deploy → логи SSH. Обычно: истёк `SSH_PRIVATE_KEY`, сменился IP VPS, или `authorized_keys` на VPS почищен.
- Переключиться на ручной деплой (п. «Rollback» → «Emergency») и расследовать secrets.
