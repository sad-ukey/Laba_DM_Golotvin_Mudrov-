import logging
import asyncio
import nest_asyncio
import calendar
from datetime import datetime, date, timedelta

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from pymongo import MongoClient
from bson.objectid import ObjectId


nest_asyncio.apply()


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Подключение к MongoDB
client = MongoClient("mongodb://localhost:27017/")
db = client["task_planner"]
entries_collection = db["entries"]
tasks_collection = db["tasks"]


# Функция для формирования главного меню (клавиатура)
def get_main_keyboard():
    keyboard = [
        ["Добавить запись", "Просмотреть записи"],
        ["Добавить задачу", "Просмотреть задачи"],
        ["Обновить задачу", "Удалить задачи за дату"],
        ["Просмотреть все данные"],
        ["Удалить все записи", "Удалить все задачи"],
        ["Отмена"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# --------------- Функции работы с данными ---------------
def add_entry(date_str: str, text: str):
    entry = {"date": date_str, "text": text}
    entries_collection.insert_one(entry)


def get_entries(date_str: str):
    return list(entries_collection.find({"date": date_str}))


def add_task(text: str, deadline: str, chat_id: int, status: str = "не выполнено", date_created: str = None):
    if date_created is None:
        date_created = date.today().isoformat()
    task = {
        "text": text,
        "deadline": deadline,  # ISO-формат
        "status": status,
        "date_created": date_created,
        "chat_id": chat_id,
        "reminders": {"day": False, "hour": False, "on_time": False},
    }
    tasks_collection.insert_one(task)


def get_tasks_by_date(date_str: str, chat_id: int):
    return list(tasks_collection.find({"date_created": date_str, "chat_id": chat_id}))


def get_tasks_by_chat(chat_id: int):
    return list(tasks_collection.find({"chat_id": chat_id}))


def update_task(task_id: str, new_text: str = None, new_status: str = None):
    update_fields = {}
    if new_text is not None:
        update_fields["text"] = new_text
    if new_status is not None:
        update_fields["status"] = new_status
    if update_fields:
        tasks_collection.update_one({"_id": ObjectId(task_id)}, {"$set": update_fields})


def delete_tasks_by_date(date_str: str, chat_id: int):
    tasks_collection.delete_many({"date_created": date_str, "chat_id": chat_id})


def delete_all_tasks():
    return tasks_collection.delete_many({})


def delete_all_entries():
    return entries_collection.delete_many({})


# --------------- Фоновая задача: Проверка дедлайнов ---------------
async def check_deadlines(bot):
    now = datetime.now()
    tasks = list(tasks_collection.find())
    for task in tasks:
        chat_id = task.get("chat_id")
        if not chat_id:
            continue
        try:
            deadline_dt = datetime.fromisoformat(task["deadline"])
        except Exception:
            continue
        reminders = task.get("reminders", {"day": False, "hour": False, "on_time": False})
        if not reminders.get("day") and (deadline_dt - now) <= timedelta(days=1) and deadline_dt > now:
            message = (
                f"⏰ <b>Напоминание!</b>\n"
                f"До дедлайна задачи <b>{task['text']}</b> осталось <b>1 день</b>.\n"
                f"📅 Дедлайн: {deadline_dt.strftime('%d.%m.%Y %H:%M')}"
            )
            await bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
            reminders["day"] = True
        if not reminders.get("hour") and (deadline_dt - now) <= timedelta(hours=1) and deadline_dt > now:
            message = (
                f"⏰ <b>Напоминание!</b>\n"
                f"До дедлайна задачи <b>{task['text']}</b> остался <b>1 час</b>.\n"
                f"📅 Дедлайн: {deadline_dt.strftime('%d.%m.%Y %H:%M')}"
            )
            await bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
            reminders["hour"] = True
        if not reminders.get("on_time") and now >= deadline_dt:
            message = (
                f"🚨 <b>Внимание!</b>\n"
                f"Сейчас наступил дедлайн задачи: <b>{task['text']}</b>.\n"
                f"Проверьте выполнение задачи!"
            )
            await bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
            reminders["on_time"] = True
        tasks_collection.update_one({"_id": task["_id"]}, {"$set": {"reminders": reminders}})


async def deadline_loop(app: Application):
    while True:
        await check_deadlines(app.bot)
        await asyncio.sleep(60)


# --------------- Команда /start и главное меню ---------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 <b>Привет!</b>\n\n"
        "Я бот-планировщик задач. Выберите нужное действие, нажав на кнопку ниже.\n"
        "Если захотите отменить текущую операцию, нажмите <i>Отмена</i>."
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=get_main_keyboard())


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Операция отменена.", reply_markup=get_main_keyboard())
    return ConversationHandler.END


# --------------- Диалог: Добавить запись ---------------
ADD_ENTRY_TEXT = 0


async def add_entry_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✏️ Введите текст записи для сегодняшнего дня:", parse_mode="HTML")
    return ADD_ENTRY_TEXT


async def add_entry_receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    today = date.today().isoformat()
    add_entry(today, text)
    await update.message.reply_text("✅ Запись успешно добавлена!", parse_mode="HTML", reply_markup=get_main_keyboard())
    return ConversationHandler.END


add_entry_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^Добавить запись$"), add_entry_start)],
    states={
        ADD_ENTRY_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_entry_receive_text)]
    },
    fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex("^Отмена$"), cancel)],
)

