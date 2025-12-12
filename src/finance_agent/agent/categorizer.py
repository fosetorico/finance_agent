import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DEFAULT_CATEGORIES = [
    "Food",
    "Transport",
    "Subscriptions",
    "Bills",
    "Shopping",
    "Entertainment",
    "Health",
    "Rent",
    "Income",
    "Other",
]

# Simple rule-based mapping (fast + free)
RULES = {
    "tesco": "Food",
    "sainsbury": "Food",
    "aldi": "Food",
    "lidl": "Food",
    "uber": "Transport",
    "bolt": "Transport",
    "train": "Transport",
    "netflix": "Subscriptions",
    "spotify": "Subscriptions",
    "prime": "Subscriptions",
    "gym": "Health",
}


def rule_based_category(merchant: str) -> str | None:
    m = merchant.strip().lower()
    for key, cat in RULES.items():
        if key in m:
            return cat
    return None


def llm_category(merchant: str, amount: float, description: str = "") -> str:
    prompt = f"""
        You are categorising personal finance transactions.
        Pick ONE category from this list:
        {", ".join(DEFAULT_CATEGORIES)}

        Transaction:
        Merchant: {merchant}
        Amount: {amount}
        Description: {description}

        Return ONLY the category name.
    """
    resp = client.responses.create(model="gpt-4.1", input=prompt)
    cat = resp.output_text.strip()
    return cat if cat in DEFAULT_CATEGORIES else "Other"


def categorise(merchant: str, amount: float, description: str = "") -> str:
    # 1) Try rules first
    cat = rule_based_category(merchant)
    if cat:
        return cat

    # 2) Fallback to LLM
    return llm_category(merchant, amount, description)
