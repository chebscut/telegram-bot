import os
import json
import re
from io import BytesIO
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
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

# ------------------- Telegram-бот -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Навигация по меню", callback_data="nav:start")],
        [InlineKeyboardButton("Поиск по номеру", callback_data="search:start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Привет! Я работаю на Render 🤖\n\nВыберите действие:",
        reply_markup=reply_markup
    )

# ------------------- Обработка кнопок /start -------------------
async def start_buttons_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "nav:start":
        await list_folders(update, context)
    elif query.data == "search:start":
        await query.message.reply_text("Введите номер блюда (например 123):")
        context.user_data['awaiting_number'] = True

# ------------------- Обработка текстового ввода -------------------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_number'):
        number = update.message.text.strip()
        context.user_data['awaiting_number'] = False
        await search_by_number_number_only(update, context, number)
    else:
        await update.message.reply_text(update.message.text)

# ------------------- Навигация по папкам -------------------
async def list_folders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    folders_result = service.files().list(
        q=f"'{FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder'",
        fields="files(id, name)"
    ).execute()
    folders = folders_result.get('files', [])

    keyboard = [[InlineKeyboardButton("Все заметки", callback_data=f"folder:{FOLDER_ID}")]]
    for f in folders:
        keyboard.append([InlineKeyboardButton(f['name'], callback_data=f"folder:{f['id']}:{FOLDER_ID}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите папку:", reply_markup=reply_markup)

async def folder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    folder_id = parts[1]
    parent_id = parts[2] if len(parts) > 2 else FOLDER_ID

    # подпапки
    folders_result = service.files().list(
        q=f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder'",
        fields="files(id, name)"
    ).execute()
    folders = folders_result.get('files', [])

    # заметки
    notes_result = service.files().list(
        q=f"'{folder_id}' in parents and mimeType='text/markdown'",
        fields="files(id, name)"
    ).execute()
    notes = notes_result.get('files', [])

    keyboard = []
    for f in folders:
        keyboard.append([InlineKeyboardButton(f['name'], callback_data=f"folder:{f['id']}:{folder_id}")])
    for n in notes:
        keyboard.append([InlineKeyboardButton(n['name'], callback_data=f"note:{n['id']}:{folder_id}")])
    if folder_id != FOLDER_ID:
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"folder:{parent_id}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Выберите папку или заметку:", reply_markup=reply_markup)

# ------------------- Просмотр заметки -------------------
async def show_note_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    file_id = parts[1]
    folder_id = parts[2] if len(parts) > 2 else FOLDER_ID

    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data=f"folder:{folder_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Вернуться:", reply_markup=reply_markup)

    meta = service.files().get(fileId=file_id, fields="name").execute()
    name = meta.get("name", "note.md")
    content = service.files().get_media(fileId=file_id).execute()
    text = content.decode("utf-8")

    img_matches = re.findall(r"!\[\[(.*?)\]\]", text, flags=re.IGNORECASE | re.MULTILINE)
    clean_text = re.sub(r"!\[\[(.*?)\]\]", "", text, flags=re.IGNORECASE | re.MULTILINE)
    if len(clean_text) > 4000:
        clean_text = clean_text[:4000] + "\n\n...✂️ (обрезано)"
    await query.message.reply_text(f"📄 {name}:\n\n{clean_text.strip()}")

    if img_matches:
        all_files = get_all_files()
        file_map = {f["name"].lower(): f["id"] for f in all_files}
        for m in img_matches:
            if not (m.lower().endswith(".png") or m.lower().endswith(".jpg")):
                m += ".png"
            file_id_img = file_map.get(m.lower())
            if file_id_img:
                img_data = service.files().get_media(fileId=file_id_img).execute()
                bio = BytesIO(img_data)
                bio.name = m
                await query.message.reply_photo(InputFile(bio))

# ------------------- Поиск заметки по номеру -------------------
async def search_by_number_number_only(update: Update, context: ContextTypes.DEFAULT_TYPE, number: str):
    all_files = get_all_files()
    matches = [f for f in all_files if f['mimeType'] == 'text/markdown' and f['name'].startswith(number + ".")]

    if not matches:
        await update.message.reply_text("Блюда с таким номером нет 😢\nВведите номер ещё раз.")
        context.user_data['awaiting_number'] = True
        return

    file = matches[0]
    file_id = file['id']
    meta = service.files().get(fileId=file_id, fields="name").execute()
    name = meta.get("name", "note.md")
    content = service.files().get_media(fileId=file_id).execute()
    text = content.decode("utf-8")

    img_matches = re.findall(r"!\[\[(.*?)\]\]", text, flags=re.IGNORECASE | re.MULTILINE)
    clean_text = re.sub(r"!\[\[(.*?)\]\]", "", text, flags=re.IGNORECASE | re.MULTILINE)
    if len(clean_text) > 4000:
        clean_text = clean_text[:4000] + "\n\n...✂️ (обрезано)"
    await update.message.reply_text(f"📄 {name}:\n\n{clean_text.strip()}")

    if img_matches:
        file_map = {f["name"].lower(): f["id"] for f in all_files}
        for m in img_matches:
            if not (m.lower().endswith(".png") or m.lower().endswith(".jpg")):
                m += ".png"
            file_id_img = file_map.get(m.lower())
            if file_id_img:
                img_data = service.files().get_media(fileId=file_id_img).execute()
                bio = BytesIO(img_data)
                bio.name = m
                await update.message.reply_photo(InputFile(bio))

# ------------------- main -------------------
def main():
    if not TOKEN:
        raise ValueError("Нет BOT_TOKEN! Добавь его в настройки Render.")

    thread = Thread(target=run_server)
    thread.start()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(start_buttons_callback, pattern=r"^(nav:start|search:start)$"))
    app.add_handler(CommandHandler("folders", list_folders))
    app.add_handler(CallbackQueryHandler(folder_callback, pattern=r"^folder:"))
    app.add_handler(CallbackQueryHandler(show_note_callback, pattern=r"^note:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling()

if __name__ == "__main__":
    main()
