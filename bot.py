import logging
import os
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Tuple

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("Не задан TELEGRAM_TOKEN")

# Память пользователей в оперативке (для начала)
USER_DATA: Dict[int, Dict[str, Any]] = {}

# Одна культура (ирисы), но структура заточена под расширение
PLANTS = {
    "iris": {
        "name": "Ирисы",
        "tasks": [  # (offset_days, title, phase)
            (0, "Посадка ирисов", "Посадка"),
            (7, "Проверить влажность почвы и при необходимости полить", "Отрастание"),
            (20, "Рыхление междурядий и прополка", "Отрастание"),
            (30, "Первая подкормка до цветения", "Бутонизация"),
            (45, "Осмотр на наличие пятен и вредителей", "Бутонизация"),
            (60, "Удаление отцветших цветков", "Цветение"),
            (75, "Подкормка после цветения", "После цветения"),
            (100, "Деление и пересадка разросшихся кустов", "После цветения"),
        ],
        "fert_rates": {
            "before_flowering": {
                "Аммиачная селитра": 20,
                "Калийная соль": 30,
                "Суперфосфат": 40,
            },
            "after_flowering": {
                "Калийная соль": 20,
                "Суперфосфат": 30,
            },
        },
    }
}

# Примитивная "машина состояний" для диалогов
STATE_WAIT_DATE = "WAIT_DATE"
STATE_WAIT_AREA = "WAIT_AREA"


def get_user(chat_id: int) -> Dict[str, Any]:
    if chat_id not in USER_DATA:
        USER_DATA[chat_id] = {
            "culture": "iris",   # по умолчанию ирисы
            "planting_date": None,
            "area_m2": None,
            "state": None,
        }
    return USER_DATA[chat_id]


def build_main_menu(user: Dict[str, Any]) -> InlineKeyboardMarkup:
    culture_name = PLANTS[user["culture"]]["name"]
    date_str = (
        user["planting_date"].strftime("%d.%m.%Y")
        if isinstance(user["planting_date"], date)
        else "не задана"
    )
    area_str = f'{user["area_m2"]} м²' if user.get("area_m2") else "не задана"

    buttons = [
        [
            InlineKeyboardButton("📅 Календарь работ", callback_data="menu_calendar"),
        ],
        [
            InlineKeyboardButton("🧮 Подкормки и удобрения", callback_data="menu_fert"),
        ],
        [
            InlineKeyboardButton("⚙️ Настройки", callback_data="menu_settings"),
        ],
        [
            InlineKeyboardButton("ℹ️ Инструкция", callback_data="menu_help"),
        ],
    ]

    text = (
        f"🌿 *Твой бот-помощник по растениям*\n\n"
        f"Культура: *{culture_name}*\n"
        f"Дата посадки: *{date_str}*\n"
        f"Площадь грядки: *{area_str}*\n\n"
        "Выбери, что сделать:"
    )

    return text, InlineKeyboardMarkup(buttons)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user = get_user(chat_id)

    text, markup = build_main_menu(user)

    if update.message:
        await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")
    else:
        await update.callback_query.message.reply_text(
            text, reply_markup=markup, parse_mode="Markdown"
        )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    USER_DATA.pop(chat_id, None)
    await update.message.reply_text(
        "Все настройки сброшены. Нажми /start, чтобы начать заново."
    )


def build_tasks_for_period(
    planting_date: date, plant_key: str, days: int = 14
) -> List[Tuple[date, str, str]]:
    today = datetime.now().date()
    tasks_def = PLANTS[plant_key]["tasks"]
    result: List[Tuple[date, str, str]] = []
    for offset, title, phase in tasks_def:
        task_date = planting_date + timedelta(days=offset)
        if today <= task_date <= today + timedelta(days=days):
            result.append((task_date, title, phase))
    result.sort(key=lambda x: x[0])
    return result


async def handle_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE, user: Dict[str, Any]) -> None:
    planting_date = user.get("planting_date")
    if not planting_date:
        await update.callback_query.message.reply_text(
            "Сначала нужно указать дату посадки.\n"
            "Открой ⚙️ *Настройки* и выбери «🗓 Установить дату посадки».",
            parse_mode="Markdown",
        )
        return

    tasks = build_tasks_for_period(planting_date, user["culture"], days=14)
    if not tasks:
        await update.callback_query.message.reply_text(
            "На ближайшие 2 недели задач нет. Похоже, сейчас спокойный период 🌿"
        )
        return

    lines = ["📅 *Задачи на ближайшие 14 дней:*"]
    for d, title, phase in tasks:
        lines.append(f"• {d.strftime('%d.%m')}: {title} (_{phase}_)")

    await update.callback_query.message.reply_text(
        "\n".join(lines), parse_mode="Markdown"
    )


async def handle_fert(update: Update, context: ContextTypes.DEFAULT_TYPE, user: Dict[str, Any]) -> None:
    plant = PLANTS[user["culture"]]
    area = user.get("area_m2")

    buttons = [
        [
            InlineKeyboardButton("До цветения", callback_data="fert_before"),
            InlineKeyboardButton("После цветения", callback_data="fert_after"),
        ],
        [
            InlineKeyboardButton("Изменить площадь", callback_data="settings_area"),
        ],
        [
            InlineKeyboardButton("⬅️ В главное меню", callback_data="back_main"),
        ],
    ]

    text = "🧮 *Подкормки и удобрения*\n\n"
    if area:
        text += f"Текущая площадь: *{area} м²*.\nВыбери этап подкормки:"
    else:
        text += (
            "Площадь пока не указана. Можно всё равно посчитать из расчёта на 1 м², "
            "или сначала задать площадь в настройках."
        )

    await update.callback_query.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )


