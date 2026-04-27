import logging
import asyncio
import aiohttp
import json
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import uuid

# ---------- НАСТРОЙКИ ----------
TOKEN = "8724966854:AAGdGtb3PESIs0uBaAI3wp4G8GaGvbpwRdU"
CRYPTO_BOT_TOKEN = "569144:AAs82ABvMXw8uTlYYfIrZOMWZA5C7bYhfdr"
ADMIN_IDS = [105635005]
GROUP_ID = -1003666187453
CHANNEL_ID = -1003938408612
CHANNEL_URL = "https://t.me/JussHellInformation"

# ---------- КОНФИГ ----------
CONFIG_FILE = "bot_config.json"
USERS_FILE = "users.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {
        "price": 5.00,
        "work_start": 0,
        "work_end": 24,
        "code_timeout": 67,
        "rental_minutes": 6,
        "min_withdraw": 1.00
    }

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

config = load_config()
PHONE_PRICE = config["price"]
WORK_START = config["work_start"]
WORK_END = config["work_end"]
CODE_TIMEOUT_SECONDS = config["code_timeout"]
RENTAL_MINUTES = config["rental_minutes"]
MIN_WITHDRAW = config["min_withdraw"]
MAIN_PHOTO_PATH = "main_photo.jpg"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

users = {}
active_numbers = {}
seller_states = {}
numbers_queue = []

if os.path.exists(USERS_FILE):
    with open(USERS_FILE, 'r') as f:
        users = json.load(f)

def save_users():
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4)

class States(StatesGroup):
    waiting_phone = State()
    waiting_code_from_seller = State()
    waiting_withdraw_amount = State()
    admin_change_price = State()
    admin_change_hours_start = State()
    admin_change_hours_end = State()
    admin_give_balance_user = State()
    admin_give_balance_amount = State()

def is_working_hours():
    now = datetime.now().hour
    return WORK_START <= now < WORK_END

async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status not in ['left', 'kicked', 'banned']
    except:
        return False

def sub_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(f"📢 Подписаться на {CHANNEL_NAME}", url=CHANNEL_URL))
    kb.add(InlineKeyboardButton("✅ Проверить подписку", callback_data="check_sub"))
    return kb

async def require_sub(user_id):
    if user_id in ADMIN_IDS:
        return True
    return await check_subscription(user_id)

async def main_menu_message(event):
    user_id = event.from_user.id if hasattr(event, 'from_user') else event.chat.id
    
    text = (
        "💵<b>Juss Hell Service - приемка и аренда номеров. Вы можете сдать свой номер, получить оплату и вести статистику аренд. Более подробно вы можете узнать снизу 👇</b>\n\n"
        f"💰 Баланс: <b>${users.get(str(user_id), {}).get('balance', 0.0):.2f}</b>\n"
        f"📋 Очередь: <b>{len(numbers_queue)}</b>"
    )
    
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("📱 Сдать номер", callback_data="menu_sell"),
        InlineKeyboardButton("👤 Профиль", callback_data="menu_profile"),
        InlineKeyboardButton("💳 Вывод средств", callback_data="menu_withdraw"),
        InlineKeyboardButton("📋 Очередь", callback_data="menu_queue"),
        InlineKeyboardButton("📞 Поддержка", callback_data="menu_support")
    )
    if user_id in ADMIN_IDS:
        kb.add(InlineKeyboardButton("⚙️ Админ панель", callback_data="admin_panel"))
    
    try:
        if os.path.exists(MAIN_PHOTO_PATH):
            with open(MAIN_PHOTO_PATH, 'rb') as photo:
                if hasattr(event, 'message'):
                    await event.message.answer_photo(photo, caption=text, reply_markup=kb, parse_mode="HTML")
                elif hasattr(event, 'answer'):
                    await event.message.delete()
                    await event.message.answer_photo(photo, caption=text, reply_markup=kb, parse_mode="HTML")
                else:
                    await bot.send_photo(user_id, photo, caption=text, reply_markup=kb, parse_mode="HTML")
                return
    except:
        pass
    
    if hasattr(event, 'message'):
        await event.message.answer(text, reply_markup=kb, parse_mode="HTML")
    elif hasattr(event, 'answer'):
        await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await bot.send_message(user_id, text, reply_markup=kb, parse_mode="HTML")

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    
    if not await require_sub(user_id):
        await message.answer(
            f"❌ <b>Обязательная подписка!</b>\n\n"
            f"📢 Подпишитесь на <b>{CHANNEL_NAME}</b>\n"
            "После подписки нажмите кнопку проверки.",
            reply_markup=sub_keyboard(), parse_mode="HTML"
        )
        return
    
    username = message.from_user.username or f"user_{user_id}"
    if str(user_id) not in users:
        users[str(user_id)] = {"balance": 0.0, "username": username}
        save_users()
    
    await main_menu_message(message)

