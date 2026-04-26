import os
import sys
import json
import time
import threading
import sqlite3
import requests
import telebot
from telebot import types
from datetime import datetime

# ==================== УСТАНОВКА ЗАВИСИМОСТЕЙ ====================
try:
    import cv2
    import numpy as np
except ImportError:
    os.system(f'{sys.executable} -m pip install opencv-python-headless numpy')
    import cv2
    import numpy as np

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = os.getenv('BOT_TOKEN', "8740649289:AAH1lk4yL2c9RR_ebpDXvlv-rV_g6cIYnBE")
ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', "105635005").split(',')]
DATA_DIR = os.getenv('DATA_DIR', '/app/data')
GROUP_ID = os.getenv('GROUP_ID', "-1003945636594")  # ID группы для выдачи номеров

os.makedirs(DATA_DIR, exist_ok=True)
bot = telebot.TeleBot(BOT_TOKEN)

# Ссылка на фото для главного меню
MAIN_PHOTO_URL = "https://i.postimg.cc/tT26DbfG/IMG-9788.jpg"

# ==================== БАЗА ДАННЫХ ====================
DB_PATH = os.path.join(DATA_DIR, 'numbers_bot.db')

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, 
            username TEXT, 
            balance REAL DEFAULT 0,
            registered_date TEXT
        );
        
        CREATE TABLE IF NOT EXISTS numbers_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            country TEXT,
            operator TEXT,
            price REAL DEFAULT 0,
            status TEXT DEFAULT 'available',
            added_date TEXT,
            taken_by INTEGER,
            taken_date TEXT
        );
        
        CREATE TABLE IF NOT EXISTS rent_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number_id INTEGER,
            user_id INTEGER,
            phone TEXT,
            rent_date TEXT,
            end_date TEXT,
            price REAL,
            status TEXT
        );
    ''')
    conn.commit()
    conn.close()

# ==================== ФУНКЦИИ ОЧЕРЕДИ ====================
def add_number_to_queue(phone, country="", operator="", price=0):
    """Добавить номер в очередь"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO numbers_queue (phone, country, operator, price, status, added_date) VALUES (?, ?, ?, ?, 'available', datetime('now'))",
        (phone, country, operator, price)
    )
    conn.commit()
    conn.close()

def get_next_number():
    """Получить следующий номер из очереди"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM numbers_queue WHERE status = 'available' ORDER BY id ASC LIMIT 1")
    number = cursor.fetchone()
    conn.close()
    return number

def assign_number(number_id, user_id):
    """Выдать номер пользователю"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE numbers_queue SET status = 'taken', taken_by = ?, taken_date = datetime('now') WHERE id = ?",
        (user_id, number_id)
    )
    conn.commit()
    conn.close()

def get_queue_count():
    """Количество номеров в очереди"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM numbers_queue WHERE status = 'available'")
    count = cursor.fetchone()['cnt']
    conn.close()
    return count

def get_queue_list():
    """Список всех номеров в очереди"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM numbers_queue WHERE status = 'available' ORDER BY id ASC")
    numbers = cursor.fetchall()
    conn.close()
    return numbers

# ==================== КЛАВИАТУРЫ ====================
def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📱 Получить номер", "📊 Очередь")
    markup.add("💰 Баланс", "📋 Мои номера")
    markup.add("ℹ️ Инфо", "📞 Поддержка")
    if user_id in ADMIN_IDS:
        markup.add("➕ Добавить номера", "🔧 Админ")
    return markup

def admin_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ Добавить номер", callback_data="add_number"),
        types.InlineKeyboardButton("📋 Все номера", callback_data="all_numbers"),
        types.InlineKeyboardButton("📊 Статистика", callback_data="stats"),
        types.InlineKeyboardButton("🗑 Очистить очередь", callback_data="clear_queue")
    )
    return markup

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, balance, registered_date) VALUES (?, ?, 0, datetime('now'))", (user_id, username))
    conn.commit()
    conn.close()
    
    text = (
        "💸 <b>Juss Hell Service</b> - приемка и аренда номеров.\n"
        "Вы можете сдать свой номер, получить оплату\n"
        "и вести статистику аренд.\n\n"
        "Более подробно вы можете узнать снизу 👇.\n\n"
        f"📱 Номеров в очереди: <b>{get_queue_count()}</b>\n"
        f"💰 Баланс: <b>$0.00</b>\n"
        f"💳 Мин. вывод: <b>$10.00</b>\n\n"
        "📞 Техподдержка: @auzom"
    )
    
    try:
        bot.send_photo(
            message.chat.id,
            MAIN_PHOTO_URL,
            caption=text,
            parse_mode="HTML",
            reply_markup=main_menu(user_id)
        )
    except:
        bot.send_message(
            message.chat.id,
            text,
            parse_mode="HTML",
            reply_markup=main_menu(user_id)
        )

@bot.message_handler(commands=['add_numbers'])
def add_numbers_command(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    msg = bot.send_message(
        message.chat.id,
        "📱 *Добавление номеров*\n\n"
        "Отправьте номера в формате:\n"
        "номер1, номер2, номер3\n\n"
        "Или:\n"
        "+79141624117, +79261234567",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, process_add_numbers)

def process_add_numbers(message):
    numbers = [n.strip() for n in message.text.split(',')]
    added = 0
    
    for phone in numbers:
        if phone and len(phone) >= 10:
            add_number_to_queue(phone)
            added += 1
    
    bot.send_message(
        message.chat.id,
        f"✅ Добавлено номеров: {added}\n"
        f"📱 Всего в очереди: {get_queue_count()}",
        reply_markup=main_menu(message.from_user.id)
    )
    
    # Обновляем информацию в группе
    update_group_info()

# ==================== ВЫДАЧА НОМЕРА ====================
def give_number_to_user(user_id, chat_id):
    """Выдать номер пользователю"""
    number = get_next_number()
    
    if not number:
        bot.send_message(
            chat_id,
            "❌ <b>Номера закончились!</b>\n\n"
            "Ожидайте пополнения очереди.",
            parse_mode="HTML"
        )
        return
    
    assign_number(number['id'], user_id)
    
    text = (
        "✅ <b>Номер выдан!</b>\n\n"
        f"📱 Номер: <code>{number['phone']}</code>\n"
        f"🆔 ID: {number['id']}\n"
        f"📅 Выдан: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        "⚠️ Номер активен 20 минут!"
    )
    
    bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=main_menu(user_id))
    
    # Уведомление в группу
    queue_msg = (
        f"📱 Выдан номер: <code>{number['phone']}</code>\n"
        f"Осталось в очереди: {get_queue_count()}"
    )
    try:
        bot.send_message(GROUP_ID, queue_msg, parse_mode="HTML")
    except:
        pass

# ==================== ОБРАБОТЧИК ГРУППЫ ====================
@bot.message_handler(func=lambda message: message.chat.type in ['group', 'supergroup'])
def handle_group_message(message):
    text = message.text.lower().strip()
    
    # Выдача номера по запросу "номер"
    if text == "номер" or text == "номе" or text == "номер!":
        number = get_next_number()
        
        if number:
            assign_number(number['id'], message.from_user.id)
            
            response = (
                f"📱 <b>Номер для @{message.from_user.username or 'User'}</b>\n\n"
                f"📞 Номер: <code>{number['phone']}</code>\n"
                f"🆔 ID: {number['id']}\n"
                f"📊 Осталось: {get_queue_count()} номеров\n\n"
                f"⚠️ Номер активен 20 минут!"
            )
            
            bot.reply_to(message, response, parse_mode="HTML")
        else:
            bot.reply_to(
                message,
                "❌ <b>Номера закончились!</b>\nОжидайте пополнения.",
                parse_mode="HTML"
            )
    
    # Информация об очереди
    elif text == "очередь" or text == "статус":
        count = get_queue_count()
        numbers = get_queue_list()
        
        response = f"📊 <b>Статус очереди:</b>\n\n📱 Номеров: {count}\n\n"
        
        if numbers:
            response += "📋 <b>Последние номера:</b>\n"
            for n in numbers[:5]:
                response += f"• <code>{n['phone']}</code>\n"
        
        bot.reply_to(message, response, parse_mode="HTML")

# ==================== ОБРАБОТЧИКИ ТЕКСТА ====================
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.from_user.id
    text = message.text
    
    if text == "📱 Получить номер":
        give_number_to_user(user_id, message.chat.id)
    
    elif text == "📊 Очередь":
        show_queue(message)
    
    elif text == "💰 Баланс":
        show_balance(message)
    
    elif text == "📋 Мои номера":
        show_my_numbers(message)
    
    elif text == "➕ Добавить номера":
        add_numbers_command(message)
    
    elif text == "🔧 Админ":
        bot.send_message(message.chat.id, "🔧 Админ-панель:", reply_markup=admin_menu())
    
    elif text == "ℹ️ Инфо":
        show_info(message)
    
    elif text == "📞 Поддержка":
        bot.send_message(message.chat.id, "📞 Техподдержка: @auzom")

def show_queue(message):
    count = get_queue_count()
    numbers = get_queue_list()
    
    text = f"📊 <b>Очередь номеров</b>\n\n📱 Доступно: {count}\n\n"
    
    if numbers:
        text += "📋 <b>Номера в очереди:</b>\n"
        for i, n in enumerate(numbers[:10], 1):
            text += f"{i}. <code>{n['phone']}</code>\n"
        
        if len(numbers) > 10:
            text += f"\n... и ещё {len(numbers) - 10}"
    
    bot.send_message(message.chat.id, text, parse_mode="HTML")

def show_balance(message):
    user_id = message.from_user.id
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    balance = user['balance'] if user else 0
    
    bot.send_message(
        message.chat.id,
        f"💰 <b>Ваш баланс:</b> ${balance:.2f}",
        parse_mode="HTML"
    )

def show_my_numbers(message):
    user_id = message.from_user.id
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM numbers_queue WHERE taken_by = ? ORDER BY taken_date DESC LIMIT 10", (user_id,))
    numbers = cursor.fetchall()
    conn.close()
    
    if not numbers:
        bot.send_message(message.chat.id, "📋 У вас нет выданных номеров")
        return
    
    text = "📋 <b>Ваши номера:</b>\n\n"
    for n in numbers:
        text += f"📱 <code>{n['phone']}</code> | {n['taken_date']}\n"
    
    bot.send_message(message.chat.id, text, parse_mode="HTML")

def show_info(message):
    try:
        bot.send_photo(
            message.chat.id,
            MAIN_PHOTO_URL,
            caption=(
                "💸 <b>Juss Hell Service</b>\n\n"
                "📱 Аренда и приемка номеров\n"
                "🔄 Автоматическая выдача\n"
                "📊 Живая очередь\n\n"
                f"📱 Номеров в очереди: <b>{get_queue_count()}</b>"
            ),
            parse_mode="HTML"
        )
    except:
        bot.send_message(
            message.chat.id,
            f"💸 <b>Juss Hell Service</b>\n\n📱 Номеров: {get_queue_count()}",
            parse_mode="HTML"
        )

# ==================== CALLBACK ОБРАБОТЧИКИ ====================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    
    if call.data == "add_number":
        msg = bot.send_message(call.message.chat.id, "📱 Отправьте номера через запятую:")
        bot.register_next_step_handler(msg, process_add_numbers)
    
    elif call.data == "all_numbers":
        numbers = get_queue_list()
        if numbers:
            text = "📋 <b>Номера в очереди:</b>\n\n"
            for n in numbers[:20]:
                text += f"🆔{n['id']} | <code>{n['phone']}</code> | {n['status']}\n"
        else:
            text = "📋 Очередь пуста"
        bot.send_message(call.message.chat.id, text, parse_mode="HTML")
    
    elif call.data == "stats":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM users")
        users = cursor.fetchone()['cnt']
        cursor.execute("SELECT COUNT(*) as cnt FROM numbers_queue WHERE status = 'available'")
        available = cursor.fetchone()['cnt']
        cursor.execute("SELECT COUNT(*) as cnt FROM numbers_queue WHERE status = 'taken'")
        taken = cursor.fetchone()['cnt']
        conn.close()
        
        bot.send_message(
            call.message.chat.id,
            f"📊 <b>Статистика</b>\n\n"
            f"👥 Пользователей: {users}\n"
            f"📱 В очереди: {available}\n"
            f"✅ Выдано: {taken}",
            parse_mode="HTML"
        )
    
    elif call.data == "clear_queue":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM numbers_queue WHERE status = 'available'")
        conn.commit()
        conn.close()
        bot.send_message(call.message.chat.id, "✅ Очередь очищена!")
    
    bot.answer_callback_query(call.id)

# ==================== ФУНКЦИЯ ОБНОВЛЕНИЯ ГРУППЫ ====================
def update_group_info():
    """Отправка актуальной информации в группу"""
    try:
        count = get_queue_count()
        text = f"📊 <b>Очередь обновлена!</b>\n📱 Доступно номеров: {count}"
        bot.send_message(GROUP_ID, text, parse_mode="HTML")
    except:
        pass

# ==================== АВТООБНОВЛЕНИЕ ОЧЕРЕДИ ====================
def queue_monitor():
    """Мониторинг очереди и уведомления"""
    last_count = 0
    
    while True:
        try:
            current_count = get_queue_count()
            
            # Уведомление если очередь пустеет
            if current_count == 0 and last_count > 0:
                try:
                    bot.send_message(GROUP_ID, "🚨 <b>Очередь пуста!</b>\nСрочно нужны номера!", parse_mode="HTML")
                except:
                    pass
            
            last_count = current_count
        except:
            pass
        
        time.sleep(60)  # Проверка каждую минуту

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    init_db()
    print("🤖 Juss Hell Service запущен!")
    print(f"📱 Очередь номеров: {get_queue_count()}")
    
    # Запуск мониторинга
    threading.Thread(target=queue_monitor, daemon=True).start()
    
    bot.infinity_polling()