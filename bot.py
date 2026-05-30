import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI
import asyncio
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
import uvicorn

# Load environment variables
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Enable logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize client pointing to Groq's server
ai_client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY
)

# Your precise system instruction
SYSTEM_PROMPT = (
    "Act as a professional AI translator and writing assistant. Translate text between different "
    "languages while preserving meaning, tone, and context. Improve grammar, rewrite awkward sentences, "
    "make content more professional or natural, and localize text for native speakers. If I provide "
    "a document, translate the entire document while maintaining formatting. If I provide a message "
    "from a foreign-language client, translate it into English and help me craft a natural response "
    "in their language."
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome! I am your AI Translator & Writing Assistant.\n\n"
        "Send me any text, client message, or text document, and I will handle it perfectly."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await update.message.reply_chat_action("typing")
    
    try:
        response = ai_client.chat.completions.create(
            model="llama3-8b-8192",  # Ultra-fast, great at multilingual translation
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ]
        )
        translated_text = response.choices[0].message.content
        await update.message.reply_text(translated_text)
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Sorry, an error occurred while translating.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document.mime_type.startswith("text/"):
        await update.message.reply_text("❌ Currently, I can only process plain text (.txt) documents.")
        return

    await update.message.reply_text("📥 Processing document...")
    await update.message.reply_chat_action("typing")

    try:
        tg_file = await context.bot.get_file(document.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        file_content = file_bytes.decode("utf-8")

        response = ai_client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Translate this keeping formatting intact:\n\n{file_content}"}
            ]
        )
        translated_text = response.choices[0].message.content
        
        if len(translated_text) <= 4000:
            await update.message.reply_text(translated_text)
        else:
            out_bytes = bytes(translated_text, "utf-8")
            await update.message.reply_document(document=out_bytes, filename=f"translated_{document.file_name}")
    except Exception as e:
        logger.error(f"Document error: {e}")
        await update.message.reply_text("❌ Failed to process document.")

async def homepage(request):
    return JSONResponse({"status": "bot is running"})

routes = [Route("/", homepage)]
starlette_app = Starlette(routes=routes)

async def main():
    # Adding a pool_timeout and read_timeout gives the bot more time to connect on slow networks
    tg_app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .pool_timeout(30.0)
        .read_timeout(30.0)
        .build()
    )
    
    tg_app.add_handler(CommandHandler("start", start))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    tg_app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Initialize the engine
    logger.info("Initializing Telegram Bot...")
    await tg_app.initialize()
    await tg_app.start()
    
    logger.info("Bot initialized successfully. Starting polling...")
    asyncio.create_task(tg_app.updater.start_polling())

    config = uvicorn.Config(app=starlette_app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)), log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
