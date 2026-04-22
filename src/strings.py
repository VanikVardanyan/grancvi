# ruff: noqa: RUF001
# cSpell:disable
from __future__ import annotations

from contextvars import ContextVar
from types import SimpleNamespace
from typing import Any

# Supported languages. `masters.lang` CHECKs against this set.
SUPPORTED_LANGS: frozenset[str] = frozenset({"ru", "hy"})
DEFAULT_LANG = "ru"

_current_lang: ContextVar[str] = ContextVar("current_lang", default=DEFAULT_LANG)


def set_current_lang(lang: str) -> None:
    """Called by LangMiddleware for each incoming update."""
    _current_lang.set(lang if lang in SUPPORTED_LANGS else DEFAULT_LANG)


def get_current_lang() -> str:
    return _current_lang.get()


_RU: dict[str, Any] = {
    "LANG_PICK_PROMPT": "Выберите язык / Ընտրեք լեզուն",
    "LANG_BTN_RU": "🇷🇺 Русский",
    "LANG_BTN_HY": "🇦🇲 Հայերեն",
    "REGISTER_WELCOME": "Добро пожаловать! Давайте настроим ваш профиль мастера.",
    "REGISTER_ASK_NAME": "Как к вам обращаться? (имя, как его увидят клиенты)",
    "REGISTER_ASK_PHONE": "Укажите телефон для связи.",
    "REGISTER_DONE": "Готово! Профиль создан. Что дальше?",
    "START_WELCOME_BACK": "С возвращением. Что дальше?",
    "MAIN_MENU_TODAY": "📅 Сегодня",
    "MAIN_MENU_ADD": "➕ Добавить запись",
    "MAIN_MENU_CALENDAR": "🗓 Календарь",
    "MAIN_MENU_SETTINGS": "⚙️ Настройки",
    "SETTINGS_MENU_TITLE": "Настройки",
    "SETTINGS_BTN_SERVICES": "Услуги",
    "SETTINGS_BTN_WORK_HOURS": "Часы работы",
    "SETTINGS_BTN_BREAKS": "Перерывы",
    "SETTINGS_BTN_LANGUAGE": "Язык",
    "LANGUAGE_PICK_PROMPT": "Выберите язык:",
    "LANGUAGE_CHANGED": "Язык переключён ✅",
    "SERVICES_EMPTY": "Услуг пока нет. Добавьте первую. Примеры: Чистка, Пломба, Стрижка.",
    "SERVICES_LIST_TITLE": "Ваши услуги:",
    "SERVICES_ITEM_FMT": "{name} · {duration} мин",
    "SERVICES_BTN_ADD": "➕ Добавить услугу",
    "SERVICES_BTN_EDIT": "✏️",
    "SERVICES_BTN_DELETE": "🗑",
    "SERVICES_ADD_ASK_NAME": "Название услуги?",
    "SERVICES_ADD_ASK_DURATION": "Длительность в минутах? (целое число)",
    "SERVICES_ADD_BAD_DURATION": "Нужно целое число минут больше нуля.",
    "SERVICES_ADDED": "Услуга добавлена.",
    "SERVICES_DELETED": "Услуга удалена.",
    "SERVICES_EDIT_MENU": "Что меняем?",
    "SERVICES_EDIT_BTN_NAME": "Название",
    "SERVICES_EDIT_BTN_DURATION": "Длительность",
    "SERVICES_EDIT_BTN_TOGGLE": "Вкл/выкл",
    "SERVICES_EDIT_NAME_PROMPT": "Новое название?",
    "SERVICES_EDIT_DURATION_PROMPT": "Новая длительность в минутах?",
    "SERVICES_UPDATED": "Услуга обновлена.",
    "SERVICES_BTN_BACK": "← назад",
    "WORK_HOURS_TITLE": "Часы работы по дням недели:",
    "WORK_HOURS_DAY_OFF": "выходной",
    "WORK_HOURS_PICK_DAY": "Выберите день:",
    "WORK_HOURS_ASK_START": "Начало рабочего дня? Формат HH:MM, например 10:00.",
    "WORK_HOURS_ASK_END": "Конец рабочего дня? Формат HH:MM, например 19:00.",
    "WORK_HOURS_BAD_FORMAT": "Не разобрал. Ожидаю HH:MM, например 10:00.",
    "WORK_HOURS_BAD_ORDER": "Конец должен быть позже начала.",
    "WORK_HOURS_BTN_DAY_OFF": "Выходной",
    "WORK_HOURS_SAVED": "Сохранено.",
    "WORK_HOURS_BTN_DONE": "Готово",
    "WEEKDAYS": {
        "mon": "Пн",
        "tue": "Вт",
        "wed": "Ср",
        "thu": "Чт",
        "fri": "Пт",
        "sat": "Сб",
        "sun": "Вс",
    },
    "SECTION_COMING_SOON": "Раздел «{section}» — скоро.",
    # --- Epic 4: client booking ---
    "CLIENT_START_NO_MASTER": "Бот пока не настроен. Попросите мастера запустить его.",
    "CLIENT_CHOOSE_SERVICE": "Выберите услугу:",
    "CLIENT_NO_SERVICES": "У мастера пока нет услуг. Попробуйте позже.",
    "CLIENT_CHOOSE_DATE": "Выберите дату:",
    "CLIENT_CHOOSE_TIME": "Свободные слоты на {date}:",
    "CLIENT_NO_SLOTS": "На этот день свободных слотов нет. Выберите другую дату.",
    "CLIENT_ASK_NAME": "Как вас зовут?",
    "CLIENT_BAD_NAME": "Пожалуйста, введите имя (1–60 символов).",
    "CLIENT_ASK_PHONE": "Телефон в формате +374 XX XXX XXX:",
    "CLIENT_BAD_PHONE": "Не разобрал номер. Пример: +374 99 123 456",
    "CLIENT_CONFIRM_TITLE": (
        "📋 Проверьте запись:\n"
        "🧑\u200d⚕️ Услуга: {service}\n"
        "📅 {date} в {time}\n"
        "👤 {name}\n"
        "📞 {phone}\n\n"
        "Подтвердить?"
    ),
    "CLIENT_BTN_CONFIRM": "✅ Подтвердить",
    "CLIENT_BTN_CANCEL": "❌ Отменить",
    "CLIENT_BTN_BACK": "← Назад",
    "CLIENT_SENT": "Заявка отправлена мастеру. Ждите подтверждения.",
    "CLIENT_CANCELLED": "Запись отменена.",
    "CLIENT_SLOT_TAKEN": "Этот слот только что заняли. Выберите другое время.",
    "CLIENT_APPT_CONFIRMED": "Мастер подтвердил вашу запись на {date} в {time}. До встречи!",
    "CLIENT_APPT_REJECTED": "К сожалению, мастер отклонил запись на {date} в {time}.",
    # --- Epic 4: master approval ---
    "APPT_NOTIFY_MASTER": (
        "🔔 Новая заявка\n"
        "🧑 {name}\n"
        "📞 {phone}\n"
        "🧑\u200d⚕️ {service} ({duration} мин)\n"
        "📅 {date} в {time} ({weekday})"
    ),
    "APPT_BTN_CONFIRM": "✅ Подтвердить",
    "APPT_BTN_REJECT": "❌ Отклонить",
    "APPT_BTN_HISTORY": "📋 История клиента",
    "APPT_ALREADY_PROCESSED": "Эта заявка уже обработана.",
    "APPT_CONFIRMED_STAMP": "\n\n✅ Подтверждено в {time}",
    "APPT_REJECTED_STAMP": "\n\n❌ Отклонено в {time}",
    "APPT_HISTORY_TITLE": "История клиента {name} (последние {limit}):",
    "APPT_HISTORY_LINE": "• {date} {time} — {service} — {status}",
    "APPT_HISTORY_EMPTY": "У клиента пока нет истории записей.",
    "APPT_STATUS_CONFIRMED": "✅ подтверждено",
    "APPT_STATUS_CANCELLED": "❌ отменено",
    "APPT_STATUS_REJECTED": "❌ отклонено",
    "APPT_STATUS_COMPLETED": "☑️ завершено",
    "APPT_STATUS_NO_SHOW": "⚠️ не пришёл",
    "MONTH_NAMES": [
        "Январь",
        "Февраль",
        "Март",
        "Апрель",
        "Май",
        "Июнь",
        "Июль",
        "Август",
        "Сентябрь",
        "Октябрь",
        "Ноябрь",
        "Декабрь",
    ],
    "WEEKDAY_SHORT": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
    # --- Epic 5: master manual add ---
    "MANUAL_PICK_CLIENT": "Выбери клиента или создай нового:",
    "MANUAL_NO_RECENT": "Ещё нет клиентов. Нажми ➕ Новый.",
    "MANUAL_SEARCH_PROMPT": "Введи 2+ символа (имя или телефон):",
    "MANUAL_SEARCH_EMPTY": "Ничего не нашёл. Попробуй ещё.",
    "MANUAL_ASK_NAME": "Имя клиента:",
    "MANUAL_NAME_BAD": "Минимум 2 символа. Попробуй ещё.",
    "MANUAL_ASK_PHONE": "Телефон клиента (+374XXXXXXXX):",
    "MANUAL_PHONE_BAD": "Формат: +374XXXXXXXX. Попробуй ещё.",
    "MANUAL_PHONE_DUP": "По этому номеру уже есть клиент «{name}». Использовать его?",
    "MANUAL_ASK_SERVICE": "Выбери услугу:",
    "MANUAL_ASK_DATE": "Выбери дату:",
    "MANUAL_ASK_SLOT": "Выбери время или введи нестандартное:",
    "MANUAL_CUSTOM_PROMPT": (
        "Введи дату и время: ДД.ММ ЧЧ:ММ (или только ЧЧ:ММ для выбранной даты):"
    ),
    "MANUAL_CUSTOM_BAD": "Неверный формат. Пример: 25.04 14:30",
    "MANUAL_CUSTOM_PAST": "Нельзя в прошлое. Выбери другое время.",
    "MANUAL_ASK_COMMENT": "Комментарий (или нажми ⏭ Пропустить):",
    "MANUAL_CONFIRM_CARD": (
        "Подтверди запись:\n👤 {client}\n📞 {phone}\n💇 {service}\n📅 {date} {time}\n📝 {notes}"
    ),
    "MANUAL_SAVED": "✅ Запись сохранена.",
    "MANUAL_CANCELED": "Отменено.",
    "MANUAL_SLOT_TAKEN": "Этот слот только что занят. Выбери другой.",
    "MANUAL_BTN_SEARCH": "🔍 Поиск",
    "MANUAL_BTN_NEW": "➕ Новый",
    "MANUAL_BTN_SEARCH_CANCEL": "⬅ Отмена поиска",
    "MANUAL_BTN_DUP_USE": "Да, использовать",
    "MANUAL_BTN_DUP_RETRY": "Отмена — ввести другой",
    "MANUAL_BTN_CUSTOM_TIME": "➕ Нестандартное время",
    "MANUAL_BTN_BACK": "⬅ Назад",
    "MANUAL_BTN_SKIP": "⏭ Пропустить",
    "MANUAL_BTN_SAVE": "✅ Сохранить",
    "MANUAL_BTN_CANCEL": "❌ Отмена",
    # --- client-side cancellation + notification ---
    "CLIENT_NOTIFY_MANUAL": "Врач записал вас на {date} {time} — {service}.",
    "CLIENT_CANCEL_BUTTON": "❌ Отменить запись",
    "CLIENT_CANCEL_DONE": "Запись отменена.",
    "CLIENT_CANCEL_UNAVAILABLE": "Запись уже недоступна.",
    "MASTER_NOTIFY_CLIENT_CANCELED": "Клиент {name} отменил запись: {date} {time} — {service}.",
    # --- Epic 6: schedule views ---
    "SCHED_DAY_HEADER": "📅 {weekday} {dd} {mon}",
    "SCHED_WORK_HOURS_LINE": "🕐 Рабочие часы: {start}–{end}",
    "SCHED_DAY_OFF_LINE": "🕐 Сегодня выходной",
    "SCHED_APPTS_SECTION": "\n📋 Записи ({count}):",
    "SCHED_APPTS_EMPTY": "\n📋 Записей нет.",
    "SCHED_APPT_LINE": "{emoji} {time}  {client} · {service}",
    "SCHED_FREE_SECTION": "\n🆓 Свободно:",
    "SCHED_FREE_NONE": "\n🆓 Свободных слотов нет.",
    "SCHED_STATUS_PENDING": "⏳",
    "SCHED_STATUS_CONFIRMED": "✅",
    "SCHED_STATUS_COMPLETED": "✅",
    "SCHED_STATUS_NO_SHOW": "❌",
    "DAY_NAV_TODAY": "⬅ Сегодня",
    "DAY_NAV_TOMORROW": "📅 Завтра",
    "DAY_NAV_WEEK": "🗓 Неделя",
    "DAY_NAV_CALENDAR": "🗓 Календарь",
    "DAY_NAV_ADD": "➕ Добавить",
    "DAY_NAV_BACK_TO_WEEK": "⬅ Назад в неделю",
    "DAY_NAV_BACK_TO_CALENDAR": "⬅ Назад в календарь",
    "MARK_PAST_PRESENT": "✅ {time} {short}",
    "MARK_PAST_NO_SHOW": "❌ {time} {short}",
    "MARK_PAST_OK_COMPLETED": "Отмечено: был",
    "MARK_PAST_OK_NO_SHOW": "Отмечено: не пришёл",
    "MARK_PAST_NOT_AVAILABLE": "Запись недоступна",
    "MARK_PAST_NOT_ENDED": "Ещё не закончилась",
    "MARK_PAST_ALREADY_CLOSED": "Уже помечена",
    "WEEK_HEADER": "🗓 Неделя с {dd} {mon}",
    "WEEK_DAY_LINE": "{wd} {dd}.{mm}  {count} зап  {bar}  {pct}%",
    "WEEK_DAY_LINE_OFF": "{wd} {dd}.{mm}  выходной  {bar}",
    "WEEK_BTN_DAY": "{wd} {dd}",
    "CLIENT_SEARCH_PROMPT": "Имя или телефон клиента:",
    "CLIENT_SEARCH_TOO_SHORT": "Минимум 2 символа. Попробуй ещё.",
    "CLIENT_SEARCH_EMPTY": "Никого не нашёл. Попробуй ещё.",
    "CLIENT_PAGE_HEADER": "👤 {name}\n📞 {phone}",
    "CLIENT_PAGE_NOTES_TITLE": "\n\n📝 Заметки:\n{notes}",
    "CLIENT_PAGE_NOTES_EMPTY": "_не указано_",
    "CLIENT_PAGE_HISTORY_TITLE": "\n\n📊 История ({count} записей):",
    "CLIENT_PAGE_HISTORY_EMPTY": "\n\n📊 Истории пока нет.",
    "CLIENT_PAGE_HISTORY_LINE": "{emoji} {dd}.{mm}  {time}  {service}{suffix}",
    "CLIENT_PAGE_HISTORY_MORE": "…и ещё {n}",
    "CLIENT_PAGE_SUFFIX_FUTURE": " · будущая",
    "CLIENT_PAGE_SUFFIX_CANCELLED": " · отменена",
    "CLIENT_PAGE_SUFFIX_REJECTED": " · отклонена",
    "CLIENT_PAGE_BTN_EDIT_NOTES": "✏️ Редактировать заметки",
    "CLIENT_PAGE_BTN_ADD_APPT": "➕ Добавить запись",
    "CLIENT_PAGE_NOT_FOUND": "Клиент не найден.",
    "CLIENT_NOTES_PROMPT": "Новые заметки (или отправь `-` чтобы очистить):",
    "CLIENT_NOTES_SAVED": "Сохранено.",
    # --- Epic 7: reminders ---
    "REMINDER_CLIENT_DAY_BEFORE": "⏰ Напоминание: завтра в {time} — {service}.\nЖдём вас!",
    "REMINDER_CLIENT_TWO_HOURS": "⏰ Через 2 часа у вас запись: {service}, {time}.",
    "REMINDER_MASTER_BEFORE": "⏰ Сейчас {time}: {client_name} — {service}.\n📞 {phone}",
    "REMINDER_PENDING_EXPIRED": (
        "К сожалению, мастер не подтвердил вашу заявку на {date} {time} — {service}.\n"
        "Попробуйте выбрать другое время: /start"
    ),
}

