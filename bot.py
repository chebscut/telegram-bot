from flask import Flask
from threading import Thread
from telegram import Update
from telegram import InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import re
import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler
from io import BytesIO

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

 ------------------- Telegram-бот -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я работаю на Render 🤖\n\n"
        "Доступные команды:\n"
        "/list — список заметок\n"
        "/note <имя> — открыть заметку"
    )


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(update.message.text)


async def list_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_files = get_all_files()
    notes = [f for f in all_files if f["mimeType"] == "text/markdown"]

    if not notes:
        await update.message.reply_text("Заметок нет 😢")
        return

    # делаем кнопки
    keyboard = []
    for note in notes[:30]:  # ограничим до 30, чтобы не перегрузить клавиатуру
        keyboard.append([InlineKeyboardButton(note["name"], callback_data=f"note:{note['id']}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📂 Выберите заметку:", reply_markup=reply_markup)


import re
from io import BytesIO
from telegram import InputFile

async def show_note_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    file_id = query.data.split(":")[1]

    # получаем содержимое заметки
    meta = service.files().get(fileId=file_id, fields="name").execute()
    name = meta.get("name", "note.md")

    content = service.files().get_media(fileId=file_id).execute()
    text = content.decode("utf-8")

    # ищем все упоминания картинок ![[...]]
    matches = re.findall(r"!\[\[(.*?)\]\]", text, flags=re.IGNORECASE | re.MULTILINE)

    # убираем все ![[...]] из текста
    clean_text = re.sub(r"!\[\[(.*?)\]\]", "", text, flags=re.IGNORECASE | re.MULTILINE)

    # ограничиваем текст
    if len(clean_text) > 4000:
        clean_text = clean_text[:4000] + "\n\n...✂️ (обрезано)"

    # отправляем текст
    await query.message.reply_text(f"📄 {name}:\n\n{clean_text.strip()}")

    # 🔥 отправляем картинки
    if matches:
        all_files = get_all_files()  # функция должна вернуть список всех файлов в Drive
        file_map = {f["name"].lower(): f["id"] for f in all_files}  # регистр-независимо

        for m in matches:
            # добавляем расширение .png, если нет
            if not (m.lower().endswith(".png") or m.lower().endswith(".jpg")):
                m = m + ".png"

            file_id_img = file_map.get(m.lower())
            if file_id_img:
                img_data = service.files().get_media(fileId=file_id_img).execute()
                bio = BytesIO(img_data)
                bio.name = m
                await query.message.reply_photo(InputFile(bio))

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
    app.add_handler(CommandHandler("note", list_notes))  # оставляем для совместимости
    app.add_handler(CallbackQueryHandler(show_note_callback, pattern="^note:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    app.run_polling()


if __name__ == "__main__":
    main()
