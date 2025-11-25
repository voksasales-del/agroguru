import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Токен бота берём из переменной окружения TELEGRAM_TOKEN
TOKEN = os.getenv("TELEGRAM_TOKEN")

# Простое хранилище данных в памяти
user_data: Dict[int, Dict[str, Any]] = {}

# Простейший "календарь работ" на основе смещений от даты посадки
# (offset_дней, название, категория, фаза)
TASKS: List[Tuple[int, str, str, str]] = [
    (0, "Посадка ирисов", "planting", "Посадка"),
    (7, "Проверить влажность почвы и при необходимости полить", "water", "Отрастание"),
    (20, "Рыхление междурядий и прополка", "care", "Отрастание"),
    (30, "Первая подкормка до цветения", "fertilize", "Бутонизация"),
    (45, "Осмотр на наличие пятен и вредителей", "inspect", "Бутонизация"),
    (60, "Удаление отцветших цветков", "cleanup", "Цветение"),
    (75, "Подкормка после цветения", "fertilize", "После цветения"),
    (100, "Деление и пересадка разросшихся кустов", "division", "После цветения"),
]

# Очень упрощённый пример норм удобрений, г/м²
FERT_RATES = {
    "before_flowering": {
        "Аммиачная селитра": 20,
        "Калийная соль": 30,
        "Суперфосфат": 40,
    },
    "after_flowering": {
        "Калийная соль": 20,
        "Суперфосфат": 30,
    },
}


def get_user(chat_id: int) -> Dict[str, Any]:
    if chat_id not in user_data:
        user_data[chat_id] = {}
    return user_data[chat_id]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user = get_user(chat_id)

    text_lines = [
        "🌸 Привет! Я бот-помощник по ирисам.",
        "",
        "Я умею:",
        "• хранить дату посадки и строить по ней календарь работ;",
        "• показывать задачи на ближайший месяц;",
        "• считать примерные нормы удобрений по площади грядки.",
        "",
        "1) Установи дату посадки командой:",
        "`/setdate 2025-04-20`",
        "2) Посмотри задачи на ближайший месяц:",
        "`/tasks`",
        "3) Посчитай удобрения по площади:",
        "`/fert 4`  – для грядки 4 м².",
    ]
    if user.get("planting_date"):
        text_lines.append("")
        text_lines.append(f"Текущая дата посадки: {user['planting_date'].strftime('%Y-%m-%d')}")

    keyboard = [
        [
            InlineKeyboardButton("📅 Задачи на месяц", callback_data="show_tasks"),
            InlineKeyboardButton("🧮 Удобрения", callback_data="show_fert_help"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "\n".join(text_lines),
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


async def set_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда: /setdate YYYY-MM-DD"""
    chat_id = update.effective_chat.id
    user = get_user(chat_id)

    if not context.args:
        await update.message.reply_text(
            "Укажи дату в формате: `/setdate 2025-04-20`",
            parse_mode="Markdown",
        )
        return

    date_str = context.args[0]
    try:
        planting_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        await update.message.reply_text(
            "Не понимаю дату. Используй формат: `ГГГГ-ММ-ДД`, например `2025-04-20`.",
            parse_mode="Markdown",
        )
        return

    user["planting_date"] = planting_date
    await update.message.reply_text(
        f"Дата посадки сохранена: {planting_date.strftime('%Y-%m-%d')}"
    )


def build_tasks_for_next_days(
    planting_date: datetime.date, days: int = 30
) -> List[Tuple[datetime.date, str, str, str]]:
    today = datetime.now().date()
    result: List[Tuple[datetime.date, str, str, str]] = []
    for offset, title, category, phase in TASKS:
        task_date = planting_date + timedelta(days=offset)
        if today <= task_date <= today + timedelta(days=days):
            result.append((task_date, title, category, phase))
    result.sort(key=lambda x: x[0])
    return result


async def tasks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда: /tasks – показать задачи на месяц."""
    chat_id = update.effective_chat.id
    user = get_user(chat_id)

    planting_date = user.get("planting_date")
    if not planting_date:
        await update.message.reply_text(
            "Сначала задай дату посадки командой `/setdate ГГГГ-ММ-ДД`.",
            parse_mode="Markdown",
        )
        return

    tasks = build_tasks_for_next_days(planting_date, days=30)
    if not tasks:
        await update.message.reply_text(
            "На ближайший месяц задач нет. Возможно, сейчас не активный сезон."
        )
        return

    lines = ["📅 Задачи на ближайшие 30 дней:"]
    for d, title, category, phase in tasks:
        lines.append(f"• {d.strftime('%d.%m')}: {title} ({phase})")
    await update.message.reply_text("\n".join(lines))


async def fert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда: /fert ПЛОЩАДЬ_В_М2 [этап]"""
    if not context.args:
        await update.message.reply_text(
            "Использование:\n"
            "`/fert 4 before`\n"
            "где 4 – площадь в м², а этап – `before` или `after`.",
            parse_mode="Markdown",
        )
        return

    try:
        area = float(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "Первая цифра должна быть площадью в м², например: `/fert 4`.",
            parse_mode="Markdown",
        )
        return

    stage_key = "before_flowering"
    if len(context.args) > 1:
        if context.args[1].lower().startswith("after"):
            stage_key = "after_flowering"

    rates = FERT_RATES.get(stage_key)
    if not rates:
        await update.message.reply_text(
            "Неизвестный этап. Используй `before` или `after`."
        )
        return

    lines = []
    for name, per_m2 in rates.items():
        total = per_m2 * area
        lines.append(f"{name}: {total:.0f} г (из расчёта {per_m2} г/м²)")

    stage_text = "до цветения" if stage_key == "before_flowering" else "после цветения"
    header = f"🧮 Примерные нормы удобрений {stage_text} для грядки {area} м²:"
    await update.message.reply_text(header + "\n" + "\n".join("• " + l for l in lines))


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "show_tasks":
        chat_id = query.message.chat_id
        user = get_user(chat_id)
        planting_date = user.get("planting_date")
        if not planting_date:
            await query.message.reply_text(
                "Сначала задай дату посадки командой `/setdate ГГГГ-ММ-ДД`.",
                parse_mode="Markdown",
            )
            return
        tasks = build_tasks_for_next_days(planting_date, days=30)
        if not tasks:
            await query.message.reply_text(
                "На ближайший месяц задач нет. Возможно, сейчас не активный сезон."
            )
            return
        lines = ["📅 Задачи на ближайшие 30 дней:"]
        for d, title, category, phase in tasks:
            lines.append(f"• {d.strftime('%d.%m')}: {title} ({phase})")
        await query.message.reply_text("\n".join(lines))
    elif data == "show_fert_help":
        await query.message.reply_text(
            "Команда для расчёта удобрений:\n"
            "`/fert 4 before` – для грядки 4 м², подкормка до цветения\n"
            "`/fert 4 after` – для грядки 4 м², подкормка после цветения",
            parse_mode="Markdown",
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling update:", exc_info=context.error)


def main() -> None:
    if not TOKEN:
        raise RuntimeError("Не задан TELEGRAM_TOKEN в переменных окружения")

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setdate", set_date))
    application.add_handler(CommandHandler("tasks", tasks_cmd))
    application.add_handler(CommandHandler("fert", fert_cmd))
    application.add_handler(CallbackQueryHandler(button_handler))

    application.add_error_handler(error_handler)

    logger.info("Бот запущен. Ожидаю сообщения...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