@dp.callback_query_handler(lambda c: c.data == "check_sub")
async def check_sub(call: types.CallbackQuery):
    if await check_subscription(call.from_user.id):
        await call.answer("✅ Подписка подтверждена!", show_alert=True)
        await call.message.delete()
        username = call.from_user.username or f"user_{call.from_user.id}"
        if str(call.from_user.id) not in users:
            users[str(call.from_user.id)] = {"balance": 0.0, "username": username}
            save_users()
        await main_menu_message(call)
    else:
        await call.answer("❌ Вы не подписались!", show_alert=True)

@dp.callback_query_handler(lambda c: c.data == "menu_main")
async def main_menu(call: types.CallbackQuery):
    if not await require_sub(call.from_user.id):
        await call.answer("❌ Подпишитесь на канал!", show_alert=True)
        return
    await call.message.delete()
    await main_menu_message(call)
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "menu_profile")
async def profile(call: types.CallbackQuery):
    if not await require_sub(call.from_user.id):
        await call.answer("❌ Подпишитесь!", show_alert=True)
        return
    
    user_id = call.from_user.id
    data = users.get(str(user_id), {"balance": 0.0})
    user_phones = sum(1 for n in numbers_queue if n[2] == user_id)
    
    text = f"👤 <b>Профиль</b>\n\n💰 Баланс: <b>${data['balance']:.2f}</b>\n📱 В очереди: <b>{user_phones}</b>"
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="menu_main"))
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "menu_queue")
async def show_queue(call: types.CallbackQuery):
    if not await require_sub(call.from_user.id):
        await call.answer("❌ Подпишитесь!", show_alert=True)
        return
    
    if not numbers_queue:
        text = "📋 <b>Очередь пуста</b>"
    else:
        text = f"📋 <b>Очередь:</b> {len(numbers_queue)} шт.\n\n"
        for i, (nid, phone, sid, suser, added) in enumerate(numbers_queue[:20], 1):
            text += f"{i}. <code>{phone}</code> 🕐 {added.strftime('%H:%M')}\n"
        if len(numbers_queue) > 20:
            text += f"\n<i>... и ещё {len(numbers_queue)-20}</i>"
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="menu_main"))
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "menu_sell")
async def sell_start(call: types.CallbackQuery):
    if not await require_sub(call.from_user.id):
        await call.answer("❌ Подпишитесь!", show_alert=True)
        return
    
    if not is_working_hours():
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 Назад", callback_data="menu_main"))
        await call.message.edit_text(
            f"🕐 Нерабочее время!\nРаботаем с {WORK_START}:00 до {WORK_END}:00",
            reply_markup=kb, parse_mode="HTML"
        )
        await call.answer()
        return
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Отмена", callback_data="cancel_phone"))
    await call.message.edit_text(
        f"📱 <b>Сдать номер</b>\n\n💰 Оплата: ${PHONE_PRICE:.2f}\n⏱ Аренда: {RENTAL_MINUTES} мин\n\n"
        "<i>Отправьте номер:</i>\n<code>+79123456789</code>",
        reply_markup=kb, parse_mode="HTML"
    )
    await States.waiting_phone.set()
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "cancel_phone", state=States.waiting_phone)
async def cancel_phone_input(call: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await call.message.delete()
    await main_menu_message(call)
    await call.answer()

@dp.message_handler(state=States.waiting_phone)
async def receive_phone(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    phone = message.text.strip()
    username = message.from_user.username or f"user_{user_id}"
    
    if not phone.startswith("+") or len(phone) < 7:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 Отмена", callback_data="cancel_phone"))
        await message.answer("❌ Неверный формат. Пример: +79123456789", reply_markup=kb)
        return
    
    number_id = str(uuid.uuid4())[:8]
    numbers_queue.append((number_id, phone, user_id, username, datetime.now()))
    
    await bot.send_message(
        GROUP_ID,
        f"📱 Новый номер в очереди!\n📋 Всего: <b>{len(numbers_queue)}</b>\n"
        "Напишите <b>«номер»</b> чтобы получить.",
        parse_mode="HTML"
    )
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 В меню", callback_data="menu_main"))
    await message.answer(
        f"✅ Номер <code>{phone}</code> в очереди!\n📋 Позиция: #{len(numbers_queue)}",
        reply_markup=kb, parse_mode="HTML"
    )
    await state.finish()

@dp.message_handler(lambda m: m.chat.id == GROUP_ID and m.text and m.text.lower() == "номер")
async def request_number(message: types.Message):
    if not is_working_hours():
        await message.answer(f"🕐 Нерабочее время. Работаем с {WORK_START}:00 до {WORK_END}:00")
        return
    
    if not numbers_queue:
        await message.answer("❌ Очередь пуста")
        return
    
    number_id, phone, seller_id, seller_username, added = numbers_queue.pop(0)
    
    kb_group = InlineKeyboardMarkup()
    kb_group.add(InlineKeyboardButton("🤙 Взять номер", callback_data=f"take_{number_id}"))
    
    group_msg = await message.answer(
        f"📱 <b>Номер из очереди!</b>\n\n📞 <code>{phone}</code>\n💰 <b>${PHONE_PRICE:.2f}</b>\n"
        f"📋 В очереди: <b>{len(numbers_queue)}</b>\n⏱ Ожидает",
        reply_markup=kb_group, parse_mode="HTML"
    )
    
    active_numbers[number_id] = {
        "phone": phone, "seller_id": seller_id, "renter_id": None,
        "status": "waiting", "start_time": None, "group_msg_id": group_msg.message_id,
        "seller_username": seller_username, "code": None
    }
    
    try:
        await bot.send_message(seller_id, f"📱 Ваш номер <code>{phone}</code> запрошен из очереди!", parse_mode="HTML")
    except:
        pass

@dp.callback_query_handler(lambda c: c.data.startswith("take_"))
async def take_number(call: types.CallbackQuery):
    user_id = call.from_user.id
    number_id = call.data.split("_")[1]
    
    if number_id not in active_numbers:
        await call.answer("❌ Неактуален", show_alert=True)
        return
    
    ndata = active_numbers[number_id]
    seller_id = ndata["seller_id"]
    
    if seller_id == user_id:
        await call.answer("❌ Нельзя свой номер", show_alert=True)
        return
    
    if ndata["renter_id"] is not None:
        await call.answer("❌ Уже арендован", show_alert=True)
        return
    
    ndata["renter_id"] = user_id
    ndata["status"] = "waiting_code_from_seller"
    
    seller_state = dp.current_state(chat=seller_id, user=seller_id)
    await seller_state.set_state(States.waiting_code_from_seller.state)
    seller_states[seller_id] = number_id
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{number_id}"))
    
    await bot.send_message(
        seller_id,
        f"🔔 <b>Запрос на аренду!</b>\n\n📞 <code>{ndata['phone']}</code>\n"
        f"👤 Арендатор: @{call.from_user.username or f'id{user_id}'}\n\n"
        f"⏱ <b>{CODE_TIMEOUT_SECONDS} сек</b>\n\n<i>Отправьте код:</i>",
        reply_markup=kb, parse_mode="HTML"
    )
    
    kb2 = InlineKeyboardMarkup()
    kb2.add(InlineKeyboardButton("🔙 Отмена", callback_data="cancel_rent"))
    await bot.send_message(user_id, f"⏳ Ожидание кода...\n📞 <code>{ndata['phone']}</code>", reply_markup=kb2, parse_mode="HTML")
    
    kb_group = InlineKeyboardMarkup()
    kb_group.add(InlineKeyboardButton("⏳ Ожидание кода...", callback_data="nop"))
    
    await bot.edit_message_text(
        f"📱 <b>Номер занят!</b>\n\n📞 <code>{ndata['phone']}</code>\n⏱ Ожидание кода ({CODE_TIMEOUT_SECONDS} сек)",
        chat_id=GROUP_ID, message_id=ndata["group_msg_id"], reply_markup=kb_group, parse_mode="HTML"
    )
    
    asyncio.create_task(seller_code_timeout(number_id, ndata, seller_id))
    await call.answer("✅ Запрос отправлен!")

async def seller_code_timeout(number_id, ndata, seller_id):
    await asyncio.sleep(CODE_TIMEOUT_SECONDS)
    if number_id in active_numbers and ndata.get("status") == "waiting_code_from_seller":
        renter = ndata["renter_id"]
        ndata["renter_id"] = None
        ndata["status"] = "waiting"
        
        seller_state = dp.current_state(chat=seller_id, user=seller_id)
        await seller_state.reset_state()
        if seller_id in seller_states:
            del seller_states[seller_id]
        
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🤙 Взять номер", callback_data=f"take_{number_id}"))
        try:
            await bot.edit_message_text(
                f"📱 <b>Снова доступен!</b>\n\n📞 <code>{ndata['phone']}</code>\n💰 ${PHONE_PRICE:.2f}",
                chat_id=GROUP_ID, message_id=ndata["group_msg_id"], reply_markup=kb, parse_mode="HTML"
            )
        except:
            pass
        try:
            await bot.send_message(renter, "⏰ Сдатчик не отправил код.")
        except:
            pass

@dp.callback_query_handler(lambda c: c.data.startswith("reject_"))
async def seller_reject(call: types.CallbackQuery):
    user_id = call.from_user.id
    number_id = call.data.split("_")[1]
    
    if number_id in active_numbers:
        ndata = active_numbers[number_id]
        renter = ndata["renter_id"]
        ndata["renter_id"] = None
        ndata["status"] = "waiting"
        
        seller_state = dp.current_state(chat=user_id, user=user_id)
        await seller_state.reset_state()
        if user_id in seller_states:
            del seller_states[user_id]
        
        try:
            await bot.send_message(renter, "❌ Сдатчик отклонил.")
        except:
            pass
        
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🤙 Взять номер", callback_data=f"take_{number_id}"))
        try:
            await bot.edit_message_text(
                f"📱 <b>Снова доступен!</b>\n\n📞 <code>{ndata['phone']}</code>",
                chat_id=GROUP_ID, message_id=ndata["group_msg_id"], reply_markup=kb, parse_mode="HTML"
            )
        except:
            pass
    
    await call.message.edit_text("❌ Отклонено")
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "cancel_rent")
async def cancel_rent(call: types.CallbackQuery):
    user_id = call.from_user.id
    for nid, ndata in active_numbers.items():
        if ndata.get("renter_id") == user_id and ndata.get("status") == "waiting_code_from_seller":
            seller = ndata["seller_id"]
            ndata["renter_id"] = None
            ndata["status"] = "waiting"
            
            seller_state = dp.current_state(chat=seller, user=seller)
            await seller_state.reset_state()
            if seller in seller_states:
                del seller_states[seller]
            
            try:
                await bot.send_message(seller, "❌ Арендатор отменил.")
            except:
                pass
            
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("🤙 Взять номер", callback_data=f"take_{nid}"))
            try:
                await bot.edit_message_text(
                    f"📱 <b>Снова доступен!</b>\n\n📞 <code>{ndata['phone']}</code>",
                    chat_id=GROUP_ID, message_id=ndata["group_msg_id"], reply_markup=kb, parse_mode="HTML"
                )
            except:
                pass
            break
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 В меню", callback_data="menu_main"))
    await call.message.edit_text("❌ Отменено", reply_markup=kb)
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "nop")
async def nop(call: types.CallbackQuery):
    await call.answer("⏳ Ожидайте код...", show_alert=True)

