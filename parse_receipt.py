import base64
import json
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

def process_receipt(image_path, anthropic_api_key):
    # Read and encode image
    with open(image_path, "rb") as image_file:
        encoded_image = base64.b64encode(image_file.read()).decode("utf-8")

    # Create the vision prompt
    prompt = """Analyze this receipt carefully and extract the following information:
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

    # Initialize Claude Haiku
    chat = ChatAnthropic(
        model_name="claude-3-haiku-20240307",
        temperature=0,
        max_tokens=1024,
        api_key=anthropic_api_key
    )

    # Send request
    msg = chat.invoke([
        HumanMessage(
            content=[
                {"type": "image", "source": {"data": encoded_image, "media_type": "image/jpeg"}},
                {"type": "text", "text": prompt}
            ]
        )
    ])

    # Parse and return JSON
    try:
        # Extract JSON content from response
        json_str = msg.content.split("```json")[1].split("```")[0].strip()
        return json.loads(json_str)
    except (IndexError, json.JSONDecodeError) as e:
        print("Error parsing response:", e)
        return None

# Usage example
if __name__ == "__main__":
    receipt_data = process_receipt(
        image_path="path/to/receipt.jpg",
        anthropic_api_key="your_anthropic_api_key"
    )
    
    if receipt_data:
        with open("receipt_data.json", "w") as f:
            json.dump(receipt_data, f, indent=2)
        print("Receipt data saved successfully!")