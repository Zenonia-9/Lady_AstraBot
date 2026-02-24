import sqlite3

from datetime import datetime, timezone, timedelta
from config import MEMORY_FILE

class ConversationMemory:
    def __init__(self, db_path=MEMORY_FILE):
        self.db_path = db_path
        # Open one persistent connection
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL;")        # Enable WAL
        self.conn.execute("PRAGMA synchronous=NORMAL;")      # Faster writes
        self.conn.execute("PRAGMA foreign_keys=ON;")         # Optional safety
        self._init_db()

    def _init_db(self):
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                fullname TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()

    def save_message(self, user_id, fullname, message):
        self.conn.execute('''
            INSERT INTO messages (user_id, fullname, message, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (user_id, fullname, message, datetime.now(timezone.utc)))
        self.conn.commit()


    def get_history(self, user_id, limit=10):
        cursor = self.conn.execute('''
            SELECT fullname, message FROM messages
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (user_id, limit))
        rows = cursor.fetchall()
        return [{"role": r, "content": m} for r, m in reversed(rows)]
    
    def delete_history(self, user_id: int, delete_type="all", amount=None):
        if delete_type == "all":
            self.conn.execute('DELETE FROM messages WHERE user_id = ?', (user_id,))
        elif delete_type in ("oldest", "newest") and amount:
            order = "ASC" if delete_type == "oldest" else "DESC"
            self.conn.execute(f'''
                DELETE FROM messages
                WHERE id IN (
                    SELECT id FROM messages
                    WHERE user_id = ?
                    ORDER BY timestamp {order}
                    LIMIT ?
                )
            ''', (user_id, amount))
        else:
            raise ValueError("Invalid delete_type or missing amount for oldest/newest")
        self.conn.commit()

    def trim_old_messages(self, days: int=30):
        cutoff = datetime.utcnow() - timedelta(days=days)
        self.conn.execute('DELETE FROM messages WHERE timestamp < ?', (cutoff.isoformat(),))
        self.conn.commit()
    
    def close(self):
        """Close connection on shutdown"""
        self.conn.close()