"""Teglo — бот-витрина и приём заявок.

Показывает, как работает бот заведения на платформе Teglo (карта гостя, меню,
живой статус заказа, игра, рассылка, отзыв, сводка владельцу), и принимает заявки.

Персональные данные не хранит: заявка пересылается владельцу в Telegram и нигде
не сохраняется. Состояние диалога — только в памяти процесса.

Переменные окружения:
  BOT_TOKEN  — токен бота (обязательно)
  OWNER_ID   — Telegram ID, куда слать заявки (обязательно)
  SITE_URL   — адрес сайта с демо, например https://teglo.ru (необязательно)
"""
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("teglo")

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])
SITE_URL = os.environ.get("SITE_URL", "").rstrip("/")

# ---------------------------------------------------------------- демо-данные
NICHES = {
    "zerno": {
        "title": "Кофейня «Зерно»",
        "brand": "зерно",
        "level": "Завсегдатай",
        "balance": "412 баллов",
        "code": "К 4821",
        "extra": "Штампы: ☕☕☕☕▫️🎁 — 6-й кофе в подарок",
        "menu_title": "Меню",
        "menu": [("Капучино 350 мл", "220 ₽"), ("Раф лаванда", "280 ₽"), ("Флэт уайт", "240 ₽"), ("Круассан", "190 ₽")],
        "live_title": "Ваш заказ №214",
        "live_steps": ["Принят", "Готовим", "Готов к выдаче"],
        "live_lines": "Капучино 350 мл · Круассан",
        "live_done": "Заберите у стойки — баллы уже на карте: +48",
        "live_src": "В «Старте» статус ставит бариста кнопкой, в «Основе» — приходит из iiko.",
        "dice": "🎰",
        "prizes": ["раф в подарок", "+50 баллов", "круассан", "двойные баллы до воскресенья"],
        "push": "Давно не виделись 👋 Ваш капучино ждёт: до воскресенья — двойные баллы.",
        "summary": (
            "<b>Зерно · итоги дня</b>\n"
            "Выручка 48 300 ₽ (+6% к прошлому вторнику)\n"
            "Чеков 104 · средний 464 ₽\n"
            "Новых гостей 9 · вернулись 31\n"
            "Отзывы: 4 × 5★, 1 × 3★ — «долго ждал заказ»"
        ),
        "churn": ["Ольга К. — 12 визитов, не была 34 дня", "Денис П. — 8 визитов, 41 день", "Света М. — 15 визитов, 29 дней"],
        "ai_q": "Почему во вторник просела выручка?",
        "ai_a": (
            "Во вторник −14% к среднему: утренний пик 8–10 был на 22 чека меньше — на одной точке "
            "не работала кофемашина (отмены в кассе с 8:12 до 9:40). Вечер в норме. Совет: отправьте "
            "утренним гостям двойные баллы до пятницы — это 118 человек."
        ),
    },
    "dakai": {
        "title": "Бренд одежды «DAKAI»",
        "brand": "DAKAI",
        "level": "Свой",
        "balance": "1 240 баллов",
        "code": "D 0731",
        "extra": "Ранний доступ к дропу 05 — у вас есть ✅",
        "menu_title": "Каталог · Дроп 04",
        "menu": [("Худи «Ветер»", "6 900 ₽"), ("Карго «Тундра»", "7 400 ₽"), ("Лонгслив", "3 900 ₽"), ("Шапка", "1 900 ₽")],
        "live_title": "Дроп 05 · Худи «Ветер»",
        "live_steps": ["Ранний доступ", "Открыт", "Осталось 12 шт"],
        "live_lines": "Размеры: S · M · L · XL — 6 900 ₽",
        "live_done": "XL отложен на 15 минут — оплатите по ссылке",
        "live_src": "Наличие и размеры — из МойСклад.",
        "dice": "🎯",
        "prizes": ["−15% на дроп 05", "бесплатная доставка", "+300 баллов", "ранний доступ на сутки"],
        "push": "Дроп 05 через 3 дня. У вас ранний доступ — завтра в 12:00 пришлём ссылку.",
        "summary": (
            "<b>DAKAI · итоги дня</b>\n"
            "Заказов 23 на 186 400 ₽\n"
            "Лист ожидания: XL худи — 41 человек\n"
            "Дроп 05: 312 в раннем доступе\n"
            "Отзывы: 3 × 5★, 1 × 3★ — «маломерит»"
        ),
        "churn": ["Никита Р. — 5 заказов, не покупал 120 дней", "Аня Д. — 3 заказа, 98 дней", "Глеб В. — 4 заказа, 105 дней"],
        "ai_q": "Что докупить к дропу 05?",
        "ai_a": (
            "В дропе 04 худи XL закончились на 2-й день, в листе ожидания 41 человек — это ~280 тыс. ₽ "
            "упущенной выручки. Карго S и M продались на 92%, L — на 54%. Совет: худи XL ×2 к прошлому "
            "тиражу, карго L — тираж −30%."
        ),
    },
    "pion": {
        "title": "Мастерская «Пион и Ко»",
        "brand": "Пион и Ко",
        "level": "Любимый клиент",
        "balance": "860 баллов",
        "code": "П 2209",
        "extra": "Напомним: день рождения мамы — 14 декабря 🌸",
        "menu_title": "Букеты недели",
        "menu": [("«Утро»", "3 900 ₽"), ("Пионы 15 шт", "5 400 ₽"), ("«Сад»", "4 600 ₽"), ("Моно-тюльпаны", "2 900 ₽")],
        "live_title": "Букет «Утро» для мамы",
        "live_steps": ["Собран", "В пути", "Доставлен"],
        "live_lines": "Курьер Алексей · будет в 13:20",
        "live_done": "Курьер получил: позвонит за 5 минут",
        "live_src": "Статус ставят флорист и курьер кнопками в рабочем чате.",
        "dice": "🎲",
        "prizes": ["−10% на букет", "открытка в подарок", "+100 баллов", "доставка 0 ₽"],
        "push": "Через 3 дня день рождения мамы 🌸 Собрать её любимые пионы к 13:00?",
        "summary": (
            "<b>Пион и Ко · итоги дня</b>\n"
            "Заказов 31 на 132 600 ₽\n"
            "Доставлено вовремя 29 из 31\n"
            "Напоминаний о датах 12 → заказали 7\n"
            "Подписки: 74 активных"
        ),
        "churn": ["Павел Л. — 9 заказов, не заказывал 70 дней", "Ира С. — 6 заказов, 64 дня", "Марина Т. — 11 заказов, 58 дней"],
        "ai_q": "Сколько пионов закупить на декабрь?",
        "ai_a": (
            "В календаре клиентов 312 дат в декабре; в прошлом году по напоминаниям заказывали 58%. "
            "Пионы выбирают в 41% таких заказов, декабрь даёт +34% за счёт корпоративов. Совет: "
            "~1 900 стеблей, из них 60% — к 20–28 декабря."
        ),
    },
}
NICHE_BTN = [("☕ Кофейня", "zerno"), ("👕 Бренд одежды", "dakai"), ("💐 Цветы", "pion")]
DEMO_NOTE = "<i>Демо: данные вымышленные.</i>"


