import asyncio
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI

from finance_agent.data.db import FinanceDB
from finance_agent.agent.router import classify_intent
from finance_agent.agent.tools import get_db_context
from finance_agent.agent.mcp_tools import create_mcp_agent

from finance_agent.tools.receipt_ocr import extract_text_from_image, parse_receipt_with_llm
from finance_agent.services.receipt_ingestion import confirm_transaction

from finance_agent.memory.memory_store import MemoryStore
from finance_agent.memory.memory_policy import should_store_memory


# --------------------------------------------------
# Load environment variables (.env)
# --------------------------------------------------
load_dotenv()

# --------------------------------------------------
# Create OpenAI async client (LLM brain)
# --------------------------------------------------
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --------------------------------------------------
# Persistent semantic memory (ChromaDB on disk)
# 🔧 EDIT: single, persistent memory instance only
# --------------------------------------------------
memory = MemoryStore(persist_dir="memory/chroma")

# --------------------------------------------------
# Finance database (SQLite)
# --------------------------------------------------
db = FinanceDB()

# --------------------------------------------------
# MCP agent (web / live tools only)
# --------------------------------------------------
mcp_agent = create_mcp_agent()


async def chat():
    print("\n=== Finance Agent Chat ===")
    print("Type 'exit' or 'quit' to end.\n")

    while True:
        user_input = input("You: ").strip()

        # -----------------------------
        # Exit handling
        # -----------------------------
        if user_input.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break

        # -----------------------------
        # Intent classification
        # -----------------------------
        intent = classify_intent(user_input)

        # -----------------------------
        # Retrieve relevant long-term memory (Chroma)
        # -----------------------------
        memory_snippets = memory.search(user_input, k=4)
        memory_block = "\n\n".join([m["text"] for m in memory_snippets])

        # -----------------------------
        # Pull DB context only when useful
        # -----------------------------
        db_context = ""
        if intent in ("db", "hybrid"):
            db_context = get_db_context(db)

        # =============================
        # WEB / MCP INTENT
        # =============================
        if intent == "web":
            print("\nAssistant (using live web tools):")
            response = await mcp_agent.run(user_input)
            print(response, "\n")

            # 🔧 EDIT: store web output ONLY if memory policy allows
            if should_store_memory(user_input, response):
                memory.add(
                    text=f"User: {user_input}\nAssistant: {response}",
                    metadata={"type": "web_memory"}
                )
            continue

        # =============================
        # RECEIPT INGESTION FLOW
        # =============================
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

            # 🔧 EDIT: confirm_transaction returns a Transaction object ONLY
            tx = confirm_transaction(parsed_json, db)

            # 🔧 EDIT: CLI is the SINGLE place that writes to DB
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

        # =============================
        # BUDGET COMMANDS
        # =============================
        if user_input.lower().startswith("budget set"):
            _, _, category, limit = user_input.split(maxsplit=3)
            db.set_budget(category, float(limit))
            print(f"✅ Budget set: {category} = £{float(limit):.2f}/month\n")
            continue

        if user_input.lower() == "budget status":
            budgets = dict(db.get_budgets())
            spent = dict(db.spend_this_month_by_category())

            if not budgets:
                print("No budgets set. Use: budget set <Category> <Amount>\n")
                continue

            print("\n=== Budget status (this month) ===")
            for cat, lim in budgets.items():
                s = float(spent.get(cat, 0.0))
                pct = (s / lim * 100.0) if lim > 0 else 0.0
                flag = "⚠️" if pct >= 90 else ""
                print(f"- {cat}: £{s:.2f} / £{lim:.2f} ({pct:.0f}%) {flag}")
            print()
            continue

        # =============================
        # TREND ANALYSIS
        # =============================
        if user_input.lower() == "trend":
            last30 = db.spend_last_30_days()
            prev30 = db.spend_prev_30_days()
            diff = last30 - prev30

            print("\n=== Spend trend ===")
            print(f"Last 30 days: £{last30:.2f}")
            print(f"Previous 30 days: £{prev30:.2f}")
            print(f"Change: £{diff:+.2f}\n")
            continue

        # =============================
        # GENERAL FINANCE INTELLIGENCE
        # =============================
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
        
        # =============================
        # LLM RESPONSE
        # =============================
        response = await client.responses.create(
            model="gpt-4.1",
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_input},
            ],
        )

        answer = response.output[0].content[0].text
        print("\nAssistant:", answer, "\n")

        # 🔧 EDIT: store ONLY durable insights
        if should_store_memory(user_input, answer):
            memory.add(
                text=f"User: {user_input}\nAssistant: {answer}",
                metadata={"type": "chat_memory"}
            )


if __name__ == "__main__":
    asyncio.run(chat())



# import asyncio
# import os

# from dotenv import load_dotenv
# from openai import AsyncOpenAI