@dp.message_handler(state=States.waiting_code_from_seller)
async def seller_sends_code(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    code = message.text.strip()
    
    if user_id not in seller_states:
        await state.finish()
        return
    
    number_id = seller_states[user_id]
    if number_id not in active_numbers:
        await state.finish()
        del seller_states[user_id]
        return
    
    ndata = active_numbers[number_id]
    if ndata.get("status") != "waiting_code_from_seller":
        await state.finish()
        del seller_states[user_id]
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
        f"📱 <b>Номер в аренде!</b>\n\n📞 <code>{ndata['phone']}</code>\n🔑 Код: <code>{code}</code>\n"
        f"⏱ <b>1/{RENTAL_MINUTES} мин</b>",
        chat_id=GROUP_ID, message_id=ndata["group_msg_id"], reply_markup=kb_group, parse_mode="HTML"
    )
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 В меню", callback_data="menu_main"))
    await message.answer(f"✅ Код отправлен в группу!\nАренда на {RENTAL_MINUTES} мин.", reply_markup=kb, parse_mode="HTML")
    
    try:
        await bot.send_message(renter_id, f"✅ Код получен!\n📞 <code>{ndata['phone']}</code>\n🔑 <code>{code}</code>", parse_mode="HTML")
    except:
        pass
    
    await state.finish()
    del seller_states[user_id]
    asyncio.create_task(rental_timer(number_id, ndata))