class Lead(StatesGroup):
    niche = State()
    business = State()
    contact = State()


# ---------------------------------------------------------------- клавиатуры
def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🧪 Попробовать как гость", callback_data="g")],
        [InlineKeyboardButton(text="📊 Кабинет владельца", callback_data="o")],
        [InlineKeyboardButton(text="💬 Оставить заявку", callback_data="lead")],
    ]
    if SITE_URL:
        rows.append([InlineKeyboardButton(text="🌐 Сайт и тарифы", url=SITE_URL)])
    return kb(rows)


def niche_menu(prefix: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for text, key in NICHE_BTN:
        b.button(text=text, callback_data=f"{prefix}:{key}")
    b.button(text="← Назад", callback_data="home")
    b.adjust(1)
    return b.as_markup()


def guest_menu(key: str) -> InlineKeyboardMarkup:
    n = NICHES[key]
    rows = [
        [InlineKeyboardButton(text=f"📋 {n['menu_title']}", callback_data=f"gm:{key}"),
         InlineKeyboardButton(text="⏱ Живой статус", callback_data=f"gl:{key}")],
        [InlineKeyboardButton(text=f"{n['dice']} Игра", callback_data=f"gg:{key}"),
         InlineKeyboardButton(text="✉️ Рассылка", callback_data=f"gp:{key}")],
        [InlineKeyboardButton(text="⭐ Оценить визит", callback_data=f"gr:{key}")],
    ]
    if SITE_URL.startswith("https://"):
        rows.append([InlineKeyboardButton(
            text="📱 Открыть сайт заведения",
            web_app=WebAppInfo(url=f"{SITE_URL}/demo.html?n={key}&m=guest&t=3"))])
    rows.append([InlineKeyboardButton(text="💬 Хочу так же", callback_data="lead"),
                 InlineKeyboardButton(text="← Назад", callback_data="g")])
    return kb(rows)


def owner_menu(key: str) -> InlineKeyboardMarkup:
    return kb([
        [InlineKeyboardButton(text="🚪 Кто перестал ходить", callback_data=f"oc:{key}")],
        [InlineKeyboardButton(text="🤖 Спросить ИИ-аналитика", callback_data=f"oa:{key}")],
        [InlineKeyboardButton(text="💬 Хочу так же", callback_data="lead"),
         InlineKeyboardButton(text="← Назад", callback_data="o")],
    ])


def back(key: str, to: str = "gn") -> InlineKeyboardMarkup:
    return kb([[InlineKeyboardButton(text="← К карте", callback_data=f"{to}:{key}")]])


# ---------------------------------------------------------------- тексты
WELCOME = (
    "Привет! Это <b>Teglo</b> — сайт, бот и программа лояльности для малого бизнеса.\n\n"
    "Здесь можно потрогать, как будет работать бот вашего заведения: карта гостя, меню, "
    "живой статус заказа, игры, рассылки и сводка владельцу.\n\n"
    "Выберите, с чего начать 👇"
)


def card_text(key: str) -> str:
    n = NICHES[key]
    return (
        f"<b>{n['brand']}</b> · карта гостя\n\n"
        f"Уровень: <b>{n['level']}</b>\n"
        f"Баланс: <b>{n['balance']}</b>\n"
        f"Код на кассе: <code>{n['code']}</code>\n"
        f"{n['extra']}\n\n"
        f"Так гость видит бот «{n['brand']}» — без приложения из магазина.\n"
        f"{DEMO_NOTE}"
    )


def live_text(n: dict, step: int) -> str:
    dots = "".join("🟢" if i <= step else "⚪️" for i in range(len(n["live_steps"])))
    bar_len = [3, 6, 10][min(step, 2)]
    bar = "▰" * bar_len + "▱" * (10 - bar_len)
    lines = [
        f"<b>{n['live_title']}</b>",
        f"{dots}  {n['live_steps'][min(step, 2)]}",
        bar,
        n["live_lines"],
    ]
    if step >= 2:
        lines.append(f"\n✅ {n['live_done']}")
    lines.append(f"\n<i>Одно сообщение обновляется само — без спама уведомлениями. {n['live_src']}</i>")
    return "\n".join(lines)


# ---------------------------------------------------------------- роутинг
dp = Dispatcher(storage=MemoryStorage())


@dp.message(CommandStart())
async def start(m: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    if command.args == "lead":
        await m.answer("Отлично, оставим заявку — это 3 коротких вопроса.")
        await ask_niche(m, state)
        return
    await m.answer(WELCOME, reply_markup=main_menu())


@dp.message(Command("menu"))
async def menu_cmd(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(WELCOME, reply_markup=main_menu())


@dp.callback_query(F.data == "home")
async def home(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.edit_text(WELCOME, reply_markup=main_menu())
    await c.answer()


@dp.callback_query(F.data == "g")
async def guest_pick(c: CallbackQuery):
    await c.message.edit_text("Выберите заведение — покажем бот глазами гостя:", reply_markup=niche_menu("gn"))
    await c.answer()


@dp.callback_query(F.data.startswith("gn:"))
async def guest_card(c: CallbackQuery):
    key = c.data.split(":")[1]
    try:
        await c.message.edit_text(card_text(key), reply_markup=guest_menu(key))
    except Exception:
        await c.message.answer(card_text(key), reply_markup=guest_menu(key))
    await c.answer()


@dp.callback_query(F.data.startswith("gm:"))
async def guest_menu_items(c: CallbackQuery):
    key = c.data.split(":")[1]
    n = NICHES[key]
    rows = "\n".join(f"• {name} — <b>{price}</b>" for name, price in n["menu"])
    await c.message.edit_text(
        f"<b>{n['menu_title']}</b>\n\n{rows}\n\nЗаказ заранее — без очереди, баллы — на карту.\n{DEMO_NOTE}",
        reply_markup=back(key))
    await c.answer()


@dp.callback_query(F.data.startswith("gl:"))
async def guest_live(c: CallbackQuery):
    key = c.data.split(":")[1]
    n = NICHES[key]
    await c.answer("Смотрите — сообщение обновится само")
    msg = await c.message.answer(live_text(n, 0))
    for step in (1, 2):
        await asyncio.sleep(2.5)
        try:
            await msg.edit_text(live_text(n, step), reply_markup=back(key) if step == 2 else None)
        except Exception as e:  # пользователь мог удалить сообщение
            log.warning("live edit failed: %s", e)
            return


@dp.callback_query(F.data.startswith("gg:"))
async def guest_game(c: CallbackQuery):
    key = c.data.split(":")[1]
    n = NICHES[key]
    await c.answer()
    d = await c.message.answer_dice(emoji=n["dice"])
    await asyncio.sleep(3.5)
    prize = n["prizes"][d.dice.value % len(n["prizes"])]
    await c.message.answer(
        f"🎉 Ваш приз: <b>{prize}</b>\n\nПризы и шансы задаёт владелец, результат честно считает Telegram. "
        f"Игры — модуль после запуска, в тарифе «Про».\n{DEMO_NOTE}",
        reply_markup=back(key))


@dp.callback_query(F.data.startswith("gp:"))
async def guest_push(c: CallbackQuery):
    key = c.data.split(":")[1]
    n = NICHES[key]
    await c.answer()
    await c.message.answer(
        f"<b>{n['brand']}</b>\n{n['push']}\n\n"
        f"<i>Так выглядит рассылка или триггер «давно не были». Отправляется только тем, кто дал согласие; "
        f"отписка — одной кнопкой.</i>",
        reply_markup=back(key))


@dp.callback_query(F.data.startswith("gr:"))
async def guest_rate(c: CallbackQuery):
    key = c.data.split(":")[1]
    b = InlineKeyboardBuilder()
    for s in range(1, 6):
        b.button(text="⭐" * s if s <= 2 else f"{s}⭐", callback_data=f"gs:{key}:{s}")
    b.adjust(5)
    await c.message.answer(f"Как вам в «{NICHES[key]['brand']}»?", reply_markup=b.as_markup())
    await c.answer()


@dp.callback_query(F.data.startswith("gs:"))
async def guest_rated(c: CallbackQuery):
    _, key, s = c.data.split(":")
    if int(s) >= 4:
        text = ("Спасибо! 🙌 Поделитесь на Яндекс Картах или в 2ГИС? Это сильно помогает заведению.\n\n"
                "<i>Хорошие оценки бот предлагает выложить на карты, плохие — сразу уходят владельцу.</i>")
    else:
        text = ("Спасибо, что сказали честно. Передали владельцу — он свяжется с вами сегодня.\n\n"
                "<i>Плохие оценки не уходят на карты, а сразу прилетают владельцу в Telegram.</i>")
    await c.message.edit_text(text, reply_markup=back(key))
    await c.answer()


@dp.callback_query(F.data == "o")
async def owner_pick(c: CallbackQuery):
    await c.message.edit_text("Чей кабинет показать?", reply_markup=niche_menu("on"))
    await c.answer()


@dp.callback_query(F.data.startswith("on:"))
async def owner_summary(c: CallbackQuery):
    key = c.data.split(":")[1]
    await c.message.edit_text(
        f"{NICHES[key]['summary']}\n\n<i>Такая сводка приходит владельцу каждый день в 22:00.</i>\n{DEMO_NOTE}",
        reply_markup=owner_menu(key))
    await c.answer()


@dp.callback_query(F.data.startswith("oc:"))
async def owner_churn(c: CallbackQuery):
    key = c.data.split(":")[1]
    rows = "\n".join(f"• {x}" for x in NICHES[key]["churn"])
    await c.message.edit_text(
        f"<b>Кто перестал ходить</b> — были постоянными:\n\n{rows}\n\n"
        f"Кнопка «Вернуть» отправит им персональное предложение.\n{DEMO_NOTE}",
        reply_markup=back(key, "on"))
    await c.answer()


@dp.callback_query(F.data.startswith("oa:"))
async def owner_ai(c: CallbackQuery):
    key = c.data.split(":")[1]
    n = NICHES[key]
    await c.message.edit_text(
        f"<b>Вы:</b> {n['ai_q']}\n\n<b>ИИ-аналитик:</b> {n['ai_a']}\n\n"
        f"<i>Отвечает по данным вашей кассы и базы, без передачи данных гостей за рубеж.</i>\n{DEMO_NOTE}",
        reply_markup=back(key, "on"))
    await c.answer()


# ---------------------------------------------------------------- заявка
async def ask_niche(m: Message, state: FSMContext):
    b = InlineKeyboardBuilder()
    for text, key in NICHE_BTN:
        b.button(text=text, callback_data=f"ln:{text}")
    b.button(text="Другое", callback_data="ln:Другое")
    b.adjust(2)
    await state.set_state(Lead.niche)
    await m.answer("1/3. Какой у вас бизнес?", reply_markup=b.as_markup())


@dp.callback_query(F.data == "lead")
async def lead_start(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await ask_niche(c.message, state)


@dp.callback_query(Lead.niche, F.data.startswith("ln:"))
async def lead_niche(c: CallbackQuery, state: FSMContext):
    await state.update_data(niche=c.data.split(":", 1)[1])
    await state.set_state(Lead.business)
    await c.message.edit_text("2/3. Как называется заведение или бренд? Можно ссылку на соцсети или карты.")
    await c.answer()


@dp.message(Lead.business, F.text)
async def lead_business(m: Message, state: FSMContext):
    await state.update_data(business=m.text[:300])
    await state.set_state(Lead.contact)
    await m.answer(
        "3/3. Как удобнее связаться?",
        reply_markup=kb([[InlineKeyboardButton(text="Напишите мне сюда, в Telegram", callback_data="lc:tg")]]))


@dp.callback_query(Lead.contact, F.data == "lc:tg")
async def lead_contact_tg(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await finish_lead(c.message.chat.id, c.from_user, "написать в Telegram", state, c.message)


@dp.message(Lead.contact, F.text)
async def lead_contact_text(m: Message, state: FSMContext):
    await finish_lead(m.chat.id, m.from_user, m.text[:200], state, m)


async def finish_lead(chat_id: int, user, contact: str, state: FSMContext, reply_to: Message):
    data = await state.get_data()
    await state.clear()
    who = f"@{user.username}" if user.username else f'<a href="tg://user?id={user.id}">{user.full_name}</a>'
    text = (
        "🔥 <b>Новая заявка Teglo</b>\n\n"
        f"Бизнес: {data.get('niche', '—')}\n"
        f"Название: {escape(data.get('business', '—'))}\n"
        f"Связь: {escape(contact)}\n"
        f"Кто: {who}"
    )
    try:
        await reply_to.bot.send_message(OWNER_ID, text)
    except Exception as e:
        log.error("cannot deliver lead to owner: %s", e)
    await reply_to.answer(
        "Готово! Заявка у нас — напишем в течение дня 🙌\n\n"
        "Первым 20 заведениям — запуск бесплатно и пониженная цена на год.\n\n"
        "<i>Контакт используем только чтобы ответить на заявку.</i>",
        reply_markup=main_menu())


def escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@dp.message()
async def fallback(m: Message):
    await m.answer("Выберите, что показать 👇", reply_markup=main_menu())


async def main():
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await bot.set_my_commands([])  # меню команд не нужно — всё на кнопках
    log.info("Teglo bot started")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
