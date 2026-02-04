import logging
import os
import threading
import datetime
import time
from flask import Flask
from google import genai
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# 1. Setup Logging
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# 2. Flask Web Server for Render
web_app = Flask(__name__)

@web_app.route('/')
def health_check():
    return "Cloud Bridge Online", 200

def run_flask():
    port = int(os.getenv("PORT", 10000))
    web_app.run(host='0.0.0.0', port=port)

# --- INTERNAL HEARTBEAT ---
def internal_heartbeat():
    while True:
        logging.info("💓 SYSTEM HEARTBEAT: Bot is active and polling...")
        time.sleep(60)

# --- SECURE KEY ROTATION LOGIC ---
RAW_KEYS = os.getenv('GEMINI_KEYS', '')
GEMINI_KEYS = [k.strip() for k in RAW_KEYS.split(',') if k.strip()]
current_key_index = 0

def get_gemini_client():
    global current_key_index
    if not GEMINI_KEYS:
        logging.error("❌ No GEMINI_KEYS found in Environment Variables!")
        return None
    key = GEMINI_KEYS[current_key_index]
    return genai.Client(api_key=key)

client = get_gemini_client()

# TOKEN & AUTH
AUTHORIZED_USER_ID = int(os.getenv('AUTHORIZED_USER_ID', '6373322579'))
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

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
    num_keys = len(GEMINI_KEYS)
    await update.message.reply_text(
        "🚀 **HOPEFREY CLOUD BRIDGE**\n\n"
        f"✅ System: Online\n"
        f"🔑 Keys Loaded: {num_keys}\n\n"
        "Commands:\n"
        "• `start ai` / `stop ai` - Toggle Gemini\n"
        "• `clear` - Wipe chat history\n"
        "• `.ping` - Manual status check"
    )

# --- MESSAGE HANDLER ---
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global client, current_key_index
    user_id = update.effective_user.id
    if not is_authorized(user_id): return

    user_text = update.message.text.lower().strip()
    record_message(user_id, update.message.message_id)

    # Manual Ping Endpoint inside Telegram
    if user_text == ".ping":
        await update.message.reply_text(f"🏓 **PONG**\nTime: {datetime.datetime.now().strftime('%H:%M:%S')}")
        return

    if user_text == "clear":
        if user_id in chat_memories:
            for msg_id in chat_memories[user_id]:
                try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
                except: pass
            chat_memories[user_id] = [] 
        return

    if user_text in ["start ai", "stop ai"]:
        context.user_data['ai_active'] = (user_text == "start ai")
        msg = await update.message.reply_text("🤖 AI Activated." if user_text == "start ai" else "💤 AI Deactivated.")
        record_message(user_id, msg.message_id)
        return

    if context.user_data.get('ai_active'):
        if not client:
            await update.message.reply_text("❌ Configuration Error: No API keys found.")
            return

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        for _ in range(len(GEMINI_KEYS)):
            try:
                response = client.models.generate_content(model="gemini-2.5-flash", contents=update.message.text)
                msg = await update.message.reply_text(response.text)
                record_message(user_id, msg.message_id)
                return
            except Exception as e:
                if "429" in str(e):
                    logging.warning(f"Key {current_key_index} hit rate limit. Rotating...")
                    current_key_index = (current_key_index + 1) % len(GEMINI_KEYS)
                    client = get_gemini_client()
                    continue
                else:
                    await update.message.reply_text(f"❌ AI Error: {str(e)}")
                    return
        
        await update.message.reply_text("⚠️ All keys are rate-limited. Try again in a minute.")
    else:
        msg = await update.message.reply_text(f"✅ Bridge: {update.message.text}")
        record_message(user_id, msg.message_id)

if __name__ == '__main__':
    # Flask (External Ping)
    threading.Thread(target=run_flask, daemon=True).start()
    # Heartbeat (Internal Ping)
    threading.Thread(target=internal_heartbeat, daemon=True).start()
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_messages))
    
    logging.info("--- SYSTEM ONLINE ---")
    app.run_polling(drop_pending_updates=True)