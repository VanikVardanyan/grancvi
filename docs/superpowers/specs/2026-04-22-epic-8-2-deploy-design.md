# Epic 8.2 — Docker Production Deployment + GitHub Actions CI (Design Spec)

**Status:** design  
**Date:** 2026-04-22  
**Depends on:** Epic 7 (complete)  
**Followed by:** Epic 8.3 (backups)

## Goal

Довести проект до состояния «push в main = через 2–3 минуты обновлённый бот работает на прод-VPS», с минимальной ручной работой и правильным failure-mode.

## Non-goals

- Домен / TLS / reverse-proxy (бот на polling, не нужен).
- Multi-instance HA, load-balancer, shared jobstore для APScheduler.
- Container registry (GHCR) — собираем образ на VPS.
- Backup strategy — отдельный Эпик 8.3.
- External uptime monitoring (UptimeRobot и т.п.) — добавим когда появятся пользователи.
- Infrastructure-as-code (Terraform) — для одной VM избыточно.

## Infrastructure baseline

| Компонент | Значение |
|---|---|
| Провайдер | Hetzner Cloud |
| Сервер | CAX11 (2 vCPU ARM64 Ampere, 4 GB RAM, 40 GB SSD) |
| Локация | NBG1 (Nuremberg, DE) |
| ОС | Ubuntu 24.04.3 LTS (aarch64) |
| Публичный IPv4 | `94.130.149.91` |
| SSH (root) | ed25519/rsa от `vanik@Vaniks-MacBook-Pro.local` |
| Стоимость | €4.39/мес (CAX11 + IPv4; без backups) |

## Architecture

```
Mac (dev)            GitHub (VanikVardanyan/grancvi)       Hetzner CAX11
   │                         │                                │
   │ git push main           │                                │
   ├────────────────────────▶│                                │
   │                         │ ci.yml: ruff+mypy+pytest       │
   │                         │ deploy.yml: ssh → pull → build │
   │                         ├───────────────────────────────▶│
   │                         │                                │ /opt/tg-bot
   │                         │                                │  └─ docker compose
   │                         │                                │     ├─ app (polling + entrypoint alembic)
   │                         │                                │     ├─ postgres (internal only)
   │                         │                                │     └─ redis (internal only)
   │                         │                                │
   │                         │                                ├─ UFW: 22/tcp only
   │                         │                                ├─ Healthcheck: curl api.telegram.org/getMe
   │                         │                                └─ Sentry → alerts by email
```

**Key properties:**
- Polling bot → нет входящего HTTP → нет nginx / TLS / домена.
- `.env` хранится **только на VPS**, GitHub не видит секретов бота.
- DB-миграции применяются entrypoint'ом контейнера при каждом старте → schema всегда in-sync.
- Docker `HEALTHCHECK` пингает `api.telegram.org/bot<token>/getMe` → `restart: on-failure` оживляет зависший polling-task.
- UFW впускает только SSH. Postgres и Redis — в docker network, наружу не торчат.
- Sentry ловит необработанные исключения → email.

## Design decisions (with rationale)

1. **Build on VPS (не GHCR).** Solo-dev, деплой раз в неделю, 5-минутная сборка на ARM приемлема. GHCR добавляет auth flow + multi-arch build в CI — ненужная сложность. Миграция на GHCR — тривиальна позже.
2. **`.env` только на VPS, не в GitHub Secrets.** Секреты не покидают prod-машину. GitHub compromise не утекает bot token. Минус (ручная смена через SSH) — операция раз в год.
3. **Push в main = авто-деплой.** Solo-dev, каждый коммит сознателен. `ci.yml` защищает main. Rollback через `git revert` + push.
4. **Миграции в entrypoint (не отдельным сервисом).** Один мастер на бот → low concurrency. Стандартный паттерн. Если миграция падает — бот не стартует (правильный failure mode).
5. **Docker HEALTHCHECK, не aiohttp-сервер.** Нет нужды в exposed HTTP порте. External monitoring отложен до появления пользователей.
6. **Shell-скрипт для bootstrap (не Ansible).** Одна машина, один раз. Bash проще Ansible-vault для solo-dev. Идемпотентный.
7. **Sentry через condition `if settings.sentry_dsn`.** На локалке пусто → sentry молчит. На проде в `.env` → активен.
8. **Deploy-юзер `deploy` (не root).** Стандарт безопасности. `deploy` в `docker` группе → может `docker compose up` без sudo. CI SSH'ится под `deploy`, не root.
9. **Отдельный deploy-ключ для CI.** Приватный ключ в GitHub Secrets, без пароля. Pub на VPS в `~deploy/.ssh/authorized_keys`. Не смешивается с личным ключом.

