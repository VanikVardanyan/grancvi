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
    """Called by LangMiddleware for each incoming update.

    Forced to RU until the HY bundle is human-translated; infrastructure kept
    intact so flipping back is a one-line change.
    """
    del lang
    _current_lang.set(DEFAULT_LANG)


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
    "STUB_TODAY": "Здесь будет список записей на сегодня (Эпик 5).",
    "STUB_ADD": "Здесь будет ручное добавление записи (Эпик 5).",
    "STUB_CALENDAR": "Здесь будет календарь (Эпик 5).",
    "SETTINGS_MENU_TITLE": "Настройки",
    "SETTINGS_BTN_SERVICES": "Услуги",
    "SETTINGS_BTN_WORK_HOURS": "Часы работы",
    "SETTINGS_BTN_BREAKS": "Перерывы",
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
}

_HY: dict[str, Any] = {
    "LANG_PICK_PROMPT": "Выберите язык / Ընտրեք լեզուն",
    "LANG_BTN_RU": "🇷🇺 Русский",
    "LANG_BTN_HY": "🇦🇲 Հայերեն",
    "REGISTER_WELCOME": "Բարի գալուստ! Եկեք կարգավորենք ձեր վարպետի պրոֆիլը։",
    "REGISTER_ASK_NAME": "Ինչպե՞ս դիմել ձեզ։ (անունը, ինչպես կտեսնեն հաճախորդները)",
    "REGISTER_ASK_PHONE": "Նշեք հեռախոսահամար կապի համար։",
    "REGISTER_DONE": "Պատրաստ է։ Պրոֆիլը ստեղծված է։ Ի՞նչ ենք անում հետո։",
    "START_WELCOME_BACK": "Բարի վերադարձ։ Ի՞նչ ենք անում հետո։",
    "MAIN_MENU_TODAY": "📅 Այսօր",
    "MAIN_MENU_ADD": "➕ Ավելացնել գրանցում",
    "MAIN_MENU_CALENDAR": "🗓 Օրացույց",
    "MAIN_MENU_SETTINGS": "⚙️ Կարգավորումներ",
    "STUB_TODAY": "Այստեղ կլինի այսօրվա գրանցումների ցանկը (Էпиկ 5)։",
    "STUB_ADD": "Այստеgh կлини ձеռqovy граnцуmи аvelаcуm (Эпик 5)։",
    "STUB_CALENDAR": "Այстеgh կлини оrаcуйcы (Эпик 5)։",
    "SETTINGS_MENU_TITLE": "Կарgаворуmнер",
    "SETTINGS_BTN_SERVICES": "Ծаռаyутhyуnnер",
    "SETTINGS_BTN_WORK_HOURS": "Ашхатаnаyин жамер",
    "SETTINGS_BTN_BREAKS": "Yndmиjуmнер",
    "SERVICES_EMPTY": "Ծаռаyутhyуnnер деռ чkаn։ Авелацреq аռаjиnы։ Ориnаk: Маqруm, Пломб, Сафрвел։",
    "SERVICES_LIST_TITLE": "Ձер ծаռаyутhyуnnеры:",
    "SERVICES_ITEM_FMT": "{name} · {duration} роpе",
    "SERVICES_BTN_ADD": "➕ Авелацнел ծаռаyутhyуn",
    "SERVICES_BTN_EDIT": "✏️",
    "SERVICES_BTN_DELETE": "🗑",
    "SERVICES_ADD_ASK_NAME": "Ծаռаyутhyуnи аnуnы?",
    "SERVICES_ADD_ASK_DURATION": "Теволутhyуnы рoпеnеров? (амбогhj тhив)",
    "SERVICES_ADD_BAD_DURATION": "Петк е амбогhj тhив зроyиc меծ։",
    "SERVICES_ADDED": "Ծаռаyутhyуnn авелацвац е։",
    "SERVICES_DELETED": "Ծаռаyутhyуnы jnjvаc е։",
    "SERVICES_EDIT_MENU": "Inч еnk фохуm։",
    "SERVICES_EDIT_BTN_NAME": "Аnуn",
    "SERVICES_EDIT_BTN_DURATION": "Теволутhyун",
    "SERVICES_EDIT_BTN_TOGGLE": "Алацнел/аnjател",
    "SERVICES_EDIT_NAME_PROMPT": "Нор аnуn?",
    "SERVICES_EDIT_DURATION_PROMPT": "Нор теволутhyуnы рoпеnеров?",
    "SERVICES_UPDATED": "Ծаռаyутhyуnы тhаrmацваc е։",
    "SERVICES_BTN_BACK": "← hет",
    "WORK_HOURS_TITLE": "Аshхатаnаyин жамер: ынд шаbатvа ореdelери:",
    "WORK_HOURS_DAY_OFF": "hаngистyин",
    "WORK_HOURS_PICK_DAY": "Ынtреq орн:",
    "WORK_HOURS_ASK_START": "Аshхатаnаyин орvа сkизбы? Форmат HH:MM, оринаk: 10:00.",
    "WORK_HOURS_ASK_END": "Аshхатаnаyин орvа верjы? Форmат HH:MM, оринаk: 19:00.",
    "WORK_HOURS_BAD_FORMAT": "Чhаskаca. Спасум еm HH:MM, оринаk: 10:00.",
    "WORK_HOURS_BAD_ORDER": "Верjы петк е лини сkизбиc уш.",
    "WORK_HOURS_BTN_DAY_OFF": "Hаngистyин",
    "WORK_HOURS_SAVED": "Паhпаnvаc е.",
    "WORK_HOURS_BTN_DONE": "Патраст е",
    "WEEKDAYS": {
        "mon": "Еркк",
        "tue": "Еркш",
        "wed": "Чрк",
        "thu": "Хнг",
        "fri": "Урб",
        "sat": "Шбт",
        "sun": "Кир",
    },
    "SECTION_COMING_SOON": "«{section}» бажины шутов.",
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
