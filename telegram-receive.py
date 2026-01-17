from telegram import Update
from telegram.ext import Application, MessageHandler, filters
from datetime import datetime

async def handle_message(update: Update, context):
 print(f"Date: {datetime.now().isoformat()} | Message: {update.message.text}")

app = Application.builder().token("8260318130:AAFRgs3DSJURYibfsKasCY0pcbkMnzE415M").build()
app.add_handler(MessageHandler(filters.TEXT, handle_message))
app.run_polling()
