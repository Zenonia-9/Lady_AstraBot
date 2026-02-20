import sqlite3

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import OWNER_ID, OWNER_USERNAME, USER_FILE, BOT_NAME
import logging

_logger = logging.getLogger(__name__)

def split_text(text: str, limit: int=4000) -> list:
    chunks = []
    while len(text) > limit:
            # Try to split at last newline before limit
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
                # If no newline, split at last space
            split_at = text.rfind(" ", 0, limit)
        if split_at == -1:
                # If no space, just split at limit
            split_at = limit
        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()
    if text:
        chunks.append(text)
    return chunks

class Manager:
    def __init__(self, db_path=USER_FILE):
        self.db_path = db_path
        self._init_db()
        self.upsert_user(
            user_id=OWNER_ID,
            username=OWNER_USERNAME,
            full_name='Thein Htoo Aung',
            role='owner'
        )

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.cursor().execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT UNIQUE NOT NULL,
                username TEXT,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user'
            )
        ''')
            conn.commit()
    
    def upsert_user(self, user_id, username: str, full_name: str, role: str="user"):
        user_id = str(user_id)
        # Check if user exists
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            existing_user = cursor.fetchone()

            if existing_user:
                # Update username and full_name
                cursor.execute(
                    "UPDATE users SET username = ?, full_name = ? WHERE user_id = ?",
                    (username, full_name, user_id)
                )
                _logger.info(f"Updated user: {full_name}")
            else:
                # Insert new user
                cursor.execute(
                    "INSERT INTO users (user_id, username, full_name, role) VALUES (?, ?, ?, ?)",
                    (user_id, username, full_name, role)
                )
                _logger.info(f"Inserted new user: {full_name}")

            conn.commit()
    
    def remove_user(self, user_id):
        user_id = str(user_id)
        with sqlite3.connect(self.db_path) as conn:
            conn.cursor().execute('''
                DELETE FROM users WHERE user_id = ?
            ''', (user_id,))
            conn.commit()

    def update_user_role(self, user_id, new_role: str='user'):
        user_id = str(user_id)
        with sqlite3.connect(self.db_path) as conn:
            conn.cursor().execute("UPDATE users SET role = ? WHERE user_id = ?", (new_role, user_id))
            conn.commit()
        return True

    def get_user_role(self, user_id):
        user_id = str(user_id)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
        return result[0] if result else None
    
    def get_admins(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, username, full_name FROM users WHERE role = 'admin'")
            return cursor.fetchall()
        
    def is_admin(self, user_id):
        user_id = str(user_id)
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT 1 FROM users WHERE user_id = ? AND (role = "admin" OR role = "owner")', (user_id,))
            return c.fetchone() is not None

    # Output methods
    async def admin_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        user_role = self.get_user_role(user.id)

        if user_role in ['admin', 'owner']:
            await update.message.reply_text("You already hold user access. There is nothing further required.")
            return

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Approve", callback_data=f"approve:{user.id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject:{user.id}")]
        ])

        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=f"""New Access Request👤

User: {'@' + user.username if user.username else user.full_name}
User ID: {user.id}

Approve or reject access to {BOT_NAME}.""",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        await update.message.reply_text(
            f"""📝 Your request has been sent.

Please wait for approval from the owner.
Once approved, you will be able to interact with {BOT_NAME}."""
                )

    async def handle_admin_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data

        if data.startswith("approve:"):
            _, user_id = data.split(":")
            self.update_user_role(user_id=user_id, new_role='admin')
            await context.bot.send_message(chat_id=int(user_id),
                                        text=f"✅ Your access request has been approved.\n\nYou may now speak with {BOT_NAME} and use her features.\n\nProceed with grace.",
                                        parse_mode="Markdown")
            await query.edit_message_text(f"✅ ({user_id}) Admin request approved.")

        elif data.startswith("reject:"):
            _, user_id = data.split(":")
            await context.bot.send_message(chat_id=int(user_id),
                                        text=f"❌ Your access request has been declined.\n\nYou are not authorized to interact with {BOT_NAME} at this time.\n\nIf you believe this is a mistake, you may contact the administrator.",
                                        parse_mode="Markdown")
            await query.edit_message_text(f"❌ ({user_id}) Admin request rejected.")

    async def remove_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != str(OWNER_ID):
            await update.message.reply_text("Sorry, You don't have permission to use this command.")
            return

        admins = self.get_admins()
        if not admins:
            await update.message.reply_text("No users to remove.")
            return

        keyboard = [[InlineKeyboardButton(f"{a[2]} (@{a[1]})", callback_data=f"removeadmin:{a[0]}")] for a in admins]
        await update.message.reply_text("Select a user to remove access:", reply_markup=InlineKeyboardMarkup(keyboard))

    async def handle_remove_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        if not query.data.startswith("removeadmin:"):
            return

        user_id = query.data.split(":")[1]
        success = self.update_user_role(user_id)
        if success:
            await query.edit_message_text(f"✅ User {user_id} removed successfully.")
        else:
            await query.edit_message_text(f"❌ Failed to remove user {user_id}.")