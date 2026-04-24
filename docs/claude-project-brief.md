# Grancvi — project brief for Claude

Paste or attach this whenever you open a fresh session. Tells the next Claude
what exists, why, and where the landmines are. Last updated 2026-04-24.

---

## 1. What this is

Telegram-first booking tool for the Armenian beauty/health market
(hairdressers, barbers, manicure/pedicure, brows/lashes, dentists…). Targets
solo masters first, salons second. Physical QR stickers are the go-to-market
wedge — master sticks QR on their chair / Instagram; client scans → books.

Two Telegram entry points:

- `@grancviWebBot` — **only** bot running in production. Hosts the TMA
  launcher, notifications, approval callbacks, APScheduler reminders,
  Alembic migrations on boot.
- `@GrancviBot` — **retired**. Its container (`app`) was removed in commit
  `62861ff`. The bot account still exists on Telegram (token alive as a
  notification fallback), but nothing listens for its updates.

Monorepo layout:

- `src/` — Python backend (FastAPI API + aiogram bot + shared services)
- `../grancvi-web/` — separate repo, React + Vite TMA, served from
  `https://app.jampord.am`

---

## 2. Stack & runtime

| Piece | Tech |
|---|---|
| API | FastAPI + async SQLAlchemy 2.0, uvicorn |
| Bot | aiogram 3.x |
| DB | Postgres 16 |
| Cache / FSM / APScheduler jobstore | Redis 7 |
| Migrations | Alembic (`migrations/versions/`) |
| Frontend | React + Vite + Tailwind + @tanstack/react-query + react-router-dom + @telegram-apps/sdk-react |
| Obs | structlog JSON + Sentry (env-gated by `SENTRY_DSN` / `VITE_SENTRY_DSN`) |
| Infra | Docker Compose on a single Hetzner VPS; nginx + certbot on host |

Compose services in prod (after decom):

- `postgres` — persistent volume `pg_data`
- `redis`
- `api` — `uvicorn src.api.main:app`, listens on 127.0.0.1:8000
- `app_bot` — runs `@grancviWebBot` + migrations on boot + APScheduler

No `app` service. Any doc that references it is stale.

Nginx sites:

- `api.jampord.am` → proxy to `127.0.0.1:8000`
- `app.jampord.am` → static `/var/www/jampord-app` (TMA dist)
- `jampord.am` root — unrelated legacy site; do NOT point TMA things there.

---

## 3. Roles & flows

### Roles (from `GET /v1/me`)

- `client` — anyone with a Telegram id who isn't a master/salon. No schema
  row until they book.
- `master` — row in `masters`, one per `tg_id`.
- `salon_owner` — row in `salons`, one per `owner_tg_id`.
- `is_admin` (orthogonal flag) — `tg_id` appears in `ADMIN_TG_IDS` env.

A single `tg_id` is either a master OR a salon_owner, not both (enforced
at registration time).

### Registration (all in-TMA now)

1. Admin or salon owner creates an invite → link
   `t.me/grancviWebBot?start=invite_<CODE>` (builder uses
   `app_bot_username`, NOT `bot_username`).
2. Invitee opens link → `app_bot` replies with a WebApp button → TMA
   opens with `tgWebAppStartParam=invite_<CODE>`.
3. `RoleRouter` routes to `/register?code=<CODE>`. Page calls
   `GET /v1/register/invite/{code}` for kind/validity.
4. Form is master-form or salon-form based on `invite.kind`. Submits to
   `POST /v1/register/master` or `/v1/register/salon`. Backend auto-generates
   a slug; we don't expose a slug field on the register form.
5. On success, `/v1/me` cache is invalidated; user lands on their dashboard.

Salon-scoped master invites (`invite.salon_id` non-null) automatically set
`master.salon_id` on redeem (see `MasterRegistrationService.register`). The
new master shows up in the salon dashboard immediately.

### Booking

- Client opens `t.me/grancviWebBot?start=master_<slug>` (or scans QR) →
  TMA routes to `/m/<slug>` → service → date → time → name/phone → submit.
- `POST /v1/bookings` creates a `pending` appointment and pushes notification
  to the master's chat with `Approve` / `Reject` inline buttons.
- Approve/Reject callbacks land on `app_bot` (`src/app_bot/approval.py`),
  which runs `BookingService.confirm/reject`, pushes the client notification,
  edits the original message to remove the keyboard.

