import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    CallbackContext, filters, ConversationHandler
)
from parse_receipt import process_receipt
from dotenv import load_dotenv
import urllib.parse  # Ensure this import is at the top of your file
from web3 import Web3

# Import CDP agentkit components for the transfer API.
from cdp_langchain.agent_toolkits import CdpToolkit
from cdp_langchain.utils import CdpAgentkitWrapper
from cdp_agentkit_core.actions.pyth.fetch_price_feed_id import pyth_fetch_price_feed_id
from cdp_agentkit_core.actions.pyth.fetch_price import pyth_fetch_price

"""
Loading environment variables
"""

# Load environment variables from .env file.
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Please set the TELEGRAM_BOT_TOKEN environment variable.")

# Load CDP_API_KEY_NAME from environment and pass it to the wrapper.
cdp_api_key_name = os.getenv("CDP_API_KEY_NAME")
if not cdp_api_key_name:
    raise ValueError("Please set the CDP_API_KEY_NAME environment variable.")

# Load CDP_API_KEY_PRIVATE_KEY from environment and pass it to the wrapper.
cdp_api_key_private_key = os.getenv("CDP_API_KEY_PRIVATE_KEY")
if not cdp_api_key_private_key:
    raise ValueError("Please set the CDP_API_KEY_PRIVATE_KEY environment variable.")

"""
CDP Agentkit Wrapper Setup
"""

# Instantiate the CDP agentkit wrapper with the API key name.
cdp = CdpAgentkitWrapper(cdp_api_key_name=cdp_api_key_name, cdp_api_key_private_key=cdp_api_key_private_key)
toolkit = CdpToolkit.from_cdp_agentkit_wrapper(cdp)

"""
Logging Setup
"""

# Set up logging for debugging purposes
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

"""
Conversation States
"""

