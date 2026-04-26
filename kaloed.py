import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputFile
import uuid
import os

# ---------- НАСТРОЙКИ ----------
TOKEN = "8740649289:AAH1lk4yL2c9RR_ebpDXvlv-rV_g6cIYnBE"
CRYPTO_BOT_TOKEN = "569144:AAs82ABvMXw8uTlYYfIrZOMWZA5C7bYhfdr"
ADMIN_IDS = [105635005]
GROUP_ID = -1003945636594
MIN_WITHDRAW = 1.00
PHONE_PRICE = 4.50
CODE_TIMEOUT_SECONDS = 60
RENTAL_MINUTES = 6

# Путь к фото для главного меню (положи фото рядом с ботом)
MAIN_PHOTO_PATH = "main_photo.jpg"  # Замени на своё фото

# ---------- ЛОГИ ----------
logging.basicConfig(level=logging.INFO)

# ---------- БОТ ----------
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# ---------- БАЗА ----------
users = {}
active_numbers = {}
seller_states = {}
numbers_queue = []  # ОЧЕРЕДЬ НОМЕРОВ: [(number_id, phone, seller_id, seller_username, added_time)]

# ---------- СОСТОЯНИЯ ----------
class States(StatesGroup):
    waiting_phone = State()
    waiting_code_from_seller = State()
    waiting_withdraw_amount = State()

# ========== /start С ФОТКОЙ ==========
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    
    if user_id not in users:
        users[user_id] = {
            "balance": 0.0,
            "username": username
        }
    
    text = (
        "🤖 <b>Sow Max</b> — приёмка и аренда номеров.\n\n"
        f"💰 Баланс: <b>${users[user_id]['balance']:.2f}</b>\n"
        f"💳 Мин. вывод: <b>${MIN_WITHDRAW:.2f}</b>\n"
        f"📋 В очереди: <b>{len(numbers_queue)}</b> номеров\n\n"
        "📞 Техподдержка: @auzom"
    )
    
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("📱 Сдать номер", callback_data="menu_sell"),
        InlineKeyboardButton("👤 Профиль", callback_data="menu_profile"),
        InlineKeyboardButton("💳 Вывод средств", callback_data="menu_withdraw"),
        InlineKeyboardButton("📋 Очередь номеров", callback_data="menu_queue"),
        InlineKeyboardButton("📞 Поддержка", callback_data="menu_support")
    )
    
    # Отправляем фото если есть
    try:
        if os.path.exists(MAIN_PHOTO_PATH):
            with open(MAIN_PHOTO_PATH, 'rb') as photo:
                await message.answer_photo(
                    photo,
                    caption=text,
                    reply_markup=kb,
                    parse_mode="HTML"
                )
            return
    except:
        pass
    
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

# ========== ГЛАВНОЕ МЕНЮ С ФОТКОЙ ==========
@dp.callback_query_handler(lambda c: c.data == "menu_main")
async def main_menu(call: types.CallbackQuery):
    user_id = call.from_user.id
    
    text = (
        "🤖 <b>Sow Max</b> — приёмка и аренда номеров.\n\n"
        f"💰 Баланс: <b>${users[user_id]['balance']:.2f}</b>\n"
        f"💳 Мин. вывод: <b>${MIN_WITHDRAW:.2f}</b>\n"
        f"📋 В очереди: <b>{len(numbers_queue)}</b> номеров"
    )
    
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("📱 Сдать номер", callback_data="menu_sell"),
        InlineKeyboardButton("👤 Профиль", callback_data="menu_profile"),
        InlineKeyboardButton("💳 Вывод средств", callback_data="menu_withdraw"),
        InlineKeyboardButton("📋 Очередь номеров", callback_data="menu_queue"),
        InlineKeyboardButton("📞 Поддержка", callback_data="menu_support")
    )
    
    # Удаляем старое сообщение и отправляем новое с фото
    await call.message.delete()
    
    try:
        if os.path.exists(MAIN_PHOTO_PATH):
            with open(MAIN_PHOTO_PATH, 'rb') as photo:
                await call.message.answer_photo(
                    photo,
                    caption=text,
                    reply_markup=kb,
                    parse_mode="HTML"
                )
            await call.answer()
            return
    except:
        pass
    
    await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()

