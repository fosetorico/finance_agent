# OCR + LLM receipt parser
# Turns receipt images into structured transactions

from PIL import Image
import pytesseract
from openai import OpenAI
import os
from dotenv import load_dotenv
import json
import re

# Load environment variables from .env
load_dotenv()

# Create OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def extract_text_from_image(image_path: str) -> str:
    """
    Uses Tesseract OCR to extract raw text from a receipt image
    """
    image = Image.open(image_path)
    text = pytesseract.image_to_string(image)
    return text


def parse_receipt_with_llm(raw_text: str) -> dict:
    """
    Uses an LLM to convert messy receipt text into structured data
    """
    prompt = f"""
        You are a finance assistant.

        From the receipt text below, extract:
        - date (YYYY-MM-DD)
        - merchant
        - total_amount
        - category (Food, Transport, Shopping, etc.)

        Return ONLY valid JSON.

        Receipt text:
        {raw_text}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    text = response.choices[0].message.content.strip()

    # 🔒 HARDENING: extract first JSON object if extra text exists
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(
            "LLM did not return valid JSON.\n"
            f"Raw output:\n{text}"
        )

    json_str = match.group(0)

    # Validate JSON now (fail fast if broken)
    json.loads(json_str)

    return json_str

