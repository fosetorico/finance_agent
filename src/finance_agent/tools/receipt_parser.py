"""
Uses OpenAI to turn messy OCR text into structured data.
"""

import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def parse_receipt_text(text: str) -> dict:
    """
    Convert OCR text into structured receipt fields.
    """
    prompt = f"""
        You are extracting structured data from a receipt.

        Return JSON with these fields:
        - date (YYYY-MM-DD)
        - merchant
        - total_amount (number)
        - category (Food, Transport, Subscriptions, Shopping, Other)

        Receipt text:
        {text}

        Return ONLY valid JSON.
    """

    response = client.responses.create(
        model="gpt-4.1",
        input=prompt
    )

    return eval(response.output_text)
