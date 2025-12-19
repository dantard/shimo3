BOT_TOKEN = ""
import os
import re
import asyncio
from telegram import Update, Bot
from telegram.ext import Application, ContextTypes, MessageHandler, filters

# --- Configuration ---
AUTHORIZED_USERS = [
    2082486102,
    6416982
]

SAVE_DIR = "downloads"

# --- Global state ---
media_groups = {}

if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)


def sanitize_filename(text: str) -> str:
    """Sanitizes text for use as a filename base."""
    text = re.sub(r'[^\w\s-]', '', text).strip()
    text = re.sub(r'[-\s]+', '_', text)
    return text[:50] if text else "unnamed_media"


def run_bot(queue, token):
    """Entry point."""

    if BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("ERROR: Please update BOT_TOKEN")
        return

    builder = Application.builder()
    builder.token(BOT_TOKEN)
    builder.concurrent_updates(False)

    # Manually set job_queue to None before building
    builder._job_queue = None

    app = builder.build()

    async def process_media_group_delayed(chat_id: int, group_id: str, safe_name) -> None:
        """Process media group after delay using global bot reference."""
        await asyncio.sleep(1.0)

        group_data = media_groups.pop((chat_id, group_id), None)
        if not group_data:
            return

        buf = group_data.get('messages', [])
        if not buf:
            return

        saved_count = 0

        for msg, file, safe_name_base in buf:
            try:
                filename = f"{safe_name}_{msg.message_id}.jpg"
                path = os.path.join(SAVE_DIR, filename)
                await file.download_to_drive(path)
                saved_count += 1
                print(f"Successfully downloaded: {filename}")
            except Exception as e:
                print(f"ERROR downloading file {msg.message_id}: {e}")

        try:
            await app.bot.send_message(chat_id, f"✅ Saved {saved_count} photos from media group.")
        except Exception as e:
            print(f"ERROR sending confirmation: {e}")

    async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handles incoming commands.
        """
        msg = update.message
        user_id = msg.from_user.id
        if user_id not in AUTHORIZED_USERS:
            await msg.reply_text(f"🛑 Access Denied. Your user ID ({user_id}) is not authorized to use this bot.")
            print(f"ACCESS DENIED: User ID {user_id} attempted to use the bot.")
            return

        command = msg.text
        if command == "/start":
            await msg.reply_text("👋 Welcome! Send me photos or media groups, and I'll save them for you.")
        elif command == "/help":
            await msg.reply_text(
                "🤖 *Bot Commands:*\n"
                "/start - Start interaction with the bot\n"
                "/m <message> - Set a message to display on screen\n"
                "/reset - Clear the screen message\n"
                "/shuffle - Shuffle the image order\n"
                "/help - Show this help message",
                parse_mode='Markdown'
            )
        elif command.split(" ")[0] in ["/m", "/reset", "/shuffle"]:
            queue.put(command)
            await msg.reply_text(f"OK!")
        else:
            await msg.reply_text(f"❓ Unknown command: {command}")

    async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming photos."""
        msg = update.message

        if msg.from_user.id not in AUTHORIZED_USERS:
            await msg.reply_text(f"🛑 Access Denied. Your user ID ({msg.from_user.id}) is not authorized.")
            return

        group_id = msg.media_group_id
        caption = msg.caption or "unnamed"

        safe_name_base = sanitize_filename(caption)

        file = await msg.photo[-1].get_file()

        if group_id:
            key = (msg.chat_id, group_id)

            if key not in media_groups:
                media_groups[key] = {'messages': []}
                asyncio.create_task(process_media_group_delayed(msg.chat_id, group_id, safe_name_base))

            media_groups[key]['messages'].append((msg, file, safe_name_base))
        else:
            filename = f"{safe_name_base}_{msg.message_id}.jpg"
            path = os.path.join(SAVE_DIR, filename)

            try:
                await file.download_to_drive(path)
                await msg.reply_text(f"✅ Saved single photo as `{filename}`", parse_mode='Markdown')
            except Exception as e:
                await msg.reply_text(f"❌ Failed to save photo: {e}")

        queue.put(f"/shuffle") # forces shuffling when a photo is received


    # Add handler
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.COMMAND, handle_command))

    print("🤖 Bot is starting... Press Ctrl+C to stop.")

    try:
        app.run_polling()
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped.")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


#if __name__ == '__main__':
#     run_bot(None)