# # from finance_agent.data.embeddings import MemoryStore
# from finance_agent.data.db import FinanceDB
# from finance_agent.agent.categorizer import categorise
# from finance_agent.agent.router import classify_intent
# from finance_agent.agent.tools import get_db_context
# from finance_agent.agent.mcp_tools import create_mcp_agent
# from finance_agent.tools.receipt_ocr import extract_text_from_image, parse_receipt_with_llm
# from finance_agent.services.receipt_ingestion import confirm_transaction
# from finance_agent.services.ledger import save_transaction
# from finance_agent.memory.memory_store import MemoryStore
# from finance_agent.memory.memory_policy import should_store_memory


# # Load environment variables from .env
# load_dotenv()

# # Create OpenAI async client
# client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# # Our simple semantic memory
# # memory = MemoryStore()
# memory = MemoryStore(persist_dir="memory/chroma")
# db = FinanceDB()
# mcp_agent = create_mcp_agent()


# async def chat():
#     print("\n=== Finance Agent Chat ===")
#     print("Type 'exit' or 'quit' to end.\n")

#     while True:
#         user_input = input("You: ").strip()

#         # if user want to quit
#         if user_input.lower() in {"exit", "quit"}:
#             print("Goodbye!")
#             break

#         # The agent will: Decide intent, Pull tools when needed, Reason only when needed
#         intent = classify_intent(user_input)

#         # Retrieve relevant long-term memories
#         memory_snippets = memory.search(user_input, k=4)
#         memory_block = "\n\n".join([m["text"] for m in memory_snippets])

#         # if user intent is databse or hybrid baased
#         db_context = ""
#         if intent in ("db", "hybrid"):
#             db_context = get_db_context(db)

#         # if user intent is web based
#         if intent == "web":
#             print("\nAssistant (using live web tools):")
#             response = await mcp_agent.run(user_input)
#             print(response, "\n")

#             if should_store_memory(user_input, response):
#                 memory.add(
#                     text=f"User: {user_input}\nAssistant: {response}",
#                     metadata={"type": "web_memory"}
#                 )
#             continue

#         # if user adds a receipt    
#         if user_input.lower().startswith("add receipt"):
#             parts = user_input.split(maxsplit=2)
#             if len(parts) < 3:
#                 print("Usage: add receipt path/to/image\n")
#                 continue

#             image_path = parts[2]

#             print("Reading receipt image...")
#             raw_text = extract_text_from_image(image_path)

#             print("Parsing receipt...")
#             parsed_json = parse_receipt_with_llm(raw_text)

#             tx = confirm_transaction(parsed_json, db)

#             if tx:
#                 db.add_transaction(
#                     date=tx.date,
#                     merchant=tx.merchant,
#                     amount=float(tx.amount),
#                     category=tx.category,
#                     source="receipt",
#                 )
#                 print("✅ Receipt saved to DB.\n")
#             continue

#         # Example: budget set Food 200
#         if user_input.lower().startswith("budget set"):
#             _, _, category, limit = user_input.split(maxsplit=3)
#             db.set_budget(category, float(limit))
#             print(f"✅ Budget set: {category} = £{float(limit):.2f}/month\n")
#             continue

#         if user_input.lower() == "budget status":
#             budgets = dict(db.get_budgets())
#             spent = dict(db.spend_this_month_by_category())

#             if not budgets:
#                 print("No budgets set. Use: budget set <Category> <Amount>\n")
#                 continue

#             print("\n=== Budget status (this month) ===")
#             for cat, lim in budgets.items():
#                 s = float(spent.get(cat, 0.0))
#                 pct = (s / lim * 100.0) if lim > 0 else 0.0
#                 flag = "⚠️" if pct >= 90 else ""
#                 print(f"- {cat}: £{s:.2f} / £{lim:.2f} ({pct:.0f}%) {flag}")
#             print()
#             continue

#         if user_input.lower() == "trend":
#             last30 = db.spend_last_30_days()
#             prev30 = db.spend_prev_30_days()
#             diff = last30 - prev30

#             print("\n=== Spend trend ===")
#             print(f"Last 30 days: £{last30:.2f}")
#             print(f"Previous 30 days: £{prev30:.2f}")
#             print(f"Change: £{diff:+.2f}\n")
#             continue

#         # System processing...
#         system_prompt = (
#             "You are a personal finance intelligence agent. "
#             "Use structured financial data when provided. "
#             "Base advice on facts, not assumptions."
#         )

#         full_input = f"""
#             User intent: {intent}

#             {db_context}

#             Relevant past memory:
#             {memory_block}

#             User question:
#             {user_input}
#         """

#         # LLM Response    
#         response = await client.responses.create(
#             model="gpt-4.1",
#             input=[
#                 {"role": "system", "content": system_prompt},
#                 {"role": "user", "content": full_input},
#             ],
#         )

#         answer = response.output[0].content[0].text
#         print("\nAssistant:", answer, "\n")

#         # Store durable memories only (avoids noisy embeddings)
#         if should_store_memory(user_input, answer):
#             memory.add(
#                 text=f"User: {user_input}\nAssistant: {answer}",
#                 metadata={"type": "chat_memory"}
#             )
#         continue


# if __name__ == "__main__":
#     asyncio.run(chat())
