# Master avatar — design

**Status:** approved, ready for implementation plan
**Date:** 2026-05-10

## Goal

Дать мастеру загрузить фото профиля через бота. Аватар отдаётся в публичном API и показывается на странице мастера и в списке мастеров салона. Хранение — на VPS-диске (named Docker volume), без S3.

## Scope

**In scope**
- Аватар у `Master`. Один файл на мастера, квадрат 256×256 JPEG.
- Загрузка в онбординге (опционально, со «Skip») и через меню профиля.
- Замена и удаление через меню профиля.
- Раздача из FastAPI как статика.
- Возврат `avatar_url` в `PublicMasterOut` и `PublicSalonMasterOut`.

**Out of scope (явно)**
- Логотип/обложка салона.
- Множественные размеры, превью, lazy variants.
- Кропинг-UI на стороне бота.
- Миграция в S3 / R2.
- Модерация изображений.

## Storage

- Колонка `Master.avatar_uploaded_at: datetime | None` (UTC, `TIMESTAMP(timezone=True)`). `None` = аватара нет. Используется как индикатор и для cache-busting (`?v=<unix_ts>`).
- Имя файла детерминированное: `<master.id>.jpg`. Отдельной колонки `filename` не нужно.
- Каталог хранения: `settings.avatars_dir`, дефолт `/app/data/avatars`. Маппится на named volume `avatars_data` в обоих compose-файлах. Том монтируется и в контейнер `api` (отдаёт), и в `app_bot` (пишет).
- Каталог создаётся на старте, если его нет (и в API при mount, и в `AvatarService` перед записью).
- Бэкап тома — отдельной задачей вне этой спеки (упомянуть в README одной строкой).

## Image processing

`src/services/avatars.py` — `AvatarService` + чистая функция `process_image(raw: bytes) -> bytes`:

На уровне модуля: `from pillow_heif import register_heif_opener; register_heif_opener()` — регистрируем HEIC/HEIF декодер один раз при импорте, дальше Pillow его читает прозрачно.

1. `Image.open(BytesIO(raw))` + `verify()` — отлавливаем «не картинка / битый файл» → `BadImage`. С зарегистрированным HEIF opener сюда же попадают `.heic` / `.heif` с iPhone.
2. Открываем заново (Pillow требует после `verify`), конвертируем в `RGB` (избавляемся от alpha, EXIF rotation применяем через `ImageOps.exif_transpose`).
3. Центральный square crop по `min(W, H)`.
4. Resize до 256×256 c `Image.LANCZOS`.
5. Save в `BytesIO` как JPEG `quality=85`, `optimize=True`. Возвращаем bytes.

Методы:
- `save(master_id: UUID, raw: bytes) -> None` — обработать и записать в `<dir>/<master_id>.jpg` (атомарно: пишем во временный файл рядом и `os.replace`).
- `delete(master_id: UUID) -> None` — `unlink(missing_ok=True)`.
- `path_for(master_id: UUID) -> Path` — для `FSInputFile` в боте.

Лимит на входе (проверяется в хендлере, до вызова сервиса): `file_size ≤ 10 MB`. Применяется и к `message.photo` (берём самый большой `PhotoSize`), и к `message.document`. Превышено → ответ `AVATAR_TOO_LARGE`.

Зависимости: `pillow` и `pillow-heif` в `pyproject.toml`. Pillow — стандартная либа обработки изображений; `pillow-heif` нужен для декодирования iPhone HEIC.

## API

- `src/api/main.py`: `Path(settings.avatars_dir).mkdir(parents=True, exist_ok=True)`, далее `app.mount("/static/avatars", StaticFiles(directory=settings.avatars_dir))`.
- `src/api/schemas.py`:
  - `PublicMasterOut.avatar_url: str | None = None`
  - `PublicSalonMasterOut.avatar_url: str | None = None`
- `src/api/routes/public.py`: общий хелпер
  ```python
  def _avatar_url(m: Master) -> str | None:
      if m.avatar_uploaded_at is None:
          return None
      return f"/static/avatars/{m.id}.jpg?v={int(m.avatar_uploaded_at.timestamp())}"
  ```
  Применяем в `public_master_by_slug` и `public_salon_by_slug`.

Кэш: `StaticFiles` сам отдаёт `last-modified` + `etag`. Cache-busting между сменами аватара — через `?v=<ts>` в URL (новая ts → новая URL → forced refetch). Фронт префиксует относительный путь API origin'ом.

