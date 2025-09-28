import os
import json
import re
from io import BytesIO
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ------------------- Telegram -------------------
TOKEN = os.getenv("BOT_TOKEN")

# ------------------- Google Drive -------------------
google_credentials = os.getenv("GOOGLE_CREDENTIALS")
if not google_credentials:
    raise ValueError("Нет GOOGLE_CREDENTIALS! Добавь ключ в настройки Render.")

service_account_info = json.loads(google_credentials)

if "private_key" in service_account_info:
    service_account_info["private_key"] = service_account_info["private_key"].replace("\\n", "\n")

SCOPES = ['https://www.googleapis.com/auth/drive']
FOLDER_ID = '1nQECNPbttj32SnAhpdBjwWuYWJUUxtto'

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

# ------------------- Работа с Drive -------------------
def get_all_files(folder_id=FOLDER_ID):
    """Возвращает все файлы и папки рекурсивно"""
    files = []
    folders_to_check = [folder_id]

    while folders_to_check:
        current_folder = folders_to_check.pop()
        results = service.files().list(
            q=f"'{current_folder}' in parents",
            fields="files(id, name, mimeType)"
        ).execute()
        for f in results.get('files', []):
            if f['mimeType'] == 'application/vnd.google-apps.folder':
                folders_to_check.append(f['id'])
            else:
                files.append(f)
    return files

# Словарь для хранения родительских папок (для кнопки "Назад")
folder_parents = {}

# ------------------- Telegram-бот -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я работаю на Render 🤖\n\n"
        "Доступные команды:\n"
        "/folders — список папок с заметками"
    )

# Список папок в корне
async def list_folders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    folders_result = service.files().list(
        q=f"'{FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder'",
        fields="files(id, name)"
    ).execute()
    folders = folders_result.get('files', [])

    keyboard = [[InlineKeyboardButton("Все заметки", callback_data=f"folder:{FOLDER_ID}")]]
    
    for f in folders:
        folder_parents[f['id']] = FOLDER_ID
        keyboard.append([InlineKeyboardButton(f['name'], callback_data=f"folder:{f['id']}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите папку:", reply_markup=reply_markup)

# Показать содержимое папки
async def folder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    folder_id = query.data.split(":")[1]
    parent_id = folder_parents.get(folder_id, FOLDER_ID)

    # Подпапки
    folders_result = service.files().list(
        q=f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder'",
        fields="files(id, name)"
    ).execute()
    folders = folders_result.get('files', [])

    # Заметки
    notes_result = service.files().list(
        q=f"'{folder_id}' in parents and mimeType='text/markdown'",
        fields="files(id, name)"
    ).execute()
    notes = notes_result.get('files', [])

    keyboard = []

    for f in folders:
        folder_parents[f['id']] = folder_id
        keyboard.append([InlineKeyboardButton(f['name'], callback_data=f"folder:{f['id']}")])

    for n in notes:
        folder_parents[n['id']] = folder_id
        keyboard.append([InlineKeyboardButton(n['name'], callback_data=f"note:{n['id']}")])

    if folder_id != FOLDER_ID:
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"folder:{parent_id}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Выберите папку или заметку:", reply_markup=reply_markup)

# Показать содержимое заметки и изображения
async def show_note_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    file_id = query.data.split(":")[1]
    folder_id = folder_parents.get(file_id, FOLDER_ID)

    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data=f"folder:{folder_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Вернуться:", reply_markup=reply_markup)

    meta = service.files().get(fileId=file_id, fields="name").execute()
    name = meta.get("name", "note.md")

    content = service.files().get_media(fileId=file_id).execute()
    text = content.decode("utf-8")

    # Ищем картинки ![[...]]
    matches = re.findall(r"!\[\[(.*?)\]\]", text, flags=re.IGNORECASE | re.MULTILINE)
    clean_text = re.sub(r"!\[\[(.*?)\]\]", "", text, flags=re.IGNORECASE | re.MULTILINE)
    if len(clean_text) > 4000:
        clean_text = clean_text[:4000] + "\n\n...✂️ (обрезано)"

    await query.message.reply_text(f"📄 {name}:\n\n{clean_text.strip()}")

    if matches:
        all_files = get_all_files()
        file_map = {f["name"].lower(): f["id"] for f in all_files}
        for m in matches:
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

    Thread(target=run_server).start()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("folders", list_folders))
    app.add_handler(CallbackQueryHandler(folder_callback, pattern=r"^folder:"))
    app.add_handler(CallbackQueryHandler(show_note_callback, pattern=r"^note:"))
    app.run_polling()

if __name__ == "__main__":
    main()