# --------------- Диалог: Просмотреть записи ---------------
VIEW_ENTRIES_DATE = 0


async def view_entries_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📅 Введите дату (в формате ГГГГ-ММ-ДД), для которой хотите посмотреть записи:",
                                    parse_mode="HTML")
    return VIEW_ENTRIES_DATE


async def view_entries_receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_str = update.message.text
    entries = get_entries(date_str)
    if not entries:
        response = "❌ <b>Записей за указанную дату не найдено.</b>"
    else:
        response = "\n".join([f"📅 <b>{entry['date']}</b> — ✏️ {entry['text']}" for entry in entries])
    await update.message.reply_text(response, parse_mode="HTML", reply_markup=get_main_keyboard())
    return ConversationHandler.END


view_entries_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^Просмотреть записи$"), view_entries_start)],
    states={
        VIEW_ENTRIES_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, view_entries_receive_date)]
    },
    fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex("^Отмена$"), cancel)],
)

# --------------- Диалог: Добавить задачу с выбором даты через ввод года, выбор месяца и числа ---------------
# Состояния: 0 - текст задачи, 1 - год, 2 - месяц, 3 - день, 4 - время
ADD_TASK_TEXT, ADD_TASK_YEAR, ADD_TASK_MONTH, ADD_TASK_DAY, ADD_TASK_TIME = range(5)


async def add_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 Введите текст задачи:", parse_mode="HTML")
    return ADD_TASK_TEXT


async def add_task_receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["task_text"] = update.message.text
    await update.message.reply_text("📅 Введите год дедлайна (например, 2025):", parse_mode="HTML")
    return ADD_TASK_YEAR


async def add_task_receive_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    year_text = update.message.text.strip()
    try:
        year = int(year_text)
        if year < 1900 or year > 3000:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Неверный год. Введите год числом (например, 2025):", parse_mode="HTML")
        return ADD_TASK_YEAR
    context.user_data["task_year"] = year
    # Предлагаем выбрать месяц из инлайн-клавиатуры
    keyboard = generate_month_keyboard()
    await update.message.reply_text("📅 Выберите месяц:", reply_markup=keyboard, parse_mode="HTML")
    return ADD_TASK_MONTH


def generate_month_keyboard():
    months = [
        ("Январь", 1), ("Февраль", 2), ("Март", 3),
        ("Апрель", 4), ("Май", 5), ("Июнь", 6),
        ("Июль", 7), ("Август", 8), ("Сентябрь", 9),
        ("Октябрь", 10), ("Ноябрь", 11), ("Декабрь", 12)
    ]
    buttons = []
    row = []
    for i, (name, month_num) in enumerate(months, start=1):
        row.append(InlineKeyboardButton(text=name, callback_data=f"month_{month_num}"))
        if i % 3 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


async def add_task_month_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("month_"):
        month = int(data.split("_")[1])
        context.user_data["task_month"] = month
        # Определяем количество дней в выбранном месяце
        year = context.user_data.get("task_year")
        num_days = calendar.monthrange(year, month)[1]
        keyboard = generate_day_keyboard(num_days)
        await query.edit_message_text("📅 Выберите число:", reply_markup=keyboard, parse_mode="HTML")
        return ADD_TASK_DAY
    else:
        await query.edit_message_text("❌ Неверный выбор. Попробуйте снова.")
        return ADD_TASK_MONTH


