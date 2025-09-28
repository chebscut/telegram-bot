from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler

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

# ------------------- Telegram-бот (заменить эту секцию) -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я работаю на Render 🤖\n\n"
        "Доступные команды:\n"
        "/list — список заметок в корне папки\n"
        "/folders — навигация по папкам (через кнопки)\n"
        "/note <имя> — открыть заметку по имени (в текущей папке/корне)"
    )

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(update.message.text)


# старый /list (оставил как был — показывает .md в корне FOLDER_ID)
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


# команда /note <имя_файла.md> — ищет по имени в текущей (корневой) папке
async def get_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /note <имя_файла.md>")
        return

    filename = " ".join(context.args)
    results = service.files().list(
        q=f"'{FOLDER_ID}' in parents and name='{filename}' and mimeType='text/markdown'",
        fields="files(id, name)"
    ).execute()
    files = results.get('files', [])
    if not files:
        await update.message.reply_text("Такой заметки нет в корне 😢")
        return

    file_id = files[0]['id']
    content = service.files().get_media(fileId=file_id).execute()
    text = content.decode("utf-8")
    if len(text) > 4000:
        await update.message.reply_text(f"📄 {filename} (первые 4000 символов):\n\n{text[:4000]}")
    else:
        await update.message.reply_text(f"📄 {filename}:\n\n{text}")


# --------- Новая навигация по папкам через inline-кнопки ----------
# helper: показать содержимое папки (folder_id). edit=True - редактировать callback сообщение
async def show_folder(update, context, folder_id=None, edit=False):
    if folder_id is None:
        folder_id = FOLDER_ID

    # получаем файлы и подпапки внутри folder_id
    results = service.files().list(
        q=f"'{folder_id}' in parents",
        fields="files(id, name, mimeType, parents)",
        pageSize=1000
    ).execute()
    items = results.get('files', [])

    if not items:
        text = "Папка пуста 😢"
        if edit and update.callback_query:
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return

    keyboard = []
    # кнопки: каждая папка/заметка в отдельной строке
    for it in items:
        if it.get("mimeType") == "application/vnd.google-apps.folder":
            keyboard.append([InlineKeyboardButton(f"📁 {it['name']}", callback_data=f"folder:{it['id']}")])
        elif it.get("mimeType") == "text/markdown" or it['name'].lower().endswith(".md"):
            keyboard.append([InlineKeyboardButton(f"📝 {it['name']}", callback_data=f"note:{it['id']}")])
        else:
            # прочие файлы — можно пропустить или показать как файл
            pass

    # добавим кнопку "Назад", если есть родитель
    if folder_id != FOLDER_ID:
        try:
            meta = service.files().get(fileId=folder_id, fields="parents").execute()
            parents = meta.get("parents", [])
            parent_id = parents[0] if parents else FOLDER_ID
        except Exception:
            parent_id = FOLDER_ID
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"folder:{parent_id}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    if edit and update.callback_query:
        await update.callback_query.edit_message_text("Выбери папку или заметку:", reply_markup=reply_markup)
    else:
        # команда /folders
        await update.message.reply_text("Выбери папку или заметку:", reply_markup=reply_markup)


# показать содержимое заметки по file_id (выбранной из кнопки)
async def show_note_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, file_id: str):
    # получим имя и родителей
    meta = service.files().get(fileId=file_id, fields="name, parents").execute()
    name = meta.get("name", "note.md")
    parents = meta.get("parents", [])
    parent_id = parents[0] if parents else FOLDER_ID

    content = service.files().get_media(fileId=file_id).execute()
    text = content.decode("utf-8")
    if len(text) > 4000:
        text = text[:4000] + "\n\n...✂️ (обрезано)"

    # предложим кнопку "назад в папку"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад к папке", callback_data=f"folder:{parent_id}")]])
    await update.callback_query.message.reply_text(f"📄 {name}:\n\n{text}", reply_markup=kb)


# callback handler для кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("folder:"):
        folder_id = data.split(":", 1)[1]
        await show_folder(update, context, folder_id=folder_id, edit=True)
    elif data.startswith("note:"):
        file_id = data.split(":", 1)[1]
        await show_note_callback(update, context, file_id)
    else:
        await query.edit_message_text("Неизвестная команда.")


# команда /folders — показать содержимое корня (FOLDER_ID)
async def folders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_folder(update, context, folder_id=FOLDER_ID, edit=False)


# ------------------- main (заменить хэндлеры и регистрация) -------------------
def main():
    if not TOKEN:
        raise ValueError("Нет BOT_TOKEN! Добавь его в настройки Render.")
    
    # Запускаем Flask-сервер в фоне для Render (оставляем архитектуру как у тебя)
    thread = Thread(target=run_server)
    thread.start()

    # Настраиваем бота и регистрируем хэндлеры (включая кнопки)
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_notes))
    app.add_handler(CommandHandler("note", get_note))
    app.add_handler(CommandHandler("folders", folders_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    app.run_polling()

if __name__ == "__main__":
    main()
