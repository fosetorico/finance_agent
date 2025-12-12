import asyncio
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI

from finance_agent.data.embeddings import MemoryStore


# Load environment variables from .env
load_dotenv()

# Create OpenAI async client
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Our simple semantic memory
memory = MemoryStore()


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
