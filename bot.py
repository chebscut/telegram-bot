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
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# 📂 Показать содержимое папки
async def list_folders(update: Update, context: ContextTypes.DEFAULT_TYPE, folder_id=None):
    if folder_id is None:
        folder_id = FOLDER_ID  # корневая папка

    results = service.files().list(
        q=f"'{folder_id}' in parents",
        fields="files(id, name, mimeType)"
    ).execute()
    files = results.get('files', [])

    if not files:
        await update.message.reply_text("Папка пуста 😢")
        return

    keyboard = []
    for f in files:
        if f["mimeType"] == "application/vnd.google-apps.folder":  # это папка
            keyboard.append([InlineKeyboardButton(f"📂 {f['name']}", callback_data=f"folder:{f['id']}")])
        elif f["mimeType"] == "text/markdown":  # это заметка
            keyboard.append([InlineKeyboardButton(f"📝 {f['name']}", callback_data=f"note:{f['id']}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("Выбери папку или заметку:", reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text("Выбери папку или заметку:", reply_markup=reply_markup)


# 📄 Показать содержимое заметки
async def show_note(update: Update, context: ContextTypes.DEFAULT_TYPE, file_id: str):
    file = service.files().get_media(fileId=file_id).execute()
    text = file.decode("utf-8")

    # обрежем слишком длинные заметки (чтобы Telegram не ругался)
    if len(text) > 4000:
        text = text[:4000] + "\n\n...✂️ заметка обрезана"

    await update.callback_query.message.reply_text(f"📄 Содержимое:\n\n{text}")


# 🎛 Обработчик кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("folder:"):
        folder_id = data.split(":", 1)[1]
        await list_folders(update, context, folder_id)
    elif data.startswith("note:"):
        file_id = data.split(":", 1)[1]
        await show_note(update, context, file_id)


# ⚡️ Регистрируем хендлеры
def register_handlers(app):
    app.add_handler(CommandHandler("folders", list_folders))
    app.add_handler(CallbackQueryHandler(button_handler))



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
