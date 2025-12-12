import asyncio
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI

from finance_agent.data.embeddings import MemoryStore
from finance_agent.data.db import FinanceDB
from finance_agent.agent.categorizer import categorise
from finance_agent.agent.router import classify_intent
from finance_agent.agent.tools import get_db_context
from finance_agent.agent.mcp_tools import create_mcp_agent
from finance_agent.tools.receipt_ocr import extract_text_from_image, parse_receipt_with_llm
from finance_agent.services.receipt_ingestion import confirm_transaction
from finance_agent.services.ledger import save_transaction


# Load environment variables from .env
load_dotenv()

# Create OpenAI async client
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Our simple semantic memory
memory = MemoryStore()
db = FinanceDB()
mcp_agent = create_mcp_agent()


async def chat():
    print("\n=== Finance Agent Chat ===")
    print("Type 'exit' or 'quit' to end.\n")

    while True:
        user_input = input("You: ")

        # if user want to quit
        if user_input.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break

        # The agent will: Decide intent, Pull tools when needed, Reason only when needed
        intent = classify_intent(user_input)

        memory_snippets = memory.search(user_input)
        memory_block = "\n\n".join(memory_snippets)

        # if user intent is databse or hybrid baased
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

        # if user intent is web based
        if intent == "web":
            print("\nAssistant (using live web tools):")
            response = await mcp_agent.run(user_input)
            print(response, "\n")

            memory.add(user_input, response)
            continue

        # if user adds a receipt    
        if user_input.lower().startswith("add receipt"):
            parts = user_input.split(maxsplit=2)
            if len(parts) < 3:
                print("Usage: add receipt path/to/image\n")
                continue

            image_path = parts[2]

            print("Reading receipt image...")
            raw_text = extract_text_from_image(image_path)

            print("Parsing receipt...")
            parsed_json = parse_receipt_with_llm(raw_text)

            tx = confirm_transaction(parsed_json, db)

            if tx:
                db.add_transaction(
                    date=tx.date,
                    merchant=tx.merchant,
                    amount=float(tx.amount),
                    category=tx.category,
                    source="receipt",
                )
                print("✅ Receipt saved to DB.\n")

            continue


        # LLM Response    
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
