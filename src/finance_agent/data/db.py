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

    def spend_by_month_and_category(self):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT substr(date, 1, 7) as month, category, SUM(amount) as total
            FROM transactions
            GROUP BY month, category
            ORDER BY month DESC, total DESC
            """
        )
        return cursor.fetchall()

    def top_merchants(self, limit: int = 5):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT merchant, SUM(amount) as total
            FROM transactions
            GROUP BY merchant
            ORDER BY total DESC
            LIMIT ?
            """,
            (limit,),
        )
        return cursor.fetchall()

    def possible_anomalies(self, high_amount_threshold: float = 100.0):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT date, merchant, amount, category
            FROM transactions
            WHERE amount >= ?
            ORDER BY amount DESC
            """,
            (high_amount_threshold,),
        )
        return cursor.fetchall()

    # Check if we've ever seen this merchant before
    def merchant_exists(self, merchant: str) -> bool:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT 1 FROM transactions WHERE lower(merchant)=lower(?) LIMIT 1",
            (merchant,),
        )
        return cursor.fetchone() is not None

    # Get typical spend stats to support anomaly detection (simple baseline)
    def avg_amount(self) -> float:
        cursor = self.conn.cursor()
        cursor.execute("SELECT AVG(amount) FROM transactions")
        val = cursor.fetchone()[0]
        return float(val) if val is not None else 0.0
