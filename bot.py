import os
import sys
import logging
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
import uvicorn

# Load environment variables
load_dotenv()

# Enable comprehensive logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Double check that keys exist before trying to use them
if not TELEGRAM_TOKEN:
    logger.critical("FATAL: TELEGRAM_TOKEN environment variable is missing!")
if not GROQ_API_KEY:
    logger.critical("FATAL: GROQ_API_KEY environment variable is missing!")

# Initialize client pointing to Groq's server
try:
    ai_client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=GROQ_API_KEY or "missing_key"
    )
except Exception as e:
    logger.error(f"Failed to initialize Groq client: {e}")

# System prompt profile
SYSTEM_PROMPT = (
    "Act as a professional AI translator and writing assistant. Translate text between different "
    "languages while preserving meaning, tone, and context. Improve grammar, rewrite awkward sentences, "
    "make content more professional or natural, and localize text for native speakers. If I provide "
    "a document, translate the entire document while maintaining formatting. If I provide a message "
    "from a foreign-language client, translate it into English and help me craft a natural response "
    "in their language."
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Welcome! I am your AI Translator & Writing Assistant. Send me text or a file!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await update.message.reply_chat_action("typing")
    try:
        response = ai_client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ]
        )
        await update.message.reply_text(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Translation Error: {e}")
        await update.message.reply_text("❌ An error occurred while translating.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document.mime_type.startswith("text/"):
        await update.message.reply_text("❌ Only text (.txt) files are supported.")
        return
    await update.message.reply_text("📥 Processing document...")
    try:
        tg_file = await context.bot.get_file(document.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        file_content = file_bytes.decode("utf-8")

        response = ai_client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Translate keeping formatting intact:\n\n{file_content}"}
            ]
        )
        await update.message.reply_text(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Document error: {e}")
        await update.message.reply_text("❌ Failed to process document.")

# Dummy web endpoint for Render
async def homepage(request):
    return JSONResponse({"status": "bot is running"})

routes = [Route("/", homepage)]
starlette_app = Starlette(routes=routes)

async def main():
    logger.info("Starting up application setup...")
    
    # Setup Telegram application without hard network checks during build/init
    tg_app = Application.builder().token(TELEGRAM_TOKEN).build()
    tg_app.add_handler(CommandHandler("start", start))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    tg_app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    try:
        logger.info("Initializing Telegram configuration components...")
        await tg_app.initialize()
        await tg_app.start()
        
        logger.info("Starting background polling loop...")
        await tg_app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram Bot polling started successfully!")
    except Exception as telegram_error:
        logger.error(f"CRITICAL ERROR starting Telegram framework: {telegram_error}")
        # Keep the script alive even if telegram network fails briefly so Render doesn't crash loop
        await asyncio.sleep(5)

    # Start the web interface to satisfy Render's port checker binding
    port = int(os.getenv("PORT", 10000))
    logger.info(f"Starting web routing engine on port {port}")
    config = uvicorn.Config(app=starlette_app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as fatal_exception:
        print(f"FATAL SYSTEM FAILURE: {fatal_exception}", file=sys.stderr)