# ========== ПРОФИЛЬ ==========
@dp.callback_query_handler(lambda c: c.data == "menu_profile")
async def profile(call: types.CallbackQuery):
    user_id = call.from_user.id
    data = users.get(user_id, {"balance": 0.0})
    
    # Считаем сколько номеров пользователя в очереди
    user_phones_in_queue = sum(1 for n in numbers_queue if n[2] == user_id)
    
    text = (
        "👤 <b>Профиль</b>\n\n"
        f"💰 Баланс: <b>${data['balance']:.2f}</b>\n"
        f"💳 Мин. вывод: <b>${MIN_WITHDRAW:.2f}</b>\n"
        f"📱 Ваших номеров в очереди: <b>{user_phones_in_queue}</b>"
    )
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="menu_main"))
    
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()

# ========== ОЧЕРЕДЬ НОМЕРОВ ==========
@dp.callback_query_handler(lambda c: c.data == "menu_queue")
async def show_queue(call: types.CallbackQuery):
    if not numbers_queue:
        text = "📋 <b>Очередь номеров пуста</b>\n\nБудьте первым кто сдаст номер!"
    else:
        text = f"📋 <b>Очередь номеров:</b> <b>{len(numbers_queue)}</b> шт.\n\n"
        for i, (nid, phone, sid, suser, added) in enumerate(numbers_queue[:20], 1):
            time_str = added.strftime("%H:%M")
            text += f"{i}. <code>{phone}</code> от @{suser} 🕐 {time_str}\n"
        
        if len(numbers_queue) > 20:
            text += f"\n<i>... и ещё {len(numbers_queue) - 20} номеров</i>"
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="menu_main"))
    kb.add(InlineKeyboardButton("📱 Сдать номер", callback_data="menu_sell"))
    
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()

# ========== СДАТЬ НОМЕР (добавляется в очередь) ==========
@dp.callback_query_handler(lambda c: c.data == "menu_sell")
async def sell_start(call: types.CallbackQuery):
    text = (
        "📱 <b>Сдать номер</b>\n\n"
        f"💰 Оплата: <b>${PHONE_PRICE:.2f}</b> за успешную аренду\n"
        f"⏱ Номер сдаётся на {RENTAL_MINUTES} минут\n"
        f"📋 Номер попадёт в очередь\n\n"
        "<i>Отправьте номер в международном формате:</i>\n"
        "<code>+1234567890</code>"
    )
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Отмена", callback_data="menu_main"))
    
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await States.waiting_phone.set()
    await call.answer()