### Cancel / reschedule

- Client cancels from `/me` → master gets a text-only notification.
- Master cancels from TMA dashboard → client gets notification with a
  rebook link.

### Manual booking (walk-in / phone call)

- Master side: `/master/book-client` → pick service/date/time/client →
  `POST /v1/master/me/appointments` (`source=master_manual`, status
  `confirmed`).
- Salon receptionist: `/salon/book-client` → pick master first → same flow →
  `POST /v1/salon/me/masters/{id}/appointments`.

### Master leaving a salon

- Salon dashboard → per-master **Исключить из салона** sets
  `master.salon_id = null`. Future appointments stay with the master.
- **Перенаправить ссылку** opens a picker: redirect the master's slug to
  another master in the salon OR to the salon landing page `/s/<slug>`.
  Stored in `master.redirect_master_id` / `master.redirect_salon_id`
  (CHECK: at most one set). `GET /v1/masters/by-slug/{slug}` returns
  MasterOut with `redirect_to`; client sees an amber banner with a CTA.

### Search

- `GET /v1/search?q=` — ILIKE across public masters + all salons. Surfaced
  on `/me` as a search bar at the top; 2-char minimum. Hits link to
  `/m/:slug` or `/s/:slug`.

---

## 4. Data model — key decisions

- `masters.slug` — public short name. **One change per 30 days**
  (`slug_changed_at`). Previous slugs live in `masters.past_slugs`
  (JSONB, GIN-indexed); `MasterRepository.by_slug` falls back to them,
  so old QR stickers keep resolving after a rename.
- `masters.redirect_master_id` / `masters.redirect_salon_id` — salon can
  point an ex-master's slug somewhere useful when they leave. CHECK
  constraint: at most one of the two is set.
- `appointments` has a partial unique index on `(master_id, start_at)
  WHERE status IN ('pending','confirmed')` → race-safe slot locking.
  On IntegrityError → `SlotAlreadyTaken` → API returns 409.
- `clients` unique on `(master_id, phone)` → phone-keyed dedup per master.
  Phone-less clients become separate anonymous rows each booking.
- `invites.ck_invites_usage_tuple` only requires `used_by_tg_id` and
  `used_at` to move together (migration `0008`); `used_for_master_id` is
  optional so salon-owner invites can be redeemed.

All timestamps are `timestamptz`, stored in UTC. Conversion to
`Asia/Yerevan` happens only at display/log boundaries. Utilities in
`src/utils/time.py` (`to_yerevan`, `to_utc`, `now_utc`, `now_yerevan`).

---

## 5. API surface

Everything under `/v1/`. Init-data auth via `X-Telegram-Init-Data` header,
validated by `require_tg_user` (HMAC of Telegram init-data using
`APP_BOT_TOKEN`).

### Public

- `GET /v1/me` — role + profile + is_admin
- `GET /v1/masters/by-slug/{slug}` → MasterOut (carries `redirect_to`
  if set; keeps resolving for blocked masters when a valid redirect
  exists). `GET /v1/masters/{id}/services|slots`.
- `POST /v1/bookings`, `GET /v1/bookings/mine`,
  `GET /v1/bookings/visited-masters`, `POST /v1/bookings/{id}/cancel`
- `GET /v1/salons/by-slug/{slug}` — public salon landing with master list
- `GET /v1/search?q=` — public search

### Master (self)

- `GET/PATCH /v1/master/me/profile` — name, specialty, slug (with
  30-day cooldown), phone, timezone, lang, is_public
- `GET/PATCH /v1/master/me/schedule` — work_hours, breaks, slot_step_min
- `GET/POST/PATCH/DELETE /v1/master/me/services`
- `GET /v1/master/me/appointments?from=&to=`
- `POST /v1/master/me/appointments` (manual booking)
- `POST /v1/master/me/appointments/{id}/approve|reject|cancel`

### Salon (self)

- `GET /v1/salon/me` / `/v1/salon/me/masters` / `/v1/salon/me/appointments`
- `POST /v1/salon/me/invites`
- `POST /v1/salon/me/masters/{id}/remove|redirect|appointments`

### Admin (gated by `ADMIN_TG_IDS`)

