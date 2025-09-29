import json
import re
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ------------------- Telegram -------------------
TOKEN = "8459115395:AAE6ahZnNgBTlwYdLjLFND7uG4jbFN2hYPA"

# ------------------- Google Drive -------------------
service_account_info = {
  "type": "service_account",
  "project_id": "telegrambotdrive-473209",
  "private_key_id": "c61483d946d8af724968a5646c0bb0ebaeb7ac7e",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQCwGHUkmRCOOGmZ\nUqzn3qxf/c3Jh16BrQ1eWWPIvW9PptgajTfBuruIQu80ejyK2iByyE6LYDT8e2OS\nZaNGkkViiyLynQHKCF4ewIunk2LOTaLdc6uA+FNSbmcAwnR0iVTyPoawSxOq0WU7\nRbFjHwkPwpvDrZd6G9vrNpKsQHx9O6xiNjx1ctgD8o47as9prdVPwG1swctqsbYw\nztNOpQO1lDXfdx0Ex3bLQ/TUrODq8G6nmnUoidKed8o+3Gli44fI4pD329z2aMvS\n6nXU/fkJfoOhiW0ev3vS+X6Vqmz4wiR4G+vwRMJz3WlSmxqay8bDeeB5jL4SiDuf\n3rK80jg/AgMBAAECggEACPFvtD3IdyCVpFbBjJO6IgnhaJ8Pr/rvlzS8+kCR+vPt\n57NM+0bA0r5rfY5zrVg/QPURSsdxCXLkGgGVauEaKv4GoVb99JpmL/OhZA+lJfW6\nvrpqzFr63aXZD1MmLOud58uVyuA/4x339oGnQkcc47MDdsrwdXVyvshVEfBtzMJP\nIa4hniPRIQdEfGy2tpj6EwOM2R1PYPpn7srwINKWtNzyHQc/gpIHEy8EEZYFIWVX\nRyVlgYhdtHee8/cwezFc8Y9sdIGI7+7RyHD2slq/2t2UUoTKtM/nc5yR9PjNMLcJ\npX+deV6NCQNvN4DTxD6i8/+Q+5U5x6BubW5w+pyhEQKBgQDh64EO+OzwmJFFoBvt\n+w/oMxV38bweFngQsT91rpdhYlsQ9Y9hw/ylgnF4/S8R6UujqhmqVfFhkluy9OIS\nse1V2CjwgBcb5pPUBnPGDRjkgSJu1rV4czgA499d4LwpUSDxAXGfwGQTtkx1FkFe\nPoGffI/c3cJuSSx+DT7+3vNqiQKBgQDHiq99GT4/27+ehOkPRn2sMjUVej2ovkG6\nvL5KSV2i+4pyD9KDPzz8ubOLW6afB8/dcChdyahRtExwPCXWn5c+0RWq7woZBF1V\ny3uzf+S0hUZ6rAcCn0dC39Hi2cqw9o2PT37D/ymk5zfeS0TLRsycwT8cDmDOoaDO\nbYJq5UI6hwKBgCe6p45/fgNtgRaSanb2ULzPxvW54BAWeXTOBs/mLR7mEgewd0+F\nDLf6cYQKWi23LiMQ9cR7qqAzAcc9w0fwXEFdaw2oKOgyK0r8+30Xron4n5qITY9q\nC640ZIJ40/4cE0PushGa3r6Mr3Njv4kYSulGGXKI2PlWCun74Fkn0fypAoGAb0Tt\noMOvy6o9SybwUz1KnPgOU+Cre2pEet3++qu4lEbSJ9Kc3+UmnALtlLtRyYJwrhl5\n2Pq3aoAw07EmpGyvyS6Md5n+Nn8RkOL8ItchcGyVJZjB+/tXoHnwryAlf9Ksk4qP\ntLmXvkXVCJdOUFA1jv/PslRuNSs54YJ9ZCBdcwcCgYBVE7twWSc8Ks6NIrTqmC1b\nqt8f37V91tK/Be81bvPRhaGE9PrViVupTN4uBa7zL4JL/z7UBcyKwHAf2A/c5tKK\nRxt9WpJP8DuLvF5SCasHq2AScZeezn6BDJiJ1yzppc7lY+MRiqUcMswQI3o2DRIQ\nh0UPSXEXcIdo2babwVcTgA==\n-----END PRIVATE KEY-----\n",
  "client_email": "bot-service-account@telegrambotdrive-473209.iam.gserviceaccount.com",
  "client_id": "109503940276287525867",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/bot-service-account%40telegrambotdrive-473209.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}

# Фикс переносов строк в приватном ключе
service_account_info["private_key"] = service_account_info["private_key"].replace("\\n", "\n")

