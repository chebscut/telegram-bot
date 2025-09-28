import os
import json
import re
from io import BytesIO
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from google.oauth2 import service_account
from googleapiclient.discovery import build
import base64

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

# ------------------- Helper Functions -------------------
def encode_id(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode()

def decode_id(s: str) -> str:
    return base64.urlsafe_b64decode(s.encode()).decode()

def get_all_files(folder_id=FOLDER_ID):
    """Возвращает список всех файлов в папке и подпапках рекурсивно"""
    files = []
    folders_to_check = [folder_id]
    while folders_to_check:
        current_folder = folders_to_check.pop()
        results = service.files().list(
            q=f"'{current_folder}' in parents",
            fields="files(id, name, mimeType, parents)"
        ).execute()
        for f in results.get('files', []):
            if f['mimeType'] == 'application/vnd.google-apps.folder':
                folders_to_check.append(f['id'])
            else:
                files.append(f)
    return files

# ------------------- Telegram Bot -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Навигация по папкам", callback_data="menu")],
        [InlineKeyboardButton("Поиск по номеру", callback_data="search_number")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Привет! Выберите действие:", reply_markup=reply_markup)

# ------------------- Меню папок -------------------
async def list_folders_from_query(query, context: ContextTypes.DEFAULT_TYPE, parent_folder=FOLDER_ID):
    folders_result = service.files().list(
        q=f"'{parent_folder}' in parents and mimeType='application/vnd.google-apps.folder'",
        fields="files(id, name)"
    ).execute()
    folders = folders_result.get('files', [])

    keyboard = [[InlineKeyboardButton("Все заметки", callback_data=f"folder:{encode_id(parent_folder)}")]]
    for f in folders:
        keyboard.append([InlineKeyboardButton(f['name'], callback_data=f"folder:{encode_id(f['id'])}:{encode_id(parent_folder)}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Выберите папку:", reply_markup=reply_markup)

async def start_buttons_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "menu":
        await list_folders_from_query(query, context)
    elif query.data == "search_number":
        await query.message.reply_text("Введите номер блюда (например 123):")
        return

# ------------------- Навигация по папкам и заметкам -------------------
async def folder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    folder_id = decode_id(parts[1])
    parent_id = decode_id(parts[2]) if len(parts) > 2 else FOLDER_ID

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
        keyboard.append([InlineKeyboardButton(f['name'], callback_data=f"folder:{encode_id(f['id'])}:{encode_id(folder_id)}")])
    for n in notes:
        keyboard.append([InlineKeyboardButton(n['name'], callback_data=f"note:{encode_id(n['id'])}:{encode_id(folder_id)}")])

    if folder_id != FOLDER_ID:
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"folder:{encode_id(parent_id)}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Выберите папку или заметку:", reply_markup=reply_markup)

# ------------------- Показ заметки -------------------
async def show_note_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    file_id = decode_id(parts[1])
    folder_id = decode_id(parts[2]) if len(parts) > 2 else FOLDER_ID

    meta = service.files().get(fileId=file_id, fields="name").execute()
    name = meta.get("name", "note.md")

    content = service.files().get_media(fileId=file_id).execute()
    text = content.decode("utf-8")

    # Картинки ![[...]]
    matches = re.findall(r"!\[\[(.*?)\]\]", text, flags=re.IGNORECASE | re.MULTILINE)
    clean_text = re.sub(r"!\[\[(.*?)\]\]", "", text, flags=re.IGNORECASE | re.MULTILINE)
    if len(clean_text) > 4000:
        clean_text = clean_text[:4000] + "\n\n...✂️ (обрезано)"

    # Отправляем текст
    await query.message.reply_text(f"📄 {name}:\n\n{clean_text.strip()}")

    # Отправляем картинки
    if matches:
        all_files = get_all_files()
        file_map = {f["name"].lower(): f["id"] for f in all_files}
        for m in matches:
            if not (m.lower().endswith(".png") or m.lower().endswith(".jpg")):
                m += ".png"
            file_id_img = file_map.get(m.lower())
            if file_id_img:
                img_data = service.files().get_media(fileId=file_id_img).execute()
                bio = BytesIO(img_data)
                bio.name = m
                await query.message.reply_photo(InputFile(bio))

    # Кнопка "Назад"
    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data=f"folder:{encode_id(folder_id)}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Вернуться:", reply_markup=reply_markup)

# ------------------- Main -------------------
def main():
    if not TOKEN:
        raise ValueError("Нет BOT_TOKEN! Добавь его в настройки Render.")

    thread = Thread(target=run_server)
    thread.start()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(start_buttons_callback, pattern=r"^(menu|search_number)$"))
    app.add_handler(CallbackQueryHandler(folder_callback, pattern=r"^folder:"))
    app.add_handler(CallbackQueryHandler(show_note_callback, pattern=r"^note:"))
    app.run_polling()

if __name__ == "__main__":
    main()