async def send_fert_calc(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: Dict[str, Any],
    stage_key: str,
) -> None:
    plant = PLANTS[user["culture"]]
    rates = plant["fert_rates"][stage_key]
    area = user.get("area_m2", 1.0)

    if not user.get("area_m2"):
        header = (
            "Площадь не указана — считаю из расчёта *1 м²*.\n"
            "Чтобы задать свою площадь, зайди в ⚙️ *Настройки*."
        )
    else:
        header = f"Площадь грядки: *{area} м²*."

    stage_text = "до цветения" if stage_key == "before_flowering" else "после цветения"

    lines = [
        f"🧮 *Подкормка {stage_text}*",
        header,
        "",
    ]
    for name, per_m2 in rates.items():
        total = per_m2 * area
        lines.append(f"• {name}: *{total:.0f} г* (из расчёта {per_m2} г/м²)")

    await update.callback_query.message.reply_text(
        "\n".join(lines), parse_mode="Markdown"
    )


async def handle_settings(update: Update, context: ContextTypes.DEFAULT_TYPE, user: Dict[str, Any]) -> None:
    culture_name = PLANTS[user["culture"]]["name"]
    date_str = (
        user["planting_date"].strftime("%d.%m.%Y")
        if isinstance(user["planting_date"], date)
        else "не задана"
    )
    area_str = f'{user["area_m2"]} м²' if user.get("area_m2") else "не задана"

    buttons = [
        [InlineKeyboardButton("🗓 Установить дату посадки", callback_data="settings_date")],
        [InlineKeyboardButton("📏 Указать площадь грядки", callback_data="settings_area")],
        [InlineKeyboardButton("⬅️ В главное меню", callback_data="back_main")],
    ]

    text = (
        "⚙️ *Настройки*\n\n"
        f"Культура: *{culture_name}*\n"
        f"Дата посадки: *{
date_str}*\n"
        f"Площадь: *{area_str}*\n\n"
        "Выбери, что изменить:"
    )

    await update.callback_query.message.reply_text(
        text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown"
    )


async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    user = get_user(chat_id)
    data = query.data

    if data == "back_main":
        text, markup = build_main_menu(user)
        await query.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")
        return

    if data == "menu_calendar":
        await handle_calendar(update, context, user)
        return

    if data == "menu_fert":
        await handle_fert(update, context, user)
        return

    if data == "menu_settings":
        await handle_settings(update, context, user)
        return

    if data == "menu_help":
        await query.message.reply_text(
            "ℹ️ *Как пользоваться ботом*\n\n"
            "1. В настройках укажи дату посадки и площадь грядки.\n"
            "2. В разделе «Календарь работ» смотри задачи на ближайшие недели.\n"
            "3. В разделе «Подкормки» бот подскажет дозировки удобрений.\n\n"
            "Сейчас бот настроен на ирисы по мотивам рабочей тетради 1986 года 🌸",
            parse_mode="Markdown",
        )
        return

    if data == "settings_date":
        user["state"] = STATE_WAIT_DATE
        await query.message.reply_text(
            "🗓 Введи дату посадки в формате `ГГГГ-ММ-ДД`, например `2025-04-20`.",
            parse_mode="Markdown",
        )
        return

    if data == "settings_area":
        user["state"] = STATE_WAIT_AREA
        await query.message.reply_text(
            "📏 Введи примерную площадь грядки в м², например: `4` или `2.5`.",
            parse_mode="Markdown",
        )
        return

    if data == "fert_before":
        await send_fert_calc(update, context, user, "before_flowering")
        return

    if data == "fert_after":
        await send_fert_calc(update, context, user, "after_flowering")
        return


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    state = user.get("state")
    text = update.message.text.strip()

    if state == STATE_WAIT_DATE:
        try:
            planting_date = datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            await update.message.reply_text(
                "Не понимаю дату 😔\n"
                "Напиши в формате `ГГГГ-ММ-ДД`, например `2025-04-20`.",
                parse_mode="Markdown",
            )
            return
        user["planting_date"] = planting_date
        user["state"] = None
        await update.message.reply_text(
            f"Дата посадки сохранена: *{planting_date.strftime('%d.%m.%Y')}*",
            parse_mode="Markdown",
        )
        text_main, markup = build_main_menu(user)
        await update.message.reply_text(
            text_main, reply_markup=markup, parse_mode="Markdown"
        )
        return

    if state == STATE_WAIT_AREA:
        try:
            area = float(text.replace(",", "."))
            if area <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "Площадь должна быть положительным числом.\n"
                "Например: `4` или `2.5`.",
                parse_mode="Markdown",
            )
            return
        user["area_m2"] = area
        user["state"] = None
        await update.message.reply_text(
            f"Площадь грядки сохранена: *{area} м²*.",
            parse_mode="Markdown",
        )
        text_main, markup = build_main_menu(user)
        await update.message.reply_text(
            text_main, reply_markup=markup, parse_mode="Markdown"
        )
        return

    # Если никакого диалога не ждём — просто подскажем /start
    await update.message.reply_text(
        "Я тебя не совсем понял 🤔\nНажми /start, чтобы открыть меню."
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling update:", exc_info=context.error)


def main() -> None:
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CallbackQueryHandler(button_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.add_error_handler(error_handler)

    logger.info("Бот запущен (юзер-френдли версия). Ожидаю сообщения...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
