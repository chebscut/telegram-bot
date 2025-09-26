import os
import json
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ------------------- Telegram -------------------
TOKEN = os.getenv("BOT_TOKEN")
URL = os.getenv("RENDER_EXTERNAL_URL")  # Render сам задаёт URL приложения

# ------------------- Google Drive -------------------
# Загружаем ключ из переменной окружения
service_account_info = json.loads(os.environ.get("GOOGLE_CREDENTIALS"))
SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_ID = "1nQECNPbttj32SnAhpdBjwWuYWJUUxtto"  # ID папки Obsidian

credentials = service_account.Credentials.from_service_account_info(
    service_account_info, scopes=SCOPES
)
service = build("drive", "v3", credentials=credentials)

# ------------------- Flask -------------------
app_server = Flask(__name__)
application = Application.builder().token(TOKEN).build()

# ------------------- Handlers -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я работаю на Render 🚀 через вебхуки!")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(update.message.text)

async def list_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    results = service.files().list(
        q=f"'{FOLDER_ID}' in parents and mimeType='text/markdown'",
        fields="files(id, name)"
    ).execute()
    files = results.get("files", [])
    if not files:
        await update.message.reply_text("Заметок нет 😢")
    else:
        names = "\n".join(file["name"] for file in files)
        await update.message.reply_text(f"Заметки:\n{names}")

# Добавляем обработчики
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("list", list_notes))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# ------------------- Webhook endpoints -------------------
@app_server.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, application.bot)
    application.update_queue.put_nowait(update)
    return "ok"

@app_server.route("/set_webhook")
async def set_webhook():
    await application.bot.set_webhook(f"{URL}/{TOKEN}")
    return "Webhook set!"

@app_server.route("/")
def home():
    return "Bot is running with webhook! 🚀"

if __name__ == "__main__":
    app_server.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
