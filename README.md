# Botik

Telegram-бот для записи к стоматологу и мастерам (парикмахер, барбер, маникюр) в Армении.

## Для кого

Индивидуальный мастер или врач, ведущий приём и желающий заменить блокнот и звонки удобным Telegram-ботом. Клиент записывается через ссылку, мастер подтверждает — как Airbnb request-to-book, а не календарь-самообслуживание.

## Документация

- [**SPEC.md**](SPEC.md) — полное техзадание, архитектура, схема БД, флоу.
- [**CLAUDE.md**](CLAUDE.md) — правила и контекст для Claude Code (подхватывается автоматически).
- [**BACKLOG.md**](BACKLOG.md) — атомарные задачи для реализации, эпиками.

Перед любой работой — читай SPEC.md.

## Стек

Python 3.12, aiogram 3.x, PostgreSQL 16, Redis 7, Docker Compose. Подробнее — в SPEC.md.

## Быстрый старт (локально)

Предусловия: Docker, Docker Compose, git.

```bash
git clone <repo> botik
cd botik
cp .env.example .env
# В .env укажи BOT_TOKEN (из @BotFather) и ADMIN_TG_IDS (твой tg id, получить у @userinfobot)

docker compose up -d
docker compose exec app alembic upgrade head
docker compose logs -f app
```

Теперь напиши `/start` своему боту в Telegram — начнёт регистрацию мастера.

## Разработка

```bash
# Линтеры
ruff check . && ruff format --check .
mypy src/

# Тесты
pytest tests/ -v --cov=src --cov-report=term-missing

# Миграции
docker compose exec app alembic revision --autogenerate -m "описание"
docker compose exec app alembic upgrade head
```

## Деплой

Прод — VPS (Hetzner Cloud CX22, €4/мес) с Docker Compose. GitHub Actions деплоит на push в main.

```bash
# на VPS (первый раз)
git clone <repo> /opt/botik
cd /opt/botik
cp .env.example .env  # прод-значения
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
docker compose exec app alembic upgrade head
```

Бэкапы БД — автоматически через cron в Backblaze B2. См. `scripts/backup.sh`.

## Roadmap

- v0.1 (MVP, 3 недели) — клиент записывается, мастер подтверждает, расписание, напоминания.
- v0.2 — multi-tenant, несколько мастеров.
- v0.3+ — платежи, СМС, команды в клинике.

Подробнее — в SPEC.md, раздел "Road Map".

## Лицензия

Private. TBD.