@dp.message_handler(state=States.waiting_phone)
async def receive_phone(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    phone = message.text.strip()
    username = message.from_user.username or f"user_{user_id}"
    
    if not phone.startswith("+") or len(phone) < 7:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 Отмена", callback_data="menu_main"))
        await message.answer("❌ Неверный формат. Пример: +1234567890", reply_markup=kb)
        return
    
    number_id = str(uuid.uuid4())[:8]
    
    # Добавляем в ОЧЕРЕДЬ
    numbers_queue.append((number_id, phone, user_id, username, datetime.now()))
    
    # Уведомляем группу о новом номере в очереди
    await bot.send_message(
        GROUP_ID,
        f"📱 <b>Новый номер в очереди!</b>\n"
        f"📋 Всего в очереди: <b>{len(numbers_queue)}</b>\n"
        f"Напишите <b>«номер»</b> чтобы получить номер из очереди.",
        parse_mode="HTML"
    )
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 В меню", callback_data="menu_main"))
    kb.add(InlineKeyboardButton("📋 Посмотреть очередь", callback_data="menu_queue"))
    
    await message.answer(
        f"✅ Номер <code>{phone}</code> добавлен в очередь!\n"
        f"📋 Позиция в очереди: <b>#{len(numbers_queue)}</b>\n"
        f"Ожидайте когда номер запросят из группы.",
        reply_markup=kb,
        parse_mode="HTML"
    )
    
    await state.finish()

# ========== ЗАПРОС НОМЕРА ИЗ ОЧЕРЕДИ (в группе) ==========
@dp.message_handler(lambda m: m.chat.id == GROUP_ID and m.text and m.text.lower() == "номер")
async def request_number_from_queue(message: types.Message):
    if not numbers_queue:
        await message.answer("❌ Очередь пуста. Пока никто не сдал номер.")
        return
    
    # Берём первый номер из очереди
    number_id, phone, seller_id, seller_username, added = numbers_queue.pop(0)
    
    # Отправляем номер + кнопку "Взять" в группу
    kb_group = InlineKeyboardMarkup()
    kb_group.add(InlineKeyboardButton("🤙 Взять номер", callback_data=f"take_{number_id}"))
    
    group_msg = await message.answer(
        f"📱 <b>Номер из очереди!</b>\n\n"
        f"📞 Номер: <code>{phone}</code>\n"
        f"💰 Цена: <b>${PHONE_PRICE:.2f}</b>\n"
        f"👤 Сдатчик: @{seller_username}\n"
        f"📋 Осталось в очереди: <b>{len(numbers_queue)}</b>\n"
        f"⏱ Статус: <b>Ожидает арендатора</b>",
        reply_markup=kb_group,
        parse_mode="HTML"
    )
    
    active_numbers[number_id] = {
        "phone": phone,
        "seller_id": seller_id,
        "renter_id": None,
        "renter_username": None,
        "status": "waiting",
        "start_time": None,
        "group_msg_id": group_msg.message_id,
        "seller_username": seller_username,
        "code": None
    }
    
    # Уведомляем сдатчика
    try:
        await bot.send_message(
            seller_id,
            f"📱 Ваш номер <code>{phone}</code> запрошен из очереди!\n"
            f"Ожидайте арендатора.",
            parse_mode="HTML"
        )
    except:
        pass

# ========== ВЗЯТЬ НОМЕР → ЗАПРОС КОДА У СДАТЧИКА ==========
@dp.callback_query_handler(lambda c: c.data.startswith("take_"))
async def take_number(call: types.CallbackQuery):
    user_id = call.from_user.id
    number_id = call.data.split("_")[1]
    
    if number_id not in active_numbers:
        await call.answer("❌ Номер уже неактуален", show_alert=True)
        return
    
    ndata = active_numbers[number_id]
    seller_id = ndata["seller_id"]
    
    if seller_id == user_id:
        await call.answer("❌ Нельзя арендовать свой номер", show_alert=True)
        return
    
    if ndata["renter_id"] is not None:
        await call.answer("❌ Уже арендован", show_alert=True)
        return
    
    ndata["renter_id"] = user_id
    ndata["renter_username"] = call.from_user.username or f"id{user_id}"
    ndata["status"] = "waiting_code_from_seller"
    
    # Ставим состояние СДАТЧИКУ
    seller_state = dp.current_state(chat=seller_id, user=seller_id)
    await seller_state.set_state(States.waiting_code_from_seller.state)
    seller_states[seller_id] = number_id
    
    # Пишем сдатчику
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{number_id}"))
    
    await bot.send_message(
        seller_id,
        f"🔔 <b>Кто-то хочет арендовать ваш номер!</b>\n\n"
        f"📞 Номер: <code>{ndata['phone']}</code>\n"
        f"👤 Арендатор: @{call.from_user.username or f'id{user_id}'}\n\n"
        f"⏱ <b>{CODE_TIMEOUT_SECONDS} секунд</b> чтобы отправить код!\n\n"
        f"<i>Отправьте код подтверждения:</i>",
        reply_markup=kb,
        parse_mode="HTML"
    )
    
    # Пишем арендатору
    kb2 = InlineKeyboardMarkup()
    kb2.add(InlineKeyboardButton("🔙 Отмена", callback_data="cancel_rent"))
    
    await bot.send_message(
        user_id,
        f"⏳ <b>Ожидание кода от сдатчика...</b>\n\n"
        f"📞 Номер: <code>{ndata['phone']}</code>\n"
        f"Сдатчик должен отправить код в течение {CODE_TIMEOUT_SECONDS} сек.",
        reply_markup=kb2,
        parse_mode="HTML"
    )
    
    # Обновляем в группе
    kb_group = InlineKeyboardMarkup()
    kb_group.add(InlineKeyboardButton("⏳ Ожидание кода...", callback_data="nop"))
    
    await bot.edit_message_text(
        f"📱 <b>Номер занят!</b>\n\n"
        f"📞 Номер: <code>{ndata['phone']}</code>\n"
        f"👤 Сдатчик: @{ndata['seller_username']}\n"
        f"👤 Арендатор: @{call.from_user.username or f'id{user_id}'}\n"
        f"⏱ Статус: <b>Ожидание кода от сдатчика ({CODE_TIMEOUT_SECONDS} сек)</b>",
        chat_id=GROUP_ID,
        message_id=ndata["group_msg_id"],
        reply_markup=kb_group,
        parse_mode="HTML"
    )
    
    asyncio.create_task(seller_code_timeout(number_id, ndata, seller_id))
    
    await call.answer("✅ Запрос кода отправлен сдатчику!")

# ========== ТАЙМАУТ СДАТЧИКА ==========
async def seller_code_timeout(number_id, ndata, seller_id):
    await asyncio.sleep(CODE_TIMEOUT_SECONDS)
    
    if number_id in active_numbers and ndata.get("status") == "waiting_code_from_seller":
        renter = ndata["renter_id"]
        ndata["renter_id"] = None
        ndata["renter_username"] = None
        ndata["status"] = "waiting"
        
        seller_state = dp.current_state(chat=seller_id, user=seller_id)
        await seller_state.reset_state()
        if seller_id in seller_states:
            del seller_states[seller_id]
        
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🤙 Взять номер", callback_data=f"take_{number_id}"))
        
        try:
            await bot.edit_message_text(
                f"📱 <b>Номер снова доступен!</b>\n\n"
                f"📞 Номер: <code>{ndata['phone']}</code>\n"
                f"💰 Цена: <b>${PHONE_PRICE:.2f}</b>\n"
                f"👤 Сдатчик: @{ndata['seller_username']}\n"
                f"⏱ Статус: <b>Ожидает арендатора</b>",
                chat_id=GROUP_ID,
                message_id=ndata["group_msg_id"],
                reply_markup=kb,
                parse_mode="HTML"
            )
        except:
            pass
        
        try:
            await bot.send_message(renter, "⏰ Сдатчик не отправил код. Номер снова свободен.")
        except:
            pass
        
        try:
            await bot.send_message(seller_id, "⏰ Время вышло. Аренда отменена.")
        except:
            pass

# ========== СДАТЧИК ОТКЛОНЯЕТ ==========
@dp.callback_query_handler(lambda c: c.data.startswith("reject_"))
async def seller_reject(call: types.CallbackQuery):
    user_id = call.from_user.id
    number_id = call.data.split("_")[1]
    
    if number_id in active_numbers:
        ndata = active_numbers[number_id]
        renter = ndata["renter_id"]
        ndata["renter_id"] = None
        ndata["renter_username"] = None
        ndata["status"] = "waiting"
        
        seller_state = dp.current_state(chat=user_id, user=user_id)
        await seller_state.reset_state()
        if user_id in seller_states:
            del seller_states[user_id]
        
        try:
            await bot.send_message(renter, "❌ Сдатчик отклонил аренду.")
        except:
            pass
        
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🤙 Взять номер", callback_data=f"take_{number_id}"))
        
        try:
            await bot.edit_message_text(
                f"📱 <b>Номер снова доступен!</b>\n\n"
                f"📞 Номер: <code>{ndata['phone']}</code>\n"
                f"💰 Цена: <b>${PHONE_PRICE:.2f}</b>\n"
                f"👤 Сдатчик: @{ndata['seller_username']}",
                chat_id=GROUP_ID,
                message_id=ndata["group_msg_id"],
                reply_markup=kb,
                parse_mode="HTML"
            )
        except:
            pass
    
    await call.message.edit_text("❌ Вы отклонили аренду.")
    await call.answer()

# ========== ОТМЕНА АРЕНДЫ ==========
@dp.callback_query_handler(lambda c: c.data == "cancel_rent")
async def cancel_rent(call: types.CallbackQuery):
    user_id = call.from_user.id
    
    for nid, ndata in active_numbers.items():
        if ndata.get("renter_id") == user_id and ndata.get("status") == "waiting_code_from_seller":
            seller = ndata["seller_id"]
            ndata["renter_id"] = None
            ndata["renter_username"] = None
            ndata["status"] = "waiting"
            
            seller_state = dp.current_state(chat=seller, user=seller)
            await seller_state.reset_state()
            if seller in seller_states:
                del seller_states[seller]
            
            try:
                await bot.send_message(seller, "❌ Арендатор отменил запрос.")
            except:
                pass
            
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("🤙 Взять номер", callback_data=f"take_{nid}"))
            
            try:
                await bot.edit_message_text(
                    f"📱 <b>Номер снова доступен!</b>\n\n"
                    f"📞 Номер: <code>{ndata['phone']}</code>\n"
                    f"💰 Цена: <b>${PHONE_PRICE:.2f}</b>\n"
                    f"👤 Сдатчик: @{ndata['seller_username']}",
                    chat_id=GROUP_ID,
                    message_id=ndata["group_msg_id"],
                    reply_markup=kb,
                    parse_mode="HTML"
                )
            except:
                pass
            break
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 В меню", callback_data="menu_main"))
    
    await call.message.edit_text("❌ Аренда отменена", reply_markup=kb)
    await call.answer()

