# Public Web Booking — Design

## Контекст и проблема

Сейчас клиент может забронировать только через Telegram TMA: открывает `t.me/grancviWebBot`, авторизуется через initData, бронирует. Если у клиента **нет Telegram** или он на десктопе вне Telegram — бронирование невозможно. QR-стикер мастера (`grancvi.am/<slug>`) сейчас редиректит в TMA, что для не-Telegram-пользователя превращается в стоп.

Мастер теряет ~30-50% потенциальных клиентов на этом барьере.

## Цели

1. **Бронирование прямо в браузере** на `grancvi.am/<slug>` — без Telegram, без логина, без SMS.
2. **TMA-флоу остаётся** без изменений — два пути в продакшене параллельно.
3. **Опциональный мост в Telegram** — после web-брони клиент может одним тапом подключить Telegram, чтобы получать напоминания и видеть свои записи.
4. **Возвращение клиента** — повторное открытие `grancvi.am/<slug>` показывает предыдущие брони из `localStorage`.

## Визуальная референция

UI-мокап утверждён пользователем: `grancvi-landing/book-mockup.html` (живёт на проде как `https://grancvi.am/book-mockup.html`). Содержит весь wizard, маску телефона, реальный месячный календарь, success-экран — без бэка, чисто vanilla JS. Реальную реализацию делаем 1:1 по нему.

## Out of scope

- **SMS-уведомления** — Twilio для AM `$0.30/SMS`, не сходится с unit-economics. Для MVP вообще без SMS, мастер сам звонит.
- **OTP-верификация телефона** — добавит трение; полагаемся на reCAPTCHA + rate-limit + post-hoc /block.
- **Регистрация/логин клиента** — нет аккаунтов, identity = (master_id, phone) уникально per master.
- **Salon flow** — пока только отдельный мастер по slug; salon-бронирование через web — отдельная задача.
- **Multi-language UI на форме** — есть переключатель `[ՀԱՅ][РУС][EN]` справа сверху. Дефолт — `hy` (Armenia-first). Выбор сохраняется в localStorage. master.lang НЕ используется для дефолта (армянский мастер может работать с русскоязычным клиентом).
- **Cancel клиентом без Telegram** — отмена возможна только если клиент подключил Telegram (через TMA `/me`). Без Telegram — звонит мастеру.

## Архитектура

### Backend (`tg-bot`)