async def rental_timer(number_id, ndata):
    for minute in range(1, RENTAL_MINUTES + 1):
        await asyncio.sleep(60)
        if number_id not in active_numbers:
            return
        if ndata.get("status") == "failed":
            return
        if ndata.get("status") != "active":
            continue
        
        try:
            kb = InlineKeyboardMarkup()
            kb.add(
                InlineKeyboardButton("🟢 Встал", callback_data=f"status_{number_id}_active"),
                InlineKeyboardButton("🔴 Слетел", callback_data=f"status_{number_id}_failed")
            )
            await bot.edit_message_text(
                f"📱 <b>В аренде!</b>\n\n📞 <code>{ndata['phone']}</code>\n🔑 <code>{ndata.get('code','---')}</code>\n"
                f"⏱ <b>{minute}/{RENTAL_MINUTES} мин</b>",
                chat_id=GROUP_ID, message_id=ndata["group_msg_id"], reply_markup=kb, parse_mode="HTML"
            )
        except:
            pass
    
    if number_id in active_numbers and ndata.get("status") == "active":
        seller_id = ndata["seller_id"]
        if str(seller_id) in users:
            users[str(seller_id)]["balance"] += PHONE_PRICE
            save_users()
        
        try:
            await bot.send_message(seller_id, f"✅ Аренда завершена!\n💰 +${PHONE_PRICE:.2f}\n💳 Баланс: ${users[str(seller_id)]['balance']:.2f}", parse_mode="HTML")
        except:
            pass
        
        try:
            await bot.edit_message_text(
                f"📱 <b>Завершено!</b>\n\n📞 <code>{ndata['phone']}</code>\n💰 ${PHONE_PRICE:.2f}",
                chat_id=GROUP_ID, message_id=ndata["group_msg_id"], parse_mode="HTML"
            )
        except:
            pass
        
        if number_id in active_numbers:
            del active_numbers[number_id]