def generate_day_keyboard(num_days):
    buttons = []
    row = []
    for day in range(1, num_days + 1):
        row.append(InlineKeyboardButton(text=str(day), callback_data=f"day_{day}"))
        if day % 7 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


async def add_task_day_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("day_"):
        day = int(data.split("_")[1])
        context.user_data["task_day"] = day
        await query.edit_message_text("⏰ Введите время дедлайна в формате <code>HH:MM</code> (например, 18:00):",
                                      parse_mode="HTML")
        return ADD_TASK_TIME
    else:
        await query.edit_message_text("❌ Неверный выбор. Попробуйте снова.")
        return ADD_TASK_DAY


async def add_task_receive_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_input = update.message.text.strip()
    try:
        time_obj = datetime.strptime(time_input, "%H:%M").time()
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат времени. Введите время в формате <code>HH:MM</code> (например, 18:00):",
            parse_mode="HTML"
        )
        return ADD_TASK_TIME
    # Собираем год, месяц и день
    year = context.user_data.get("task_year")
    month = context.user_data.get("task_month")
    day = context.user_data.get("task_day")
    try:
        deadline_dt = datetime(year, month, day, time_obj.hour, time_obj.minute)
    except Exception as e:
        await update.message.reply_text("❌ Ошибка формирования даты. Попробуйте снова.", parse_mode="HTML")
        return ConversationHandler.END
    deadline_iso = deadline_dt.isoformat()
    task_text = context.user_data.get("task_text")
    chat_id = update.message.chat.id
    add_task(task_text, deadline_iso, chat_id)
    await update.message.reply_text("✅ Задача успешно добавлена!", parse_mode="HTML", reply_markup=get_main_keyboard())
    return ConversationHandler.END


add_task_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^Добавить задачу$"), add_task_start)],
    states={
        ADD_TASK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_receive_text)],
        ADD_TASK_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_receive_year)],
        ADD_TASK_MONTH: [CallbackQueryHandler(add_task_month_selected, pattern="^month_")],
        ADD_TASK_DAY: [CallbackQueryHandler(add_task_day_selected, pattern="^day_")],
        ADD_TASK_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_receive_time)],
    },
    fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex("^Отмена$"), cancel)],
)

# --------------- Диалог: Просмотреть задачи ---------------
VIEW_TASKS_DATE = 0


async def view_tasks_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📅 Введите дату (в формате ГГГГ-ММ-ДД), для которой хотите посмотреть задачи:",
                                    parse_mode="HTML")
    return VIEW_TASKS_DATE


async def view_tasks_receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_str = update.message.text
    chat_id = update.message.chat.id
    tasks = get_tasks_by_date(date_str, chat_id)
    if not tasks:
        response = "❌ <b>Задач за указанную дату не найдено.</b>"
    else:
        now = datetime.now()
        response_lines = []
        for task in tasks:
            try:
                deadline_dt = datetime.fromisoformat(task["deadline"])
                time_remaining = deadline_dt - now
                remaining_str = "Время истекло" if time_remaining.total_seconds() < 0 else \
                str(time_remaining).split('.')[0]
            except Exception:
                remaining_str = "Ошибка в дедлайне"
            response_lines.append(
                f"🆔 <b>{task['_id']}</b> | 📝 {task['text']} | 📅 {deadline_dt.strftime('%d.%m.%Y %H:%M')} | 🔄 {task['status']} | ⏳ {remaining_str}"
            )
        response = "\n".join(response_lines)
    await update.message.reply_text(response, parse_mode="HTML", reply_markup=get_main_keyboard())
    return ConversationHandler.END


view_tasks_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^Просмотреть задачи$"), view_tasks_start)],
    states={
        VIEW_TASKS_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, view_tasks_receive_date)]
    },
    fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex("^Отмена$"), cancel)],
)

# --------------- Диалог: Обновить задачу (с выбором из списка) ---------------
# Состояния: 0 - выбор задачи, 1 - выбор изменения текста, 2 - ввод нового текста, 3 - выбор статуса
UPDATE_TASK_SELECT, UPDATE_TASK_TEXT_OPTION, UPDATE_TASK_TEXT_INPUT, UPDATE_TASK_STATUS = range(4)


