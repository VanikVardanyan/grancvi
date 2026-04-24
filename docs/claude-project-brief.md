# tg-bot — контекст для Claude Project

Этот документ — брифинг для Claude.ai, чтобы он знал проект без дополнительных вопросов. Добавить его в Project knowledge на claude.ai/projects.

---

## Что за проект

Telegram-бот для записи к мастеру (стоматолог, парикмахер) на рынке Армении. Два типа пользователей:
- **Мастер** — врач/парикмахер. Один мастер на инстанс бота (MVP).
- **Клиент** — любой пользователь Telegram.

Флоу: клиент выбирает услугу и слот → заявка (`pending`) → мастер подтверждает/отклоняет → подтверждённая запись (`confirmed`). Мастер также может добавить запись вручную (клиент позвонил).

Репа: `github.com/VanikVardanyan/grancvi` (main защищён auto-deploy'ем).

## Текущее состояние (на 2026-04-22)

**Закрыто:** Эпики 1–7 (фундамент → MVP функционал) + Эпик 8.2 (production-деплой).

**В проде:**
- VPS: Hetzner CAX11, Ubuntu 24.04 ARM64, IP `94.130.149.91`.
- Бот живёт в docker compose (postgres 16 + redis 7 + app).
- Auto-deploy: push в `main` → GitHub Actions CI (ruff + format + mypy + pytest) → SSH на VPS → `git reset --hard origin/main && docker compose up -d --build`.
- Sentry подключен (DSN в `/opt/tg-bot/.env` на VPS).
- Runbook: `docs/deployment/README.md`.
- Последний тег: `v0.8.2-epic-8-2-deploy`.

**Следующий эпик:** 8.3 — бэкапы. `BACKLOG.md` — источник правды по scope.

## Стек (не менять без обсуждения)

- **Python 3.12**, async везде.
- **aiogram 3.x** (не 2.x — API другой).
- **SQLAlchemy 2.0** async + **Alembic**.
- **PostgreSQL 16**, **Redis 7**.
- **APScheduler 3.x** с `MemoryJobStore` (см. ниже почему не Redis jobstore).
- `pydantic-settings`, `structlog`.
- `pytest` + `pytest-asyncio`.
- `ruff` (lint + format), `mypy --strict`.
- `uv` для пакетов (lock файл: `uv.lock`).
- Docker Compose для локалки и прода.

## Архитектура

Слоистая:

```
handlers → services → repositories → db/models
```

- **`handlers/`** — тонкие. Достать данные из update'а, позвать сервис, отформатировать ответ. НЕТ бизнес-логики.
- **`services/`** — use-cases (`BookingService`, `AvailabilityService`, `ReminderService`). Вся бизнес-логика.
- **`repositories/`** — только БД. CRUD + доменные запросы. Возвращают SQLAlchemy-модели или dataclass'ы.
- **`callback_data/`** — **typed** `CallbackData` классы, НИКОГДА строковые `f"approve:{id}"`.
- **`keyboards/`** — функции, возвращающие `InlineKeyboardMarkup` / `ReplyKeyboardMarkup`.
- **`fsm/`** — `StatesGroup` классы состояний.
- **`strings.py`** — i18n (`RU` + `HY` dicts), выбор языка по `user.language_code` из middleware.

## Критические технические правила

### Время
- **В БД всё UTC.** Колонки `timestamptz`, `datetime.now(timezone.utc)`.
- **На границах** (ввод/вывод пользователю) конвертация в `Asia/Yerevan` через `zoneinfo.ZoneInfo`.
- Naive `datetime.now()` без tz — **запрещено**.
- Утилиты в `utils/time.py`: `to_yerevan()`, `to_utc()`, `now_utc()`, `now_yerevan()`.

### Race condition на бронировании
Unique partial index `(master_id, start_at) WHERE status IN ('pending','confirmed')`. При `INSERT` лови `IntegrityError` → выкидывай доменный `SlotAlreadyTaken` → handler рендерит обновлённую сетку.

### FSM
- Storage **только `RedisStorage`**. Не `MemoryStorage` — иначе рестарт = юзеры застряли.
- Каждое состояние — атрибут в `StatesGroup`.
- В `state.data` храни только ID'шники, не целые объекты.

### Callback data
```python
# ПРАВИЛЬНО
class ApprovalCallback(CallbackData, prefix="appr"):
    action: Literal["confirm", "reject", "alt_time", "history"]
    appointment_id: UUID
```
Лимит Telegram — 64 байта. UUID 36 символов укладывается, но не клади туда имена/телефоны.

### Сессии БД
- Middleware `db.py` даёт новую `AsyncSession` на каждый update.
- Commit — в конце handler'а или в сервисе. Один паттерн, без миксов.
- Исключение → автоматический rollback через async context manager.

### APScheduler
- `build_scheduler()` возвращает `AsyncIOScheduler(timezone="UTC")` с **default MemoryJobStore**.
- RedisJobStore НЕ используем: наши job'ы — cron, они регистрируются при старте процесса; плюс aiogram `Bot` + `async_sessionmaker` не picklable → `ValueError: This Job cannot be serialized` при `add_job`.

### i18n
Все тексты пользователю — через `strings.t(key, lang)` (или эквивалент в middleware). Не хардкоди русский. Ключи в `RU` и `HY` словарях.

### Логи
- `structlog` + JSON renderer на проде.
- **Никаких PII в info** (телефоны, имена, тексты сообщений). Только ID.
- В debug — можно, но debug не на проде.

### Тесты
- `AvailabilityService` — 100% покрытия (чистая функция).
- `BookingService`, `ReminderService` — ≥90%.
- Handlers — ≥60% через aiogram test patterns.
- Тестовая БД — `botik_test`, сбрасывается между тестами. Admin engine в `tests/conftest.py:29` подключается к БД `botik` для `DROP/CREATE DATABASE botik_test` — **CI service container должен иметь `POSTGRES_DB: botik`**, не `botik_test`.

## Код-стайл

- Type hints везде. `mypy --strict` обязан проходить.
- `from __future__ import annotations` в каждом файле.
- Функции короткие, одна ответственность.
- Имена осмысленные: не `data`/`result`/`item`, а `appointment`/`free_slots`/`master`.
- Docstrings для публичных методов сервисов, не для приватных.
- `# type: ignore` — только с комментарием-обоснованием.
- Кастомные исключения в `src/exceptions.py`, не `raise Exception(...)`.

## Репа: важные директории

```
src/
├── main.py              # entrypoint (aiogram polling)
├── config.py            # pydantic-settings
├── db/                  # engine, models, middleware
├── handlers/            # тонкие обработчики
├── services/            # бизнес-логика
├── repositories/        # CRUD
├── fsm/                 # состояния
├── keyboards/           # кнопочки
├── callback_data/       # typed CallbackData
├── strings.py           # i18n RU + HY
└── utils/time.py        # UTC/Yerevan конвертеры

migrations/              # alembic
tests/                   # pytest
scripts/
├── bootstrap-vps.sh     # идемпотентный bootstrap Ubuntu 24.04
└── healthcheck.py       # для Docker HEALTHCHECK (stdlib-only)

docs/
├── deployment/README.md # operational runbook
└── superpowers/         # specs + plans

.github/workflows/
├── ci.yml               # lint + format + mypy + pytest
└── deploy.yml           # workflow_run → SSH deploy

docker-compose.yml       # base
docker-compose.prod.yml  # prod override (ports !reset [], restart always, healthcheck, log rotation)
Dockerfile               # alembic upgrade head + polling
```

## Workflow

### Локалка
```bash
# поднять стек
docker compose up -d postgres redis
uv sync
uv run alembic upgrade head
uv run python -m src.main
```

### Перед коммитом
```bash
uv run ruff check . && uv run ruff format . && uv run mypy src/ && uv run pytest -q
```
(pre-commit hook настроен)

### Деплой
Просто `git push origin main`. Остальное — GitHub Actions.

### Откат
```bash
git revert <sha> && git push origin main   # CI auto-deploys revert через ~2 мин
```
Ручной emergency-rollback — в `docs/deployment/README.md`.

### Логи с VPS
```bash
ssh deploy@94.130.149.91 'cd /opt/tg-bot && docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f --tail 300 app'
```

## Секреты

### GitHub Actions (repo Settings → Secrets)
- `SSH_HOST` = `94.130.149.91`
- `SSH_USER` = `deploy`
- `SSH_PRIVATE_KEY` = deploy-only ed25519 без пароля

### `/opt/tg-bot/.env` на VPS
- `BOT_TOKEN` — от @BotFather
- `ADMIN_TG_IDS` — telegram id мастера (через запятую)
- `SENTRY_DSN` — sentry.io
- `POSTGRES_PASSWORD` — `openssl rand -base64 24`, синхронно с `DATABASE_URL`
- `DATABASE_URL` — `postgresql+asyncpg://botik:${POSTGRES_PASSWORD}@postgres:5432/botik`
- `REDIS_URL` — `redis://redis:6379/0`
- `DEFAULT_TIMEZONE` — `Asia/Yerevan`
- `LOG_LEVEL` — `INFO`

## Что НЕ делать

- ❌ Не добавлять зависимости без обсуждения. Стек зафиксирован.
- ❌ Не писать код для фич, которых нет в текущей задаче (платежи, СМС, веб-дашборд — не сейчас).
- ❌ Не использовать глобальное состояние. Всё через DI/middleware.
- ❌ Не комментировать код — удалять. Комментарии только про "почему", не "что".
- ❌ Не копировать логику в handler'ах — выносить в сервис.
- ❌ Не писать raw SQL в handler'ах — только через repository.
- ❌ Не коммитить `.env`, `.env.prod`, приватные ключи.
- ❌ Не делать `git push --force` в main.
- ❌ Не ломать invariant "CI service container использует POSTGRES_DB=botik" — иначе 321 тест упадёт на CI.
- ❌ Не экспонировать порты postgres/redis в проде — в `docker-compose.prod.yml` должен быть `ports: !reset []`, не `ports: []` (plain `[]` мержится, не перезаписывает).

## Стиль работы с Claude в этом проекте

- Общение на русском.
- Если не уверен в требовании — открой `SPEC.md` или `BACKLOG.md` и найди ответ. Если нет ответа — **спроси**, не додумывай.
- Simple > complex. MVP, не продакшн для 10k мастеров.
- При handoff на план — выбирается Subagent-Driven Development (без повторного вопроса).

## Основные скиллы superpowers в работе

Проект ведётся через цикл:
1. `brainstorming` → spec в `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`
2. `writing-plans` → план в `docs/superpowers/plans/YYYY-MM-DD-<topic>.md`
3. `subagent-driven-development` → исполнение по тасок-за-таской с двухстадийным ревью
