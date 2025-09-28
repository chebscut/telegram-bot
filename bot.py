from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ------------------- Telegram -------------------
TOKEN = os.getenv("BOT_TOKEN")

# ------------------- Google Drive -------------------
google_credentials = os.getenv("GOOGLE_CREDENTIALS")
if not google_credentials:
    raise ValueError("Нет GOOGLE_CREDENTIALS! Добавь ключ в настройки Render.")

service_account_info = json.loads(google_credentials)

# 🔑 фиксируем переносы строк в private_key
if "private_key" in service_account_info:
    service_account_info["private_key"] = service_account_info["private_key"].replace("\\n", "\n")

SCOPES = ['https://www.googleapis.com/auth/drive']
FOLDER_ID = '1nQECNPbttj32SnAhpdBjwWuYWJUUxtto'  # ID папки Obsidian в Google Drive

credentials = service_account.Credentials.from_service_account_info(
    service_account_info, scopes=SCOPES
)
service = build('drive', 'v3', credentials=credentials)

# ------------------- Flask-сервер -------------------
app_server = Flask(__name__)

@app_server.route("/")
def home():
    return "Bot is running!"

def run_server():
    app_server.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# ------------------- Telegram-бот -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я работаю на Render 🤖\n\n"
                                    "Доступные команды:\n"
                                    "/list — список заметок\n"
                                    "/note <имя> — открыть заметку")

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

# 🔥 новая команда
async def get_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /note <имя_файла.md>")
        return

    filename = " ".join(context.args)

    # ищем файл в папке Obsidian
    results = service.files().list(
        q=f"'{FOLDER_ID}' in parents and name='{filename}'",
        fields="files(id, name)"
    ).execute()
    files = results.get('files', [])

    if not files:
        await update.message.reply_text("Такой заметки нет 😢")
        return

    file_id = files[0]['id']
    # скачиваем содержимое
    content = service.files().get_media(fileId=file_id).execute()
    text = content.decode("utf-8")

    # Telegram ограничивает сообщение 4096 символами
    if len(text) > 4000:
        await update.message.reply_text(f"📄 {filename} (показаны первые 4000 символов):\n\n{text[:4000]}")
    else:
        await update.message.reply_text(f"📄 {filename}:\n\n{text}")


# ------------------- main -------------------

def main():
    if not TOKEN:
        raise ValueError("Нет BOT_TOKEN! Добавь его в настройки Render.")
    
    # Запускаем Flask-сервер в фоне для Render
    thread = Thread(target=run_server)
    thread.start()

    # Настраиваем бота
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_notes))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    app.add_handler(CommandHandler("note", get_note))
    app.run_polling()
    

if __name__ == "__main__":
    main()
