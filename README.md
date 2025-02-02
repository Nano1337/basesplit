# BaseSplit

BaseSplit is a smart bill-splitting tool that streamlines the process of sharing expenses with friends. Simply snap a photo of your physical bill, send it through iMessage, and BaseSplit automatically processes the image to generate and send cryptocurrency payment requests to your friends. With its automated workflow and crypto integration, BaseSplit makes splitting bills hassle-free and modern.



## How it works

This project implements a Telegram bot that processes receipt images. Users can send an image of a receipt to the bot, which then uses OpenAI's vision capabilities (via LangChain) to extract receipt details. After verifying the details with the user, the bot provides an option to split the payment evenly among participants and generate a MetaMask-compatible payment link (EIP-681 format) on the Base Sepolia network.


## Features

- **Receipt Processing:**  
  Upload a receipt image and let the bot analyze it using an OpenAI-powered API. The bot extracts key details such as:
  - Merchant name
  - Transaction date
  - Total amount
  - Tax amount
  - Currency
  - List of items purchased

- **User Confirmation:**  
  After processing, users can confirm if the extracted details are correct using inline buttons. If the details aren’t accurate, the bot prompts for a new image upload.

- **Payment Splitting:**  
  Once confirmed, users can choose to split the bill evenly. The bot calculates each participant’s share in ETH (by converting from USD based on the price feed) and creates an EIP-681 (MetaMask universal) deep link for payment requests.

- **Extensibility:**  
  Although the "custom split" feature is noted as under development, the structure allows easy integration of additional splitting methods.

- **Resilient Operations:**  
  Uses the `tenacity` library to perform retryable API calls (both for image downloads and for calling the OpenAI API), ensuring robustness against transient network or API-related issues.

---

## Project Structure

- **telegram_bot.py**  
  Contains the main bot logic including command handlers, conversation handlers, and inline keyboard interactions. It also performs wallet address confirmation and calculates payment splits.

- **parse_receipt.py**  
  Handles receipt image downloading, MIME type detection, image base64 encoding, and sending the image to the OpenAI API for text extraction using LangChain with a structured JSON response.

## Setup

1. We use `uv` as the dependency manager. If you don't have it installed, you can install it with `brew install uv` or other ways following the instructions [here](https://docs.astral.sh/uv/).

2. Run `uv sync` to get started

3. Activate the virtual env. On mac/ubuntu run `source .venv/bin/activate` and on windows run `.\.venv\Scripts\activate`


## Environment Variables

Create a `.env` file in the project root directory with the following environment variables:

```dotenv
# Telegram Bot Token from BotFather
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# CDP Agentkit API settings
CDP_API_KEY_NAME=your_cdp_api_key_name_here
CDP_API_KEY_PRIVATE_KEY=your_cdp_api_key_private_key_here

# OpenAI API Key for receipt processing
OPENAI_API_KEY=your_openai_api_key_here
```

Ensure that the tokens and API keys are kept secure and are **not** committed to version control.

---

## Running the Bot

1. **Start the Bot:**

   Run the following command from the project root:

   ```bash
   python telegram_bot.py
   ```

2. **Interact with the Bot on Telegram:**

   - Open Telegram and search for your bot using its username or use the link `t.me/basesplit_bot`.
   - Start the conversation with the `/start` command.
   - Follow the instructions:
     - Upload a receipt image.
     - Confirm the extracted details.
     - Choose the payment splitting option (even split).
     - Receive a payment request link with instructions to share via MetaMask.

---

## Dependencies & Technologies

- **[python-telegram-bot](https://python-telegram-bot.org/):**  
  Used for interacting with the Telegram Bot API and handling commands, messages, and callback queries.

- **[requests](https://docs.python-requests.org):**  
  For HTTP requests, particularly for downloading receipt images.

- **[LangChain](https://langchain.readthedocs.io):**  
  Facilitates the integration with OpenAI's API for processing receipt images.

- **[openai](https://beta.openai.com/docs/):**  
  Provides the API for analyzing image content and returning structured data.

- **[tenacity](https://tenacity.readthedocs.io):**  
  Implements retry logic for robust API and network operations.

- **[Web3.py](https://web3py.readthedocs.io):**  
  Used for Ethereum address handling and converting ETH values; essential for generating payment links.

- **[CDP Agentkit](https://github.com/cdp-langchain/cdp-agentkit):**  
  Contains additional components for transfer APIs and price feed fetching, integrated into the bot.


## Contributing

Contributions are welcome! Please fork the repository and submit pull requests for any issues or feature enhancements. For major changes, please open an issue first to discuss what you would like to change.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---
