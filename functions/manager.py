import sqlite3, os

import logging, asyncio
import matplotlib.pyplot as plt

from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import OWNER_ID, OWNER_USERNAME, USER_FILE, BOT_NAME, UPTIME_FILE, GRAPH_DIR
from functions.memory import ConversationMemory
from collections import defaultdict

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

class Uptime:
    def __init__(self, beatsec: int=60, db_path=UPTIME_FILE):
        self.db_path = db_path
        self.beatsec = beatsec
        self.__init_db()

    def __init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS heartbeat (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS hourly_uptime (
                date TEXT,
                hour INTEGER,
                uptime_percent REAL,
                PRIMARY KEY (date, hour)
            )
            """)
            conn.commit()
    
    def save_heartbeat(self):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()

            cur.execute(
                "INSERT INTO heartbeat(timestamp) VALUES(?)",
                (datetime.now(timezone.utc),)
            )

            conn.commit()

    def calculate_hourly_uptime(self):
        max_per_hour = 3600 // self.beatsec

        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT 
                date(timestamp) AS day,
                strftime('%H', timestamp) AS hour,
                COUNT(*) AS total
            FROM heartbeat
            GROUP BY day, hour
            """)

            rows = cur.fetchall()
            data = defaultdict(lambda: {h: 0 for h in range(24)})

            for day, hour, total in rows:
                data[day][int(hour)] = total

            # Save uptime %
            for day, hours in data.items():
                for hour in range(24):
                    count = hours[hour]
                    uptime_percent = (count / max_per_hour) * 100

                    cur.execute("""
                    INSERT OR REPLACE INTO hourly_uptime (date, hour, uptime_percent)
                    VALUES (?, ?, ?)
                    """, (day, hour, uptime_percent))

            _logger.info("Uptime.calculate_hourly_uptime(): Saved hourly uptime successfully.")
            conn.commit()
    
    async def heartbeat_loop(self):
        while True:
            self.save_heartbeat()
            _logger.info("Uptime.heartbeat_loop(): Heartbeat ping…")
            await asyncio.sleep(self.beatsec)

    def get_alltime_avg(self):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()

            cur.execute("SELECT AVG(uptime_percent) FROM hourly_uptime")
            avg = cur.fetchone()[0]

        return avg or 0
    
    def get_today_avg(self):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()

            cur.execute("""
                SELECT AVG(uptime_percent)
                FROM hourly_uptime
                WHERE date = date('now')
            """)

            avg = cur.fetchone()[0]
        return avg or 0

    def generate_weekly_uptime_graph(self) -> str:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()

            cur.execute("""
                SELECT hour, uptime_percent
                FROM hourly_uptime
                WHERE date >= date('now', '-7 days') 
            """) 
            # AND date < date('now')

            rows = cur.fetchall()

        if not rows:
            return None
        
        hourly_values = defaultdict(list)
        for hour, uptime in rows:
            hourly_values[int(hour)].append(float(uptime))

        weekly_avg = {}
        for hour in range(24):
            values = hourly_values.get(hour, [])
            weekly_avg[hour] = sum(values) / len(values) if values else 0.0

        # 4️⃣ Draw Graph
        hours = list(range(24))
        uptimes = [weekly_avg[h] for h in hours]

        plt.figure(figsize=(10, 5))
        plt.plot(hours, uptimes, marker='o', linestyle='-', color='blue')
        plt.xticks(hours)
        plt.xlabel("Hour")
        plt.ylabel("Average Uptime %")
        plt.title("Weekly Average Uptime Per Hour")
        plt.grid(True)

        now = datetime.now().astimezone()
        safe_time = now.strftime("%Y-%m-%d_%H-%M-%S")

        save_path = GRAPH_DIR / f"{safe_time}_uptime.png"
        if save_path:
            plt.savefig(save_path, bbox_inches='tight')
            _logger.info(f"Uptime.generate_weekly_uptime_graph(): Graph saved as {save_path}")

        plt.close()
        return str(save_path)

    async def command_uptime(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.calculate_hourly_uptime()

        graph_path = self.generate_weekly_uptime_graph()
        alltime_avg = self.get_alltime_avg()
        today_avg = self.get_today_avg()

        text = f"""
    System Status ✨

    Today Avg: {today_avg:.2f}%
    All Time Avg: {alltime_avg:.2f}%
    """

        if os.path.exists(graph_path):
            await update.message.reply_photo(
                photo=open(graph_path, "rb"),
                caption=text
            )
            os.remove(graph_path)
            _logger.info(f"Uptime.command_uptime(): Removed path {graph_path}")
        else:
            await update.message.reply_text("No uptime data yet.")

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