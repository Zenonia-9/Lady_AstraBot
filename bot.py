from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,filters, ContextTypes
from config import TELEGRAM_BOT_TOKEN, BOT_USERNAME, BOT_NAME, verify_tokens
from functions.manager import Manager, split_text
from features.AI import talk_back, summarize_text


manager = Manager()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    manager.upsert_user(user.id, user.username, user.full_name)

    await update.message.reply_text(
f"""Welcome {user.full_name}. I am {BOT_NAME}.

I am here to assist you with knowledge, guidance, and refined conversation.

Before we begin, you must request access using /userrequest.
Once approved, you may speak with me freely and use my features.

Use /help to see available commands."""
    )
    print(f'User({user.id}) in ({update.message.chat.type}) is sending /start.')

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    manager.upsert_user(user.id, user.username, user.full_name)
    await update.message.reply_text(
f"""I am {BOT_NAME} ✨ — here to chat, help, and guide you gracefully.
If you’re new here, don’t worry — I’ll show you how things work.

You can talk to me or use these commands:

/start - View introduction and usage instructions.

/help - View the list of available commands.

/userrequest - Request permission to chat with {BOT_NAME}.

/summarize - Summarize long text into clear insights.
Usage: /summarize <text>

/deletehistory - Delete your saved chat history (all, oldest, or newest messages)
""")
    print(f'User({update.effective_user.id}) in ({update.message.chat.type}) is sending /help.')

async def summarize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    manager.upsert_user(user.id, user.username, user.full_name)

    print(f'User({user.id}) request to summrize.')
    await update.message.chat.send_action(action="typing")

    if update.message.reply_to_message:
        # Case 1: User replied to a message
        original_text = update.message.reply_to_message.text
    else:
        # Case 2: User passed the text directly
        args = context.args
        if not args:
            print('Rejecting a summarize request because of wrong format!')
            await update.message.reply_text("Please either reply to a message or add the text like:\n/summarize your text here")
            return
        original_text = " ".join(args)

    await update.message.reply_text("🔍 Summarizing, please wait...")
    
    summary = await summarize_text(original_text)

    print('Bot replied!')
    await update.message.reply_text(f"📚 Summary:\n{summary}")

async def welcome_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for new_user in update.message.new_chat_members:
        user_id = str(new_user.id)
        username = new_user.username
        name = new_user.full_name

        print(user_id == str(context.bot.id))
        print(f'({user_id}) : ({str(context.bot.id)})')

        if user_id == str(context.bot.id):
            await context.bot.send_message(update.effective_chat.id, f"""🌸 Greetings. I am {BOT_NAME}.

I will be present here to offer guidance, knowledge, and composed conversation.

Those who wish to speak with me must first request access using /userrequest.

I look forward to observing this space."""
)
        else:
            manager.upsert_user(user_id, username, name)

            await update.message.reply_text(
                f"""🌸 Welcome {name}. Your presence has been noted.

Conduct yourself with respect and clarity, and you will find this space… pleasant.

If you wish to speak with me directly, you may request access using /userrequest.
"""
            )

async def goodbye_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.left_chat_member:
        name = update.message.left_chat_member.full_name
        user_id = update.message.left_chat_member.id

        manager.remove_user(user_id)
        
        await update.message.reply_text(
            f"""It seems someone has taken their leave.

May their path forward be steady and well chosen."""
        )

# Responds
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_type: str = update.message.chat.type

    user = update.effective_user

    user_id = str(user.id)
    full_name = user.full_name
    text: str = update.message.text
    
    manager.upsert_user(user_id, user.username, full_name)
    await update.message.chat.send_action(action="typing")
    if message_type in ["group", "supergroup"]:
        if '@'+BOT_USERNAME in text:
            new_text = text.replace('@'+BOT_USERNAME, '').strip()

            if manager.is_admin(update.effective_user.id):
                response = await talk_back(str(update.effective_chat.id), new_text, 'group')
            else:
                response = f"""Sorry {update.effective_user.full_name}, 
You do not currently have permission to speak with {BOT_NAME}.

Please send /userrequest to request access.
Approval is required before interaction is allowed."""
        else:
            return
    else:
        if manager.is_admin(update.message.chat.id):
            response = await talk_back(user_id, text)
        else:
            response: str = f"""Sorry {update.effective_user.full_name}, You do not currently have permission to speak with {BOT_NAME}.

Please send /userrequest to request access.
Approval is required before interaction is allowed."""
    
    if len(response) > 4000:
        print("Reply too long, splliting into chunks")

    for chunk in split_text(response):
        try:
            await update.message.reply_text(chunk, parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(chunk)  # fallback
            print(f"bot.handle_message(): Failed to send Telegram message: {e}\nbot.handle_message(): Send fallback plain text.")  

async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f'Update {update} caused error {context.error}')

# === Main app ===
def main():
    verify_tokens()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Add command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help))
    app.add_handler(CommandHandler("summarize", summarize_command))
    app.add_handler(CommandHandler("userrequest", manager.command_admin_request))
    app.add_handler(CallbackQueryHandler(manager.handle_admin_request, pattern="^(approve|reject):"))
    app.add_handler(CommandHandler("removeadmin", manager.command_remove_admin))
    app.add_handler(CallbackQueryHandler(manager.handle_remove_admin, pattern="^removeadmin:"))

    app.add_handler(CommandHandler("deletehistory", manager.command_delete_history))
    app.add_handler(CallbackQueryHandler(
        manager.handle_delete_choice,
        pattern="^del_(all|oldest|newest|cancel)$"
    ))

    app.add_handler(CallbackQueryHandler(
        manager.handle_delete_amount,
        pattern="^del_amount_|^del_back$"
    ))

    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_user))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, goodbye_user))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    app.add_error_handler(error)

    print(f"🤖 {BOT_NAME} is running... waiting for messages 💌")
    
    app.run_polling(poll_interval=5)

# === Run the bot ===
if __name__ == "__main__":
    main()
