import asyncio
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI

from finance_agent.data.embeddings import MemoryStore
from finance_agent.data.db import FinanceDB


# Load environment variables from .env
load_dotenv()

# Create OpenAI async client
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Our simple semantic memory
memory = MemoryStore()
db = FinanceDB()


async def chat():
    print("\n=== Finance Agent Chat ===")
    print("Type 'exit' or 'quit' to end.\n")

    while True:
        user_input = input("You: ")

        if user_input.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break

        # Retrieve similar past exchanges from memory
        similar = memory.search(user_input)
        context_block = "\n\n".join(similar)

        # Pull structured facts from SQLite
        total = db.total_spend()
        by_cat = db.spend_by_category()
        recent = db.recent_transactions(limit=10)

        by_cat_text = "\n".join([f"- {cat}: £{amt:.2f}" for cat, amt in by_cat]) if by_cat else "No data yet."
        recent_text = "\n".join([f"- {d} | {m} | £{a:.2f} | {c}" for d, m, a, c in recent]) if recent else "No data yet."

        finance_facts = f"""
            Structured finance facts (from SQLite):
            Total spend recorded: £{total:.2f}

            Spend by category:
            {by_cat_text}

            Recent transactions (latest first):
            {recent_text}
        """

        # Build a prompt that includes memory
        system_prompt = (
            "You are a helpful personal finance assistant. "
            "You help the user understand spending, budgeting, and financial habits. "
            "Be clear, concise, and practical."
        )

        full_input = f"""
            {finance_facts}
            
            Previous relevant conversation snippets:
            {context_block}

            User question:
            {user_input}
        """
        # Simple command handling
        if user_input.lower().startswith("add transaction"):
            # Example:
            # add transaction 2024-01-10 Tesco 24.50 Food
            parts = user_input.split()

            try:
                date = parts[2]
                merchant = parts[3]
                amount = float(parts[4])
                category = parts[5]

                db.add_transaction(date, merchant, amount, category)
                print("Transaction added successfully.\n")
                continue

            except Exception:
                print(
                    "Invalid format.\n"
                    "Use: add transaction YYYY-MM-DD Merchant Amount Category\n"
                )
                continue

        if user_input.lower() == "total spend":
            total = db.total_spend()
            print(f"\nTotal spend recorded: £{total:.2f}\n")
            continue


        # Call OpenAI Responses API (gpt-4.1)
        response = await client.responses.create(
            model="gpt-4.1",
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_input},
            ],
        )

        # Extract text output
        answer = response.output[0].content[0].text

        print("\nAssistant:", answer, "\n")

        # Save this new exchange into memory
        memory.add(user_input, answer)


if __name__ == "__main__":
    asyncio.run(chat())