`is_public=False` или `blocked_at != NULL` → API не отдаёт мастера вообще, аватар недостижим. Сам файл не удаляется (он не PII). Удаляем файл только при явном «Удалить» в меню или при удалении аккаунта (последнее уже существует и должно подхватить — проверить в плане реализации).

## Bot UX

### Онбординг

Текущий поток: `lang → name → phone → specialty → slug → DONE`.

После успешного `MasterRegistrationService.register(...)` (там, где сейчас `state.clear() + REGISTER_DONE`) переходим в новое состояние `MasterRegister.waiting_avatar` и шлём prompt:

> «Пришлите фото профиля. Его увидят клиенты на странице записи. Можно пропустить — добавите потом из меню профиля.»

Под prompt'ом — инлайн-кнопка «Пропустить» (callback `AvatarActionCallback(action="skip")`).

Хендлеры в `MasterRegister.waiting_avatar`:
- `message.photo` → процесс → `state.clear()` → `REGISTER_DONE` + главное меню.
- `message.document` с `mime_type` startswith `image/` (включая `image/heic`, `image/heif`, `image/jpeg`, `image/png`, `image/webp`) → процесс → как `message.photo`.
- `AvatarActionCallback(action="skip")` → `state.clear()` → `REGISTER_DONE` + главное меню.
- Документ с не-image mime, текст, стикер → ответ `AVATAR_NEED_PHOTO`, состояние не меняем.

### Меню профиля

В `profile_menu_kb()` добавляется четвёртая кнопка `PROFILE_BTN_AVATAR` (callback `ProfileFieldCallback(field="avatar")`).

Хендлер на `ProfileFieldCallback.filter(F.field == "avatar")`:
- Если `master.avatar_uploaded_at is not None` — `answer_photo` файлом с диска (`FSInputFile(AvatarService.path_for(master.id))`) с инлайн-клавиатурой:
  - «Заменить» → `AvatarActionCallback(action="replace")`
  - «Удалить» → `AvatarActionCallback(action="delete")`
  - «Назад» → `AvatarActionCallback(action="back")`
- Если `None` — текстом `PROFILE_AVATAR_NONE` + клавиатура «Прислать фото» (= replace) и «Назад».

Хендлеры на `AvatarActionCallback`:
- `replace` → `state.set_state(ProfileEdit.waiting_avatar)` + prompt.
- `delete` → `AvatarService.delete(master.id)` + `set_avatar_uploaded_at(master.id, None)` + commit + ответ `PROFILE_UPDATED` + меню профиля.
- `back` → возврат в меню профиля (`open_profile_menu`).
- `skip` (только в онбординге) — см. выше.

`ProfileEdit.waiting_avatar`:
- `message.photo` или `message.document` c `mime_type` startswith `image/` → процесс → `state.clear()` → `PROFILE_UPDATED` + меню.
- Иначе — `AVATAR_NEED_PHOTO`.

## Files

**Новые**
- `src/services/avatars.py` — `AvatarService` + `process_image`.
- `src/handlers/master/avatar.py` — Router, регистрируется в `src/handlers/master/__init__.py`.
- `tests/services/test_avatars.py`
- `tests/repositories/test_masters_avatar.py`
- `tests/api/test_public_avatar.py`
- `migrations/versions/<rev>_add_master_avatar_uploaded_at.py`

**Изменения**
- `src/db/models.py` — `Master.avatar_uploaded_at`.
- `src/api/main.py` — mkdir + StaticFiles mount.
- `src/api/schemas.py` — `avatar_url` в двух Public*Out.
- `src/api/routes/public.py` — `_avatar_url`, заполнение в обоих хендлерах.
- `src/repositories/masters.py` — `set_avatar_uploaded_at`.
- `src/callback_data/profile.py` — `AvatarActionCallback`; расширить `ProfileFieldCallback` значением `"avatar"`.
- `src/fsm/master_register.py` — `waiting_avatar`.
- `src/fsm/profile.py` — `waiting_avatar`.
- `src/handlers/master/registration.py` — после `svc.register` уходим в `MasterRegister.waiting_avatar`, а не в `state.clear()` + DONE.
- `src/handlers/master/profile.py` — кнопка `PROFILE_BTN_AVATAR` в `profile_menu_kb`.
- `src/handlers/master/__init__.py` (или wherever routers подключаются) — подключить avatar router.
- `src/strings.py` + `locales/ru/LC_MESSAGES/bot.ftl` + `locales/hy/LC_MESSAGES/bot.ftl` — новые ключи (см. ниже).
- `src/config.py` — `avatars_dir: Path = Path("/app/data/avatars")`.
- `pyproject.toml` — `pillow`, `pillow-heif`.
- `docker-compose.yml` и `docker-compose.prod.yml` — named volume `avatars_data`, маппинг в `api` и `app_bot`.
- `.env.example` — комментарий про `avatars_dir` если оверрайдить локально (опционально).

