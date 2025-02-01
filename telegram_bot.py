import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, CallbackContext, filters
from parse_receipt import process_receipt
from dotenv import load_dotenv

# Load environment variables from .env file (if you use one)
load_dotenv()
# The Telegram bot token should be stored in an environment variable for safety.
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Please set the TELEGRAM_BOT_TOKEN environment variable.")

# Set up logging for debugging purposes
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: CallbackContext) -> None:
    """
    Handler for the /start command. Sends a welcome message with instruction to upload a receipt image.
    """
    await update.message.reply_text("Welcome! Please upload an image of the receipt.")

async def echo(update: Update, context: CallbackContext) -> None:
    """
    Handler for echoing text messages. Wraps text in bold HTML.
    """
    await update.message.reply_text(
        f"<b>{update.message.text}</b>",
        parse_mode=ParseMode.HTML
    )

async def handle_receipt(update: Update, context: CallbackContext) -> None:
    """
    Handler for processing messages that contain photos.
    Extracts the highest quality image from the message, builds a file URL using
    Telegram's file API, and then calls process_receipt() to process the receipt.
    If the receipt is valid (receipt_data["is_receipt"] is True), it sends
    the receipt details along with two inline buttons:
      - "Yes this is correct" and "No reupload image."
    """
    user = update.message.from_user
    chat_id = update.message.chat_id
    logger.info("Received a message from %s", user.first_name)

    photos = update.message.photo
    if not photos:
        await update.message.reply_text("No image found. Please send a receipt picture.")
        return

    # Get the best (largest) photo; the list is sorted by increasing size.
    photo = photos[-1]
    file_obj = await context.bot.get_file(photo.file_id)
    file_path = file_obj.file_path

    # If file_path already starts with "http", then it's a full URL already.
    if file_path.startswith("http"):
        file_url = file_path
    else:
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    
    logger.info("Processing image: %s", file_url)

    try:
        receipt_data = process_receipt(file_url)
        if not receipt_data.get("is_receipt", False):
            await update.message.reply_text("This image does not seem to be a valid receipt. Please send a valid receipt image.")
            return

        response_msg = (
            f"Receipt processed:\n"
            f"Merchant: {receipt_data.get('merchant', 'N/A')}\n"
            f"Date: {receipt_data.get('date', 'N/A')}\n"
            f"Total: {receipt_data.get('total', 'N/A')} {receipt_data.get('currency', '')}\n"
            f"Tax: {receipt_data.get('tax', 'N/A')}\n"
            f"Items: {len(receipt_data.get('items', []))} items listed\n\n"
            "Is this correct?"
        )
        
        # Create inline keyboard with Yes and No options
        keyboard = [
            [
                InlineKeyboardButton("Yes this is correct", callback_data="receipt_yes"),
                InlineKeyboardButton("No reupload image", callback_data="receipt_no")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(response_msg, reply_markup=reply_markup)

    except Exception as e:
        logger.exception("Error processing the receipt")
        await update.message.reply_text(f"Error processing receipt: {str(e)}")

async def handle_confirmation_callback(update: Update, context: CallbackContext) -> None:
    """
    Handles callback queries from inline buttons.
    
    - If the user clicks "No reupload image", the bot prompts them to send a new image.
    - If the user clicks "Yes this is correct", a second inline keyboard is shown with two buttons:
         "Even" and "Custom".
    - If the user then selects one of these options, responds with "Got to this point".
    """
    query = update.callback_query
    await query.answer()  # Acknowledge the callback query

    data = query.data
    if data == "receipt_no":
        # User indicates receipt is not correct, prompt reupload.
        await query.edit_message_text("Please send a new receipt image.")
    elif data == "receipt_yes":
        # Receipt confirmed as correct; now offer splitting options.
        keyboard = [
            [
                InlineKeyboardButton("Even", callback_data="split_even"),
                InlineKeyboardButton("Custom", callback_data="split_custom")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Receipt confirmed. How do you want to split?", reply_markup=reply_markup)
    elif data in ("split_even", "split_custom"):
        # Further logic will follow here.
        await query.edit_message_text("Got to this point")
    else:
        await query.edit_message_text("Unknown action.")

def handle_text(update: Update, context: CallbackContext) -> None:
    """
    Handle text messages that do not contain a photo.
    """
    update.message.reply_text("Please send a receipt image instead of text.")

def main() -> None:
    """
    Main function that sets up the bot using the new Application style,
    registers the handlers, and starts polling updates.
    """
    # Replace "<YOUR_BOT_TOKEN_HERE>" with your bot token.
    application = Application.builder().token(BOT_TOKEN).build()

    # Register command, message, and callback query handlers using the new async style callbacks.
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    application.add_handler(MessageHandler(filters.PHOTO, handle_receipt))
    application.add_handler(CallbackQueryHandler(handle_confirmation_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Run the bot until you press Ctrl-C
    application.run_polling()

if __name__ == '__main__':
    main()