## File structure

### Create

- `scripts/bootstrap-vps.sh` — идемпотентный первичный setup VPS.
- `scripts/healthcheck.py` — Python-скрипт для Docker HEALTHCHECK (`getMe` ping).
- `docker-compose.prod.yml` — override прод-режима.
- `.env.prod.example` — чеклист секретов на VPS.
- `.github/workflows/ci.yml` — PR + push-гейты (ruff, format, mypy, pytest).
- `.github/workflows/deploy.yml` — SSH-деплой после зелёного ci.yml на main.
- `docs/deployment/README.md` — operational runbook.

### Modify

- `Dockerfile` — добавить `HEALTHCHECK`, сменить `CMD` на `sh -c "alembic upgrade head && exec python -m src.main"`, скопировать `scripts/healthcheck.py`.
- `src/main.py` — `sentry_sdk.init()` если `settings.sentry_dsn`.
- `pyproject.toml` — `sentry-sdk>=2.0` в runtime dependencies (httpx не нужен, healthcheck на stdlib `urllib`).
- `.env.example` — добавить `POSTGRES_USER/PASSWORD/DB` (сейчас в compose захардкожены как `botik`).

### Not touched

- `docker-compose.yml` (base) — остаётся для локальной разработки. Прод = base + prod override через `-f`.
- Бизнес-логика в `src/` — эпик про инфраструктуру, не про фичи.

## Detailed specs

### `scripts/bootstrap-vps.sh`

Запускается под `root` на свежей VM.

```bash
#!/usr/bin/env bash
set -euo pipefail

# Step 1: apt update + essentials
apt-get update
apt-get upgrade -y
apt-get install -y ca-certificates curl gnupg git ufw

# Step 2: Docker Engine + compose plugin (official repo)
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${VERSION_CODENAME}") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Step 3: deploy user + docker group + SSH keys
id -u deploy >/dev/null 2>&1 || useradd -m -s /bin/bash deploy
usermod -aG docker deploy
mkdir -p /home/deploy/.ssh
cp /root/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys

# Step 4: UFW — only SSH
ufw allow 22/tcp
ufw default deny incoming
ufw default allow outgoing
ufw --force enable

# Step 5: harden sshd
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
systemctl restart ssh

# Step 6: clone repo under deploy
mkdir -p /opt/tg-bot
chown deploy:deploy /opt/tg-bot
sudo -u deploy git clone https://github.com/VanikVardanyan/grancvi.git /opt/tg-bot || true
# `|| true` — идемпотентность: если уже склонирован, git clone упадёт, но это ок.

echo ""
echo "==============================================="
echo " Bootstrap complete."
echo " Next steps:"
echo "   1. Copy .env template:"
echo "      sudo -u deploy cp /opt/tg-bot/.env.prod.example /opt/tg-bot/.env"
echo "   2. Edit /opt/tg-bot/.env, fill BOT_TOKEN/SENTRY_DSN/etc."
echo "   3. First build & start:"
echo "      cd /opt/tg-bot && sudo -u deploy docker compose \\"
echo "        -f docker-compose.yml -f docker-compose.prod.yml up -d --build"
echo "   4. Add deploy SSH key to ~deploy/.ssh/authorized_keys"
echo "      (generate locally, paste pub; put priv in GitHub Secrets)"
echo "==============================================="
```

