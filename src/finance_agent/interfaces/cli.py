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

        # 1) Retrieve similar past exchanges from memory
        similar = memory.search(user_input)
        context_block = "\n\n".join(similar)

        # 2) Build a prompt that includes memory
        system_prompt = (
            "You are a helpful personal finance assistant. "
            "You help the user understand spending, budgeting, and financial habits. "
            "Be clear, concise, and practical."
        )

        full_input = f"""
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


        # 3) Call OpenAI Responses API (gpt-4.1)
        response = await client.responses.create(
            model="gpt-4.1",
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_input},
            ],
        )

        # 4) Extract text output
        answer = response.output[0].content[0].text

        print("\nAssistant:", answer, "\n")

        # 5) Save this new exchange into memory
        memory.add(user_input, answer)


if __name__ == "__main__":
    asyncio.run(chat())