**Новые эндпоинты** (без `X-Telegram-Init-Data`, защита через slug + reCAPTCHA + rate-limit):

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/v1/public/masters/{slug}/services` | Активные услуги мастера |
| GET | `/v1/public/masters/{slug}/slots/month?service_id&month=YYYY-MM` | Свободные дни месяца |
| GET | `/v1/public/masters/{slug}/slots/day?service_id&date=YYYY-MM-DD` | Свободные слоты дня |
| POST | `/v1/public/bookings` | Создать заявку (см. payload ниже) |
| GET | `/v1/public/bookings/{id}` | Получить статус по UUID (UUID = pseudo-auth) |

**Изменения существующего:**

| Файл | Что |
|---|---|
| `src/api/routes/public.py` | Добавить новые эндпоинты выше; уже есть `/v1/public/by-slug/{slug}`, расширим. |
| `src/db/models.py` | Добавить `Client.link_token: str \| None` (nullable, indexed). UUID для post-booking Telegram-link. |
| `src/api/schemas.py` | `PublicBookingIn`, `PublicBookingOut`, `PublicSlotsOut`, `PublicServiceOut`. |
| `src/services/booking.py` | Новый метод `create_public(...)` — без `tg_id` validation, источник `source="web"`. |
| `src/app_bot/handlers.py` | `/start link_<token>` ловит, привязывает `Client.tg_id = update.from_user.id`, очищает `link_token`. |
| `src/utils/recaptcha.py` (NEW) | Helper для проверки reCAPTCHA v3 token. |
| `migrations/versions/0018_client_link_token.py` (NEW) | ALTER TABLE clients ADD COLUMN link_token. |

**Не меняется:**

- `Appointment` — старая таблица переиспользуется. Новая запись имеет `source="web"`.
- Master notification flow (`_approve_kb` + `notify_user`) — сработает на любую новую `Appointment` независимо от source.
- TMA endpoints (`/v1/bookings`, `/v1/master/me/*`) — нетронуты.

### Frontend — `grancvi-landing` repo (NOT `grancvi-web`)

Web-форма живёт в **репо лендоса**, рядом с `index.html` и `r.html`. Vanilla JS + Tailwind (CDN), без React. Причина: лендос уже статичный, scp-deploy готов, не тащить весь Vite-билд для одной страницы.

**Меняется:**

| Файл | Что |
|---|---|
| `r.html` | Расширяем: если открыто в Telegram-клиенте — редирект в TMA как сейчас; иначе — рендерим step-wizard форму. |

**Альтернатива:** новый файл `book.html` + `r.html` остаётся редиректом. Решение — расширяем `r.html` (один URL, меньше кода для пользователя).

### Frontend — `grancvi-web` (TMA)

**Минимальные изменения:**

| Файл | Что |
|---|---|
| `src/App.tsx` | Обработать `start_param=link_<token>` — редирект на `/me` (бот уже привязал tg_id, MyBookings подхватит) |

`/v1/bookings/mine` уже умеет искать appointments по `Client.tg_id` — никаких изменений в TMA-эндпоинтах.

## Детали UX

### Step-by-step wizard на `grancvi.am/<slug>`

3 экрана, каждый с back-кнопкой и next-кнопкой. State хранится в JS-памяти (`{step, serviceId, date, time, name, phone}`). При back — данные сохраняются.

**Шаг 1/3 — Услуга**

```
[← На страницу мастера]   [1/3 услуга]

Анна Аракелян
Колорист · Парикмахер ж.

Какую услугу?
  ◯ Стрижка женская   60 мин
  ◯ Окрашивание       120 мин · 15 000 ֏
  ◯ Балаяж            180 мин · 25 000 ֏

                         [Далее →]   ← disabled пока не выбрано
```

**Шаг 2/3 — Дата + время**

Полноценный месячный календарь как в TMA (`grancvi-web/src/components/Calendar.tsx`):

```
[← Назад]                       [2/3 когда]

Окрашивание · 120 мин

Дата
┌─────────────────────────────────┐
│  ‹     Май 2026             ›   │
│  пн вт ср чт пт сб вс           │
│        1  2  3  4  5            │
│   6  7  8  9 10 11 12           │
│  13 14 15 16 17 18 19           │
│  20 21 22 23 24 25 26           │
│  27 28 29 30 31                 │
└─────────────────────────────────┘
- Прошедшие дни: серым, disabled
- Сегодня: точка под цифрой
- Доступные: белая ячейка с тонкой рамкой
- Выбранный: индиго-фон, белая цифра
- Без свободных слотов: серым, disabled

[Время на 5 мая]   ← появляется после выбора даты
                     auto-scroll в этот блок (smooth)
  10:00  11:00  12:00  14:00
  15:30  17:00  18:30

                         [Далее →]
```

**Auto-scroll:** при выборе даты — scroll smooth к `#times-block`. При выборе времени — кнопка «Далее» становится enabled (TG-MainButton-style).

**Шаг 3/3 — Контакты**

```
[← Назад]                  [3/3 контакты]

Окрашивание · 5 мая, 14:00 у Анны

Имя *
[___________________________]

Телефон *
+374 [_ _]  [_ _ _]  [_ _ _]
   ↑ маска: 8 цифр, форматируется при вводе

Записываясь, ты соглашаешься на обработку имени и телефона.

                  [✓ Записаться]
```

### Маска телефона

Префикс `+374` фиксирован как label. Ввод:

| Что ввёл | Действие |
|---|---|
| `0 93 144 550` | срезаем ведущий 0 → отправляем `+37493144550` |
| `93 144 550` | оставляем как есть → `+37493144550` |
| `+374 93 144 550` | срезаем дублирующийся `+374` → `+37493144550` |
| `93144` (5 цифр, не 8) | блокируем submit, hint «Нужно 8 цифр» |
| `99 abc 550` | в реалтайме фильтруем не-цифры |

Display-формат: `+374 XX XXX XXX`. Первая цифра — `4/5/7/9` (AM-mobile prefixes), иначе warning «Похоже не на мобильный AM-номер» (не блокируем).

### Submit

```http
POST /v1/public/bookings
Content-Type: application/json

{
  "master_slug": "anna",
  "service_id": "550e8400-...",
  "start_at_utc": "2026-05-05T10:00:00Z",
  "client_name": "Mariam",
  "client_phone": "+37493144550",
  "recaptcha_token": "..."
}
```

Бэк:

1. **reCAPTCHA** проверка (score >= 0.5 — score-based, не блок-всё-подряд)
2. **Rate-limit**: 5 POST на endpoint в час с одного IP (`limits` — Redis sorted set)
3. **Resolve master** by slug; если нет / blocked — `404 not_found`
4. **Resolve service** by id, проверить принадлежит мастеру; если нет — `404 service_not_found`
5. **Validate slot** — занят/нет, попадает в work_hours, не в blackout. Если нет — `409 slot_taken`.
6. **Get-or-create Client** by `(master_id, phone)`. Если новый — генерим `link_token = uuid4()`. Если существующий — `link_token` остаётся старый или генерим новый, в зависимости от `tg_id` (если уже привязан — токен не нужен).
7. **Create Appointment** with `status="pending"`, `source="web"`, `decision_deadline = now + 24h`.
8. **Notify master** через существующий `notify_user(...)` + `_approve_kb` — мастер получит Telegram с approve/reject.
9. **Return** payload:

```json
{
  "id": "770e8400-...",
  "master_name": "Анна",
  "service_name": "Окрашивание",
  "start_at": "2026-05-05T14:00:00+04:00",
  "status": "pending",
  "telegram_link_url": "https://t.me/grancviWebBot?start=link_<token>"
}
```

### После сабмита — экран успеха

```
✅ Записано!

[карточка с записью]
  5 мая, 14:00
  Окрашивание у Анны

Получай напоминания и будь на связи с мастером —
[📲 Открыть в Telegram]   ← открывает telegram_link_url

Мастер скоро свяжется для подтверждения.

[← Записаться ещё]
```

**Никакого "⏳ Ожидает подтверждения"** — клиент видит запись как готовую. Статус (pending/confirmed/rejected) подтягивается при возврате на страницу через GET endpoint.

Над кнопкой Telegram — короткий pitch-текст («получай напоминания и будь на связи»), а сама кнопка остаётся короткой ("Открыть в Telegram" / "Բացել Telegram-ում") чтобы не выглядеть тяжело.

### localStorage

```javascript
// При успешном POST:
const stored = JSON.parse(localStorage.getItem("grancvi.bookings") ?? "[]");
stored.push({
  id: response.id,
  master_slug: "anna",
  master_name: "Анна",
  service_name: "Окрашивание",
  start_at: "2026-05-05T14:00:00+04:00",
  status: "pending",
  created_at: Date.now(),
});
localStorage.setItem("grancvi.bookings", JSON.stringify(stored));
```

При возврате на `grancvi.am/anna`: фильтруем по `master_slug === "anna"`, рендерим список «Твои записи к Анне», параллельно делаем **один** `GET /v1/public/bookings/<id>` per booking для свежего статуса.

**Не polling.** Polling включаем только если клиент сам нажимает «Обновить» или при `visibilitychange`-событии (вкладка вернулась в фокус). Этого достаточно — мастер обычно отвечает в минутах/часах, не секундах.

Записи старше 30 дней или со статусом `rejected`/`completed` подсвечиваются меньше; через 90 дней удаляем из localStorage автоматически (cleanup при загрузке).

### Telegram opt-in flow

Клиент тапнул `📲 Подробнее в Telegram-боте`:

```
1. Открывается t.me/grancviWebBot?start=link_<token>
2. Bot's app_bot/handlers.py CommandStart() ловит
3. _kind_for("link_<token>") → новый kind "link"
4. Бот:
   a) находит Client.link_token == token
   b) если Client.tg_id уже != null и != message.from_user.id → ошибка
      (someone else's token), отправляем "Эта ссылка уже привязана к другому
      аккаунту"
   c) иначе: client.tg_id = message.from_user.id, client.link_token = None
      (одноразовый), commit
   d) отвечает inline-кнопкой "Открыть приложение" → tgWebAppStartParam=link_<token>
5. Клиент тапает кнопку → TMA открывается
6. RoleRouter видит startParam="link_<token>" → редирект на /me
7. MyBookings фетчит /v1/bookings/mine
   → теперь находит Appointment, потому что Client.tg_id = клиент
8. Показывает запись клиенту с обычным TMA-UI (cancel-кнопка, статус, etc.)
```

С этого момента все следующие напоминания и нотификации этому клиенту идут **через Telegram бесплатно**.

## Anti-spam

| Слой | Что |
|---|---|
| **reCAPTCHA v3** на форме | invisible, score-based; backend проверяет `score >= 0.5`. Если ниже — soft-reject с шансом ретрая |
| **Rate-limit IP** | 5 POST в час; `Redis sorted set` `ratelimit:public_bookings:<ip>` |
| **Rate-limit phone** | 3 POST в час с одного телефона на одного мастера (защита от засорения календаря) |
| **Master block** | если мастер видит спам — клик на запись в TMA → `Block client` → `Client.blocked_at` (новая колонка в `clients`) → следующие POST с этим телефоном этому мастеру отказывают |

## Координация деплоя

Три репо, три деплоя:

| Что | Куда | Когда |
|---|---|---|
| Backend (`tg-bot` на main) | auto-deploy через GitHub Actions | первым |
| Frontend TMA (`grancvi-web`) | scp `dist/*` на VPS | после бэка (минимально, только App.tsx for link_<token>) |
| Frontend Lander (`grancvi-landing`) | scp `index.html` + `r.html` на VPS | последним |

Backwards-compat:
- Старый `r.html` (только-redirect) до деплоя нового бэка — клиент попадает в TMA, всё работает как раньше.
- Новый `r.html` без нового бэка — POST упадёт 404, клиент увидит ошибку. Поэтому **бэк деплоим первым**.

## Метрики успеха

- **Доля web-броней vs TMA-броней** через 1 месяц после релиза: цель ≥30% (сейчас 0%).
- **Доля web-клиентов которые подключили Telegram** (через post-booking link): цель ≥40%.
- **No-show rate** для web-броней: baseline установить, цель ≤25% (industry average).
- **Spam-rate**: количество `/block client` срабатываний в неделю — должно быть ≤2.

## Риски

1. **Spam-flood до master block** — мастер всё равно увидит фейковые брони в Telegram, расстраивается. Митигация: чёткий UX «Block client» в TMA + reCAPTCHA score высокий (≥0.7).
2. **No-show без напоминаний** — клиент забыл про бронь, мастер потерял 60 минут. Митигация: показать в success-экране призыв «Подключи Telegram чтобы не забыть» + крупный текст «Мастер позвонит за день до записи» — это psychological commitment.
3. **localStorage сбрасывается** (private browsing, чистка) — клиент теряет историю. Источник истины — БД, через Telegram-link можно вернуть. Без Telegram — клиент звонит мастеру.
4. **Дубли клиентов в БД** — уникальный constraint `(master_id, phone)` уже работает, get-or-create на бэке.
5. **slot_taken гонка** — два клиента сабмитят на тот же слот одновременно. Уникальный partial index `uq_appointment_slot` уже ловит → 409 → клиент видит «Слот занят, выбери другой».

## Открытые вопросы (для ревью)

1. **reCAPTCHA secret + site key** — кто заводит Google Cloud project / reCAPTCHA admin? Я могу подсказать шаги, но key владеет user.
2. **Rate-limit точные числа** — 5/час IP + 3/час phone достаточно? Может быть строже на старте.
3. **Privacy-page** — нужен короткий текст. Могу написать минимальный (RU/HY/EN), но юр.валидность для AM не гарантируется.
4. **Lang detection в форме** — стартуем с `master.lang` (RU/HY) детектом по slug? Или всегда RU? Для AM-мастеров — HY, для остальных — RU. Думаю да, использовать master.lang.
5. **Phone format display** — `+374 XX XXX XXX` или `+374 (XX) XXX-XX-XX` (более «цивильно»)? Я бы взял первый — проще.