**Идемпотентность:** повторный запуск безопасен — `apt install` no-op на уже установленных, `useradd` skip при существующем юзере, `ufw allow` допускает дубликаты, `git clone || true` не падает, sed меняет нужные строки в уже изменённом sshd_config без побочных эффектов.

### `scripts/healthcheck.py`

```python
"""Exits 0 if bot can reach Telegram API, 1 otherwise.

Called by Docker HEALTHCHECK every 60s.
Uses stdlib only to avoid adding an HTTP-client dependency.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("BOT_TOKEN not set", file=sys.stderr)
        return 1
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        with urllib.request.urlopen(url, timeout=8.0) as resp:
            body = resp.read()
    except urllib.error.URLError as exc:
        print(f"getMe failed: {exc}", file=sys.stderr)
        return 1
    except TimeoutError as exc:
        print(f"getMe timed out: {exc}", file=sys.stderr)
        return 1

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        print(f"getMe response not JSON: {exc}", file=sys.stderr)
        return 1

    if not data.get("ok"):
        print(f"Telegram returned ok=false: {data}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Свойства:** если Telegram API недоступен дольше 3 consecutive checks → контейнер помечается `unhealthy` → `restart: on-failure` перезапускает.

### `docker-compose.prod.yml`

```yaml
services:
  postgres:
    ports: []  # strip dev expose
    restart: always
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  redis:
    ports: []
    restart: always
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  app:
    restart: always
    healthcheck:
      test: ["CMD", "python", "/app/scripts/healthcheck.py"]
      interval: 60s
      timeout: 10s
      retries: 3
      start_period: 30s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

Запускается командой: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`.

### `Dockerfile` — changes

```dockerfile
# ... existing multi-stage build ...

# Add script copy (healthcheck) near source copy
COPY scripts ./scripts

# Change CMD
CMD ["sh", "-c", "alembic upgrade head && exec python -m src.main"]

# Add healthcheck (complementary to compose.prod.yml, useful for standalone docker run)
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python /app/scripts/healthcheck.py || exit 1
```

### `src/main.py` — changes

В начале `main()`, после `configure_logging()`:

```python
async def main() -> None:
    configure_logging()
    if settings.sentry_dsn:
        import sentry_sdk
        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.0)
    # ... rest unchanged
```

### `pyproject.toml` — changes

```toml
[project]
dependencies = [
    # ... existing ...
    "sentry-sdk>=2.0",
]
```

### `.env.prod.example`

```bash
# Bot
BOT_TOKEN=

# Admin
ADMIN_TG_IDS=

# Observability
SENTRY_DSN=
LOG_LEVEL=INFO

# Database
POSTGRES_USER=botik
POSTGRES_PASSWORD=           # generate: openssl rand -base64 24
POSTGRES_DB=botik
DATABASE_URL=postgresql+asyncpg://botik:${POSTGRES_PASSWORD}@postgres:5432/botik

# Redis
REDIS_URL=redis://redis:6379/0

# Locale
DEFAULT_TIMEZONE=Asia/Yerevan
```

### `.github/workflows/ci.yml`

```yaml
name: ci

on:
  pull_request:
  push:
    branches: [main]

jobs:
  gates:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: botik
          POSTGRES_PASSWORD: botik
          POSTGRES_DB: botik_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd="pg_isready -U botik"
          --health-interval=3s
          --health-timeout=3s
          --health-retries=20
      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
        options: >-
          --health-cmd="redis-cli ping"
          --health-interval=3s
          --health-timeout=3s
          --health-retries=20
    env:
      DATABASE_URL: postgresql+asyncpg://botik:botik@localhost:5432/botik_test
      REDIS_URL: redis://localhost:6379/0
      BOT_TOKEN: dummy
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          version: "0.5.4"
      - name: Set up Python
        run: uv python install 3.12
      - name: Sync deps
        run: uv sync --frozen
      - name: Ruff
        run: uv run ruff check .
      - name: Format check
        run: uv run ruff format --check .
      - name: Mypy
        run: uv run mypy src/
      - name: Pytest
        run: uv run pytest -q
