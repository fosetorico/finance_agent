import sqlite3
from pathlib import Path

DB_PATH = Path("finance.db")


class FinanceDB:
    def __init__(self, db_path: Path = DB_PATH):
        self.conn = sqlite3.connect(db_path)
        self._create_tables()

    def _create_tables(self):
        cursor = self.conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                merchant TEXT,
                amount REAL,
                category TEXT,
                source TEXT
            )
            """
        )

        self.conn.commit()

    def add_transaction(
        self,
        date: str,
        merchant: str,
        amount: float,
        category: str,
        source: str = "manual",
    ):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO transactions (date, merchant, amount, category, source)
            VALUES (?, ?, ?, ?, ?)
            """,
            (date, merchant, amount, category, source),
        )
        self.conn.commit()

    def get_all_transactions(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT date, merchant, amount, category FROM transactions")
        return cursor.fetchall()

    def total_spend(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT SUM(amount) FROM transactions")
        result = cursor.fetchone()[0]
        return result or 0.0

    def spend_by_category(self):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT category, SUM(amount) as total
            FROM transactions
            GROUP BY category
            ORDER BY total DESC
            """
        )
        return cursor.fetchall()

    def recent_transactions(self, limit: int = 10):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT date, merchant, amount, category
            FROM transactions
            ORDER BY date DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return cursor.fetchall()

