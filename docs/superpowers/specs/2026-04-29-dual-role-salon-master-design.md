# Dual-Role: Salon Owner + Master — Design

## Контекст

Сейчас один Telegram-аккаунт (`tg_id`) может играть только **одну** роль: либо `master`, либо `salon_owner`, либо `client`. Это — искусственное ограничение в API:

- `src/api/routes/register.py:148-152` — `register_master_self` возвращает 409 `already_registered`, если у `tg_id` есть запись в `salons.owner_tg_id`.
- `src/api/routes/register.py:281-282` — `register_salon_self` симметрично 409, если есть запись в `masters.tg_id`.

Реальность Армении: владельцы салонов часто работают в своих же салонах как мастера. Сейчас они вынуждены выбирать одну роль или просить админа удалить запись и регистрироваться заново. Это пользователь сегодня (2026-04-29) встретил в проде:

> «он зарегался как салон, попросил меня удалить, потом не может зарегиться как мастер».

## Цели

1. **Один `tg_id` = до двух ролей** (`master` + `salon_owner`). `client` отдельно — это «никаких регистрационных записей».
2. **Автосвязь**: если salon_owner становится мастером, его новая `Master.salon_id` ставится на id его салона. Появляется в каталоге своего салона.
3. **Toggle в TMA** для переключения между двумя кабинетами.
4. **Существующие single-role юзера ничего не замечают** — toggle не показывается им, ни одного нового UI-элемента не видно.

## Out of scope

- Удаление мастера/салона через админку — поведение остаётся как сейчас (hard-delete; вторая роль остаётся).
- Slug-namespace остаётся общим: master-slug и salon-slug не могут совпадать (это уже работает через `SlugService.is_taken`).
- Возможность объединить мастера-в-салоне через invite (есть отдельный flow `invite_*`) — не пересекается.
- Реализация в WebApp клиента (catalog) — никаких изменений; salon-owner-master виден в каталоге как обычный мастер.

## Архитектура

### Backend (`tg-bot`)

**Изменяется:**

| Файл | Что |
|---|---|
| `src/api/routes/register.py` | `register_master_self`: убрать salon-cross-check. `register_salon_self`: убрать master-cross-check. После создания мастера, если у `tg_id` уже есть salon — `master.salon_id = salon.id`. |
| `src/api/schemas.py` | `MeOut` — добавить `master_profile: MeProfileOut \| None` и `salon_profile: MeSalonProfileOut \| None`. Существующее поле `profile` оставить (backwards-compat, отражает primary role). Если оба профиля есть — primary = master. |
| `src/api/routes/me.py` | Заполнить новые поля в `MeOut`. Логика: попробовать найти Master, попробовать найти Salon, заполнить оба если есть. Поле `role` отдаёт primary (master, если есть; иначе salon_owner; иначе client). |
| `tests/test_api_register.py` | Тесты на удаление cross-check + auto-link. |
| `tests/test_api_me.py` | Тест на dual-role response. |

**Не меняется:**

- Схема БД — `Master.tg_id` и `Salon.owner_tg_id` уже отдельные.
- Slug-проверки.
- `cmd_block_master`, `cmd_unblock_master`.

### Frontend (`grancvi-web`)

**Изменяется:**

| Файл | Что |
|---|---|
| `src/api/types.ts` | `MeOut` — добавить `master_profile: MeProfileOut \| null`, `salon_profile: SalonProfile \| null`. |
| `src/components/RoleToggle.tsx` | NEW. Маленький компонент с двумя пилюлями `[Мастер][Салон]`, рендерится только если оба профиля есть. На клик — `localStorage.setItem("grancvi.activeRole", ...)` и `navigate("/")`. |
| `src/components/Layout.tsx` | Добавить `<RoleToggle />` в шапку (только если dual-role). |
| `src/App.tsx` (`RoleRouter`) | Если оба профиля → читать `localStorage.activeRole` (default: `"master"`); рендерить соответствующий dashboard. |
| `src/pages/SalonDashboard.tsx` | Когда `salon_profile && !master_profile` — показать CTA «+ Я тоже мастер» → `navigate("/register/self")`. |
| `src/pages/MasterDashboard.tsx` | Когда `master_profile && !salon_profile` — показать CTA «+ Открыть свой салон» → `navigate("/register/self-salon")`. |
| `src/lib/i18n.ts` | Новые ключи: `role_toggle_master`, `role_toggle_salon`, `cta_become_master`, `cta_open_salon`. |