@dp.callback_query_handler(lambda c: c.data.startswith("status_"))
async def status_update(call: types.CallbackQuery):
    parts = call.data.split("_")
    number_id = parts[1]
    new_status = parts[2]
    
    if number_id not in active_numbers:
        await call.answer("Не найден", show_alert=True)
        return
    
    ndata = active_numbers[number_id]
    seller_id = ndata["seller_id"]
    
    if new_status == "active":
        ndata["status"] = "active"
        await bot.send_message(GROUP_ID, "🟢 Номер встал!", parse_mode="HTML")
        try:
            await bot.send_message(seller_id, f"🟢 Ваш номер <code>{ndata['phone']}</code> встал!", parse_mode="HTML")
        except:
            pass
    else:
        ndata["status"] = "failed"
        await bot.send_message(GROUP_ID, "🔴 Номер слетел!", parse_mode="HTML")
        try:
            await bot.send_message(seller_id, f"🔴 Ваш номер <code>{ndata['phone']}</code> слетел!\n❌ Оплата не начислена.", parse_mode="HTML")
        except:
            pass
        if ndata.get("renter_id"):
            try:
                await bot.send_message(ndata["renter_id"], "🔴 Номер слетел!", parse_mode="HTML")
            except:
                pass
        if number_id in active_numbers:
            del active_numbers[number_id]
    
    await call.answer("Обновлено!")