```

### `.github/workflows/deploy.yml`

```yaml
name: deploy

on:
  workflow_run:
    workflows: [ci]
    branches: [main]
    types: [completed]

jobs:
  deploy:
    if: ${{ github.event.workflow_run.conclusion == 'success' }}
    runs-on: ubuntu-latest
    steps:
      - uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.SSH_HOST }}
          username: ${{ secrets.SSH_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            set -euo pipefail
            cd /opt/tg-bot
            git fetch --all --tags --prune
            git reset --hard origin/main
            docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
            docker image prune -f
```

### `docs/deployment/README.md`

Разделы:
- **Первый запуск** — bootstrap runbook (создать VM в Hetzner → `ssh root@IP` → скопировать/выполнить `bootstrap-vps.sh` → заполнить `.env` → первый `docker compose up -d --build`).
- **Настройка CI-ключа** — сгенерировать ed25519 без пароля, положить pub на VPS, вставить priv в GitHub Secrets.
- **Что лежит в GitHub Secrets** — `SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY` (только эти три).
- **Что лежит в `.env` на VPS** — перечень по `.env.prod.example`.
- **Смена секрета** — SSH на VPS, `nano /opt/tg-bot/.env`, `docker compose -f ... up -d` (только app перезапустится).
- **Откат** — через git (`git revert <sha> && git push`) или прямо на VPS (`git reset --hard <sha> && docker compose ... up -d --build`).
- **Доступ к psql** — `ssh deploy@IP && cd /opt/tg-bot && docker compose exec postgres psql -U botik botik`.
- **Логи** — `docker compose logs -f app` (только последние 300 строк: `--tail 300`).
- **Перезапуск только app** — `docker compose -f ... up -d --build app`.

## Secrets summary

### GitHub Actions (repo Settings → Secrets and variables → Actions)

| Secret | Value |
|---|---|
| `SSH_HOST` | `94.130.149.91` |
| `SSH_USER` | `deploy` |
| `SSH_PRIVATE_KEY` | Приватный ключ deploy-only ed25519 (без пароля) |

### VPS `/opt/tg-bot/.env`

| Key | Source |
|---|---|
| `BOT_TOKEN` | @BotFather |
| `ADMIN_TG_IDS` | Telegram user id мастера |
| `SENTRY_DSN` | sentry.io → Project → Settings → Client Keys |
| `POSTGRES_PASSWORD` | `openssl rand -base64 24` при первом setup |
| `POSTGRES_USER`, `POSTGRES_DB`, `DATABASE_URL`, `REDIS_URL`, `LOG_LEVEL`, `DEFAULT_TIMEZONE` | Из `.env.prod.example`, без изменений |

## Acceptance criteria

1. **CI работает:** PR в main триггерит `ci.yml` со всеми четырьмя гейтами (ruff, format, mypy, pytest). Ни один гейт не блокирует ложно.
2. **Автодеплой работает:** push в main → ~2 минуты спустя `docker compose ps` на VPS показывает обновлённую ревизию (`git rev-parse HEAD` на VPS = локальный HEAD).
3. **Security boundary:** `nmap -p 1-10000 94.130.149.91` снаружи показывает только `22/tcp open` — Postgres/Redis невидимы.
4. **SSH под паролем заблокирован:** `ssh -o PreferredAuthentications=password root@IP` → `Permission denied`.
5. **Root SSH заблокирован для паролей** (только ключ): `PermitRootLogin prohibit-password`.
6. **Healthcheck работает:** `docker inspect tg-bot-app-1 --format='{{.State.Health.Status}}'` через 90 секунд после старта возвращает `healthy`.
7. **Sentry алертит:** если сломать код (например `raise RuntimeError` в тестовом хэндлере) → в sentry.io появляется событие; email приходит.
8. **Миграции применяются при старте:** `docker compose up -d` на свежей БД создаёт схему (виден `Running upgrade` в логах app).
9. **Runbook полон:** инженер, не знающий проект, по `docs/deployment/README.md` может: первый setup, откатить релиз, сменить токен бота, залогиниться в psql.
10. **Rollback через `git revert`:** `git revert HEAD && git push origin main` → CI докатывает старую ревизию за ~2 минуты, бот не теряет данных.

## Out-of-scope for this epic

- **pg_dump → B2** — Epic 8.3.
- **External uptime monitoring** — добавим когда появятся реальные пользователи (UptimeRobot free tier на 5 чеков).
- **Fail2ban** — UFW + no-password-ssh достаточно; fail2ban добавит сложности.
- **Automatic security updates** (`unattended-upgrades`) — включим ручной командой в runbook, но автоматизация авто-reboot'а при kernel update — out of scope.
- **Reverse proxy** — для polling-бота не нужен. Если в будущем добавим webhook-mode или admin-UI — отдельный эпик.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Docker build падает на ARM из-за пакета без aarch64-wheel | Весь текущий стек проверен: asyncpg, sentry-sdk имеют aarch64 wheels. Fallback — собрать в CI x86 и pull (GHCR миграция, не в этом эпике). |
| Миграция alembic падает → бот не стартует | Правильный failure mode. Sentry видит, что контейнер ребутится. Rollback через `git revert migration-commit`. |
| Telegram rate-limit на `getMe` (healthcheck raz v minutu) | getMe не rate-limited отдельно — лимит общий на все методы бота. 1 rps от healthcheck пренебрежимо. |
| SSH-ключ CI утекает из GitHub Secrets | Deploy-only ключ: max повреждение — злоумышленник пушит свой код. Ротация: создать новый ключ, заменить в Secrets + authorized_keys. |
| Postgres volume потерян при пересоздании VM | Volume `pg_data` переживает `docker compose down`, но не пересоздание VM. Эпик 8.3 (pg_dump → B2) — реальный disaster recovery. |
| Первый push → кольцевой эффект: ci.yml включает ruff/mypy, но код может не пройти из-за старых правил | Перед первым push прогнать гейты локально (`source .venv/bin/activate && ruff check . && ruff format --check . && mypy src/ && pytest`). Если красные — фиксим до push. |

## Implementation order (для плана)

1. Написать `scripts/healthcheck.py` + тест на сбой (отсутствующий токен → exit 1).
2. Обновить `pyproject.toml` + `uv.lock` (sentry-sdk).
3. Обновить `src/main.py` (Sentry conditional init) + тесты.
4. Обновить `Dockerfile` (entrypoint + HEALTHCHECK + COPY scripts).
5. Написать `docker-compose.prod.yml`.
6. Написать `.env.prod.example` + обновить `.env.example`.
7. Написать `scripts/bootstrap-vps.sh` + smoke-проверить локально в Docker-sandbox (опционально).
8. Написать `docs/deployment/README.md`.
9. Написать `.github/workflows/ci.yml` + локально прогнать `act` (опционально) или проверить синтаксис.
10. Написать `.github/workflows/deploy.yml`.
11. **Manual step — user:** запустить bootstrap на VPS; создать Sentry-проект; получить DSN; заполнить `.env`; первый build+up.
12. **Manual step — user:** сгенерировать deploy-key, положить pub на VPS, priv в GitHub Secrets; добавить `SSH_HOST`/`SSH_USER`.
13. `git push origin main` — первый автодеплой. Ждать ~2 мин, проверять логи.
14. Smoke-тест: все acceptance criteria из раздела выше.
15. Тег `v0.8.2-epic-8-2-deploy`.
