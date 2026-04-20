# CLAUDE.md

Контекст для Claude Code. Полная спецификация — в `SPEC.md`. Читай её перед любой новой задачей.

## Что это за проект

Telegram-бот для записи к стоматологу/парикмахеру на рынке Армении. Два типа пользователей: мастер (врач) и клиент. Клиент присылает заявку → мастер подтверждает (request-to-book). Мастер также может добавлять записи вручную (клиент позвонил).

## Стек (строго следуй)

- Python 3.12, async везде
- **aiogram 3.x** (НЕ 2.x — API другое)
- SQLAlchemy 2.0 async, Alembic для миграций
- PostgreSQL 16, Redis 7
- APScheduler 3.x с Redis jobstore
- pydantic-settings, structlog
- pytest + pytest-asyncio
- ruff + mypy (strict mode)
- Docker Compose для локалки и прода

## Архитектура

Слоистая: `handlers → services → repositories → db/models`.

- **handlers/** — тонкие: достать данные из update'а, позвать service, отформатировать ответ. Никакой бизнес-логики.
- **services/** — use-cases: `BookingService`, `AvailabilityService`, `ReminderService`. Тут вся бизнес-логика.
- **repositories/** — только БД. CRUD + доменные запросы. Возвращают модели SQLAlchemy или dataclass'ы.
- **callback_data/** — typed CallbackData классы, НИКАКИХ строковых f"approve:{id}".
- **keyboards/** — функции, возвращающие InlineKeyboardMarkup / ReplyKeyboardMarkup.
- **fsm/** — классы состояний (State, StatesGroup).

## Критические технические правила

### Работа со временем
- **В БД всё UTC.** `timestamptz`, `datetime.now(timezone.utc)`.
- **На границах** (ввод/вывод пользователю) — конвертация в `Asia/Yerevan` через `zoneinfo.ZoneInfo`.
- **Никогда** не используй naive `datetime.now()` без tz. Никогда.
- Утилиты в `utils/time.py`: `to_yerevan()`, `to_utc()`, `now_utc()`, `now_yerevan()`.

### Race condition на бронировании
Unique partial index на `(master_id, start_at) WHERE status IN ('pending','confirmed')` — фундамент. При создании записи лови `IntegrityError` → выбрасывай `SlotAlreadyTaken` → хэндлер показывает обновлённую сетку слотов.

### FSM
- Storage — **только RedisStorage**, не MemoryStorage. Иначе рестарт = юзеры застряли.
- Каждое состояние FSM — отдельный класс-атрибут в StatesGroup.
- В state.data складывай минимум: ID'шники, не целые объекты.

### Callback data
```python
# ПРАВИЛЬНО
class ApprovalCallback(CallbackData, prefix="appr"):
    action: Literal["confirm", "reject", "alt_time", "history"]
    appointment_id: UUID

# НЕПРАВИЛЬНО
callback_data = f"approve:{appointment.id}"
```

Лимит Telegram — 64 байта на callback_data. UUID занимает 36 символов — нормально, но не кидай туда имена/телефоны.

### Session и транзакции
- Middleware `db.py` даёт новую сессию на каждый update.
- Commit — в конце handler'а, на уровне middleware или в сервисе (выбери один паттерн и держись).
- При исключении — rollback автоматически через async context manager.

### i18n
Все тексты пользователю — через `i18n` middleware, не хардкоди русский. Ключи в `locales/ru/LC_MESSAGES/bot.ftl` и `locales/hy/LC_MESSAGES/bot.ftl`.

### Логи
- structlog + JSON renderer.
- Никаких PII в info (телефоны, имена, сообщения). Только ID'шники.
- В debug можно, но debug не на проде.

### Тесты
- `services/availability.py` — 100% покрытия, это чистая функция.
- Бизнес-сервисы (booking, reminders) — ≥90%.
- Handlers — ≥60% через aiogram test patterns.
- Для БД-тестов — отдельная тестовая БД в `conftest.py`, с fixtures на каждый тест.

## Код-стайл

- **Type hints везде.** mypy --strict должен проходить.
- Используй `from __future__ import annotations`.
- Функции — короткие, одна ответственность.
- Имена — осмысленные. Не `data`, `result`, `item` — а `appointment`, `free_slots`, `master`.
- Docstrings для публичных методов сервисов, не обязательно для приватных.
- Никаких `# type: ignore` без очень веской причины (и коммента рядом).
- Для исключений — кастомные классы в `exceptions.py`, не `raise Exception(...)`.

## Работа с БД

- async engine: `create_async_engine(DATABASE_URL, echo=False)`.
- Dependency injection сессии через aiogram middleware, не через глобальный `session`.
- Для сложных запросов — методы в repository, не пиши raw SQL в handler'ах.
- Миграции — всегда через Alembic: `alembic revision --autogenerate -m "..."` → ревью → `alembic upgrade head`.

## Git workflow

- Коммиты — атомарные, по одной фиче. Сообщение на русском или английском, но стиль один.
- Ветки feature/fix-название. main — защищённая, через PR.
- Перед коммитом — `ruff check . && ruff format . && mypy src/` (pre-commit hook настроен в проекте).

## При неопределённости

- Если не уверен в требовании — открой SPEC.md и найди ответ.
- Если в SPEC.md нет — **спроси**, не додумывай. Плохое предположение дороже уточняющего вопроса.
- Предпочитай простое решение сложному. MVP, не продакшн для 10k мастеров.

## Что НЕ делать

- ❌ Не добавляй зависимости без обсуждения. Стек зафиксирован.
- ❌ Не пиши код для фич, которых нет в текущей задаче (платежи, СМС, веб-дашборд).
- ❌ Не используй глобальное состояние. Всё через DI.
- ❌ Не комменти код — удаляй. Комментарии — только про "почему", не про "что".
- ❌ Не копируй одинаковую логику в разные handler'ы — выноси в service.
