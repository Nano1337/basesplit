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
    return llm.invoke(messages)

def process_receipt(image_url: str) -> dict:
    """Process receipt image through OpenAI Vision API with JSON mode."""
    filename = None
    try:
        print(f"\nDownloading image from {image_url}")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
        }
        response = requests.get(image_url, headers=headers, timeout=15)
        response.raise_for_status()
        
        print(f"Image downloaded ({len(response.content)} bytes)")
        print(f"First 16 bytes: {response.content[:16].hex()}")  # Debug 15

        # Enhanced MIME detection
        mime_type = "image/jpeg"
        if response.content.startswith(b'\x89PNG\r\n\x1a\n'):
            mime_type = "image/png"
        elif response.content.startswith(b'%PDF'):
            raise ValueError("PDF files not supported")
            
        print(f"Detected MIME type: {mime_type}")

        # Use in-memory file instead of writing to disk
        base64_image = base64.b64encode(response.content).decode("utf-8")
        
        print("Initializing OpenAI client")  # Debug 10
        llm = ChatOpenAI(
            model="gpt-4o",
            max_tokens=4000,
            api_key=os.getenv("OPENAI_API_KEY"),
            model_kwargs={"response_format": {"type": "json_object"}}
        )
        
        # Create structured prompt
        vision_prompt = """Analyze this receipt carefully and extract the following information:
        - Total amount
        - Tax amount
        - Date of transaction
        - Merchant/store name
        - List of items with their individual prices and quantities
        
        Structure the output as JSON with this exact format:
        {
            "merchant": "Store Name",
            "date": "YYYY-MM-DD",
            "total": 0.00,
            "tax": 0.00,
            "currency": "USD",
            "items": [
                {
                    "name": "Item Name",
                    "price": 0.00,
                    "quantity": 1
                }
            ]
        }
        Ensure numerical values are floats. If any field is missing, try to calculate it.
        Include ALL items from the receipt."""
        
        # Create message with image and prompt
        message = HumanMessage(
            content=[
                {
                    "type": "text",
                    "text": vision_prompt
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{base64_image}"
                    }
                }
            ]
        )
        
        # Retryable OpenAI call
        result = call_openai_with_retry(llm, [message])
        print("OpenAI response received")  # Debug 12
        
        # Parse and validate JSON response
        receipt_data = json.loads(result.content)
        
        # Basic validation
        required_fields = ["merchant", "date", "total", "currency", "items"]
        if not all(field in receipt_data for field in required_fields):
            raise ValueError("Missing required fields in response")
            
        return receipt_data
            
    except RetryError as e:
        print(f"Max retries exceeded: {e.last_attempt.exception()}")
        return None
    except Exception as e:
        print(f"Image processing failed: {str(e)}", exc_info=True)
        return None