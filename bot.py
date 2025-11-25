import logging
import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TELEGRAM_TOKEN')

user_data = {}

FERTILIZER_RATES = {
    'супесь': {'corovyak': 1, 'nitrogen': 30, 'phosphate': 50, 'potash': 20},
    'суглинок': {'corovyak': 1, 'nitrogen': 35, 'phosphate': 60, 'potash': 35},
    'тяжелый_суглинок': {'corovyak': 1, 'nitrogen': 35, 'phosphate': 60, 'potash': 35}
}

WORK_SCHEDULE = [
    (-30, 'Подготовка участка', 'prep', 'Подготовка'),
    (-15, 'Перекопка и выравнивание', 'soil', 'Подготовка'),
    (-5, 'Внесение удобрений перед посадкой', 'fertilize', 'Подготовка'),
    
    (0, 'Посадка корневищ', 'plant', 'Посадка'),
    (0, 'Обильный полив', 'water', 'Посадка'),
    (5, 'Мульчирование торфом/перегноем', 'mulch', 'Посадка'),
    
    (200, 'Подкормка по снегу (апрель)', 'fertilize', 'Отрастание'),
    (210, 'Удаление отмерших частей', 'cleanup', 'Отрастание'),
    (215, 'Рыхление почвы', 'soil', 'Отрастание'),
    
    (230, 'Подкормка в период отрастания', 'fertilize', 'Отрастание'),
    (235, 'Полив обильный', 'water', 'Отрастание'),
    (240, 'Обработка против ржавчины', 'pest', 'Отрастание'),
    
    (260, 'Подкормка до цветения', 'fertilize', 'Бутонизация'),
    (265, 'Полив перед цветением', 'water', 'Бутонизация'),
    (270, 'Обработка Бордоской жидкостью', 'disease', 'Бутонизация'),
    
    (285, 'Удаление отцветших соцветий', 'cleanup', 'Цветение'),
    (290, 'Опрыскивание против трипсов и тлей', 'pest', 'Цветение'),
    
    (310, 'Первая подкормка после цветения', 'fertilize', 'После цветения'),
    (325, 'Вторая подкормка после цветения', 'fertilize', 'После цветения'),
    (330, 'Полив (развитие почек)', 'water', 'После цветения'),
    
    (350, 'Осенняя перекопка (12-15 см)', 'soil', 'Подготовка к зиме'),
    (355, 'Удаление отмерших листьев', 'cleanup', 'Подготовка к зиме'),
    (360, 'Подокучивание корневищ', 'prep', 'Подготовка к зиме'),
]