# ========== ВЫВОД СРЕДСТВ ==========
@dp.callback_query_handler(lambda c: c.data == "menu_withdraw")
async def withdraw_menu(call: types.CallbackQuery):
    if not await require_sub(call.from_user.id):
        await call.answer("❌ Подпишитесь!", show_alert=True)
        return
    
    user_id = str(call.from_user.id)
    balance = users.get(user_id, {}).get("balance", 0.0)
    
    if balance < MIN_WITHDRAW:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 Назад", callback_data="menu_main"))
        await call.message.edit_text(
            f"❌ Мало средств\n💰 ${balance:.2f}\n💳 Мин: ${MIN_WITHDRAW:.2f}",
            reply_markup=kb, parse_mode="HTML"
        )
        await call.answer()
        return
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="menu_main"))
    await call.message.edit_text(
        f"💳 Вывод\n💰 Доступно: ${balance:.2f}\n\nВведите сумму:",
        reply_markup=kb, parse_mode="HTML"
    )
    await States.waiting_withdraw_amount.set()
    await call.answer()

@dp.message_handler(state=States.waiting_withdraw_amount)
async def process_withdraw(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
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
    
    check = await create_crypto_check(amount, int(user_id))
    if not check:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 В меню", callback_data="menu_main"))
        await message.answer("❌ Ошибка создания чека.\nидите нахуй", reply_markup=kb)
        await state.finish()
        return
    
    users[user_id]["balance"] -= amount
    save_users()
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("💎 Получить USDT", url=check["url"]))
    kb.add(InlineKeyboardButton("🔙 В меню", callback_data="menu_main"))
    await message.answer(
        f"✅ Чек создан!\n\n💰 Сумма: ${amount:.2f}\n💳 Остаток: ${users[user_id]['balance']:.2f}\n\n"
        "Нажмите кнопку чтобы получить USDT",
        reply_markup=kb, parse_mode="HTML"
    )
    await state.finish()

async def create_crypto_check(amount, user_id):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://pay.crypt.bot/api/createCheck",
                headers={"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN},
                json={"asset": "USDT", "amount": str(amount), "pin_to_user_id": int(user_id)}
            ) as resp:
                data = await resp.json()
                if data.get("ok"):
                    r = data["result"]
                    return {
                        "check_id": r["check_id"],
                        "url": r.get("check_url") or r.get("url") or r.get("bot_check_url"),
                        "amount": r["amount"]
                    }
                return None
    except:
        return None

