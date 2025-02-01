import requests
import os
import base64
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage
import json
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from openai import APIError, APIConnectionError, RateLimitError
from tenacity import RetryError
import logging
from langchain.output_parsers import StructuredOutputParser, ResponseSchema
import re

# Updated expected schema to include receipt validation information.
response_schemas = [
    ResponseSchema(
        name="is_receipt",
        type="boolean",
        description="Indicates if the provided image is a valid receipt. True if valid; false otherwise."
    ),
    ResponseSchema(
        name="merchant",
        type="string",
        description="Merchant/store name (only provided if is_receipt is true)."
    ),
    ResponseSchema(
        name="date",
        type="string",
        description="Date of transaction in YYYY-MM-DD format (only provided if is_receipt is true)."
    ),
    ResponseSchema(
        name="total",
        type="number",
        description="Total amount (only provided if is_receipt is true)."
    ),
    ResponseSchema(
        name="tax",
        type="number",
        description="Tax amount (only provided if is_receipt is true)."
    ),
    ResponseSchema(
        name="currency",
        type="string",
        description="Currency (e.g. USD) (only provided if is_receipt is true)."
    ),
    ResponseSchema(
        name="items",
        type="list",
        description=(
            "List of items (only provided if is_receipt is true). Each item is an object that contains "
            "the item name (string), price (number), and quantity (integer)."
        )
    ),
    ResponseSchema(
        name="message",
        type="string",
        description="Only present if is_receipt is false. Prompt to provide valid receipt. Otherwise should be omitted."
    ),
]

output_parser = StructuredOutputParser.from_response_schemas(response_schemas)

@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    retry=(
        retry_if_exception_type(APIError) |
        retry_if_exception_type(APIConnectionError) |
        retry_if_exception_type(requests.exceptions.RequestException)
    )
)
def download_image_with_retry(image_url: str):
    print(f"Attempting download: {image_url}")
    response = requests.get(image_url, timeout=10)
    response.raise_for_status()
    return response

@retry(
    wait=wait_exponential(multiplier=1, min=2, max=20),
    stop=stop_after_attempt(5),
    retry=(
        retry_if_exception_type(APIError) |
        retry_if_exception_type(APIConnectionError) |
        retry_if_exception_type(RateLimitError) |
        retry_if_exception_type(json.JSONDecodeError)
    )
)
def call_openai_with_retry(llm, messages):
    print("Attempting OpenAI API call")
    result = llm.invoke(messages)
    print("Raw response:", repr(result.content))
    return result

def extract_json(text: str) -> str:
    """
    Extracts JSON from text that might be wrapped in markdown code blocks.
    """
    # More robust pattern to handle different markdown variations
    pattern = r"```(?:json)?[\s]*({.*})[\s]*```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()

def process_receipt(image_url: str) -> dict:
    """Process receipt image through OpenAI Vision API in JSON mode.
    
    The output is forced to always include:
      - "is_receipt": boolean
      - "merchant": string or None
      - "date": string or None
      - "total": number or None
      - "tax": number or None
      - "currency": string or None
      - "items": list
      - "message": string (only when is_receipt is False)
    """
    try:
        print(f"\nDownloading image from {image_url}")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
        }
        response = requests.get(image_url, headers=headers, timeout=15)
        response.raise_for_status()
        
        print(f"Image downloaded ({len(response.content)} bytes)")
        print(f"First 16 bytes: {response.content[:16].hex()}")  # Debug
        
        # Enhanced MIME detection
        mime_type = "image/jpeg"
        if response.content.startswith(b'\x89PNG\r\n\x1a\n'):
            mime_type = "image/png"
        elif response.content.startswith(b'%PDF'):
            raise ValueError("PDF files not supported")
            
        print(f"Detected MIME type: {mime_type}")
        
        # Encode image in base64 for inline transmission
        base64_image = base64.b64encode(response.content).decode("utf-8")
        
        print("Initializing OpenAI client")
        llm = ChatOpenAI(
            model="gpt-4o",
            max_tokens=4000,
            api_key=os.getenv("OPENAI_API_KEY")
        )
        
        vision_prompt = f"""Analyze the provided image and determine if it is a valid receipt.
If the image is a valid receipt, extract the following details:
- Merchant/store name
- Date of transaction (in YYYY-MM-DD format)
- Total amount
- Tax amount
- Currency (e.g. USD)
- List each item with its name, price, and quantity

Return only a valid JSON object following this schema:
{output_parser.get_format_instructions()}

Important:
- Always include the key "is_receipt" with a boolean value.
- If the image is a receipt, set "is_receipt" to true, provide the corresponding details, and include "message" as an empty string.
- If the image is not a receipt, set "is_receipt" to false and include the "message" key that instructs the user to provide a valid receipt image.
Ensure your output contains only the JSON object and no additional text."""
        
        # Create message with image and prompt
        message = HumanMessage(
            content=[
                {"type": "text", "text": vision_prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}}
            ]
        )
        
        # Retryable OpenAI call
        result = call_openai_with_retry(llm, [message])
        print("OpenAI response received")
        print("Raw response:", repr(result.content))
        
        # Remove markdown formatting if present
        cleaned_content = extract_json(result.content)
        print("Cleaned JSON response:", repr(cleaned_content))
        
        # First try to use the structured output parser.
        try:
            receipt_data = output_parser.parse(cleaned_content)
        except Exception as e:
            print("Structured parser error, attempting manual fallback:", e)
            receipt_data = json.loads(cleaned_content)
        
        # Define base expected keys (excluding message)
        base_expected_keys = {
            "is_receipt": False,
            "merchant": None,
            "date": None,
            "total": None,
            "tax": None,
            "currency": None,
            "items": []
        }
        
        # Fill in any missing base keys from the response
        for key in base_expected_keys:
            if key not in receipt_data:
                receipt_data[key] = base_expected_keys[key]
        
        # Handle message key based on is_receipt status
        if receipt_data["is_receipt"]:
            # Remove the message key, since the receipt is valid.
            receipt_data.pop("message", None)
            # Validate required fields for a valid receipt (removed date validation)
            required_fields = ["merchant", "total", "currency", "items"]
            if not all(receipt_data.get(field) is not None for field in required_fields):
                raise ValueError("Missing required fields in receipt response")
        else:
            # For an invalid receipt, provide a fallback message.
            receipt_data["message"] = receipt_data.get(
                "message", 
                "Please provide a valid receipt image."
            )
        
        return receipt_data

    except RetryError as e:
        print(f"Max retries exceeded: {e.last_attempt.exception()}")
        return None
    except json.JSONDecodeError as e:
        logging.exception("Image processing failed: %s", str(e))
        return None
    except Exception as e:
        print(f"Image processing failed: {e}")
        return None