SCOPES = ['https://www.googleapis.com/auth/drive']
FOLDER_ID = '1nQECNPbttj32SnAhpdBjwWuYWJUUxtto'

credentials = service_account.Credentials.from_service_account_info(
    service_account_info, scopes=SCOPES
)
service = build('drive', 'v3', credentials=credentials)

# ------------------- Работа с Drive -------------------
def get_all_files(folder_id=FOLDER_ID):
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

folder_parents = {}
# ------------------- Бот -------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📂 Навигация по папкам", callback_data="folders")],
        [InlineKeyboardButton("🔍 Поиск по номеру", callback_data="search")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)


async def start_buttons_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "folders":
        await list_folders(query, context, FOLDER_ID)

    elif query.data == "search":
        context.user_data["search_mode"] = True
        keyboard = [[InlineKeyboardButton("⬅️ Назад в меню", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Введите номер заметки:", reply_markup=reply_markup)

    elif query.data == "back_to_menu":
        keyboard = [
            [InlineKeyboardButton("📂 Навигация по папкам", callback_data="folders")],
            [InlineKeyboardButton("🔍 Поиск по номеру", callback_data="search")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Главное меню:", reply_markup=reply_markup)


async def list_folders(query, context, folder_id):
    results = service.files().list(
        q=f"'{folder_id}' in parents",
        fields="files(id, name, mimeType)"
    ).execute()

    files = results.get('files', [])
    folders = [f for f in files if f['mimeType'] == 'application/vnd.google-apps.folder']
    notes = [f for f in files if f['mimeType'] != 'application/vnd.google-apps.folder']

    keyboard = []
    for folder in folders:
        folder_parents[folder["id"]] = folder_id
        keyboard.append([InlineKeyboardButton(f"📁 {folder['name']}", callback_data=f"folder_{folder['id']}")])

    for note in notes:
        keyboard.append([InlineKeyboardButton(note['name'], callback_data=f"note_{note['id']}")])

    if folder_id != FOLDER_ID:
        parent_id = folder_parents.get(folder_id, FOLDER_ID)
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"folder_{parent_id}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Выберите папку или заметку:", reply_markup=reply_markup)


async def folder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    folder_id = query.data.split("_")[1]
    await list_folders(query, context, folder_id)


async def note_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    file_id = query.data.split("_")[1]
    file = service.files().get(fileId=file_id, fields="id, name, mimeType").execute()
    file_data = service.files().get_media(fileId=file_id).execute()

    if file["mimeType"].startswith("image/"):
        await query.message.reply_photo(BytesIO(file_data), caption=file["name"])
    else:
        text = file_data.decode("utf-8", errors="ignore")
        await query.message.reply_text(f"📝 {file['name']}\n\n{text}")

    # Добавляем кнопку назад
    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data=f"folder_{folder_parents.get(file_id, FOLDER_ID)}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Выберите действие:", reply_markup=reply_markup)


async def search_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("search_mode"):
        return

    text = update.message.text.strip()
    match = re.search(r"\d+", text)
    if not match:
        keyboard = [
            [InlineKeyboardButton("🔍 Ввести номер снова", callback_data="search")],
            [InlineKeyboardButton("⬅️ Назад в меню", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("❌ Неверный ввод. Введите число:", reply_markup=reply_markup)
        return

    number = match.group(0)
    files = get_all_files()
    found = None
    for f in files:
        if number in f["name"]:
            found = f
            break

    if not found:
        keyboard = [
            [InlineKeyboardButton("🔍 Ввести номер снова", callback_data="search")],
            [InlineKeyboardButton("⬅️ Назад в меню", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("❌ Заметка не найдена.", reply_markup=reply_markup)
        return

    file_data = service.files().get_media(fileId=found["id"]).execute()
    if found["mimeType"].startswith("image/"):
        await update.message.reply_photo(BytesIO(file_data), caption=found["name"])
    else:
        text = file_data.decode("utf-8", errors="ignore")
        await update.message.reply_text(f"📝 {found['name']}\n\n{text}")

    # Кнопки после поиска
    keyboard = [
        [InlineKeyboardButton("🔍 Ввести номер снова", callback_data="search")],
        [InlineKeyboardButton("⬅️ Назад в меню", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)


# ------------------- Запуск -------------------

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(start_buttons_callback, pattern="^(folders|search|back_to_menu)$"))
    app.add_handler(CallbackQueryHandler(folder_callback, pattern="^folder_"))
    app.add_handler(CallbackQueryHandler(note_callback, pattern="^note_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_message))

    app.run_polling()


if __name__ == "__main__":
    main()