# ========== NOP ==========
@dp.callback_query_handler(lambda c: c.data == "nop")
async def nop(call: types.CallbackQuery):
    await call.answer("⏳ Ожидайте код от сдатчика...", show_alert=True)

# ========== СДАТЧИК ОТПРАВЛЯЕТ КОД → В ГРУППУ ==========
@dp.message_handler(state=States.waiting_code_from_seller)
async def seller_sends_code(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    code = message.text.strip()
    
    if user_id not in seller_states:
        await state.finish()
        await message.answer("❌ У вас нет активных запросов на код.")
        return
    
    number_id = seller_states[user_id]
    
    if number_id not in active_numbers:
        await state.finish()
        del seller_states[user_id]
        await message.answer("❌ Номер уже неактуален.")
        return
    
    ndata = active_numbers[number_id]
    
    if ndata.get("status") != "waiting_code_from_seller":
        await state.finish()
        del seller_states[user_id]
        await message.answer("❌ Запрос уже неактуален.")
        return
    
    ndata["code"] = code
    ndata["status"] = "active"
    ndata["start_time"] = datetime.now()
    
    renter_id = ndata["renter_id"]
    
    kb_group = InlineKeyboardMarkup()
    kb_group.add(
        InlineKeyboardButton("🟢 Встал", callback_data=f"status_{number_id}_active"),
        InlineKeyboardButton("🔴 Слетел", callback_data=f"status_{number_id}_failed")
    )
    
    await bot.edit_message_text(
        f"📱 <b>Номер в аренде!</b>\n\n"
        f"📞 Номер: <code>{ndata['phone']}</code>\n"
        f"🔑 Код: <code>{code}</code>\n"
        f"👤 Сдатчик: @{ndata['seller_username']}\n"
        f"👤 Арендатор: @{ndata['renter_username']}\n"
        f"⏱ Статус: <b>Активна (1/{RENTAL_MINUTES} мин)</b>",
        chat_id=GROUP_ID,
        message_id=ndata["group_msg_id"],
        reply_markup=kb_group,
        parse_mode="HTML"
    )
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 В меню", callback_data="menu_main"))
    await message.answer(
        f"✅ Код <code>{code}</code> отправлен в группу!\n"
        f"Аренда началась на {RENTAL_MINUTES} минут.",
        reply_markup=kb,
        parse_mode="HTML"
    )
    
    try:
        await bot.send_message(
            renter_id,
            f"✅ <b>Код получен!</b>\n\n"
            f"📞 Номер: <code>{ndata['phone']}</code>\n"
            f"🔑 Код: <code>{code}</code>\n\n"
            f"Аренда на {RENTAL_MINUTES} минут началась!",
            parse_mode="HTML"
        )
    except:
        pass
    
    await state.finish()
    del seller_states[user_id]
    
    asyncio.create_task(rental_timer(number_id, ndata))

# ========== ТАЙМЕР АРЕНДЫ ==========
async def rental_timer(number_id, ndata):
    for minute in range(1, RENTAL_MINUTES + 1):
        await asyncio.sleep(60)
        
        if number_id not in active_numbers or ndata.get("status") != "active":
            return
        
        try:
            kb = InlineKeyboardMarkup()
            kb.add(
                InlineKeyboardButton("🟢 Встал", callback_data=f"status_{number_id}_active"),
                InlineKeyboardButton("🔴 Слетел", callback_data=f"status_{number_id}_failed")
            )
            
            await bot.edit_message_text(
                f"📱 <b>Номер в аренде!</b>\n\n"
                f"📞 Номер: <code>{ndata['phone']}</code>\n"
                f"🔑 Код: <code>{ndata.get('code', '---')}</code>\n"
                f"👤 Сдатчик: @{ndata['seller_username']}\n"
                f"👤 Арендатор: @{ndata.get('renter_username', 'неизвестно')}\n"
                f"⏱ Статус: <b>{minute}/{RENTAL_MINUTES} мин</b>",
                chat_id=GROUP_ID,
                message_id=ndata["group_msg_id"],
                reply_markup=kb,
                parse_mode="HTML"
            )
        except:
            pass
    
    if number_id in active_numbers and ndata.get("status") == "active":
        seller_id = ndata["seller_id"]
        
        if seller_id in users:
            users[seller_id]["balance"] += PHONE_PRICE
        
        try:
            await bot.send_message(
                seller_id,
                f"✅ Аренда завершена!\n"
                f"💰 Зачислено: <b>${PHONE_PRICE:.2f}</b>\n"
                f"💳 Баланс: <b>${users[seller_id]['balance']:.2f}</b>",
                parse_mode="HTML"
            )
        except:
            pass
        
        try:
            await bot.edit_message_text(
                f"📱 <b>Аренда завершена!</b>\n\n"
                f"📞 Номер: <code>{ndata['phone']}</code>\n"
                f"👤 Сдатчик: @{ndata['seller_username']}\n"
                f"💰 Начислено: <b>${PHONE_PRICE:.2f}</b>",
                chat_id=GROUP_ID,
                message_id=ndata["group_msg_id"],
                parse_mode="HTML"
            )
        except:
            pass
        
        if number_id in active_numbers:
            del active_numbers[number_id]

# ========== ВСТАЛ/СЛЕТЕЛ ==========
@dp.callback_query_handler(lambda c: c.data.startswith("status_"))
async def status_update(call: types.CallbackQuery):
    parts = call.data.split("_")
    number_id = parts[1]
    new_status = parts[2]
    
    if number_id not in active_numbers:
        await call.answer("Номер не найден", show_alert=True)
        return
    
    ndata = active_numbers[number_id]
    
    if new_status == "active":
        ndata["status"] = "active"
        await bot.send_message(GROUP_ID, f"🟢 Номер <code>{ndata['phone']}</code> встал!", parse_mode="HTML")
    else:
        await bot.send_message(GROUP_ID, f"🔴 Номер <code>{ndata['phone']}</code> слетел!", parse_mode="HTML")
        if number_id in active_numbers:
            del active_numbers[number_id]
    
    await call.answer("Обновлено!")

# ========== ВЫВОД СРЕДСТВ ==========
@dp.callback_query_handler(lambda c: c.data == "menu_withdraw")
async def withdraw_menu(call: types.CallbackQuery):
    user_id = call.from_user.id
    balance = users[user_id]["balance"]
    
    if balance < MIN_WITHDRAW:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 Назад", callback_data="menu_main"))
        await call.message.edit_text(
            f"❌ Недостаточно средств\n\n"
            f"💰 Баланс: <b>${balance:.2f}</b>\n"
            f"💳 Минимум: <b>${MIN_WITHDRAW:.2f}</b>",
            reply_markup=kb,
            parse_mode="HTML"
        )
        await call.answer()
        return
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="menu_main"))
    
    await call.message.edit_text(
        f"💳 <b>Вывод средств</b>\n\n"
        f"💰 Доступно: <b>${balance:.2f}</b>\n\n"
        "Введите сумму (минимум $1.00):",
        reply_markup=kb,
        parse_mode="HTML"
    )
    
    await States.waiting_withdraw_amount.set()
    await call.answer()

