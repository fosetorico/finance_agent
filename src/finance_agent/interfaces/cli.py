import asyncio
import os
import re 

from dotenv import load_dotenv
from openai import AsyncOpenAI

from finance_agent.data.db import FinanceDB

from finance_agent.agent.router import classify_intent
from finance_agent.agent.tools import get_db_context
from finance_agent.agent.mcp_tools import create_mcp_agent

from finance_agent.tools.receipt_ocr import extract_text_from_image, parse_receipt_with_llm
from finance_agent.tools.fx import get_fx_rate, convert, get_supported_currencies
from finance_agent.tools.news import get_finance_news, get_ai_news
from finance_agent.tools.gdelt_news import fetch_latest_news, format_headlines

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

        # =============================
        # FX / CURRENCY (handle early so it never goes to MCP)
        # =============================
        fx_text = user_input.upper()

        # Extract currency codes like GBP, USD, EUR
        codes = re.findall(r"\b[A-Z]{3}\b", fx_text)
        supported = get_supported_currencies()
        codes = [c for c in codes if c in supported]

        if "EXCHANGE RATE" in fx_text or fx_text.startswith("CONVERT"):
            try:
                if fx_text.startswith("CONVERT"):
                    # Example: "convert 120 GBP to USD"
                    parts = fx_text.split()
                    amount = float(parts[1])
                    base = parts[2]
                    target = parts[4]
                    result = convert(amount, base, target)
                    print(f"\n{amount} {base} = {result} {target}\n")
                else:
                    # Example: "What is the GBP to USD exchange rate?"
                    if len(codes) >= 2:
                        base, target = codes[0], codes[1]
                    else:
                        # Fallback default if user didn't specify clearly
                        base, target = "GBP", "USD"

                    rate = get_fx_rate(base, target)
                    print(f"\n1 {base} = {rate:.4f} {target}\n")

            except Exception as e:
                print(f"\n❌ FX error: {e}\n")
            continue

        # =============================
        # NEWS / WEB SEARCH (via MCP tools)
        # 🔧 EDIT: Replace stub news functions with live MCP search
        # =============================
        lower = user_input.lower()

        # Allow explicit "Search the web: ..." command
        if lower.startswith("search the web:"):
            query = user_input.split(":", 1)[1].strip()

            print("\n🌐 Searching the web (via MCP)...\n")
            try:
                response = await mcp_agent.run(query)
                print(response, "\n")
            except Exception as e:
                print(f"❌ Web search error: {e}\n")

            # 🔧 EDIT: Do NOT store volatile web results in memory
            continue

        # Handle "news" questions (AI + finance) using MCP
        if "news" in lower:
            print("\n📰 Fetching latest Finance + AI news (via MCP)...\n")

            try:
                finance_prompt = (
                    "Search the web for the 5 latest finance/markets news headlines today. "
                    "Return a concise bullet list with: title | source | date."
                )
                ai_prompt = (
                    "Search the web for the 5 latest AI news headlines today. "
                    "Return a concise bullet list with: title | source | date."
                )

                finance_resp = await mcp_agent.run(finance_prompt)
                ai_resp = await mcp_agent.run(ai_prompt)

                # If DDG search was blocked, fallback to GDELT
                blocked = "ddg detected an anomaly" in str(finance_resp).lower() or "ddg detected an anomaly" in str(ai_resp).lower()
                if blocked:
                    print("⚠️ Search tool blocked (DDG anomaly). Falling back to GDELT live news.\n")

                    finance_items = fetch_latest_news("finance OR markets OR stocks OR inflation OR central bank", max_results=5)
                    ai_items = fetch_latest_news("artificial intelligence OR AI OR LLM OR OpenAI OR Google DeepMind", max_results=5)

                    print("📊 Finance News (GDELT):")
                    print(format_headlines(finance_items), "\n")

                    print("🤖 AI & Tech News (GDELT):")
                    print(format_headlines(ai_items), "\n")

                    continue

                # 🔧 EDIT: Guardrail - if MCP tools aren't connected, avoid stale LLM answers
                if not finance_resp or "no mcp servers defined" in str(finance_resp).lower():
                    print("⚠️ Live web tools are not connected, so I can\’t fetch today\’s news reliably.\n")
                    continue

            except Exception as e:
                print(f"❌ News error: {e}\n")

            # 🔧 EDIT: Do NOT store volatile news in memory
            continue

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
