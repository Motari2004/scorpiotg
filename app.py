import logging
import os
import threading
from flask import Flask
from google import genai
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# 1. Setup Logging
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# 2. Flask Web Server for Render Port Binding
web_app = Flask(__name__)

@web_app.route('/')
def health_check():
    return "Bot is running!", 200

def run_flask():
    # Render provides the port via environment variable
    port = int(os.getenv("PORT", 10000))
    web_app.run(host='0.0.0.0', port=port)

# SECURITY & KEYS
AUTHORIZED_USER_ID = int(os.getenv('AUTHORIZED_USER_ID', '6373322579'))
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

client = genai.Client(api_key=GEMINI_API_KEY)

chat_memories = {}

def is_authorized(user_id):
    return user_id == AUTHORIZED_USER_ID

def record_message(user_id, message_id):
    if user_id not in chat_memories:
        chat_memories[user_id] = []
    chat_memories[user_id].append(message_id)

# --- COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id): return
    msg = await update.message.reply_text(
        "🚀 **HOPEFREY CLOUD BRIDGE**\n\n"
        "Commands:\n"
        "• `start ai` / `stop ai` - Toggle Gemini\n"
        "• `clear` - Wipe chat history"
    )
    record_message(update.effective_user.id, update.message.message_id)
    record_message(update.effective_user.id, msg.message_id)

# --- MESSAGE HANDLER ---
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id): return

    user_text = update.message.text.lower().strip()
    record_message(user_id, update.message.message_id)

    if user_text == "clear":
        if user_id in chat_memories:
            for msg_id in chat_memories[user_id]:
                try:
                    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
                except:
                    pass
            chat_memories[user_id] = [] 
        return

    if user_text == "start ai":
        context.user_data['ai_active'] = True
        msg = await update.message.reply_text("🤖 AI Activated.")
        record_message(user_id, msg.message_id)
        return
    
    if user_text == "stop ai":
        context.user_data['ai_active'] = False
        msg = await update.message.reply_text("💤 AI Deactivated.")
        record_message(user_id, msg.message_id)
        return

    if context.user_data.get('ai_active'):
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        try:
            # Note: 429 errors usually mean the Free API quota is hit. 
            response = client.models.generate_content(model="gemini-2.5-flash", contents=update.message.text)
            msg = await update.message.reply_text(response.text)
            record_message(user_id, msg.message_id)
        except Exception as e:
            await update.message.reply_text(f"❌ AI Error: {str(e)}")
    else:
        print(f"BRIDGE LOG: {update.message.text}")
        msg = await update.message.reply_text(f"✅ Bridge: {update.message.text}")
        record_message(user_id, msg.message_id)

if __name__ == '__main__':
    # Start Flask in a background thread
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Start Telegram Bot
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_messages))
    
    print("🚀 Cloud Bridge with Port Binding is running...")
    app.run_polling()