TYPE_EMOJI = {
    'water': '💧',
    'fertilize': '🌱',
    'pest': '🐛',
    'disease': '🦠',
    'cleanup': '🗑️',
    'soil': '🌍',
    'prep': '📋',
    'plant': '🌿',
    'mulch': '🥀'
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Стартовая команда"""
    keyboard = [
        [InlineKeyboardButton('📅 Календарь работ', callback_data='calendar')],
        [InlineKeyboardButton('✅ Чек-листы', callback_data='checklist')],
        [InlineKeyboardButton('🧮 Калькулятор удобрений', callback_data='calculator')],
        [InlineKeyboardButton('⚙️ Мои параметры', callback_data='settings')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        '🌸 Добро пожаловать в AgroGuru!\n\n'
        'Советская рабочая тетрадь 1986 года\n'
        'Выращивание ИРИСОВ в Telegram\n\n'
        'Выбери, что нужно:',
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if query.data == 'calendar':
        await show_calendar(query, user_id, context)
    elif query.data == 'checklist':
        await show_checklist(query, user_id)
    elif query.data == 'calculator':
        await show_calculator_menu(query, user_id)
    elif query.data == 'settings':
        await show_settings(query, user_id, context)
    elif query.data.startswith('set_date_'):
        await set_date(query, user_id, context)
    elif query.data.startswith('set_soil_'):
        await set_soil(query, user_id, context)
    elif query.data.startswith('set_area_'):
        await set_area(query, user_id, context)
    elif query.data == 'calc_fertilizer':
        await calculate_fertilizer(query, user_id)
    elif query.data.startswith('phase_'):
        phase = query.data.replace('phase_', '')
        await show_phase_checklist(query, user_id, phase)
    elif query.data == 'back_to_menu':
        await back_to_menu(query)
    elif query.data == 'set_date_dialog':
        await show_date_options(query)
    elif query.data == 'set_soil_dialog':
        await show_soil_options(query)
    elif query.data == 'set_area_dialog':
        await show_area_options(query)
    elif query.data == 'calendar':
        await show_calendar(query, user_id, context)
    elif query.data == 'checklist':
        await show_checklist(query, user_id)

async def show_calendar(query, user_id, context):
    """Показывает календарь работ"""
    if user_id not in user_data or 'planting_date' not in user_data[user_id]:
        await query.edit_message_text('⚠️ Сначала установи дату посадки в параметрах!')
        return
    
    planting_date = datetime.strptime(user_data[user_id]['planting_date'], '%Y-%m-%d')
    
    text = '📅 *Календарь работ на год*\n\n'
    current_phase = None
    
    for days_offset, name, work_type, phase in WORK_SCHEDULE:
        work_date = planting_date + timedelta(days=days_offset)
        
        if phase != current_phase:
            text += f'\n*{phase}*\n'
            current_phase = phase
        
        emoji = TYPE_EMOJI.get(work_type, '📌')
        date_str = work_date.strftime('%d.%m.%Y')
        text += f'{emoji} {name}\n   {date_str}\n'
    
    keyboard = [[InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_checklist(query, user_id):
    """Показывает меню чек-листов по этапам"""
    phases = [
        'Подготовка', 'Посадка', 'Отрастание', 
        'Бутонизация', 'Цветение', 'После цветения', 
        'Подготовка к зиме'
    ]
    
    keyboard = [[InlineKeyboardButton(phase, callback_data=f'phase_{phase}')] for phase in phases]
    keyboard.append([InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        '✅ *Выбери этап:*',
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_phase_checklist(query, user_id, phase):
    """Показывает чек-лист для конкретного этапа"""
    tasks = [task for task in WORK_SCHEDULE if task[3] == phase]
    
    text = f'✅ *{phase}*\n\n'
    for i, (days_offset, name, work_type, _) in enumerate(tasks):
        emoji = TYPE_EMOJI.get(work_type, '📌')
        text += f'{emoji} {name}\n'
    
    keyboard = [[InlineKeyboardButton('◀️ Назад', callback_data='checklist')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_calculator_menu(query, user_id):
    """Меню калькулятора"""
    keyboard = [
        [InlineKeyboardButton('🧮 Рассчитать удобрения', callback_data='calc_fertilizer')],
        [InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        '🧮 *Калькулятор*\n\nВыбери действие:',
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def calculate_fertilizer(query, user_id):
    """Рассчитывает удобрения"""
    if user_id not in user_data:
        await query.edit_message_text('⚠️ Установи параметры в меню настроек!')
        return
    
    user = user_data[user_id]
    soil = user.get('soil', 'суглинок')
    area = user.get('area', 10)
    
    rates = FERTILIZER_RATES.get(soil, FERTILIZER_RATES['суглинок'])
    
    text = f'🧮 *Расчет удобрений на {area} м²*\n'
    text += f'Тип почвы: *{soil}*\n\n'
    
    text += f'🐄 Коровяк (1:15): *{rates["corovyak"] * area} ведер*\n'
    text += f'💛 Аммиачная селитра: *{int(rates["nitrogen"] * area * 3)} г* (за сезон)\n'
    text += f'⚪ Суперфосфат: *{int(rates["phosphate"] * area * 2)} г*\n'
    text += f'🟠 Калийная соль: *{int(rates["potash"] * area * 4)} г*\n\n'
    
    text += '💡 *Режим подкормок:*\n'
    text += '🌱 Апрель: по снегу\n'
    text += '🌿 Май-июнь: перед цветением\n'
    text += '🌸 После цветения: 2 раза с интервалом 15-20 дней\n\n'
    text += '⚠️ Перед подкормкой обильно полить!'
    
    keyboard = [[InlineKeyboardButton('◀️ Назад', callback_data='calculator')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_settings(query, user_id, context):
    """Показывает настройки"""
    text = '⚙️ *Твои параметры:*\n\n'
    
    if user_id in user_data:
        user = user_data[user_id]
        text += f'📅 Дата посадки: {user.get("planting_date", "не установлена")}\n'
        text += f'🌍 Тип почвы: {user.get("soil", "не установлен")}\n'
        text += f'📏 Площадь: {user.get("area", "не установлена")} м²\n\n'
    
    keyboard = [
        [InlineKeyboardButton('📅 Установить дату посадки', callback_data='set_date_dialog')],
        [InlineKeyboardButton('🌍 Выбрать тип почвы', callback_data='set_soil_dialog')],
        [InlineKeyboardButton('📏 Установить площадь', callback_data='set_area_dialog')],
        [InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_date_options(query):
    """Показывает варианты дат"""
    keyboard = [
        [InlineKeyboardButton('Сегодня', callback_data='set_date_today')],
        [InlineKeyboardButton('Через 7 дней', callback_data='set_date_week')],
        [InlineKeyboardButton('Август 2025', callback_data='set_date_august')],
        [InlineKeyboardButton('◀️ Назад', callback_data='settings')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text('📅 Выбери дату посадки:', reply_markup=reply_markup)

async def show_soil_options(query):
    """Показывает варианты почв"""
    keyboard = [
        [InlineKeyboardButton('Супесь', callback_data='set_soil_superl')],
        [InlineKeyboardButton('Суглинок', callback_data='set_soil_susuglinok')],
        [InlineKeyboardButton('Тяжелый суглинок', callback_data='set_soil_heavy')],
        [InlineKeyboardButton('◀️ Назад', callback_data='settings')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text('🌍 Выбери тип почвы:', reply_markup=reply_markup)

async def show_area_options(query):
    """Показывает варианты площадей"""
    keyboard = [
        [InlineKeyboardButton('5 м²', callback_data='set_area_5')],
        [InlineKeyboardButton('10 м²', callback_data='set_area_10')],
        [InlineKeyboardButton('20 м²', callback_data='set_area_20')],
        [InlineKeyboardButton('50 м²', callback_data='set_area_50')],
        [InlineKeyboardButton('◀️ Назад', callback_data='settings')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text('📏 Выбери площадь участка:', reply_markup=reply_markup)

async def set_date(query, user_id, context):
    """Установка даты посадки"""
    today = datetime.now()
    date_map = {
        'set_date_today': today,
        'set_date_week': today + timedelta(days=7),
        'set_date_august': datetime(2025, 8, 20),
    }
    
    date = date_map.get(query.data, today)
    
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id]['planting_date'] = date.strftime('%Y-%m-%d')
    
    await query.edit_message_text(f'✅ Дата установлена: {date.strftime("%d.%m.%Y")}')

async def set_soil(query, user_id, context):
    """Установка типа почвы"""
    soil_map = {
        'set_soil_superl': 'супесь',
        'set_soil_susuglinok': 'суглинок',
        'set_soil_heavy': 'тяжелый_суглинок'
    }
    soil = soil_map.get(query.data, 'суглинок')
    
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id]['soil'] = soil
    
    await query.edit_message_text(f'✅ Тип почвы установлен: {soil}')

async def set_area(query, user_id, context):
    """Установка площади"""
    area_map = {
        'set_area_5': 5,
        'set_area_10': 10,
        'set_area_20': 20,
        'set_area_50': 50,
    }
    area = area_map.get(query.data, 10)
    
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id]['area'] = area
    
    await query.edit_message_text(f'✅ Площадь установлена: {area} м²')

async def back_to_menu(query):
    """Возврат в главное меню"""
    keyboard = [
        [InlineKeyboardButton('📅 Календарь работ', callback_data='calendar')],
        [InlineKeyboardButton('✅ Чек-листы', callback_data='checklist')],
        [InlineKeyboardButton('🧮 Калькулятор удобрений', callback_data='calculator')],
        [InlineKeyboardButton('⚙️ Мои параметры', callback_data='settings')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        '🌸 AgroGuru - Главное меню\n\nВыбери, что нужно:',
        reply_markup=reply_markup
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

def main():
    """Запуск бота"""
    if not TOKEN:
        print("❌ ОШИБКА: переменная TELEGRAM_TOKEN не установлена!")
        return
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_error_handler(error_handler)
    
    print('🤖 AgroGuru бот запущен!')
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