_HY: dict[str, Any] = {
    "LANG_PICK_PROMPT": "Ընտրեք լեզուն / Выберите язык",
    "LANG_BTN_RU": "🇷🇺 Русский",
    "LANG_BTN_HY": "🇦🇲 Հայերեն",
    "REGISTER_WELCOME": "Բարի գալուստ։ Եկեք կարգավորենք ձեր վարպետի պրոֆիլը։",
    "REGISTER_ASK_NAME": "Ինչպե՞ս դիմել ձեզ (անունը, ինչպես հաճախորդները կտեսնեն)",
    "REGISTER_ASK_PHONE": "Նշեք կապի հեռախոսահամարը։",
    "REGISTER_DONE": "Պատրաստ է։ Պրոֆիլը ստեղծված է։ Ի՞նչ հետո։",
    "START_WELCOME_BACK": "Բարի վերադարձ։ Ի՞նչ հետո։",
    "MAIN_MENU_TODAY": "📅 Այսօր",
    "MAIN_MENU_ADD": "➕ Ավելացնել գրանցում",
    "MAIN_MENU_CALENDAR": "🗓 Օրացույց",
    "MAIN_MENU_SETTINGS": "⚙️ Կարգավորումներ",
    "SETTINGS_MENU_TITLE": "Կարգավորումներ",
    "SETTINGS_BTN_SERVICES": "Ծառայություններ",
    "SETTINGS_BTN_WORK_HOURS": "Աշխատանքային ժամեր",
    "SETTINGS_BTN_BREAKS": "Ընդմիջումներ",
    "SETTINGS_BTN_LANGUAGE": "Լեզու",
    "LANGUAGE_PICK_PROMPT": "Ընտրեք լեզուն։",
    "LANGUAGE_CHANGED": "Լեզուն փոխվեց ✅",
    "SERVICES_EMPTY": (
        "Ծառայություններ դեռ չկան։ Ավելացրեք առաջինը։ Օրինակներ՝ Մաքրում, Լցոնում, Սանրվածք։"
    ),
    "SERVICES_LIST_TITLE": "Ձեր ծառայությունները։",
    "SERVICES_ITEM_FMT": "{name} · {duration} րոպե",
    "SERVICES_BTN_ADD": "➕ Ավելացնել ծառայություն",
    "SERVICES_BTN_EDIT": "✏️",
    "SERVICES_BTN_DELETE": "🗑",
    "SERVICES_ADD_ASK_NAME": "Ծառայության անունը՞",
    "SERVICES_ADD_ASK_DURATION": "Տևողությունը րոպեներով՞ (ամբողջ թիվ)",
    "SERVICES_ADD_BAD_DURATION": "Պետք է ամբողջ թիվ լինի՝ 0-ից մեծ։",
    "SERVICES_ADDED": "Ծառայությունը ավելացվեց։",
    "SERVICES_DELETED": "Ծառայությունը ջնջվեց։",
    "SERVICES_EDIT_MENU": "Ի՞նչ փոխենք։",
    "SERVICES_EDIT_BTN_NAME": "Անուն",
    "SERVICES_EDIT_BTN_DURATION": "Տևողություն",
    "SERVICES_EDIT_BTN_TOGGLE": "Միացնել/անջատել",
    "SERVICES_EDIT_NAME_PROMPT": "Նոր անունը՞",
    "SERVICES_EDIT_DURATION_PROMPT": "Նոր տևողությունը րոպեներով՞",
    "SERVICES_UPDATED": "Ծառայությունը թարմացվեց։",
    "SERVICES_BTN_BACK": "← հետ",
    "WORK_HOURS_TITLE": "Աշխատանքային ժամերը ըստ շաբաթվա օրերի։",
    "WORK_HOURS_DAY_OFF": "հանգստյան",
    "WORK_HOURS_PICK_DAY": "Ընտրեք օրը։",
    "WORK_HOURS_ASK_START": "Աշխատանքային օրվա սկիզբը՞ HH:MM ձևաչափով (օր. 10:00)",
    "WORK_HOURS_ASK_END": "Աշխատանքային օրվա ավարտը՞ HH:MM ձևաչափով (օր. 19:00)",
    "WORK_HOURS_BAD_FORMAT": "Չհասկացա։ Սպասվում է HH:MM (օր. 10:00)",
    "WORK_HOURS_BAD_ORDER": "Ավարտը պետք է ավելի ուշ լինի, քան սկիզբը։",
    "WORK_HOURS_BTN_DAY_OFF": "Հանգստյան օր",
    "WORK_HOURS_SAVED": "Պահպանվեց։",
    "WORK_HOURS_BTN_DONE": "Պատրաստ է",
    "WEEKDAYS": {
        "mon": "Երկ",
        "tue": "Երք",
        "wed": "Չրք",
        "thu": "Հնգ",
        "fri": "Ուրբ",
        "sat": "Շաբ",
        "sun": "Կիր",
    },
    "SECTION_COMING_SOON": "«{section}» բաժինը՝ շուտով։",
    # --- Epic 4: client booking ---
    "CLIENT_START_NO_MASTER": "Բոտը դեռ կարգավորված չէ։ Խնդրեք վարպետին գործարկել այն։",
    "CLIENT_CHOOSE_SERVICE": "Ընտրեք ծառայությունը։",
    "CLIENT_NO_SERVICES": "Վարպետը դեռ ծառայություններ չունի։ Փորձեք ավելի ուշ։",
    "CLIENT_CHOOSE_DATE": "Ընտրեք ամսաթիվը։",
    "CLIENT_CHOOSE_TIME": "Ազատ ժամանակներ {date}-ին։",
    "CLIENT_NO_SLOTS": "Այս օրը ազատ ժամեր չկան։ Ընտրեք այլ ամսաթիվ։",
    "CLIENT_ASK_NAME": "Ինչպե՞ս է ձեր անունը։",
    "CLIENT_BAD_NAME": "Խնդրում ենք մուտքագրել անուն (1–60 սիմվոլ)։",
    "CLIENT_ASK_PHONE": "Հեռախոսը՝ +374 XX XXX XXX ձևաչափով։",
    "CLIENT_BAD_PHONE": "Չհասկացա համարը։ Օրինակ՝ +374 99 123 456",
    "CLIENT_CONFIRM_TITLE": (
        "📋 Ստուգեք գրանցումը:\n"
        "🧑\u200d⚕️ Ծառայություն՝ {service}\n"
        "📅 {date} {time}\n"
        "👤 {name}\n"
        "📞 {phone}\n\n"
        "Հաստատե՞լ"
    ),
    "CLIENT_BTN_CONFIRM": "✅ Հաստատել",
    "CLIENT_BTN_CANCEL": "❌ Չեղարկել",
    "CLIENT_BTN_BACK": "← Հետ",
    "CLIENT_SENT": "Հայտը ուղարկվել է վարպետին։ Սպասեք հաստատմանը։",
    "CLIENT_CANCELLED": "Գրանցումը չեղարկվեց։",
    "CLIENT_SLOT_TAKEN": "Այս ժամը արդեն զբաղված է։ Ընտրեք այլ ժամանակ։",
    "CLIENT_APPT_CONFIRMED": "Վարպետը հաստատեց ձեր գրանցումը {date} {time}-ին։ Կտեսնվենք։",
    "CLIENT_APPT_REJECTED": "Ցավոք, վարպետը մերժեց գրանցումը {date} {time}-ին։",
    # --- Epic 4: master approval ---
    "APPT_NOTIFY_MASTER": (
        "🔔 Նոր հայտ\n"
        "🧑 {name}\n"
        "📞 {phone}\n"
        "🧑\u200d⚕️ {service} ({duration} րոպե)\n"
        "📅 {date} {time} ({weekday})"
    ),
    "APPT_BTN_CONFIRM": "✅ Հաստատել",
    "APPT_BTN_REJECT": "❌ Մերժել",
    "APPT_BTN_HISTORY": "📋 Հաճախորդի պատմություն",
    "APPT_ALREADY_PROCESSED": "Այս հայտը արդեն մշակված է։",
    "APPT_CONFIRMED_STAMP": "\n\n✅ Հաստատված {time}-ին",
    "APPT_REJECTED_STAMP": "\n\n❌ Մերժված {time}-ին",
    "APPT_HISTORY_TITLE": "{name} հաճախորդի պատմություն (վերջին {limit})։",
    "APPT_HISTORY_LINE": "• {date} {time} — {service} — {status}",
    "APPT_HISTORY_EMPTY": "Հաճախորդը դեռ պատմություն չունի։",
    "APPT_STATUS_CONFIRMED": "✅ հաստատված",
    "APPT_STATUS_CANCELLED": "❌ չեղարկված",
    "APPT_STATUS_REJECTED": "❌ մերժված",
    "APPT_STATUS_COMPLETED": "☑️ ավարտված",
    "APPT_STATUS_NO_SHOW": "⚠️ չի եկել",
    "MONTH_NAMES": [
        "Հունվար",
        "Փետրվար",
        "Մարտ",
        "Ապրիլ",
        "Մայիս",
        "Հունիս",
        "Հուլիս",
        "Օգոստոս",
        "Սեպտեմբեր",
        "Հոկտեմբեր",
        "Նոյեմբեր",
        "Դեկտեմբեր",
    ],
    "WEEKDAY_SHORT": ["Երկ", "Երք", "Չրք", "Հնգ", "Ուրբ", "Շաբ", "Կիր"],
    # --- Epic 5: master manual add ---
    "MANUAL_PICK_CLIENT": "Ընտրիր հաճախորդին կամ ստեղծիր նորին։",
    "MANUAL_NO_RECENT": "Դեռ հաճախորդներ չկան։ Սեղմիր ➕ Նոր։",
    "MANUAL_SEARCH_PROMPT": "Մուտքագրիր 2+ սիմվոլ (անուն կամ հեռախոս)։",
    "MANUAL_SEARCH_EMPTY": "Ոչինչ չգտնվեց։ Փորձիր կրկին։",
    "MANUAL_ASK_NAME": "Հաճախորդի անունը։",
    "MANUAL_NAME_BAD": "Առնվազն 2 սիմվոլ։ Փորձիր կրկին։",
    "MANUAL_ASK_PHONE": "Հաճախորդի հեռախոսահամարը (+374XXXXXXXX)։",
    "MANUAL_PHONE_BAD": "Ձևաչափը՝ +374XXXXXXXX։ Փորձիր կրկին։",
    "MANUAL_PHONE_DUP": "Այս համարով արդեն կա հաճախորդ «{name}»։ Օգտագործե՞լ նրան։",
    "MANUAL_ASK_SERVICE": "Ընտրիր ծառայությունը։",
    "MANUAL_ASK_DATE": "Ընտրիր ամսաթիվը։",
    "MANUAL_ASK_SLOT": "Ընտրիր ժամանակը կամ մուտքագրիր ոչ ստանդարտ։",
    "MANUAL_CUSTOM_PROMPT": (
        "Մուտքագրիր ամսաթիվը և ժամանակը՝ ՕՕ.ԱԱ ԺԺ:ՐՐ (կամ միայն ԺԺ:ՐՐ ընտրված ամսաթվի համար)։"
    ),
    "MANUAL_CUSTOM_BAD": "Սխալ ձևաչափ։ Օրինակ՝ 25.04 14:30",
    "MANUAL_CUSTOM_PAST": "Անցյալ ժամանակ չի կարելի ընտրել։ Ընտրիր այլ ժամանակ։",
    "MANUAL_ASK_COMMENT": "Մեկնաբանություն (կամ սեղմիր ⏭ Բաց թողնել)։",
    "MANUAL_CONFIRM_CARD": (
        "Հաստատիր գրանցումը։\n👤 {client}\n📞 {phone}\n💇 {service}\n📅 {date} {time}\n📝 {notes}"
    ),
    "MANUAL_SAVED": "✅ Գրանցումը պահպանվեց։",
    "MANUAL_CANCELED": "Չեղարկվեց։",
    "MANUAL_SLOT_TAKEN": "Այս ժամանակը հենց նոր զբաղվեց։ Ընտրիր այլը։",
    "MANUAL_BTN_SEARCH": "🔍 Որոնում",
    "MANUAL_BTN_NEW": "➕ Նոր",
    "MANUAL_BTN_SEARCH_CANCEL": "⬅ Չեղարկել որոնումը",
    "MANUAL_BTN_DUP_USE": "Այո, օգտագործել",
    "MANUAL_BTN_DUP_RETRY": "Չեղարկել — մուտքագրել այլը",
    "MANUAL_BTN_CUSTOM_TIME": "➕ Ոչ ստանդարտ ժամանակ",
    "MANUAL_BTN_BACK": "⬅ Հետ",
    "MANUAL_BTN_SKIP": "⏭ Բաց թողնել",
    "MANUAL_BTN_SAVE": "✅ Պահպանել",
    "MANUAL_BTN_CANCEL": "❌ Չեղարկել",
    # --- client-side cancellation + notification ---
    "CLIENT_NOTIFY_MANUAL": "Վարպետը ձեզ գրանցել է {date} {time} — {service}։",
    "CLIENT_CANCEL_BUTTON": "❌ Չեղարկել գրանցումը",
    "CLIENT_CANCEL_DONE": "Գրանցումը չեղարկվեց։",
    "CLIENT_CANCEL_UNAVAILABLE": "Գրանցումը արդեն հասանելի չէ։",
    "MASTER_NOTIFY_CLIENT_CANCELED": (
        "Հաճախորդը {name} չեղարկեց գրանցումը՝ {date} {time} — {service}։"
    ),
    # --- Epic 6: schedule views ---
    "SCHED_DAY_HEADER": "📅 {weekday} {dd} {mon}",
    "SCHED_WORK_HOURS_LINE": "🕐 Աշխատանքային ժամեր՝ {start}–{end}",
    "SCHED_DAY_OFF_LINE": "🕐 Այսօր հանգստյան օր է",
    "SCHED_APPTS_SECTION": "\n📋 Գրանցումներ ({count}):",
    "SCHED_APPTS_EMPTY": "\n📋 Գրանցումներ չկան։",
    "SCHED_APPT_LINE": "{emoji} {time}  {client} · {service}",
    "SCHED_FREE_SECTION": "\n🆓 Ազատ ժամանակներ։",
    "SCHED_FREE_NONE": "\n🆓 Ազատ ժամանակներ չկան։",
    "SCHED_STATUS_PENDING": "⏳",
    "SCHED_STATUS_CONFIRMED": "✅",
    "SCHED_STATUS_COMPLETED": "✅",
    "SCHED_STATUS_NO_SHOW": "❌",
    "DAY_NAV_TODAY": "⬅ Այսօր",
    "DAY_NAV_TOMORROW": "📅 Վաղը",
    "DAY_NAV_WEEK": "🗓 Շաբաթ",
    "DAY_NAV_CALENDAR": "🗓 Օրացույց",
    "DAY_NAV_ADD": "➕ Ավելացնել",
    "DAY_NAV_BACK_TO_WEEK": "⬅ Վերադառնալ շաբաթ",
    "DAY_NAV_BACK_TO_CALENDAR": "⬅ Վերադառնալ օրացույց",
    "MARK_PAST_PRESENT": "✅ {time} {short}",
    "MARK_PAST_NO_SHOW": "❌ {time} {short}",
    "MARK_PAST_OK_COMPLETED": "Նշված է՝ եղել է",
    "MARK_PAST_OK_NO_SHOW": "Նշված է՝ չի եկել",
    "MARK_PAST_NOT_AVAILABLE": "Գրանցումը հասանելի չէ",
    "MARK_PAST_NOT_ENDED": "Դեռ չի ավարտվել",
    "MARK_PAST_ALREADY_CLOSED": "Արդեն նշված է",
    "WEEK_HEADER": "🗓 Շաբաթը սկսած {dd} {mon}",
    "WEEK_DAY_LINE": "{wd} {dd}.{mm}  {count} գրանցում  {bar}  {pct}%",
    "WEEK_DAY_LINE_OFF": "{wd} {dd}.{mm}  հանգստյան օր  {bar}",
    "WEEK_BTN_DAY": "{wd} {dd}",
    "CLIENT_SEARCH_PROMPT": "Հաճախորդի անունը կամ հեռախոսը։",
    "CLIENT_SEARCH_TOO_SHORT": "Առնվազն 2 սիմվոլ։ Փորձիր կրկին։",
    "CLIENT_SEARCH_EMPTY": "Ոչ մեկ չգտնվեց։ Փորձիր կրկին։",
    "CLIENT_PAGE_HEADER": "👤 {name}\n📞 {phone}",
    "CLIENT_PAGE_NOTES_TITLE": "\n\n📝 Նշումներ:\n{notes}",
    "CLIENT_PAGE_NOTES_EMPTY": "_նշված չէ_",
    "CLIENT_PAGE_HISTORY_TITLE": "\n\n📊 Պատմություն ({count} գրանցում):",
    "CLIENT_PAGE_HISTORY_EMPTY": "\n\n📊 Պատմություն դեռ չկա։",
    "CLIENT_PAGE_HISTORY_LINE": "{emoji} {dd}.{mm}  {time}  {service}{suffix}",
    "CLIENT_PAGE_HISTORY_MORE": "…և ևս {n}",
    "CLIENT_PAGE_SUFFIX_FUTURE": "  · ապագա",
    "CLIENT_PAGE_SUFFIX_CANCELLED": "  · չեղարկված",
    "CLIENT_PAGE_SUFFIX_REJECTED": "  · մերժված",
    "CLIENT_PAGE_BTN_EDIT_NOTES": "✏️  Խմբագրել նշումները",
    "CLIENT_PAGE_BTN_ADD_APPT": "➕ Ավելացնել գրանցում",
    "CLIENT_PAGE_NOT_FOUND": "Հաճախորդը չի գտնվել։",
    "CLIENT_NOTES_PROMPT": "Նոր նշումներ (կամ ուղարկիր `-` մաքրելու համար)։",
    "CLIENT_NOTES_SAVED": "Պահպանվեց։",
    # --- Epic 7: reminders ---
    "REMINDER_CLIENT_DAY_BEFORE": "⏰ Հիշեցում․ վաղը {time} — {service}։\nՍպասում ենք ձեզ։",
    "REMINDER_CLIENT_TWO_HOURS": "⏰ 2 ժամից ձեր գրանցումն է՝ {service}, {time}։",
    "REMINDER_MASTER_BEFORE": "⏰ Հիմա {time}։ {client_name} — {service}։\n📞 {phone}",
    "REMINDER_PENDING_EXPIRED": (
        "Ցավոք, վարպետը չի հաստատել ձեր հայտը {date} {time} — {service}։\n"
        "Փորձեք ընտրել այլ ժամանակ՝ /start"
    ),
}

_BUNDLES: dict[str, dict[str, Any]] = {"ru": _RU, "hy": _HY}


class _StringsProxy:
    """Module-like proxy: `strings.REGISTER_WELCOME` resolves against the current lang."""

    def __getattr__(self, key: str) -> Any:
        bundle = _BUNDLES.get(get_current_lang(), _RU)
        try:
            return bundle[key]
        except KeyError as exc:
            # Fall back to RU so a missing HY key doesn't crash the bot.
            if key in _RU:
                return _RU[key]
            raise AttributeError(key) from exc


strings: Any = _StringsProxy()


def get_bundle(lang: str) -> SimpleNamespace:
    """For tests / ad-hoc access to a language bundle without touching the ContextVar."""
    return SimpleNamespace(**_BUNDLES.get(lang, _RU))