# Define conversation states for even split (only three states now)
SPLIT_EVEN_WALLET, SPLIT_EVEN_CONFIRM, SPLIT_EVEN_NUMBER = range(1, 4)

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

        # Save receipt total for later calculations.
        context.user_data["receipt_total"] = receipt_data.get("total", 0)

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
    """
    query = update.callback_query
    await query.answer()  # Acknowledge the callback query

    data = query.data
    # If split handler data is present, do nothing here so that the dedicated handlers take over.
    if data in ("split_even", "split_custom"):
        return

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
    else:
        await query.edit_message_text("Unknown action.")

async def split_custom_handler(update: Update, context: CallbackContext) -> None:
    """
    Handler for the custom-split inline button.
    For now, simply informs the user that the feature is under development.
    """
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Split custom feature is still being developed.")

# --- Split Even Conversation Handlers ---

async def split_even_entry(update: Update, context: CallbackContext) -> int:
    """
    Entry point for even split when "Even" is selected.
    Prompts the user for their base wallet address.
    """
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Please enter your base wallet address (the wallet that will receive the funds):")
    return SPLIT_EVEN_WALLET

async def split_even_wallet_handler(update: Update, context: CallbackContext) -> int:
    """
    Captures the wallet address and then asks the user to confirm it.
    """
    wallet_address = update.message.text.strip()
    context.user_data["wallet_address"] = wallet_address
    keyboard = [
        [
            InlineKeyboardButton("Yes", callback_data="wallet_yes"),
            InlineKeyboardButton("No", callback_data="wallet_no")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"Is this the correct wallet address: {wallet_address}?",
        reply_markup=reply_markup
    )
    return SPLIT_EVEN_CONFIRM

async def split_even_wallet_confirm_handler(update: Update, context: CallbackContext) -> int:
    """
    Processes the wallet confirmation. If confirmed, requests the number of contacts
    to share the payment request with.
    """
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "wallet_yes":
        await query.edit_message_text(f"Wallet address confirmed: {context.user_data['wallet_address']}")
        # Send a new prompt asking for the number of participants:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Please enter the number of participants (other than you) to split the bill with:"
        )
        return SPLIT_EVEN_NUMBER
    elif data == "wallet_no":
        await query.edit_message_text("Please re-enter your base wallet address:")
        return SPLIT_EVEN_WALLET

def create_link(recipient: str, chain_id: int, value_in_wei: float) -> str:
    """
    Create an EIP-681 link with full precision for the ETH value.
    This version avoids rounding by using fixed-point notation.
    """
    # Convert the float to a string in fixed-point notation.
    value_str = format(value_in_wei, 'f')
    # Optionally remove any trailing zeros and the decimal point if not needed.
    if "." in value_str:
        value_str = value_str.rstrip("0").rstrip(".")
    return f"send/pay-{recipient}@{chain_id}?value={value_str}"

async def split_even_number_handler(update: Update, context: CallbackContext) -> int:
    try:
        num = int(update.message.text.strip()) + 1 # add 1 for the person who is paying
        base_wallet = Web3.to_checksum_address(context.user_data["wallet_address"])

        # Convert dollars to ETH to Wei
        each_person_dollars = float(context.user_data["receipt_total"] / num)

        feed_id = pyth_fetch_price_feed_id("eth")
        price = pyth_fetch_price(feed_id)
        price = float(price)

        eth_amount = float(each_person_dollars / price)
        context.user_data["eth_amount"] = eth_amount  # Store eth_amount for later use
        each_person_wei = float(eth_amount * 1e18)

        rest_of_uri = create_link(
            recipient=base_wallet,
            chain_id=84532,  # Base Sepolia
            value_in_wei=each_person_wei
        )
        
        # Create MetaMask universal link
        metamask_link = f"https://metamask.app.link/{rest_of_uri}"
        print("Generated Link:", metamask_link)
        
        # Construct a share message and build a Telegram share URL.
        share_text = f"Please complete the payment by clicking the link: {metamask_link}"
        telegram_share_url = (
            "https://t.me/share/url?"
            "url=" + urllib.parse.quote(metamask_link) +
            "&text=" + urllib.parse.quote(share_text)
        )
        
        # Create an inline keyboard with both "Pay Now" and "Share Payment Request" buttons.
        keyboard = [
            [
                InlineKeyboardButton("Share Payment Request", url=telegram_share_url)
            ]
        ]
        
        # Send the message
        await update.message.reply_text(
            f"Requesting {eth_amount} ETH ({each_person_dollars} USD) on Base Sepolia:\n"
            "Tap below to share the request with others:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")
        return ConversationHandler.END

async def prompt_for_image(update: Update, context: CallbackContext) -> None:
    """
    Default text handler prior to image upload.
    If the user sends any text before uploading an image, prompt them to send the receipt image.
    """
    await update.message.reply_text("Please upload an image of the receipt.")

async def send_share_link(update: Update, context: CallbackContext) -> None:
    """
    Constructs a Telegram share link that, when clicked, allows the user to send
    a pre-filled message containing the MetaMask transaction link to their friends.
    """
    base_wallet = context.user_data.get("wallet_address", "0xYourWalletAddress")
    
    # Retrieve the eth_amount that was stored earlier.
    share_amount = context.user_data.get("eth_amount")
    if share_amount is None:
         await update.message.reply_text("Error: Payment amount data not found.")
         return

    # Construct the MetaMask deep link.
    metamask_link = f"metamask://pay/?address={base_wallet}&amount={share_amount:.6f}&chain=ethereum"

    # Create the text that will appear in the shared message.
    share_text = f"Please complete the payment by clicking the link: {metamask_link}"

    # Build the Telegram share URL (URL-encoded)
    telegram_share_url = (
        "https://t.me/share/url?"
        "url=" + urllib.parse.quote(metamask_link) +
        "&text=" + urllib.parse.quote(share_text)
    )

    # Create the share button as an inline keyboard.
    keyboard = [
        [InlineKeyboardButton("Share Payment Request", url=telegram_share_url)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send the message with the share button.
    await update.message.reply_text(
        "To request payment from your friend, click the button below and choose the contact:",
        reply_markup=reply_markup
    )

def main() -> None:
    """
    Main function that sets up the bot, registers handlers, and starts polling updates.
    """
    application = Application.builder().token(BOT_TOKEN).build()

    # Conversation handler for the split even flow.
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(split_even_entry, pattern="^split_even$")],
        states={
            SPLIT_EVEN_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND, split_even_wallet_handler)],
            SPLIT_EVEN_CONFIRM: [CallbackQueryHandler(split_even_wallet_confirm_handler, pattern="^(wallet_yes|wallet_no)$")],
            SPLIT_EVEN_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, split_even_number_handler)]
        },
        fallbacks=[],
        allow_reentry=True,
    )
    # Ensure conversation handler is added first.
    application.add_handler(conv_handler)

    # Then register the command, photo, and callback query handlers.
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.PHOTO, handle_receipt))
    application.add_handler(CallbackQueryHandler(handle_confirmation_callback, pattern="^(?!split_even|split_custom|wallet_).*$"))
    application.add_handler(CallbackQueryHandler(split_custom_handler, pattern="^split_custom$"))
    
    # Instead of echoing text, prompt the user to upload an image if no conversation is active.
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, prompt_for_image))

    # Run the bot until you press Ctrl-C.
    application.run_polling()

if __name__ == '__main__':
    main()