## i18n keys

- `REGISTER_ASK_AVATAR` — prompt в онбординге.
- `AVATAR_SKIP_BTN` — текст «Пропустить».
- `PROFILE_BTN_AVATAR` — текст кнопки в меню профиля.
- `PROFILE_AVATAR_NONE` — «Аватара пока нет. Пришлите фото.»
- `PROFILE_AVATAR_REPLACE_BTN` / `PROFILE_AVATAR_DELETE_BTN` / `PROFILE_AVATAR_SEND_BTN` / `BACK_BTN` (последний — если ещё нет).
- `AVATAR_TOO_LARGE` — «Фото слишком большое, до 10 MB.»
- `AVATAR_BAD_IMAGE` — «Не получилось прочитать картинку, попробуйте другое фото.»
- `AVATAR_NEED_PHOTO` — «Пришлите именно фото (не файл, не текст).»

Все ключи — RU + HY.

## Migration

Alembic ревизия:
- `op.add_column('masters', sa.Column('avatar_uploaded_at', sa.TIMESTAMP(timezone=True), nullable=True))`
- Downgrade: `op.drop_column('masters', 'avatar_uploaded_at')`

## Tests

- `tests/services/test_avatars.py`:
  - `process_image` валидного 3000×2000 JPEG → bytes размер 256×256, JPEG, ≤ 60 KB.
  - `process_image(b"not an image")` → `BadImage`.
  - PNG с alpha → корректный JPEG (alpha съелась).
  - HEIC sample → корректный JPEG 256×256 (фикстура — небольшой `.heic` в `tests/fixtures/`).
  - Save/delete на временный каталог.

- `tests/repositories/test_masters_avatar.py`:
  - `set_avatar_uploaded_at(id, ts)` записывает.
  - `set_avatar_uploaded_at(id, None)` зануляет.

- `tests/api/test_public_avatar.py`:
  - `GET /v1/public/masters/<slug>` без аватара → `avatar_url is None`.
  - С `avatar_uploaded_at` выставленным → URL содержит `master.id`, заканчивается на `.jpg`, есть `?v=<digits>`.
  - `GET /v1/public/salons/<slug>` — мастера в списке тоже получают `avatar_url`.

Хендлеры — без отдельных тестов (consistent с текущим coverage). Если поймаем регрессию — добавим точечно.

## Risks / known caveats

- **Telegram file_size может прийти `None`** на некоторых клиентах для compressed photo. Тогда фолбэк: пробуем скачать, и если на стороне Pillow картинка декодируется и проходит — норм; иначе `AVATAR_BAD_IMAGE`. Лимит 10 MB всё равно работает на уровне Telegram сервера для photo.
- **HEIC payload бывает большим** (full-res с iPhone — 3-5 MB). Лимит 10 MB покрывает; если мастер прислал что-то экзотическое крупнее — отвечаем `AVATAR_TOO_LARGE`.
- **`pillow-heif` подтягивает libheif** через wheel'ы. На целевых linux/amd64 (production) и darwin/arm64 (dev) wheel'ы есть, доп. системных пакетов в Dockerfile ставить не нужно. Проверить факт в CI первой сборкой.
- **Атомарная запись** — пишем во временный файл и `os.replace`, чтобы во время записи API не отдал полу-файл.
- **Гонка между API и ботом** на одном volume не критична: API только читает, бот только пишет, дубликатов нет.
- **Старый аватар при замене** — имя файла одно (`<master_id>.jpg`), `os.replace` перезаписывает. Cache-busting через новую `avatar_uploaded_at` гарантирует, что клиенты получат свежую версию.
- **Удаление аккаунта мастера** — если такой код есть, проверить, что аватар-файл тоже удаляется. Если кода нет — это вне scope этой спеки.
