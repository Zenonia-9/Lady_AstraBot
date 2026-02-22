import sqlite3

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import OWNER_ID, OWNER_USERNAME, USER_FILE, BOT_NAME
from functions.memory import ConversationMemory

_logger = logging.getLogger(__name__)
memory = ConversationMemory()

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
        self.__init_db()
        self.upsert_user(
            user_id=OWNER_ID,
            username=OWNER_USERNAME,
            full_name='Thein Htoo Aung',
            role='owner'
        )

    def __init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute('''
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
    async def command_admin_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            reply_markup=keyboard
        )
        await update.message.reply_text(
            f"""📝 Your request has been sent.

Please wait for approval from the owner.
Once approved, you will be able to interact with {BOT_NAME}."""
                )

    async def handle_admin_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data

        if data.startswith("approve:"):
            _, user_id = data.split(":")
            self.update_user_role(user_id=user_id, new_role='admin')
            await context.bot.send_message(chat_id=int(user_id),
                                        text=f"✅ Your access request has been approved.\n\nYou may now speak with {BOT_NAME} and use her features.\n\nProceed with grace.")
            await query.edit_message_text(f"✅ ({user_id}) Admin request approved.")

        elif data.startswith("reject:"):
            _, user_id = data.split(":")
            await context.bot.send_message(chat_id=int(user_id),
                                        text=f"❌ Your access request has been declined.\n\nYou are not authorized to interact with {BOT_NAME} at this time.\n\nIf you believe this is a mistake, you may contact the administrator.")
            await query.edit_message_text(f"❌ ({user_id}) Admin request rejected.")

    async def command_remove_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    async def show_delete_menu(self, target):
        keyboard = [
            [
                InlineKeyboardButton("🗑 All", callback_data="del_all"),
                InlineKeyboardButton("🕰 Oldest", callback_data="del_oldest"),
                InlineKeyboardButton("✨ Newest", callback_data="del_newest"),
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="del_cancel")]
        ]
        text = 'Would you like to clear part of our chat history?\nChoose what you’d like to remove.\n<b>Deleted messages can’t be recovered.</b>'

        if hasattr(target, "message"):  
            # callback query
            await target.edit_message_text(
                text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            # normal message
            await target.reply_text(
                text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    async def command_delete_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.show_delete_menu(update.message)
    
    async def handle_delete_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        data = query.data
        user_id = query.from_user.id

        if data == "del_cancel":
            await query.edit_message_text("Cancelled.")
            return

        if data == "del_all":
            memory.delete_history(user_id=user_id, delete_type="all")
            await query.edit_message_text("🗑 All messages deleted.")
            return

        # Store type for next step
        if data == "del_oldest":
            context.user_data["delete_type"] = "oldest"
        elif data == "del_newest":
            context.user_data["delete_type"] = "newest"

        # Show amount buttons
        keyboard = [
            [
                InlineKeyboardButton("2", callback_data="del_amount_2"),
                InlineKeyboardButton("4", callback_data="del_amount_4"),
                InlineKeyboardButton("10", callback_data="del_amount_10"),
                InlineKeyboardButton("20", callback_data="del_amount_20"),
                InlineKeyboardButton("50", callback_data="del_amount_50"),
            ],
            [InlineKeyboardButton("⬅ Back", callback_data="del_back")]
        ]

        await query.edit_message_text(
            "How many messages?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def handle_delete_amount(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        data = query.data
        user_id = query.from_user.id

        if data == "del_back":
            return await self.show_delete_menu(query)

        # Extract number
        amount = int(data.split("_")[-1])
        delete_type = context.user_data.get("delete_type")

        memory.delete_history(
            user_id=user_id,
            delete_type=delete_type,
            amount=amount
        )

        await query.edit_message_text(
            f"✨ {amount} messages removed."
        )