- `GET /v1/admin/stats`, `/v1/admin/masters`
- `POST /v1/admin/masters/{id}/block|unblock`
- `POST /v1/admin/invites` (`kind: master | salon_owner`)

### Registration

- `GET /v1/register/invite/{code}` — preview
- `POST /v1/register/master` / `/v1/register/salon`

---

## 6. Frontend — notable wiring

- Root `RoleRouter` routes by `/v1/me.role` plus `start_param`:
  - `invite_<CODE>` → `/register`
  - `master_<slug>` → `/m/<slug>`
  - `salon_<slug>` → `/s/<slug>`
- Back-button strategy: `useBackButton` + Layout's visible ← both call
  `WebApp.close()` when `window.history.length <= 1` to avoid a
  RoleRouter bounce loop on deep-linked pages.
- Safe areas: `#root { min-height: 100dvh }`. Sticky header uses
  `.tma-safe-top` which reads Telegram safe-area vars plus a
  `max(topInset+20, 96px)` floor when `isFullscreen` so the header
  clears the floating close/kebab overlay.
- `useMainButton` supports `visible` — pages hide the MainButton when
  nothing is dirty instead of leaving it disabled and floating.
- `<Toast>` is a fixed-position floating success banner (used after
  profile/schedule save). Doesn't jump with scroll.
- Theme sync: MainButton is themed via
  `themeParams.button_color / button_text_color`, and on boot + theme
  toggle we call `setHeaderColor / setBackgroundColor /
  setBottomBarColor` to avoid the white bottom-strip clash.
- Stale-state fix: a `visibilitychange` listener invalidates appointment
  queries when the TMA regains focus, so a bot-side approve reflects
  the next time the app is brought forward.

---

## 7. Notifications

Every server-initiated message goes through `src/utils/client_notify.py`
`notify_user(app_bot, fallback_bot, chat_id, text, reply_markup?)`:

