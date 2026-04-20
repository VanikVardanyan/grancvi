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
    "START_UNKNOWN": "Нужна ссылка от клиники.",
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
    "CLIENT_STUB": "Привет! Запись через меню клиники появится позже.",
    "SECTION_COMING_SOON": "Раздел «{section}» — скоро.",
}

_HY: dict[str, Any] = {
    "LANG_PICK_PROMPT": "Выберите язык / Ընտրեք լեզուն",
    "LANG_BTN_RU": "🇷🇺 Русский",
    "LANG_BTN_HY": "🇦🇲 Հայերեն",
    "REGISTER_WELCOME": "Բարի գալուստ! Եկեք կարգավորենք ձեր վարպետի պրոֆիլը։",
    "REGISTER_ASK_NAME": "Ինչպե՞ս դիմել ձեզ։ (անունը, ինչպես կտեսնեն հաճախորդները)",
    "REGISTER_ASK_PHONE": "Նշեք հեռախոսահամար կապի համար։",
    "REGISTER_DONE": "Պատրաստ է։ Պրոֆիլը ստեղծված է։ Ի՞նչ ենք անում հետո։",
    "START_UNKNOWN": "Անհրաժեշտ է հղում կլինիկայից։",
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
    "CLIENT_STUB": "Барев. Клиникайи менyуиc грancуmн кавелана авели ушов.",
    "SECTION_COMING_SOON": "«{section}» бажины шутов.",
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