## Детали логики

### Backend: auto-link master to salon

Псевдокод изменения в `register_master_self`:

```python
# (после создания master row)
existing_salon = await session.scalar(
    select(Salon).where(Salon.owner_tg_id == tg_id)
)
if existing_salon is not None:
    master.salon_id = existing_salon.id
```

Это выполняется **после** `register_self` создаёт `master`, но **до** `commit`. Аналогично можно сделать для register_salon_self → если у tg_id есть Master, обновить `master.salon_id = new_salon.id`. Но это инверсия: при регистрации салона бывший единственный мастер автоматически становится «работающим в своём же салоне». Полезно? Да, симметрично. Делаем оба направления.

### Backend: `MeOut` shape

Текущая (ru):
```python
class MeOut(BaseModel):
    role: Literal["master", "salon_owner", "client"]
    profile: MeProfileOut
    is_admin: bool
    onboarded: bool | None = None
```

Новая:
```python
class MeOut(BaseModel):
    role: Literal["master", "salon_owner", "client"]  # primary
    profile: MeProfileOut  # backwards-compat: master if has master, else salon, else basic
    master_profile: MeMasterProfileOut | None = None
    salon_profile: MeSalonProfileOut | None = None
    is_admin: bool
    onboarded: bool | None = None
```

`master_profile` и `salon_profile` — каждый со своим `slug`, `name`, `is_public`. Если присутствуют оба — `role` = `"master"` (приоритет master над salon — потому что мастер чаще принимает деньги, важнее не пропустить).

### Frontend: RoleToggle UX

Видимый только когда `me.master_profile != null && me.salon_profile != null`:

```
┌──────────────────────────────────┐
│ [● Мастер] [○ Салон]    @grancvi │   ← header
└──────────────────────────────────┘
```

Тап → `setItem("grancvi.activeRole", "salon")` → `navigate("/")` → `RoleRouter` рендерит `SalonDashboard`. Без перезагрузки.

### Frontend: RoleRouter дополнение

```tsx
// в RoleRouter, после deep-link checks
const dual = me.data.master_profile && me.data.salon_profile;
const stored = (typeof localStorage !== "undefined"
                && localStorage.getItem(ACTIVE_ROLE_KEY)) || "master";
const active = dual ? (stored === "salon" ? "salon" : "master") : me.data.role;

if (active === "master" && me.data.master_profile) {
  return <MasterDashboard ... />;
}
if (active === "salon" || me.data.role === "salon_owner") {
  return <SalonDashboard ... />;
}
```

## Координация деплоя

Backend деплоится первым (auto-deploy при push в main, как обычно). Frontend — `pnpm build` + scp. Backwards-compat:

- **Старый фронт + новый бэк**: фронт получает старые поля (`role`, `profile`), новые поля игнорятся. Существующие single-role юзеры работают как раньше. Dual-role впервые регистрирующиеся попадут в один кабинет (master, по приоритету `role`).
- **Новый фронт + старый бэк**: новый фронт ждёт `master_profile`/`salon_profile`, получает `undefined` → toggle никогда не покажется → fallback к старому поведению через `me.role`.

→ безопасно деплоить в любом порядке. Деплоим бэк первым, фронт через 5 минут.

## Риски

1. **Slug коллизия между master и salon одного юзера** — невозможна, `SlugService.is_taken()` проверяет обе таблицы. Юзер увидит ошибку `slug_taken` и выберет другой — это **корректное** поведение (нельзя занять одинаковый slug в двух ролях).
2. **Активная роль в localStorage** теряется при переустановке Telegram / очистке storage. Fallback — primary role (master). Не критично.
3. **Salon-owner регится мастером, потом удаляет себя как мастера через /admin** — Master row удалится, но `salon` остаётся. Toggle пропадает. Корректно.

## Тестовый план

- E2E в проде: ты регишься салоном → потом регишься мастером → видишь toggle → переключаешься между кабинетами.
- Backend unit: `test_register_master_self_when_salon_exists_links_salon_id`, `test_register_salon_self_when_master_exists_updates_master_salon_id`, `test_me_returns_both_profiles_when_dual_role`.
