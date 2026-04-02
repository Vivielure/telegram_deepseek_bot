import os
import requests
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from http.server import HTTPServer, BaseHTTPRequestHandler

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not TELEGRAM_TOKEN or not OPENROUTER_API_KEY:
    raise ValueError("Missing required environment variables")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "deepseek/deepseek-chat"
TEMPERATURE = 0.7
MAX_TOKENS = 1000

user_histories = {}
user_names = {}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== КОМАНДЫ БОТА ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.first_name or update.effective_user.username
    user_names[user_id] = username
    await update.message.reply_text(
        f"🤖 Привет, {username}! Я бот на базе DeepSeek.\n"
        "Просто напиши мне сообщение!\n\n"
        "⚙️ Команды:\n/setname Имя - установить имя\n/clear - очистить историю"
    )

async def set_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if context.args:
        new_name = " ".join(context.args)
        user_names[user_id] = new_name
        await update.message.reply_text(f"✅ Теперь я буду называть тебя **{new_name}**")
    else:
        current = user_names.get(user_id, "неизвестно")
        await update.message.reply_text(f"Сейчас я называю тебя: {current}")

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_histories:
        user_histories[user_id] = []
    await update.message.reply_text("🧹 История диалога очищена!")

async def get_deepseek_response(user_id: int, user_message: str) -> str:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    user_name = user_names.get(user_id, "пользователь")
    messages = [
        {"role": "system", "content": f"Ты дружелюбный AI-ассистент. Пользователя зовут {user_name}. Отвечай на русском языке."}
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
            return "❌ Ошибка: неверный API ключ."
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
            await update.message.reply_text(response_text[i:i+4096])
    else:
        await update.message.reply_text(response_text)

# ========== ПРОСТОЙ KEEP-ALIVE СЕРВЕР ==========
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health" or self.path == "/":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Отключаем лишние логи
        pass

def run_keepalive_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    import threading
    # Запускаем keep-alive сервер в фоновом потоке
    server_thread = threading.Thread(target=run_keepalive_server, daemon=True)
    server_thread.start()
    logger.info(f"Keep-alive сервер запущен на порту {os.environ.get('PORT', 10000)}")
    
    # Запускаем Telegram бота в основном потоке
    logger.info("🤖 Запуск Telegram бота...")
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setname", set_name))
    application.add_handler(CommandHandler("clear", clear_history))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling(allowed_updates=Update.ALL_TYPES)