@dp.message_handler(state=States.waiting_withdraw_amount)
async def process_withdraw(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    try:
        amount = float(message.text.strip())
    except:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 Отмена", callback_data="menu_main"))
        await message.answer("❌ Введите число", reply_markup=kb)
        return
    
    balance = users[user_id]["balance"]
    
    if amount < MIN_WITHDRAW or amount > balance:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 Отмена", callback_data="menu_main"))
        await message.answer(f"❌ Сумма от ${MIN_WITHDRAW:.2f} до ${balance:.2f}", reply_markup=kb)
        return
    
    check = await create_crypto_check(amount, user_id)
    
    if not check:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 В меню", callback_data="menu_main"))
        await message.answer("❌ Ошибка создания чека. Обратитесь к @auzom", reply_markup=kb)
        await state.finish()
        return
    
    users[user_id]["balance"] -= amount
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("💎 Получить USDT", url=check["url"]))
    kb.add(InlineKeyboardButton("🔙 В меню", callback_data="menu_main"))
    
    await message.answer(
        f"✅ <b>Чек создан!</b>\n\n"
        f"💰 Сумма: <b>${amount:.2f}</b>\n"
        f"💳 Остаток: <b>${users[user_id]['balance']:.2f}</b>\n\n"
        "Нажмите кнопку ниже чтобы получить USDT 💎",
        reply_markup=kb,
        parse_mode="HTML"
    )
    
    await state.finish()

async def create_crypto_check(amount, user_id):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://pay.crypt.bot/api/createCheck",
                headers={"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN},
                json={"asset": "USDT", "amount": str(amount), "pin_to_user_id": user_id}
            ) as resp:
                data = await resp.json()
                if data.get("ok"):
                    r = data["result"]
                    return {
                        "check_id": r["check_id"],
                        "url": f"https://t.me/CryptoBot?start={r['check_id']}",
                        "amount": r["amount"]
                    }
    except Exception as e:
        logging.error(f"CryptoBot error: {e}")
    return None

# ========== ПОДДЕРЖКА ==========
@dp.callback_query_handler(lambda c: c.data == "menu_support")
async def support(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("👤 Написать @auzom", url="https://t.me/auzom"))
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="menu_main"))
    
    await call.message.edit_text(
        "📞 <b>Техподдержка</b>\n\n"
        "По всем вопросам обращайтесь:\n"
        "👤 @auzom",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await call.answer()

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    print("🤖 Sow Max запущен...")
    executor.start_polling(dp, skip_updates=True)