# bot.py
# Полный Telegram-бот по ТЗ (aiogram 3.7+)
# ВНИМАНИЕ: все кнопки – inline под сообщениями; главное меню скрывается после выбора разделов A–D,
# остаются только "Поддержка" и "Назад в меню".
# Хранилище: SQLite ("ads.db"). Фото сохраняются как file_id через запятую.
# Контакты продавца/репетитора показываются ТОЛЬКО после лайка.
# Фильтр по учебному заведению при просмотре ленты: после выбора категории/предмета — выбор "Москва" или "Ввести своё".
# Токен бота указан пользователем в ТЗ.

import asyncio
import logging
import sqlite3
from typing import List, Dict, Any, Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
)

API_TOKEN = "8342403001:AAHnSqngTU3j0z5WE6uIBH_U5I5oh3qG9NI"

# ----------------------- ЛОГИ -----------------------
logging.basicConfig(level=logging.INFO)

# ----------------------- БД ------------------------
conn = sqlite3.connect("ads.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS goods(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    condition TEXT NOT NULL,
    description TEXT NOT NULL,
    price TEXT NOT NULL,
    photos TEXT DEFAULT '',
    nickname TEXT NOT NULL,
    school TEXT NOT NULL
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS tutors(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    subject TEXT NOT NULL,
    school TEXT NOT NULL,
    achievements TEXT NOT NULL,
    details TEXT NOT NULL,
    price TEXT NOT NULL,
    photos TEXT DEFAULT '',
    nickname TEXT NOT NULL
)
""")
conn.commit()

# ----------------------- КОНСТАНТЫ ------------------------
# Категории товаров
GOODS_CATEGORIES = [
    "🧥 Худак",     # худи/худак
    "👖 Джинсы",
    "👕 Футболка",
    "✏️ Канцелярия",
    "💻 Техника",
    "👗 Одежда",
    "📦 Другое"
]

# Предметы (репетиторы)
TUTOR_SUBJECTS = [
    "📐 Математика",
    "📘 Русский язык",
    "🧬 Биология",
    "🇬🇧 Английский язык",
    "🔭 Физика",
    "💻 Информатика",
    "⚖️ Право",
    "📜 Обществознание",
    "🏺 История",
    "⚗️ Химия",
    "🗺 География",
    "📚 Литература",
    "➗ Прикладная математика",
]

SUPPORT_NICK = "@zloyzloyy"

# ----------------------- ВСПОМОГАТЕЛЬНОЕ ------------------------
def kb_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Смотреть ленту объявлений", callback_data="menu_feed")],
        [InlineKeyboardButton(text="🛒 Создать объявление о продаже", callback_data="menu_create_good")],
        [InlineKeyboardButton(text="🔍 Поиск репетитора", callback_data="menu_find_tutor")],
        [InlineKeyboardButton(text="🎓 Размещение услуги репетитора", callback_data="menu_create_tutor")],
        [InlineKeyboardButton(text="📂 Мои объявления", callback_data="menu_my_ads")],
        [InlineKeyboardButton(text="💬 Поддержка", callback_data="menu_support")]
    ])

def kb_back_support() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="menu_back")],
        [InlineKeyboardButton(text="💬 Поддержка", callback_data="menu_support")]
    ])

def kb_goods_categories(include_nav=True) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=cat, callback_data=f"feed_cat_{cat}") ] for cat in GOODS_CATEGORIES]
    if include_nav:
        rows += [[InlineKeyboardButton(text="🔙 Назад в меню", callback_data="menu_back")],
                 [InlineKeyboardButton(text="💬 Поддержка", callback_data="menu_support")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_tutor_subjects(include_nav=True) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=sub, callback_data=f"feed_sub_{sub}") ] for sub in TUTOR_SUBJECTS]
    if include_nav:
        rows += [[InlineKeyboardButton(text="🔙 Назад в меню", callback_data="menu_back")],
                 [InlineKeyboardButton(text="💬 Поддержка", callback_data="menu_support")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_school_selector(prefix: str) -> InlineKeyboardMarkup:
    # prefix: "feed" (поиск), "good" (создание товара), "tutor" (создание репетитора)
    # Выбор направления: Москва (все вузы/школы внутри МСК) или ввести своё
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏙 Москва (все внутри МСК)", callback_data=f"{prefix}_school_moscow")],
        [InlineKeyboardButton(text="✍️ Ввести своё учебное", callback_data=f"{prefix}_school_custom")],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="menu_back")],
        [InlineKeyboardButton(text="💬 Поддержка", callback_data="menu_support")],
    ])

def kb_like_dislike(ad_type: str, ad_id: int) -> InlineKeyboardMarkup:
    # ad_type: "goods" | "tutors"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="❤️ Нравится", callback_data=f"like_{ad_type}_{ad_id}"),
            InlineKeyboardButton(text="👎 Дальше", callback_data=f"dis_{ad_type}_{ad_id}")
        ],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="menu_back")],
        [InlineKeyboardButton(text="💬 Поддержка", callback_data="menu_support")],
    ])

def kb_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Опубликовать", callback_data="confirm_publish")],
        [InlineKeyboardButton(text="📝 Редактировать", callback_data="confirm_edit")],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="menu_back")],
        [InlineKeyboardButton(text="💬 Поддержка", callback_data="menu_support")],
    ])

def kb_my_ads_entry() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Мои товары", callback_data="my_goods")],
        [InlineKeyboardButton(text="🧑‍🏫 Мои репетиторы", callback_data="my_tutors")],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="menu_back")],
        [InlineKeyboardButton(text="💬 Поддержка", callback_data="menu_support")],
    ])

def kb_my_ad_controls(ad_type: str, idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"my_edit_{ad_type}_{idx}")],
        [InlineKeyboardButton(text="➡️ Следующее", callback_data=f"my_next_{ad_type}_{idx}")],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="menu_back")],
        [InlineKeyboardButton(text="💬 Поддержка", callback_data="menu_support")],
    ])

def kb_photos_controls(prefix: str) -> InlineKeyboardMarkup:
    # Для шага фотографий: можно завершить приём или пропустить
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Готово (1–3 фото)", callback_data=f"{prefix}_photos_done")],
        [InlineKeyboardButton(text="⏭️ Пропустить фото", callback_data=f"{prefix}_photos_skip")],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="menu_back")],
        [InlineKeyboardButton(text="💬 Поддержка", callback_data="menu_support")],
    ])

# ----------------------- FEED СОСТОЯНИЕ ------------------------
# Состояние ленты (по одному объявлению)
# feed_state[user_id] = {
#   "type": "goods"|"tutors",
#   "category" or "subject": str,
#   "school_filter": "Москва" | str,
#   "ids": [list of ids],
#   "i": current index (int)
# }
feed_state: Dict[int, Dict[str, Any]] = {}

# Состояние "Мои объявления"
# my_state[user_id] = {"type": "goods"|"tutors", "ids":[...], "i": int}
my_state: Dict[int, Dict[str, Any]] = {}

# ----------------------- FSM СОЗДАНИЯ ------------------------
class GoodFSM(StatesGroup):
    title = State()
    category = State()
    condition = State()
    description = State()
    price = State()
    photos = State()
    nickname = State()
    school_choice = State()  # выбор Москва / ввести своё
    school = State()
    confirm = State()
    editing = State()  # признак редактирования (храним флаг в data)

class TutorFSM(StatesGroup):
    name = State()
    subject = State()
    school_choice = State()
    school = State()
    achievements = State()
    details = State()
    price = State()
    photos = State()
    nickname = State()
    confirm = State()
    editing = State()

# ----------------------- ЗАПУСК ------------------------
bot = Bot(API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ----------------------- СТАРТ + МЕНЮ ------------------------
@router.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Добро пожаловать! Выберите раздел:",
        reply_markup=kb_main_menu()
    )

@router.callback_query(F.data == "menu_back")
async def menu_back(call: CallbackQuery, state: FSMContext):
    await state.clear()
    feed_state.pop(call.from_user.id, None)
    my_state.pop(call.from_user.id, None)
    await call.message.answer("Главное меню:", reply_markup=kb_main_menu())
    await call.answer()

@router.callback_query(F.data == "menu_support")
async def menu_support(call: CallbackQuery):
    await call.message.answer(
        f"Если возникли проблемы — обратитесь в поддержку: {SUPPORT_NICK}",
        reply_markup=kb_back_support()
    )
    await call.answer()

# ======================= РАЗДЕЛ A: ЛЕНТА ТОВАРОВ =======================
@router.callback_query(F.data == "menu_feed")
async def menu_feed(call: CallbackQuery):
    await call.message.answer(
        "Выберите категорию товаров:",
        reply_markup=kb_goods_categories()
    )
    await call.answer()

@router.callback_query(F.data.startswith("feed_cat_"))
async def feed_choose_category(call: CallbackQuery, state: FSMContext):
    cat = call.data.replace("feed_cat_", "")
    # после выбора категории — выбор школы/вуза: Москва или ввести своё
    await call.message.answer(
        f"Категория: <b>{cat}</b>\nТеперь выберите способ фильтра по учебному заведению:",
        reply_markup=kb_school_selector(prefix="feed_goods")
    )
    # Временное сохранение выбранной категории в FSM контекст для поиска
    await state.update_data(feed_type="goods", feed_category=cat)
    await call.answer()

@router.callback_query(F.data.in_(["feed_goods_school_moscow", "feed_goods_school_custom"]))
async def feed_goods_school_filter(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cat = data.get("feed_category")
    if call.data.endswith("moscow"):
        school = "Москва"
        await begin_goods_feed(call, category=cat, school_filter=school)
        await call.answer()
    else:
        # запросить ввод учебного заведения текстом
        await state.update_data(feed_school_mode="custom")
        await call.message.answer(
            "Введите название школы/ВУЗа (точное название):",
            reply_markup=kb_back_support()
        )
        await state.set_state(GoodFSM.school)  # переиспользуем для приема текста в поиске
        await call.answer()

@router.message(StateFilter(GoodFSM.school))
async def feed_goods_school_entered(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("feed_type") == "goods":
        cat = data.get("feed_category")
        school = message.text.strip()
        await begin_goods_feed_from_message(message, category=cat, school_filter=school)
        await state.clear()

async def begin_goods_feed(call: CallbackQuery, category: str, school_filter: str):
    cur.execute(
        "SELECT id, title, condition, description, price, photos, nickname, school "
        "FROM goods WHERE category=? AND ( ( ?='Москва' AND lower(school) LIKE '%моск%' ) OR lower(school)=lower(?) ) "
        "ORDER BY id DESC",
        (category, school_filter, school_filter)
    )
    rows = cur.fetchall()
    uid = call.from_user.id
    feed_state[uid] = {"type": "goods", "category": category, "school_filter": school_filter, "ids": [r[0] for r in rows], "i": 0}
    if not rows:
        await call.message.answer("Пока что объявлений из этой категории и учебного заведения нет.", reply_markup=kb_back_support())
        return
    await show_good_by_row(call.message, rows[0])

async def begin_goods_feed_from_message(message: Message, category: str, school_filter: str):
    cur.execute(
        "SELECT id, title, condition, description, price, photos, nickname, school "
        "FROM goods WHERE category=? AND ( ( ?='Москва' AND lower(school) LIKE '%моск%' ) OR lower(school)=lower(?) ) "
        "ORDER BY id DESC",
        (category, school_filter, school_filter)
    )
    rows = cur.fetchall()
    uid = message.from_user.id
    feed_state[uid] = {"type": "goods", "category": category, "school_filter": school_filter, "ids": [r[0] for r in rows], "i": 0}
    if not rows:
        await message.answer("Пока что объявлений из этой категории и учебного заведения нет.", reply_markup=kb_back_support())
        return
    await show_good_by_row(message, rows[0])

async def show_good_by_row(target_message: Message, row: tuple):
    # row: (id, title, condition, description, price, photos, nickname, school)
    photos = (row[5] or "").split(",") if row[5] else []
    caption = (
        f"<b>{row[1]}</b>\n"
        f"Состояние: {row[2]}\n"
        f"Описание: {row[3]}\n"
        f"Цена: {row[4]}"
    )
    if photos:
        await target_message.answer_photo(
            photo=photos[0],
            caption=caption,
            reply_markup=kb_like_dislike("goods", row[0])
        )
    else:
        await target_message.answer(
            caption,
            reply_markup=kb_like_dislike("goods", row[0])
        )

@router.callback_query(F.data.startswith("like_goods_"))
async def like_goods(call: CallbackQuery):
    ad_id = int(call.data.split("_")[-1])
    # На лайк: показать @ник и перейти к следующему объявлению
    cur.execute("SELECT nickname FROM goods WHERE id=?", (ad_id,))
    row = cur.fetchone()
    if row:
        await call.message.answer(f"Контакт продавца: {row[0]}")
    await show_next_in_feed(call)
    await call.answer()

@router.callback_query(F.data.startswith("dis_goods_"))
async def dislike_goods(call: CallbackQuery):
    await show_next_in_feed(call)
    await call.answer()

async def show_next_in_feed(call: CallbackQuery):
    uid = call.from_user.id
    st = feed_state.get(uid)
    if not st:
        await call.message.answer("Лента завершена.", reply_markup=kb_back_support())
        return
    st["i"] += 1
    ids = st["ids"]
    if st["i"] >= len(ids):
        await call.message.answer("Объявления закончились.", reply_markup=kb_back_support())
        return
    ad_type = st["type"]
    next_id = ids[st["i"]]
    if ad_type == "goods":
        cur.execute(
            "SELECT id, title, condition, description, price, photos, nickname, school FROM goods WHERE id=?",
            (next_id,)
        )
        row = cur.fetchone()
        if row:
            await show_good_by_row(call.message, row)
    else:
        cur.execute(
            "SELECT id, name, subject, school, achievements, details, price, photos, nickname FROM tutors WHERE id=?",
            (next_id,)
        )
        row = cur.fetchone()
        if row:
            await show_tutor_by_row(call.message, row)

# ======================= РАЗДЕЛ Б: СОЗДАНИЕ ТОВАРА =======================
@router.callback_query(F.data == "menu_create_good")
async def create_good_start(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(GoodFSM.title)
    await call.message.answer("Введите <b>Название</b> товара:", reply_markup=kb_back_support())
    await call.answer()

@router.message(StateFilter(GoodFSM.title))
async def good_title_step(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(GoodFSM.category)
    # выбор категории кнопками
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=cat, callback_data=f"good_cat_{cat}") ] for cat in GOODS_CATEGORIES
    ] + [
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="menu_back")],
        [InlineKeyboardButton(text="💬 Поддержка", callback_data="menu_support")],
    ])
    await message.answer("Выберите <b>Категорию</b>:", reply_markup=kb)

@router.callback_query(StateFilter(GoodFSM.category), F.data.startswith("good_cat_"))
async def good_category_step(call: CallbackQuery, state: FSMContext):
    category = call.data.replace("good_cat_", "")
    await state.update_data(category=category)
    await state.set_state(GoodFSM.condition)
    await call.message.answer("Укажите <b>Состояние вещи</b>:", reply_markup=kb_back_support())
    await call.answer()

@router.message(StateFilter(GoodFSM.condition))
async def good_condition_step(message: Message, state: FSMContext):
    await state.update_data(condition=message.text.strip())
    await state.set_state(GoodFSM.description)
    await message.answer("Введите <b>Описание</b>:", reply_markup=kb_back_support())

@router.message(StateFilter(GoodFSM.description))
async def good_description_step(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await state.set_state(GoodFSM.price)
    await message.answer("Укажите <b>Стоимость</b>:", reply_markup=kb_back_support())

@router.message(StateFilter(GoodFSM.price))
async def good_price_step(message: Message, state: FSMContext):
    await state.update_data(price=message.text.strip(), photos=[])
    await state.set_state(GoodFSM.photos)
    await message.answer(
        "Отправьте 1–3 <b>фото</b> (по одному сообщению). Когда закончите — нажмите «Готово».\n"
        "Можно пропустить.",
        reply_markup=kb_photos_controls(prefix="good")
    )

@router.message(StateFilter(GoodFSM.photos), F.photo)
async def good_photos_collect(message: Message, state: FSMContext):
    data = await state.get_data()
    photos: List[str] = data.get("photos", [])
    if len(photos) >= 3:
        await message.answer("Вы уже добавили 3 фото. Нажмите «Готово».", reply_markup=kb_photos_controls(prefix="good"))
        return
    file_id = message.photo[-1].file_id
    photos.append(file_id)
    await state.update_data(photos=photos)
    await message.answer(f"Фото добавлено ({len(photos)}/3).", reply_markup=kb_photos_controls(prefix="good"))

@router.callback_query(StateFilter(GoodFSM.photos), F.data == "good_photos_done")
async def good_photos_done(call: CallbackQuery, state: FSMContext):
    await state.set_state(GoodFSM.nickname)
    await call.message.answer("Укажите <b>ник в Telegram</b> (начиная с @):", reply_markup=kb_back_support())
    await call.answer()

@router.callback_query(StateFilter(GoodFSM.photos), F.data == "good_photos_skip")
async def good_photos_skip(call: CallbackQuery, state: FSMContext):
    await state.update_data(photos=[])
    await state.set_state(GoodFSM.nickname)
    await call.message.answer("Укажите <b>ник в Telegram</b> (начиная с @):", reply_markup=kb_back_support())
    await call.answer()

@router.message(StateFilter(GoodFSM.nickname))
async def good_nick_step(message: Message, state: FSMContext):
    nick = message.text.strip()
    if not nick.startswith("@"):
        await message.answer("Ник должен начинаться с @. Повторите ввод:", reply_markup=kb_back_support())
        return
    await state.update_data(nickname=nick)
    await state.set_state(GoodFSM.school_choice)
    await message.answer(
        "Выберите учебное заведение для объявления:",
        reply_markup=kb_school_selector(prefix="good")
    )

@router.callback_query(StateFilter(GoodFSM.school_choice), F.data.in_(["good_school_moscow", "good_school_custom"]))
async def good_school_choice(call: CallbackQuery, state: FSMContext):
    if call.data.endswith("moscow"):
        await state.update_data(school="Москва")
        await show_good_confirm(call.message, state)
    else:
        await state.set_state(GoodFSM.school)
        await call.message.answer("Введите название вашей школы/ВУЗа:", reply_markup=kb_back_support())
    await call.answer()

@router.message(StateFilter(GoodFSM.school))
async def good_school_text(message: Message, state: FSMContext):
    await state.update_data(school=message.text.strip())
    await show_good_confirm(message, state)

async def show_good_confirm(target, state: FSMContext):
    await state.set_state(GoodFSM.confirm)
    data = await state.get_data()
    title = data["title"]
    category = data["category"]
    condition = data["condition"]
    description = data["description"]
    price = data["price"]
    photos: List[str] = data.get("photos", [])
    nickname = data["nickname"]
    school = data["school"]

    caption = (
        f"Проверьте объявление:\n\n"
        f"<b>{title}</b>\n"
        f"Категория: {category}\n"
        f"Состояние: {condition}\n"
        f"Описание: {description}\n"
        f"Цена: {price}\n"
        f"Школа/ВУЗ: {school}\n"
        f"Ник (скроется в ленте): {nickname}"
    )
    if photos:
        await target.answer_photo(photos[0], caption=caption, reply_markup=kb_confirm())
    else:
        await target.answer(caption, reply_markup=kb_confirm())

@router.callback_query(StateFilter(GoodFSM.confirm), F.data == "confirm_publish")
async def good_publish(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    editing_id = data.get("editing_id")
    if editing_id:
        cur.execute(
            "UPDATE goods SET title=?, category=?, condition=?, description=?, price=?, photos=?, nickname=?, school=? "
            "WHERE id=?",
            (
                data["title"], data["category"], data["condition"], data["description"], data["price"],
                ",".join(data.get("photos", [])), data["nickname"], data["school"], editing_id
            )
        )
    else:
        cur.execute(
            "INSERT INTO goods(user_id, title, category, condition, description, price, photos, nickname, school) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (
                call.from_user.id, data["title"], data["category"], data["condition"], data["description"],
                data["price"], ",".join(data.get("photos", [])), data["nickname"], data["school"]
            )
        )
    conn.commit()
    await call.message.answer("✅ Объявление опубликовано!", reply_markup=kb_back_support())
    await state.clear()
    await call.answer()

@router.callback_query(StateFilter(GoodFSM.confirm), F.data == "confirm_edit")
async def good_edit_restart(call: CallbackQuery, state: FSMContext):
    # "По кругу" – начинаем заново с Названия
    await state.set_state(GoodFSM.title)
    await call.message.answer("Введите <b>Название</b> товара:", reply_markup=kb_back_support())
    await call.answer()

# ======================= РАЗДЕЛ В: ПОИСК РЕПЕТИТОРА (ЛЕНТА) =======================
@router.callback_query(F.data == "menu_find_tutor")
async def menu_find_tutor(call: CallbackQuery):
    await call.message.answer("Выберите предмет:", reply_markup=kb_tutor_subjects())
    await call.answer()

@router.callback_query(F.data.startswith("feed_sub_"))
async def feed_choose_subject(call: CallbackQuery, state: FSMContext):
    sub = call.data.replace("feed_sub_", "")
    await state.update_data(feed_type="tutors", feed_subject=sub)
    await call.message.answer(
        f"Предмет: <b>{sub}</b>\nТеперь выберите способ фильтра по учебному заведению:",
        reply_markup=kb_school_selector(prefix="feed_tutors")
    )
    await call.answer()

@router.callback_query(F.data.in_(["feed_tutors_school_moscow", "feed_tutors_school_custom"]))
async def feed_tutors_school_filter(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    sub = data.get("feed_subject")
    if call.data.endswith("moscow"):
        school = "Москва"
        await begin_tutors_feed(call, subject=sub, school_filter=school)
        await call.answer()
    else:
        await state.update_data(feed_school_mode="custom_tutor")
        await call.message.answer("Введите название школы/ВУЗа для фильтра:", reply_markup=kb_back_support())
        await state.set_state(TutorFSM.school)  # переиспользуем для приема текста в поиске
        await call.answer()

@router.message(StateFilter(TutorFSM.school))
async def feed_tutors_school_entered(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("feed_type") == "tutors":
        sub = data.get("feed_subject")
        school = message.text.strip()
        await begin_tutors_feed_from_message(message, subject=sub, school_filter=school)
        await state.clear()

async def begin_tutors_feed(call: CallbackQuery, subject: str, school_filter: str):
    cur.execute(
        "SELECT id, name, subject, school, achievements, details, price, photos, nickname "
        "FROM tutors WHERE subject=? AND ( ( ?='Москва' AND lower(school) LIKE '%моск%' ) OR lower(school)=lower(?) ) "
        "ORDER BY id DESC",
        (subject, school_filter, school_filter)
    )
    rows = cur.fetchall()
    uid = call.from_user.id
    feed_state[uid] = {"type": "tutors", "subject": subject, "school_filter": school_filter, "ids": [r[0] for r in rows], "i": 0}
    if not rows:
        await call.message.answer("Пока что объявлений по этому предмету и учебному заведению нет.", reply_markup=kb_back_support())
        return
    await show_tutor_by_row(call.message, rows[0])

async def begin_tutors_feed_from_message(message: Message, subject: str, school_filter: str):
    cur.execute(
        "SELECT id, name, subject, school, achievements, details, price, photos, nickname "
        "FROM tutors WHERE subject=? AND ( ( ?='Москва' AND lower(school) LIKE '%моск%' ) OR lower(school)=lower(?) ) "
        "ORDER BY id DESC",
        (subject, school_filter, school_filter)
    )
    rows = cur.fetchall()
    uid = message.from_user.id
    feed_state[uid] = {"type": "tutors", "subject": subject, "school_filter": school_filter, "ids": [r[0] for r in rows], "i": 0}
    if not rows:
        await message.answer("Пока что объявлений по этому предмету и учебному заведению нет.", reply_markup=kb_back_support())
        return
    await show_tutor_by_row(message, rows[0])

async def show_tutor_by_row(target_message: Message, row: tuple):
    # row: (id, name, subject, school, achievements, details, price, photos, nickname)
    photos = (row[7] or "").split(",") if row[7] else []
    caption = (
        f"<b>{row[1]}</b>\n"
        f"Предмет: {row[2]}\n"
        f"Школа/ВУЗ: {row[3]}\n"
        f"Достижения: {row[4]}\n"
        f"Обучение: {row[5]}\n"
        f"Цена (р/час): {row[6]}"
    )
    if photos:
        await target_message.answer_photo(
            photo=photos[0],
            caption=caption,
            reply_markup=kb_like_dislike("tutors", row[0])
        )
    else:
        await target_message.answer(
            caption,
            reply_markup=kb_like_dislike("tutors", row[0])
        )

@router.callback_query(F.data.startswith("like_tutors_"))
async def like_tutors(call: CallbackQuery):
    ad_id = int(call.data.split("_")[-1])
    cur.execute("SELECT nickname FROM tutors WHERE id=?", (ad_id,))
    row = cur.fetchone()
    if row:
        await call.message.answer(f"Контакт репетитора: {row[0]}")
    await show_next_in_feed(call)
    await call.answer()

@router.callback_query(F.data.startswith("dis_tutors_"))
async def dislike_tutors(call: CallbackQuery):
    await show_next_in_feed(call)
    await call.answer()

# ======================= РАЗДЕЛ Г: РАЗМЕЩЕНИЕ РЕПЕТИТОРА =======================
@router.callback_query(F.data == "menu_create_tutor")
async def create_tutor_start(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(TutorFSM.name)
    await call.message.answer("Введите <b>Имя</b>:", reply_markup=kb_back_support())
    await call.answer()

@router.message(StateFilter(TutorFSM.name))
async def tutor_name_step(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(TutorFSM.subject)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=sub, callback_data=f"tutor_sub_{sub}") ] for sub in TUTOR_SUBJECTS
    ] + [
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="menu_back")],
        [InlineKeyboardButton(text="💬 Поддержка", callback_data="menu_support")],
    ])
    await message.answer("Выберите <b>Предмет</b>:", reply_markup=kb)

@router.callback_query(StateFilter(TutorFSM.subject), F.data.startswith("tutor_sub_"))
async def tutor_subject_step(call: CallbackQuery, state: FSMContext):
    sub = call.data.replace("tutor_sub_", "")
    await state.update_data(subject=sub)
    # выбор школы: Москва или ввести своё (как просили — кнопками путь выбора)
    await state.set_state(TutorFSM.school_choice)
    await call.message.answer("Укажите учебное заведение:", reply_markup=kb_school_selector(prefix="tutor"))
    await call.answer()

@router.callback_query(StateFilter(TutorFSM.school_choice), F.data.in_(["tutor_school_moscow", "tutor_school_custom"]))
async def tutor_school_choice(call: CallbackQuery, state: FSMContext):
    if call.data.endswith("moscow"):
        await state.update_data(school="Москва")
        await state.set_state(TutorFSM.achievements)
        await call.message.answer("Перечислите <b>достижения</b>:", reply_markup=kb_back_support())
    else:
        await state.set_state(TutorFSM.school)
        await call.message.answer("Введите название школы/ВУЗа (пример: МГУ, 2 курс):", reply_markup=kb_back_support())
    await call.answer()

@router.message(StateFilter(TutorFSM.school))
async def tutor_school_text(message: Message, state: FSMContext):
    await state.update_data(school=message.text.strip())
    await state.set_state(TutorFSM.achievements)
    await message.answer("Перечислите <b>достижения</b>:", reply_markup=kb_back_support())

@router.message(StateFilter(TutorFSM.achievements))
async def tutor_achievements_step(message: Message, state: FSMContext):
    await state.update_data(achievements=message.text.strip())
    await state.set_state(TutorFSM.details)
    await message.answer("Укажите <b>основные моменты обучения</b>:", reply_markup=kb_back_support())

@router.message(StateFilter(TutorFSM.details))
async def tutor_details_step(message: Message, state: FSMContext):
    await state.update_data(details=message.text.strip())
    await state.set_state(TutorFSM.price)
    await message.answer("Укажите <b>цену за р/час</b>:", reply_markup=kb_back_support())

@router.message(StateFilter(TutorFSM.price))
async def tutor_price_step(message: Message, state: FSMContext):
    await state.update_data(price=message.text.strip(), photos=[])
    await state.set_state(TutorFSM.photos)
    await message.answer(
        "Отправьте 1–3 <b>фото</b> (по одному сообщению). Когда закончите — нажмите «Готово». Можно пропустить.",
        reply_markup=kb_photos_controls(prefix="tutor")
    )

@router.message(StateFilter(TutorFSM.photos), F.photo)
async def tutor_photos_collect(message: Message, state: FSMContext):
    data = await state.get_data()
    photos: List[str] = data.get("photos", [])
    if len(photos) >= 3:
        await message.answer("Добавлено 3 фото. Нажмите «Готово».", reply_markup=kb_photos_controls(prefix="tutor"))
        return
    file_id = message.photo[-1].file_id
    photos.append(file_id)
    await state.update_data(photos=photos)
    await message.answer(f"Фото добавлено ({len(photos)}/3).", reply_markup=kb_photos_controls(prefix="tutor"))

@router.callback_query(StateFilter(TutorFSM.photos), F.data == "tutor_photos_done")
async def tutor_photos_done(call: CallbackQuery, state: FSMContext):
    await state.set_state(TutorFSM.nickname)
    await call.message.answer("Укажите <b>ник в Telegram</b> (начиная с @):", reply_markup=kb_back_support())
    await call.answer()

@router.callback_query(StateFilter(TutorFSM.photos), F.data == "tutor_photos_skip")
async def tutor_photos_skip(call: CallbackQuery, state: FSMContext):
    await state.update_data(photos=[])
    await state.set_state(TutorFSM.nickname)
    await call.message.answer("Укажите <b>ник в Telegram</b> (начиная с @):", reply_markup=kb_back_support())
    await call.answer()

@router.message(StateFilter(TutorFSM.nickname))
async def tutor_nick_step(message: Message, state: FSMContext):
    nick = message.text.strip()
    if not nick.startswith("@"):
        await message.answer("Ник должен начинаться с @. Повторите ввод:", reply_markup=kb_back_support())
        return
    await state.update_data(nickname=nick)
    await show_tutor_confirm(message, state)

async def show_tutor_confirm(target, state: FSMContext):
    await state.set_state(TutorFSM.confirm)
    data = await state.get_data()
    name = data["name"]
    subject = data["subject"]
    school = data["school"]
    achievements = data["achievements"]
    details = data["details"]
    price = data["price"]
    photos: List[str] = data.get("photos", [])
    nickname = data["nickname"]

    caption = (
        f"Проверьте объявление:\n\n"
        f"<b>{name}</b>\n"
        f"Предмет: {subject}\n"
        f"Школа/ВУЗ: {school}\n"
        f"Достижения: {achievements}\n"
        f"Обучение: {details}\n"
        f"Цена (р/час): {price}\n"
        f"Ник (скроется в ленте): {nickname}"
    )
    if photos:
        await target.answer_photo(photos[0], caption=caption, reply_markup=kb_confirm())
    else:
        await target.answer(caption, reply_markup=kb_confirm())

@router.callback_query(StateFilter(TutorFSM.confirm), F.data == "confirm_publish")
async def tutor_publish(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    editing_id = data.get("editing_id")
    if editing_id:
        cur.execute(
            "UPDATE tutors SET name=?, subject=?, school=?, achievements=?, details=?, price=?, photos=?, nickname=? "
            "WHERE id=?",
            (
                data["name"], data["subject"], data["school"], data["achievements"], data["details"],
                data["price"], ",".join(data.get("photos", [])), data["nickname"], editing_id
            )
        )
    else:
        cur.execute(
            "INSERT INTO tutors(user_id, name, subject, school, achievements, details, price, photos, nickname) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (
                call.from_user.id, data["name"], data["subject"], data["school"], data["achievements"], data["details"],
                data["price"], ",".join(data.get("photos", [])), data["nickname"]
            )
        )
    conn.commit()
    await call.message.answer("✅ Объявление репетитора опубликовано!", reply_markup=kb_back_support())
    await state.clear()
    await call.answer()

@router.callback_query(StateFilter(TutorFSM.confirm), F.data == "confirm_edit")
async def tutor_edit_restart(call: CallbackQuery, state: FSMContext):
    await state.set_state(TutorFSM.name)
    await call.message.answer("Введите <b>Имя</b>:", reply_markup=kb_back_support())
    await call.answer()

# ======================= РАЗДЕЛ Д: МОИ ОБЪЯВЛЕНИЯ =======================
@router.callback_query(F.data == "menu_my_ads")
async def my_ads_menu(call: CallbackQuery):
    await call.message.answer(
        "Выберите тип ваших объявлений:",
        reply_markup=kb_my_ads_entry()
    )
    await call.answer()

@router.callback_query(F.data == "my_goods")
async def my_goods_start(call: CallbackQuery):
    uid = call.from_user.id
    cur.execute("SELECT id FROM goods WHERE user_id=? ORDER BY id DESC", (uid,))
    ids = [r[0] for r in cur.fetchall()]
    my_state[uid] = {"type": "goods", "ids": ids, "i": 0}
    if not ids:
        await call.message.answer("У вас нет объявлений с товарами.", reply_markup=kb_back_support())
        await call.answer()
        return
    await show_my_good_by_index(call.message, uid, 0)
    await call.answer()

async def show_my_good_by_index(target: Message, uid: int, idx: int):
    ids = my_state[uid]["ids"]
    ad_id = ids[idx]
    cur.execute("SELECT id, title, condition, description, price, photos, school FROM goods WHERE id=?", (ad_id,))
    row = cur.fetchone()
    if not row:
        await target.answer("Объявление не найдено.", reply_markup=kb_back_support())
        return
    photos = (row[5] or "").split(",") if row[5] else []
    caption = (
        f"<b>{row[1]}</b>\n"
        f"Состояние: {row[2]}\n"
        f"Описание: {row[3]}\n"
        f"Цена: {row[4]}\n"
        f"Школа/ВУЗ: {row[6]}"
    )
    if photos:
        await target.answer_photo(photos[0], caption=caption, reply_markup=kb_my_ad_controls("goods", idx))
    else:
        await target.answer(caption, reply_markup=kb_my_ad_controls("goods", idx))

@router.callback_query(F.data == "my_tutors")
async def my_tutors_start(call: CallbackQuery):
    uid = call.from_user.id
    cur.execute("SELECT id FROM tutors WHERE user_id=? ORDER BY id DESC", (uid,))
    ids = [r[0] for r in cur.fetchall()]
    my_state[uid] = {"type": "tutors", "ids": ids, "i": 0}
    if not ids:
        await call.message.answer("У вас нет объявлений репетитора.", reply_markup=kb_back_support())
        await call.answer()
        return
    await show_my_tutor_by_index(call.message, uid, 0)
    await call.answer()

async def show_my_tutor_by_index(target: Message, uid: int, idx: int):
    ids = my_state[uid]["ids"]
    ad_id = ids[idx]
    cur.execute("SELECT id, name, subject, school, achievements, details, price, photos FROM tutors WHERE id=?", (ad_id,))
    row = cur.fetchone()
    if not row:
        await target.answer("Объявление не найдено.", reply_markup=kb_back_support())
        return
    photos = (row[7] or "").split(",") if row[7] else []
    caption = (
        f"<b>{row[1]}</b>\n"
        f"Предмет: {row[2]}\n"
        f"Школа/ВУЗ: {row[3]}\n"
        f"Достижения: {row[4]}\n"
        f"Обучение: {row[5]}\n"
        f"Цена (р/час): {row[6]}"
    )
    if photos:
        await target.answer_photo(photos[0], caption=caption, reply_markup=kb_my_ad_controls("tutors", idx))
    else:
        await target.answer(caption, reply_markup=kb_my_ad_controls("tutors", idx))

@router.callback_query(F.data.startswith("my_next_"))
async def my_next(call: CallbackQuery):
    _, ad_type, idx_str = call.data.split("_", 2)
    uid = call.from_user.id
    st = my_state.get(uid)
    if not st or st["type"] != ad_type:
        await call.message.answer("Список объявлений недоступен.", reply_markup=kb_back_support())
        await call.answer()
        return
    st["i"] = int(idx_str) + 1
    if st["i"] >= len(st["ids"]):
        await call.message.answer("Это было последнее объявление.", reply_markup=kb_back_support())
        await call.answer()
        return
    if ad_type == "goods":
        await show_my_good_by_index(call.message, uid, st["i"])
    else:
        await show_my_tutor_by_index(call.message, uid, st["i"])
    await call.answer()

@router.callback_query(F.data.startswith("my_edit_"))
async def my_edit(call: CallbackQuery, state: FSMContext):
    _, ad_type, idx_str = call.data.split("_", 2)
    uid = call.from_user.id
    idx = int(idx_str)
    ids = my_state.get(uid, {}).get("ids", [])
    if idx >= len(ids):
        await call.message.answer("Объявление не найдено.", reply_markup=kb_back_support())
        await call.answer()
        return
    ad_id = ids[idx]
    if ad_type == "goods":
        cur.execute("SELECT title, category, condition, description, price, photos, nickname, school FROM goods WHERE id=?", (ad_id,))
        row = cur.fetchone()
        if not row:
            await call.message.answer("Объявление не найдено.", reply_markup=kb_back_support())
            await call.answer()
            return
        # Заполняем черновик и запускаем флоу по кругу
        await state.set_state(GoodFSM.title)
        await state.update_data(
            title=row[0], category=row[1], condition=row[2], description=row[3], price=row[4],
            photos=(row[5].split(",") if row[5] else []), nickname=row[6], school=row[7], editing_id=ad_id
        )
        await call.message.answer("Редактирование товара. Введите <b>Название</b>:", reply_markup=kb_back_support())
    else:
        cur.execute("SELECT name, subject, school, achievements, details, price, photos, nickname FROM tutors WHERE id=?", (ad_id,))
        row = cur.fetchone()
        if not row:
            await call.message.answer("Объявление не найдено.", reply_markup=kb_back_support())
            await call.answer()
            return
        await state.set_state(TutorFSM.name)
        await state.update_data(
            name=row[0], subject=row[1], school=row[2], achievements=row[3], details=row[4],
            price=row[5], photos=(row[6].split(",") if row[6] else []), nickname=row[7], editing_id=ad_id
        )
        await call.message.answer("Редактирование репетитора. Введите <b>Имя</b>:", reply_markup=kb_back_support())
    await call.answer()

# ======================= УТИЛИТЫ =======================
def get_good_by_id(ad_id: int) -> Optional[tuple]:
    cur.execute("SELECT id, title, condition, description, price, photos, nickname, school FROM goods WHERE id=?", (ad_id,))
    return cur.fetchone()

def get_tutor_by_id(ad_id: int) -> Optional[tuple]:
    cur.execute("SELECT id, name, subject, school, achievements, details, price, photos, nickname FROM tutors WHERE id=?", (ad_id,))
    return cur.fetchone()

# ----------------------- /help как дубль поддержки -----------------------
@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(f"Поддержка: {SUPPORT_NICK}", reply_markup=kb_back_support())

# ----------------------- RUN -----------------------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
