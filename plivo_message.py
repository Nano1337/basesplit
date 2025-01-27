from flask import Flask, request, Response
import os
import json
from plivo.rest import Client
from dotenv import load_dotenv

from parse_receipt import process_receipt

# Initialize Flask app
app = Flask(__name__)

load_dotenv()

# Plivo configuration
PLIVO_AUTH_ID = os.getenv("PLIVO_AUTH_ID")
PLIVO_AUTH_TOKEN = os.getenv("PLIVO_AUTH_TOKEN")
PLIVO_PHONE_NUMBER = os.getenv("PLIVO_NUMBER")  # Your Plivo MMS-enabled number
plivo_client = Client(PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN)

@app.route("/plivo-webhook", methods=["POST"])
def handle_plivo_mms():
    sender = request.form.get("From")
    num_media = int(request.form.get("MediaCount", 0))
    
    print(f"\n=== Received MMS from {sender} ===")
    print(f"Form data: {dict(request.form)}")

    if num_media == 0:
        print("No media attached")
        return Response("<Response><Message>Please send a receipt image</Message></Response>", 
                       mimetype="application/xml")

    try:
        for i in range(num_media):
            media_url = request.form.get(f"Media{i}")
            print(f"Processing media {i}: {media_url}")  # Debug 4a
            
            try:
                print(f"Attempting to process as image: {media_url}")
                receipt_data = process_receipt(media_url)
                
                if receipt_data:
                    response_msg = f"""Receipt processed:
                    Merchant: {receipt_data['merchant']}
                    Date: {receipt_data['date']}
                    Total: {receipt_data['total']} {receipt_data['currency']}
                    Tax: {receipt_data.get('tax', 'N/A')}
                    Items: {len(receipt_data['items'])} items listed
                    """
                    print(f"Successfully processed image: {media_url}")
                    print(f"Response message: {response_msg}")
                    return Response(f"<Response><Message>{response_msg}</Message></Response>", 
                                  mimetype="application/xml")
                                  
            except Exception as e:
                print(f"Failed to process media {i}: {str(e)}")
                continue

        print("No processable media found")
        return Response("<Response><Message>Failed to process receipt image</Message></Response>",
                       mimetype="application/xml")
        
    except Exception as e:
        print(f"ERROR: {str(e)}", exc_info=True)
        return Response(f"<Response><Message>Error processing media: {str(e)}</Message></Response>", 
                       mimetype="application/xml")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)