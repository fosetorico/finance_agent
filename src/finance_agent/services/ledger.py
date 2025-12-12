import json
from finance_agent.domain.models import Transaction
from pathlib import Path

LEDGER_PATH = Path("data/transactions.json")

# Persist approved transaction
def save_transaction(tx: Transaction):
    LEDGER_PATH.parent.mkdir(exist_ok=True)

    transactions = []
    if LEDGER_PATH.exists():
        transactions = json.loads(LEDGER_PATH.read_text())

    transactions.append(tx.__dict__)
    LEDGER_PATH.write_text(json.dumps(transactions, indent=2))

    print("✅ Transaction saved.")
