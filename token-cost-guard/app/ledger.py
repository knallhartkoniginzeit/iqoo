import sqlite3
from typing import Dict, Any, Optional, List
from pathlib import Path
from contextlib import contextmanager


class Ledger:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent / "ledger.db"
        self.db_path = str(db_path)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    api_key_hash TEXT NOT NULL,
                    project TEXT,
                    model TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER,
                    estimated_cost_usd REAL NOT NULL,
                    actual_cost_usd REAL,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_key_time ON usage(api_key_hash, created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_created_at ON usage(created_at)")
            conn.commit()

    def create_entry(self, api_key_hash: str, project: Optional[str], model: str, input_tokens: int,
                     output_tokens: Optional[int], estimated_cost_usd: float, status: str = "pending",
                     error_message: Optional[str] = None) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO usage (api_key_hash, project, model, input_tokens, output_tokens, estimated_cost_usd, status, error_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (api_key_hash, project, model, input_tokens, output_tokens, estimated_cost_usd, status, error_message))
            conn.commit()
            return cursor.lastrowid

    def update_entry(self, entry_id: int, actual_cost_usd: Optional[float] = None, status: Optional[str] = None,
                     error_message: Optional[str] = None) -> bool:
        with self._get_connection() as conn:
            updates, values = [], []
            if actual_cost_usd is not None:
                updates.append("actual_cost_usd = ?")
                values.append(actual_cost_usd)
            if status is not None:
                updates.append("status = ?")
                values.append(status)
            if error_message is not None:
                updates.append("error_message = ?")
                values.append(error_message)
            if not updates:
                return False
            values.append(entry_id)
            conn.execute(f"UPDATE usage SET {', '.join(updates)} WHERE id = ?", values)
            conn.commit()
            return True

    @staticmethod
    def _hash_filter(api_key_hash: Optional[str]) -> tuple:
        if not api_key_hash:
            return "1=1", []
        if len(api_key_hash) >= 64:
            return "api_key_hash = ?", [api_key_hash]
        return "api_key_hash LIKE ?", [f"{api_key_hash}%"]

    def get_spend_today(self, api_key_hash: str, include_pending: bool = True) -> float:
        with self._get_connection() as conn:
            hash_filter, hash_params = self._hash_filter(api_key_hash)
            query = f"SELECT COALESCE(SUM(estimated_cost_usd), 0) as total FROM usage WHERE {hash_filter} AND DATE(created_at) = DATE('now')"
            if not include_pending:
                query += " AND status != 'pending'"
            query += " AND status != 'blocked'"
            row = conn.execute(query, hash_params).fetchone()
            return float(row["total"]) if row else 0.0

    def get_entries_since(self, api_key_hash: str, hours: int = 24) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            hash_filter, hash_params = self._hash_filter(api_key_hash)
            rows = conn.execute(
                f"SELECT * FROM usage WHERE {hash_filter} AND created_at >= datetime('now', ?) ORDER BY created_at DESC",
                (*hash_params, f"-{hours} hours")).fetchall()
            return [dict(row) for row in rows]

    def get_spend_by_model(self, api_key_hash: Optional[str] = None, hours: int = 24) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            where_clause, params = self._hash_filter(api_key_hash)
            params = list(params)
            where_clause += " AND created_at >= datetime('now', ?)"
            params.append(f"-{hours} hours")
            rows = conn.execute(f"""
                SELECT model, COUNT(*) as request_count, SUM(input_tokens) as total_input_tokens,
                       SUM(output_tokens) as total_output_tokens, SUM(actual_cost_usd) as total_cost_usd,
                       SUM(estimated_cost_usd) as estimated_cost_usd
                FROM usage WHERE {where_clause} GROUP BY model ORDER BY total_cost_usd DESC
            """, params).fetchall()
            return [dict(row) for row in rows]

    def get_summary(self, hours: int = 24) -> Dict[str, Any]:
        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT COUNT(*) as requests,
                       COALESCE(SUM(input_tokens), 0) as input_tokens,
                       COALESCE(SUM(output_tokens), 0) as output_tokens,
                       COALESCE(SUM(estimated_cost_usd), 0) as estimated_cost_usd,
                       COALESCE(SUM(actual_cost_usd), 0) as actual_cost_usd
                FROM usage WHERE created_at >= datetime('now', ?)
            """, (f"-{hours} hours",)).fetchone()
            return dict(row)

    def get_spend_by_key(self, hours: int = 24) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT api_key_hash,
                       COUNT(*) as request_count,
                       SUM(estimated_cost_usd) as estimated_cost_usd,
                       SUM(actual_cost_usd) as actual_cost_usd,
                       MAX(created_at) as last_activity,
                       COALESCE(SUM(CASE WHEN DATE(created_at) = DATE('now') AND status != 'blocked'
                                         THEN estimated_cost_usd ELSE 0 END), 0) as spent_today_usd
                FROM usage WHERE created_at >= datetime('now', ?)
                GROUP BY api_key_hash ORDER BY spent_today_usd DESC
            """, (f"-{hours} hours",)).fetchall()
            return [dict(row) for row in rows]

    def get_recent_entries(self, hours: int = 24, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM usage WHERE created_at >= datetime('now', ?) ORDER BY created_at DESC, id DESC LIMIT ?",
                (f"-{hours} hours", limit)).fetchall()
            return [dict(row) for row in rows]


ledger = Ledger()
