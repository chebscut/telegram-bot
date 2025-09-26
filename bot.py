from flask import Flask, request
from threading import Thread
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ------------------- Telegram -------------------
TOKEN = os.getenv("BOT_TOKEN")
URL = os.getenv("RENDER_EXTERNAL_URL")  # URL Render для вебхука
if not TOKEN:
    raise ValueError("Нет BOT_TOKEN! Добавь его в настройки Render.")

# ------------------- Google Drive -------------------
google_credentials = os.getenv("GOOGLE_CREDENTIALS")
if not google_credentials:
    raise ValueError("Нет GOOGLE_CREDENTIALS! Добавь ключ в настройки Render.")

service_account_info = json.loads(google_credentials)
# 🔑 фиксируем переносы строк в private_key
if "private_key" in service_account_info:
    service_account_info["private_key"] = service_account_info["private_key"].replace("\\n", "\n")

SCOPES = ['https://www.googleapis.com/auth/drive']
FOLDER_ID = '1nQECNPbttj32SnAhpdBjwWuYWJUUxtto'  # ID папки Obsidian

credentials = service_account.Credentials.from_service_account_info(
    service_account_info, scopes=SCOPES
)
service = build('drive', 'v3', credentials=credentials)

# ------------------- Flask-сервер -------------------
app_server = Flask(__name__)

@app_server.route("/")
def home():
    return "Bot is running!"

@app_server.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    """Обрабатываем апдейты от Telegram"""
    data = request.get_json(force=True)
    update = Update.de_json(data, application.bot)
    application.update_queue.put_nowait(update)
    return "ok"

def run_server():
    app_server.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# ------------------- Telegram-бот -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я работаю на Render через вебхук 🤖")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(update.message.text)

async def list_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    results = service.files().list(
        q=f"'{FOLDER_ID}' in parents and mimeType='text/markdown'",
        fields="files(id, name)"
    ).execute()
    files = results.get('files', [])
    if not files:
        await update.message.reply_text("Заметок нет 😢")
    else:
        names = "\n".join(file['name'] for file in files)
        await update.message.reply_text(f"Заметки:\n{names}")

# ------------------- Main -------------------
def main():
    # Запускаем Flask-сервер в фоне для Render
    thread = Thread(target=run_server)
    thread.start()

    # Настраиваем бота
    global application
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("list", list_notes))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Устанавливаем webhook на URL Render
    application.bot.set_webhook(f"{URL}/{TOKEN}")

    # Применяем webhook (не polling)
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        url_path=TOKEN
    )

if __name__ == "__main__":
    main()
