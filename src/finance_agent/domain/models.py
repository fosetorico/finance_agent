from dataclasses import dataclass
from datetime import date

# Represents a single financial transaction
@dataclass
class Transaction:
    date: date
    merchant: str
    amount: float
    category: str