async def update_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    tasks = get_tasks_by_chat(chat_id)
    if not tasks:
        await update.message.reply_text("❌ Нет задач для обновления.", reply_markup=get_main_keyboard())
        return ConversationHandler.END
    buttons = []
    for task in tasks:
        deadline_dt = datetime.fromisoformat(task["deadline"])
        button_text = f"📝 {task['text']} (📅 {deadline_dt.strftime('%d.%m.%Y %H:%M')})"
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"upd_{task['_id']}")])
    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Выберите задачу для обновления:", reply_markup=reply_markup)
    return UPDATE_TASK_SELECT


async def update_task_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("upd_"):
        task_id = data[4:]
        context.user_data["update_task_id"] = task_id
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Изменить текст", callback_data="text_change"),
             InlineKeyboardButton("🔒 Не изменять текст", callback_data="text_keep")]
        ])
        await query.edit_message_text("Хотите изменить текст задачи?", reply_markup=keyboard)
        return UPDATE_TASK_TEXT_OPTION
    return ConversationHandler.END


async def update_task_text_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "text_change":
        await query.edit_message_text("✏️ Введите новый текст задачи:")
        return UPDATE_TASK_TEXT_INPUT
    elif data == "text_keep":
        context.user_data["update_task_new_text"] = None
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ выполнено", callback_data="status_выполнено"),
             InlineKeyboardButton("❌ не выполнено", callback_data="status_не выполнено")]
        ])
        await query.edit_message_text("Выберите новый статус задачи:", reply_markup=keyboard)
        return UPDATE_TASK_STATUS
    else:
        await query.edit_message_text("❌ Неверный выбор. Попробуйте снова.")
        return UPDATE_TASK_TEXT_OPTION


async def update_task_receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_text = update.message.text.strip()
    context.user_data["update_task_new_text"] = new_text
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ выполнено", callback_data="status_выполнено"),
         InlineKeyboardButton("❌ не выполнено", callback_data="status_не выполнено")]
    ])
    await update.message.reply_text("Выберите новый статус задачи:", reply_markup=keyboard)
    return UPDATE_TASK_STATUS


async def update_task_status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # формат "status_выполнено" или "status_не выполнено"
    if data.startswith("status_"):
        new_status = data[7:]
        context.user_data["update_task_new_status"] = new_status
        task_id = context.user_data.get("update_task_id")
        new_text = context.user_data.get("update_task_new_text")
        logger.info(f"Обновляем задачу {task_id}: новый текст: {new_text}, новый статус: {new_status}")
        try:
            update_task(task_id, new_text, new_status)
            await query.edit_message_text("✅ Задача успешно обновлена!")
        except Exception as e:
            logger.error(f"Ошибка при обновлении задачи {task_id}: {e}")
            await query.edit_message_text("❌ Ошибка при обновлении задачи.")
        return ConversationHandler.END
    return ConversationHandler.END


update_task_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^Обновить задачу$"), update_task_start)],
    states={
        UPDATE_TASK_SELECT: [CallbackQueryHandler(update_task_select, pattern="^upd_")],
        UPDATE_TASK_TEXT_OPTION: [CallbackQueryHandler(update_task_text_option, pattern="^(text_change|text_keep)$")],
        UPDATE_TASK_TEXT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_task_receive_text)],
        UPDATE_TASK_STATUS: [CallbackQueryHandler(update_task_status_handler, pattern="^status_")],
    },
    fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex("^Отмена$"), cancel)],
)

# --------------- Диалог: Удалить задачи за дату ---------------
DELETE_TASKS_DATE = 0


async def delete_tasks_date_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📅 Введите дату (ГГГГ-ММ-ДД), для которой хотите удалить задачи:",
                                    parse_mode="HTML")
    return DELETE_TASKS_DATE


async def delete_tasks_date_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_str = update.message.text
    chat_id = update.message.chat.id
    delete_tasks_by_date(date_str, chat_id)
    await update.message.reply_text("✅ Все задачи за указанную дату удалены.", parse_mode="HTML",
                                    reply_markup=get_main_keyboard())
    return ConversationHandler.END


delete_tasks_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^Удалить задачи за дату$"), delete_tasks_date_start)],
    states={
        DELETE_TASKS_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_tasks_date_receive)]
    },
    fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex("^Отмена$"), cancel)],
)

# --------------- Диалог: Удалить все записи ---------------
CONFIRM_DELETE_ALL_ENTRIES = 0


