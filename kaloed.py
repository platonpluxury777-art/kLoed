import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import uuid

# ---------- НАСТРОЙКИ ----------
TOKEN = "8685363623:AAFeiGkHhyfwwyRFgy27xSZ8e17K6I7UNuI"
CRYPTO_BOT_TOKEN = "569144:AAs82ABvMXw8uTlYYfIrZOMWZA5C7bYhfdr"  # Получить: @CryptoBot
ADMIN_IDS = [105635005]
GROUP_ID = -1003945636594  # ID группы
MIN_WITHDRAW = 1.00  # Минимум $1

# ---------- ЛОГИРОВАНИЕ ----------
logging.basicConfig(level=logging.INFO)

# ---------- БОТ ----------
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# ---------- БАЗА ДАННЫХ ----------
users = {}
active_numbers = {}
pending_codes = {}

# ---------- КЛАВИАТУРЫ ----------
def main_menu():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("💰 Сдать номер"), KeyboardButton("👤 Профиль"))
    keyboard.add(KeyboardButton("💳 Вывод средств"), KeyboardButton("👥 Реферальная программа"))
    keyboard.add(KeyboardButton("📋 Другое"), KeyboardButton("📞 Поддержка"))
    return keyboard

# ---------- СОСТОЯНИЯ ----------
class WithdrawStates(StatesGroup):
    waiting_amount = State()

# ---------- ОБРАБОТЧИКИ ----------
@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    
    if user_id not in users:
        users[user_id] = {
            "balance": 0.0,
            "referrals": [],
            "referral_code": f"ref{user_id}",
            "username": username
        }
    
    text = (
        "🤖 <b>Sow Max</b> — приёмка и аренда номеров.\n\n"
        f"💰 Ваш баланс: ${users[user_id]['balance']:.2f}\n"
        f"💳 Мин. вывод: ${MIN_WITHDRAW:.2f}\n\n"
        "📞 Техподдержка: @auzom"
    )
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("✅ ОК", callback_data="ok_main"))
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

@dp.callback_query_handler(lambda c: c.data == "ok_main")
async def process_ok(callback_query: types.CallbackQuery):
    await callback_query.message.answer("Главное меню:", reply_markup=main_menu())
    await callback_query.answer()

# ---------- ВЫВОД СРЕДСТВ ЧЕРЕЗ CRYPTO BOT ----------
@dp.message_handler(lambda m: m.text == "💳 Вывод средств")
async def withdraw_start(message: types.Message):
    user_id = message.from_user.id
    balance = users.get(user_id, {}).get("balance", 0.0)
    
    if balance < MIN_WITHDRAW:
        await message.answer(
            f"❌ Недостаточно средств!\n\n"
            f"💰 Ваш баланс: ${balance:.2f}\n"
            f"💳 Мин. вывод: ${MIN_WITHDRAW:.2f}",
            reply_markup=main_menu()
        )
        return
    
    await message.answer(
        f"💳 <b>Вывод средств</b>\n\n"
        f"💰 Доступно: ${balance:.2f}\n"
        f"💳 Минимум: ${MIN_WITHDRAW:.2f}\n\n"
        "Введите сумму для вывода (например: 5.00):",
        parse_mode="HTML"
    )
    await WithdrawStates.waiting_amount.set()

@dp.message_handler(state=WithdrawStates.waiting_amount)
async def process_withdraw_amount(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    try:
        amount = float(message.text.strip())
    except:
        await message.answer("❌ Введите число (например: 5.00)")
        return
    
    balance = users[user_id]["balance"]
    
    if amount < MIN_WITHDRAW:
        await message.answer(f"❌ Минимальная сумма вывода: ${MIN_WITHDRAW:.2f}")
        return
    
    if amount > balance:
        await message.answer(f"❌ Недостаточно средств! Баланс: ${balance:.2f}")
        return
    
    # Создаем чек в Crypto Bot
    check = await create_crypto_check(amount, user_id)
    
    if not check:
        await message.answer(
            "❌ Ошибка при создании выплаты. Обратитесь в поддержку: @auzom",
            reply_markup=main_menu()
        )
        await state.finish()
        return
    
    # Списание с баланса
    users[user_id]["balance"] -= amount
    
    # Красивый ответ с чеком
    text = (
        "✅ <b>Выплата создана!</b>\n\n"
        f"💰 Сумма: ${amount:.2f}\n"
        f"🏦 Остаток: ${users[user_id]['balance']:.2f}\n\n"
        f"🔗 <b>Ваш чек:</b>\n"
        f"{check['url']}\n\n"
        "Нажмите на ссылку чтобы получить USDT 💎"
    )
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("💎 Получить USDT", url=check['url']))
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await message.answer("Что дальше?", reply_markup=main_menu())
    
    # Уведомление админу
    for admin in ADMIN_IDS:
        await bot.send_message(
            admin,
            f"💳 <b>Вывод средств</b>\n"
            f"👤 User: @{message.from_user.username or user_id}\n"
            f"💰 Сумма: ${amount:.2f}\n"
            f"🏦 Остаток: ${users[user_id]['balance']:.2f}",
            parse_mode="HTML"
        )
    
    await state.finish()

# ---------- ФУНКЦИЯ CRYPTO BOT API ----------
async def create_crypto_check(amount: float, user_id: int):
    """Создание чека в Crypto Bot API"""
    url = "https://pay.crypt.bot/api/createCheck"
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    
    payload = {
        "asset": "USDT",  # USDT, BTC, TON, ETH и др.
        "amount": str(amount),
        "pin_to_user_id": user_id  # Чек привязан к юзеру
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                data = await response.json()
                
                if data.get("ok"):
                    check = data["result"]
                    return {
                        "check_id": check["check_id"],
                        "url": f"https://t.me/CryptoBot?start={check['check_id']}",
                        "amount": check["amount"]
                    }
                else:
                    logging.error(f"Crypto Bot API error: {data}")
                    return None
                    
    except Exception as e:
        logging.error(f"Crypto Bot request failed: {e}")
        return None

# ---------- ПОДДЕРЖКА ----------
@dp.message_handler(lambda m: m.text == "📞 Поддержка")
async def support(message: types.Message):
    await message.answer(
        "📞 <b>Техподдержка</b>\n\n"
        "По всем вопросам:\n"
        "👤 @auzom\n\n"
        "• Проблемы с выводом\n"
        "• Вопросы по аренде\n"
        "• Ошибки бота",
        parse_mode="HTML"
    )

# ---------- ЗАПУСК ----------
if __name__ == '__main__':
    print("🤖 Бот Sow Max с авто-выплатами Crypto Bot запущен...")
    executor.start_polling(dp, skip_updates=True)