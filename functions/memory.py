import sqlite3

from datetime import datetime, timezone, timedelta
from config import MEMORY_FILE

class ConversationMemory:
    def __init__(self, db_path=MEMORY_FILE):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.cursor().execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                fullname TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
            conn.commit()

    def save_message(self, user_id, fullname, message):
        with sqlite3.connect(self.db_path) as conn:
            conn.cursor().execute('''
            INSERT INTO messages (user_id, fullname, message, timestamp) VALUES (?, ?, ?, ?)
        ''', (user_id, fullname, message, datetime.now(timezone.utc)))
            conn.commit()

    def get_history(self, user_id, limit=10):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''
            SELECT fullname, message FROM messages
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (user_id, limit))
        rows = c.fetchall()
        return [ {"role": r, "content": m} for r, m in reversed(rows) ]
    
    def delete_history(self, user_id: int, delete_type="all", amount=None):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if delete_type == "all":
                cursor.execute('DELETE FROM messages WHERE user_id = ?', (user_id,))
            
            elif delete_type in ("oldest", "newest") and amount:
                # Determine order
                order = "ASC" if delete_type == "oldest" else "DESC"
                cursor.execute(f'''
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
            
            conn.commit()

    def trim_old_messages(self, days: int=30):
        cutoff = datetime.utcnow() - timedelta(days=days)
        with sqlite3.connect(self.db_path) as conn:
            conn.cursor().execute('''
            DELETE FROM messages WHERE timestamp < ?
        ''', (cutoff.isoformat(),))
            conn.commit()