1. Try `app_bot` (`@grancviWebBot`) first.
2. On 403 Forbidden (user hasn't opened the new bot yet) → fall back
   to `fallback_bot` (the legacy token; the bot _account_ still
   accepts sends even though the container is dead).

Callers: `bookings.create_booking`, `bookings.cancel_by_client`,
`master.approve/reject/cancel`, `salon.create_manual_appointment`,
`scheduler/jobs.send_due_reminders`.

Inline buttons attached to notifications:

- New booking → `ApprovalCallback` keyboard (handled in
  `src/app_bot/approval.py`).
- Salon manual booking / master-cancel → WebApp button `Գրանցվել`
  pointing to `https://app.jampord.am`.
- Client cancel → text-only (no action needed).

---

## 8. Menu button & bot UX

- Bot-wide default: `Open App` (set in `app_bot_main.py` at boot).
- On `/start` we call `set_chat_menu_button` per user:
  - `language_code` starts with `hy` → `Հավելված`
  - else → `Приложение`
- Welcome message text + inline button are also language-dispatched
  (`Գրանցվել` for hy, `Записаться` for ru/other).

---

## 9. Ops

- VPS: Hetzner, single host, deploy user `deploy` (docker group, no sudo).
- Deploy: GitHub Actions `deploy.yml` → `docker compose up -d --build`
  on push to main (after `ci.yml` passes). Prod overrides in
  `docker-compose.prod.yml`.
- **Local Postgres backups**: `/opt/tg-bot/backup.sh` via crontab at
  03:00 UTC. Writes gzipped dumps to `/opt/tg-bot/backups/`, keeps
  last 14 days. **Offsite backup (Backblaze B2 / rclone) is not wired
  up yet** — this is the biggest open ops risk.
- Sentry: `SENTRY_DSN` env toggles reporting in `api`, `app_bot`, and
  the TMA (`VITE_SENTRY_DSN`). Both default to no-op.
- Migrations run on every `app_bot` boot
  (`sh -c "alembic upgrade head && exec python -m src.app_bot_main"`).
- TMA is NOT deployed by CI — deploy with:

  ```sh
  cd ../grancvi-web
  pnpm build
  scp -i ~/.ssh/grancvi-deploy dist/index.html deploy@94.130.149.91:/var/www/jampord-app/
  scp -i ~/.ssh/grancvi-deploy dist/assets/* deploy@94.130.149.91:/var/www/jampord-app/assets/
  ```

  Always copy BOTH JS and CSS; Vite hashes the two independently.

---

## 10. Product state

### Shipped

- Master: dashboard with today/tomorrow/week/month calendar, services
  CRUD with per-specialty preset picker, schedule editor with
  per-weekday on/off + lunch break, profile editor with 30-day slug
  cooldown, in-chat Approve/Reject, manual walk-in booking, QR sheet
  with share/copy/download.
- Salon: master list with per-master counters, unified calendar with
  master filter, invite flow (QR + link), remove + redirect master,
  public salon page, receptionist booking for any master, salon public
  QR on dashboard.
- Admin: stats, masters list, block/unblock, invite master/salon.
- Client: search, `/me` upcoming bookings + previously-visited masters,
  deep-link booking, rebook shortcut.
- Registration: both master and salon via TMA (no more legacy bot
  FSM), salon-scoped invite auto-links the new master to the salon.
- i18n: ru / hy throughout. Telegram `language_code` drives the menu
  button and bot inline button. TMA has a user-controlled language
  toggle in the header.
- PWA-installable: `manifest.json` + pass-through `sw.js`.

### Not done / known gaps

- **Multi-salon masters** — a master belongs to at most one salon
  (`Master.salon_id` singular). User flagged the "works at salon + at
  home" and "works at two salons" cases; design is to add a
  `master_salons` M2M junction. Discussed, not implemented.
- **Offsite backups** — see §9.
- **Tests** — services and repos have 500+ unit tests; recent TMA
  features (register, salon dashboard, search, salon receptionist,
  profile editor, redirect) ship with thin handler tests. Booking +
  cancel paths are the highest-risk units to backfill.
- **Observability** — only Sentry errors. No metrics, no slow-query
  logging, no uptime monitoring wired.
- **Payments / subscription billing** — not built. Pricing (per user
  memory): solo 2500 AMD/mo after 10 free bookings; salon tier TBD.

---

## 11. Gotchas eaten more than once

- **Don't strip `@GrancviBot` token from env** — it still works as a
  silent fallback in `notify_user` for clients who only opened the
  old bot. Removing it flips some notifications from "delivered via
  fallback" to "dropped".
- **Menu button is cached per chat** Telegram-side. If you change
  `_menu_label_for()`, existing users see the old label until they
  `/start` again (which triggers `set_chat_menu_button` for their chat).
- **CI deploy only rebuilds containers** — the TMA dist is NOT
  deployed by CI. `scp` after every `pnpm build`. Always copy both
  JS and CSS; Vite hashes are independent and you WILL forget one.
  Recovery when the stylesheet 404s: rebuild, scp the missing file,
  reload TMA — no server restart needed.
- **Inline WebApp buttons don't carry `start_param` by default** —
  the URL must include `?tgWebAppStartParam=...` explicitly. See
  `_launch_kb` in `src/app_bot/handlers.py`.
- **TMA in fullscreen** covers the notch / Telegram close button with
  app content. The `.tma-safe-top` padding + `max(top+20, 96)` floor
  is calibrated against Android; if headers start getting chopped on
  a new device, bump the floor in `syncSafeAreaVars`.
- **SQLAlchemy CHECK constraints bite on rename-only columns.** When
  a column flips from required to optional, check that no CHECK
  mentions the old invariant (see migration `0008` for the invite
  example that blocked salon registration in prod for an hour).
- **Alembic migrations run on `app_bot` boot.** Adding a migration
  without rebuilding the image = container still on the old migration
  file. Use `docker compose up -d --build app_bot`; `run --rm app_bot
  alembic upgrade` alone picks the old image.
- **React Query default staleTime is 30s.** Actions that bypass the
  cache (bot-side Approve, cron jobs) won't reflect in the TMA until
  the `visibilitychange` handler fires or the query is manually
  invalidated.

---

## 12. Working norms with me (the user)

- Default: Russian in chat. Comments / commit messages / code in English.
- Terse responses; no "here's what I'll do" preambles — just do it.
- Ship incrementally: commit → deploy → verify → tell me. One concrete
  change at a time; avoid batching unrelated work.
- When a decision is between simple-now and clean-later, ask once with
  the tradeoff; I'll pick.
- For destructive ops (drop, reset, force-push), confirm first, even on
  test data.
- On plan handoff, default to Subagent-Driven execution; skip the
  "which mode?" prompt. Destructive ops are not subagent work — ask first.
