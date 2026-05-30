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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Enable logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize OpenAI client
ai_client = OpenAI(api_key=OPENAI_API_KEY)

# Define the precise system prompt provided
SYSTEM_PROMPT = (
    "Act as a professional AI translator and writing assistant. Translate text between different "
    "languages while preserving meaning, tone, and context. Improve grammar, rewrite awkward sentences, "
    "make content more professional or natural, and localize text for native speakers. If I provide "
    "a document, translate the entire document while maintaining formatting. If I provide a message "
    "from a foreign-language client, translate it into English and help me craft a natural response "
    "in their language."
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a friendly welcome message when the /start command is issued."""
    await update.message.reply_text(
        "👋 Welcome! I am your Professional AI Translator & Writing Assistant.\n\n"
        "Send me any text, client message, or text document, and I will translate it, "
        "refine its grammar, and help you craft natural responses automatically."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes plain text messages using OpenAI."""
    user_text = update.message.text
    await update.message.reply_chat_action("typing")
    
    try:
        response = ai_client.chat.completions.create(
            model="gpt-4o-mini",  # Budget-friendly, extremely fast, and highly capable
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ]
        )
        translated_text = response.choices[0].message.content
        await update.message.reply_text(translated_text)
    except Exception as e:
        logger.error(f"Error during AI translation: {e}")
        await update.message.reply_text("❌ Sorry, an error occurred while processing your request.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes document files (.txt) sent by the user."""
    document = update.message.document
    
    # Restrict to simple text files for basic processing
    if not document.mime_type.startswith("text/"):
        await update.message.reply_text("❌ Currently, I can only process plain text (.txt) documents.")
        return

    await update.message.reply_text("📥 Processing your document, please wait...")
    await update.message.reply_chat_action("typing")

    try:
        # Download file into memory
        tg_file = await context.bot.get_file(document.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        file_content = file_bytes.decode("utf-8")

        response = ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Translate the following document text while keeping formatting intact:\n\n{file_content}"}
            ]
        )
        translated_text = response.choices[0].message.content
        
        # If the output fits in a single message send it; otherwise save as file
        if len(translated_text) <= 4000:
            await update.message.reply_text(translated_text)
        else:
            out_bytes = bytes(translated_text, "utf-8")
            await update.message.reply_document(document=out_bytes, filename=f"translated_{document.file_name}")

    except Exception as e:
        logger.error(f"Error during document translation: {e}")
        await update.message.reply_text("❌ Failed to process and translate the document.")

# Dummy web server to keep Render Free Tier happy
async def homepage(request):
    return JSONResponse({"status": "bot is running"})

routes = [Route("/", homepage)]
starlette_app = Starlette(routes=routes)

async def main():
    """Initializes and runs the Telegram Bot along with the web framework."""
    # Build the Telegram Bot application
    tg_app = Application.builder().token(TELEGRAM_TOKEN).build()
    tg_app.add_handler(CommandHandler("start", start))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    tg_app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Initialize the engine
    await tg_app.initialize()
    await tg_app.start()
    
    # Run the polling side-by-side with Starlette web server
    asyncio.create_task(tg_app.updater.start_polling())

    # Start the dummy web portal to fulfill Render's network port check
    config = uvicorn.Config(app=starlette_app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)), log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
