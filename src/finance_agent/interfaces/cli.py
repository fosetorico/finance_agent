import asyncio
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI

from finance_agent.data.embeddings import MemoryStore
from finance_agent.data.db import FinanceDB
from finance_agent.agent.categorizer import categorise
from finance_agent.agent.router import classify_intent
from finance_agent.agent.tools import get_db_context


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

        # The agent will: Decide intent, Pull tools when needed, Reason only when needed
        intent = classify_intent(user_input)

        memory_snippets = memory.search(user_input)
        memory_block = "\n\n".join(memory_snippets)

        db_context = ""
        if intent in ("db", "hybrid"):
            db_context = get_db_context(db)

        system_prompt = (
            "You are a personal finance intelligence agent. "
            "Use structured financial data when provided. "
            "Base advice on facts, not assumptions."
        )

        full_input = f"""
            User intent: {intent}

            {db_context}

            Relevant past memory:
            {memory_block}

            User question:
            {user_input}
        """

        response = await client.responses.create(
            model="gpt-4.1",
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_input},
            ],
        )

        answer = response.output[0].content[0].text
        print("\nAssistant:", answer, "\n")

        memory.add(user_input, answer)
        continue


if __name__ == "__main__":
    asyncio.run(chat())
