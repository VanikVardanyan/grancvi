# Changelog

## v0.9.0-epic-9-multi-master — 2026-04-22

Мульти-мастер платформа: инвайты, каталог, модерация.

### Added
- **Invite-based регистрация мастеров.** Admin или действующий мастер создаёт инвайт (код `XXXX-YYYY`, TTL 7 дней). Кандидат открывает `t.me/<bot>?start=invite_<code>` и проходит FSM-регистрацию: язык → имя → телефон → специальность → slug. Slug валидируется (3–32 символа, латиница/цифры/дефис, резервные слова запрещены), автогенерится из транслита имени.
- **Клиентский deep-link.** `t.me/<bot>?start=master_<slug>` открывает карточку конкретного мастера и booking flow. Недействительный slug или заблокированный мастер → fallback в каталог.
- **Публичный каталог мастеров.** `/start` без payload показывает всех активных публичных мастеров, отсортированных по дате регистрации.
- **Админ-панель.** Меню с кнопками + слэш-команды: `/masters` (список), `/master <slug>` (карточка), `/stats` (статистика), `/invites` (все инвайты), `/block <slug>`, `/unblock <slug>`.
- **Soft-block модерация.** `/block` ставит `blocked_at`, все pending-записи переводит в `rejected`, клиенты получают уведомление. Confirmed записи сохраняются (мастер должен выполнить обязательства). `BlockedMasterGuardMiddleware` блокирует все действия мастера, показывая баннер; `/start` и `/cancel` разрешены.
- **Scoped bot commands.** `setup_bot_commands` регистрирует три scope'а: default (клиенты), chat (мастера + админы). Админы видят расширенный набор с `/masters`, `/stats`, `/block` и т.п.
- **Button-first UX.** Каждая новая команда имеет кнопочный путь (per user feedback memory). Button-dispatch тесты покрывают меню admin, master settings, profile editor.

### Changed
- **UserMiddleware multi-master safe.** Убран поиск Client по tg_id (крэшил `MultipleResultsFound` когда один tg_id — клиент у нескольких мастеров). Клиенты теперь резолвятся внутри BookingService per-appointment.
- **Aiogram 3.x routing propagation.** Admin/start и master/start теперь используют Filter классы (`IsAdminNoMaster`, `HasInviteOrMaster`) вместо silent-return в теле хендлера. В aiogram 3.x matched handler потребляет update даже при `return None`, поэтому fallback на следующий роутер требует filter-gating.

### Database
- **Миграция 0003.** `masters.slug` (unique), `masters.specialty_text`, `masters.blocked_at`, `masters.is_public`. Новая таблица `invites` с FK на мастеров (creator + used_for_master_id), CHECK constraint `ck_invites_usage_tuple`. Data migration: backfill slug для существующих мастеров через транслит имени.

### Internal
- 6 новых сервисов/репозиториев: `InviteService`, `SlugService`, `ModerationService`, `MasterRegistrationService`, `InviteRepository`, расширения `MasterRepository` / `AppointmentRepository`.
- `BlockedMasterGuardMiddleware` в цепи middleware (после UserMiddleware, до LangMiddleware).
- 439 тестов, mypy --strict clean, ruff clean.

---

## v0.8.2-epic-8-2-deploy — 2026-04-22
Docker production deployment + GitHub Actions CI/CD. Бот развёрнут на Hetzner CAX11.

## v0.7.0-epic-7 — Напоминания
## v0.6.0-epic-6 — Просмотр расписания
## v0.5.0-epic-5 — Ручное добавление мастером
## v0.4.0-epic-4 — FSM клиентской записи
## v0.3.0-epic-3 — Доступность слотов
## v0.2.0-epic-2 — Регистрация мастера и настройки
## v0.1.0-epic-1 — Фундамент