async def delete_all_entries_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚠️ Вы уверены, что хотите удалить <b>ВСЕ</b> записи? Напишите <i>да</i> для подтверждения:",
        parse_mode="HTML",
    )
    return CONFIRM_DELETE_ALL_ENTRIES


async def delete_all_entries_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.lower() == "да":
        result = delete_all_entries()
        await update.message.reply_text(f"✅ Удалено записей: {result.deleted_count}.", parse_mode="HTML",
                                        reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text("❌ Операция отменена.", parse_mode="HTML", reply_markup=get_main_keyboard())
    return ConversationHandler.END


delete_all_entries_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^Удалить все записи$"), delete_all_entries_start)],
    states={
        CONFIRM_DELETE_ALL_ENTRIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_all_entries_confirm)]
    },
    fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex("^Отмена$"), cancel)],
)

# --------------- Диалог: Удалить все задачи ---------------
CONFIRM_DELETE_ALL_TASKS = 0


async def delete_all_tasks_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚠️ Вы уверены, что хотите удалить <b>ВСЕ</b> задачи? Напишите <i>да</i> для подтверждения:",
        parse_mode="HTML",
    )
    return CONFIRM_DELETE_ALL_TASKS


async def delete_all_tasks_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.lower() == "да":
        result = delete_all_tasks()
        await update.message.reply_text(f"✅ Удалено задач: {result.deleted_count}.", parse_mode="HTML",
                                        reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text("❌ Операция отменена.", parse_mode="HTML", reply_markup=get_main_keyboard())
    return ConversationHandler.END


delete_all_tasks_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^Удалить все задачи$"), delete_all_tasks_start)],
    states={
        CONFIRM_DELETE_ALL_TASKS: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_all_tasks_confirm)]
    },
    fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex("^Отмена$"), cancel)],
)


# --------------- Команда: Просмотреть все данные (без диалога) ---------------
async def view_all_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_entries = list(entries_collection.find())
    all_tasks = list(tasks_collection.find())

    response_parts = ["<b>ВСЕ ДАННЫЕ:</b>"]
    response_parts.append("\n<b>Записи:</b>")
    if not all_entries:
        response_parts.append("  Нет записей.")
    else:
        for entry in all_entries:
            response_parts.append(f"  📅 <b>{entry.get('date', 'N/A')}</b> — ✏️ {entry.get('text', '')}")

    response_parts.append("\n<b>Задачи:</b>")
    if not all_tasks:
        response_parts.append("  Нет задач.")
    else:
        now = datetime.now()
        for task in all_tasks:
            try:
                deadline_dt = datetime.fromisoformat(task["deadline"])
                time_remaining = deadline_dt - now
                remaining_str = "Время истекло" if time_remaining.total_seconds() < 0 else \
                str(time_remaining).split('.')[0]
            except Exception:
                remaining_str = "Ошибка в дедлайне"
            response_parts.append(
                f"  🆔 <b>{task.get('_id')}</b> | 📝 {task.get('text')} | 📅 {datetime.fromisoformat(task.get('deadline')).strftime('%d.%m.%Y %H:%M')} | 🔄 {task.get('status')} | ⏳ {remaining_str}"
            )
    await update.message.reply_text("\n".join(response_parts), parse_mode="HTML", reply_markup=get_main_keyboard())


# --------------- Основная функция ---------------
async def main():
    TOKEN = "7757802683:AAEAL6v68Jq9eoVSQwOWbKSSoJh5TNJu4sA"  # Замените на свой токен от BotFather
    app = Application.builder().token(TOKEN).build()

    # Регистрируем обработчики диалогов и команд
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(add_entry_conv)
    app.add_handler(view_entries_conv)
    app.add_handler(add_task_conv)
    app.add_handler(view_tasks_conv)
    app.add_handler(update_task_conv)
    app.add_handler(delete_tasks_conv)
    app.add_handler(delete_all_entries_conv)
    app.add_handler(delete_all_tasks_conv)
    app.add_handler(MessageHandler(filters.Regex("^Просмотреть все данные$"), view_all_data))
    app.add_handler(CommandHandler("cancel", cancel))

    # Фоновая задача проверки дедлайнов
    app.create_task(deadline_loop(app))

    # Запускаем polling без закрытия event loop
    await app.run_polling(close_loop=False)


if __name__ == "__main__":
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.create_task(main())
    loop.run_forever()