# ========== АДМИН ПАНЕЛЬ ==========
@dp.callback_query_handler(lambda c: c.data == "admin_panel")
async def admin_panel(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("❌ Нет доступа", show_alert=True)
        return
    
    text = (
        "⚙️ <b>Админ панель</b>\n\n"
        f"💵 Цена: ${PHONE_PRICE:.2f}\n"
        f"🕐 Работа: {WORK_START}:00-{WORK_END}:00\n"
        f"📋 Очередь: {len(numbers_queue)}\n"
        f"📱 В аренде: {len(active_numbers)}"
    )
    
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("💵 Цена", callback_data="admin_price"),
        InlineKeyboardButton("🕐 Начало работы", callback_data="admin_hours_start"),
        InlineKeyboardButton("🕐 Конец работы", callback_data="admin_hours_end"),
        InlineKeyboardButton("💰 Выдать баланс", callback_data="admin_give_balance"),
        InlineKeyboardButton("🗑 Очистить очередь", callback_data="admin_clear_queue"),
        InlineKeyboardButton("🔙 В меню", callback_data="menu_main")
    )
    
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "admin_price")
async def admin_price(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Админ панель", callback_data="admin_panel"))
    await call.message.edit_text(f"💵 Цена: ${PHONE_PRICE:.2f}\nВведите новую цену:", reply_markup=kb, parse_mode="HTML")
    await States.admin_change_price.set()
    await call.answer()

@dp.message_handler(state=States.admin_change_price)
async def admin_price_set(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: await state.finish(); return
    try:
        new_price = float(message.text.strip())
        if new_price <= 0: raise ValueError
    except:
        await message.answer("❌ Введите положительное число"); return
    global PHONE_PRICE; PHONE_PRICE = new_price
    config["price"] = new_price; save_config(config)
    await message.answer(f"✅ Цена: ${new_price:.2f}", parse_mode="HTML")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == "admin_hours_start")
async def admin_hours_start(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Админ панель", callback_data="admin_panel"))
    await call.message.edit_text(f"🕐 Начало: {WORK_START}:00\nВведите час (0-23):", reply_markup=kb, parse_mode="HTML")
    await States.admin_change_hours_start.set()
    await call.answer()

@dp.message_handler(state=States.admin_change_hours_start)
async def admin_hours_start_set(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: await state.finish(); return
    try:
        hour = int(message.text.strip())
        if hour < 0 or hour > 23: raise ValueError
    except:
        await message.answer("❌ Введите 0-23"); return
    global WORK_START; WORK_START = hour
    config["work_start"] = hour; save_config(config)
    await message.answer(f"✅ Начало: {hour}:00", parse_mode="HTML")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == "admin_hours_end")
async def admin_hours_end(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Админ панель", callback_data="admin_panel"))
    await call.message.edit_text(f"🕐 Конец: {WORK_END}:00\nВведите час (0-24):", reply_markup=kb, parse_mode="HTML")
    await States.admin_change_hours_end.set()
    await call.answer()

@dp.message_handler(state=States.admin_change_hours_end)
async def admin_hours_end_set(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: await state.finish(); return
    try:
        hour = int(message.text.strip())
        if hour < 0 or hour > 24: raise ValueError
    except:
        await message.answer("❌ Введите 0-24"); return
    global WORK_END; WORK_END = hour
    config["work_end"] = hour; save_config(config)
    await message.answer(f"✅ Конец: {hour}:00", parse_mode="HTML")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == "admin_give_balance")
async def admin_give_balance(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Админ панель", callback_data="admin_panel"))
    await call.message.edit_text("💰 Введите ID пользователя:", reply_markup=kb, parse_mode="HTML")
    await States.admin_give_balance_user.set()
    await call.answer()

@dp.message_handler(state=States.admin_give_balance_user)
async def admin_give_balance_user(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: await state.finish(); return
    try:
        target_id = int(message.text.strip())
    except:
        await message.answer("❌ Введите числовой ID"); return
    await state.update_data(target_id=target_id)
    await message.answer(f"👤 ID: {target_id}\nВведите сумму:")
    await States.admin_give_balance_amount.set()

@dp.message_handler(state=States.admin_give_balance_amount)
async def admin_give_balance_amount(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: await state.finish(); return
    data = await state.get_data()
    target_id = str(data["target_id"])
    try:
        amount = float(message.text.strip())
        if amount <= 0: raise ValueError
    except:
        await message.answer("❌ Введите положительное число"); return
    
    if target_id not in users:
        users[target_id] = {"balance": 0.0, "username": f"user_{target_id}"}
    users[target_id]["balance"] += amount
    save_users()
    
    await message.answer(f"✅ Баланс {target_id} +${amount:.2f}\n💰 Итог: ${users[target_id]['balance']:.2f}", parse_mode="HTML")
    try:
        await bot.send_message(int(target_id), f"💰 +${amount:.2f}\n💳 Баланс: ${users[target_id]['balance']:.2f}", parse_mode="HTML")
    except:
        pass
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == "admin_clear_queue")
async def admin_clear_queue(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    global numbers_queue
    count = len(numbers_queue)
    numbers_queue = []
    await call.message.edit_text(f"🗑 Очередь очищена! Удалено {count} номеров.", parse_mode="HTML")
    await call.answer("Очищено!")

# ========== ПОДДЕРЖКА ==========
@dp.callback_query_handler(lambda c: c.data == "menu_support")
async def support(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("👤 @auzom", url="https://t.me/auzom"))
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="menu_main"))
    await call.message.edit_text("📞 Поддержка: @auzom", reply_markup=kb, parse_mode="HTML")
    await call.answer()

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    print("🤖 Sow Max запущен...")
    executor.start_polling(dp, skip_updates=True)if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)