import os
import requests
import logging
import asyncio
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ========== НАСТРОЙКИ (через переменные окружения) ==========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Проверяем, что токены установлены
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не установлен! Добавьте его в переменные окружения.")
if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY не установлен! Добавьте его в переменные окружения.")

# OpenRouter API endpoint
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Настройки модели
MODEL = "deepseek/deepseek-chat"
TEMPERATURE = 0.7
MAX_TOKENS = 1000
# =================================

# Хранилище для истории и имен пользователей
user_histories = {}
user_names = {}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.first_name or update.effective_user.username
    user_names[user_id] = username

    await update.message.reply_text(
        f"🤖 Привет, {username}! Я бот на базе DeepSeek через OpenRouter.\n\n"
        f"📝 Я запомнил твое имя! Просто напиши мне сообщение.\n\n"
        f"⚙️ Команды:\n"
        f"/start - Показать это сообщение\n"
        f"/setname Имя - Установить новое имя\n"
        f"/clear - Очистить историю\n"
        f"/model - Показать модель"
    )
    logger.info(f"Пользователь {username} запустил бота")


async def set_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if context.args:
        new_name = " ".join(context.args)
        user_names[user_id] = new_name
        await update.message.reply_text(f"✅ Теперь я буду называть тебя **{new_name}**")
    else:
        current = user_names.get(user_id, "неизвестно")
        await update.message.reply_text(f"Сейчас я называю тебя: {current}\n/setname Имя - чтобы изменить")


async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_histories:
        user_histories[user_id] = []
    await update.message.reply_text("🧹 История диалога очищена!")


async def show_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🤖 Модель: **{MODEL}**\n🌡️ Температура: {TEMPERATURE}")


async def get_deepseek_response(user_id: int, user_message: str) -> str:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/your-telegram-bot",
        "X-Title": "DeepSeek Telegram Bot"
    }

    user_name = user_names.get(user_id, "пользователь")

    messages = [
        {
            "role": "system",
            "content": f"Ты дружелюбный AI-ассистент. Пользователя зовут {user_name}. Обращайся к нему по имени. Отвечай на русском языке."
        }
    ]

    if user_id in user_histories:
        messages.extend(user_histories[user_id][-10:])

    messages.append({"role": "user", "content": user_message})

    data = {
        "model": MODEL,
        "messages": messages,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS
    }

    try:
        response = requests.post(OPENROUTER_URL, headers=headers, json=data, timeout=45)

        if response.status_code == 200:
            result = response.json()
            answer = result['choices'][0]['message']['content']

            if user_id not in user_histories:
                user_histories[user_id] = []
            user_histories[user_id].append({"role": "user", "content": user_message})
            user_histories[user_id].append({"role": "assistant", "content": answer})

            return answer
        elif response.status_code == 401:
            return "❌ Ошибка авторизации: неверный API ключ."
        elif response.status_code == 402:
            return "❌ Недостаточно средств. Используйте бесплатную модель: deepseek/deepseek-r1:free"
        else:
            return f"❌ Ошибка API: {response.status_code}"

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return f"❌ Ошибка: {str(e)}"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text
    username = user_names.get(user_id, update.effective_user.first_name or "пользователь")

    logger.info(f"📨 Сообщение от {username}: {user_message[:100]}...")
    await update.message.chat.send_action(action="typing")

    response_text = await get_deepseek_response(user_id, user_message)

    if len(response_text) > 4096:
        for i in range(0, len(response_text), 4096):
            await update.message.reply_text(response_text[i:i + 4096])
    else:
        await update.message.reply_text(response_text)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text("😕 Произошла ошибка. Попробуйте позже.")


def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setname", set_name))
    application.add_handler(CommandHandler("clear", clear_history))
    application.add_handler(CommandHandler("model", show_model))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)

    print("🤖 Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()