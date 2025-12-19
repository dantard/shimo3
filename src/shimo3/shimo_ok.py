import multiprocessing
import time

import pygame
import os
import random
import os
import re
import yaml
#from telegram import Update
#from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, Job

from pathlib import Path


def main():
    # load config
    try:
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"File config.yaml not found or corrupted")
        config = {}

    # bot_token: PASTE_YOUR_BOT_TOKEN_HERE
    # download_folder: downloads
    # delay: 1500
    # zoom_speed: 0.001
    # authorized_users:
    #     - 2082486102
    #     - 6416982
    # font_size: 60
    # show_remaining: True

    home_dir = os.path.expanduser("~")

    BOT_TOKEN = config.get("bot_token", "")
    FOLDER = config.get("download_folder", home_dir + os.sep + "shimo")
    DELAY_AFTER_ZOOM = config.get("delay", 1500)
    ZOOM_SPEED = config.get("zoom_speed", 0.001)
    hz = config.get("hz", 30)
    AUTHORIZED_USERS = config.get("authorized_users", [])
    font_size = config.get("font_size", 40)
    show_remaining = config.get("show_remaining", True)
    show_time = config.get("show_clock", True)

    # queue to communicate with the bot process
    queue = multiprocessing.Queue()

    # --- Global Buffer ---
    # Stores media groups that are still being assembled.
    # Key: (chat_id, group_id)
    # Value: List of tuples (message, file, safe_name_base)
    media_groups: dict[tuple[int, str], list[tuple[any, any, str]]] = {}

    # Ensure the save directory exists
    if not os.path.exists(FOLDER):
        os.makedirs(FOLDER)

    # --- Helper Function ---



    # --- Application Setup ---
    def run_bot() -> None:
        from telegram import Update
        from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, Job

        def sanitize_filename(text: str) -> str:
            """Sanitizes text for use as a filename base."""
            # Replace non-word characters (except spaces) with nothing
            text = re.sub(r'[^\w\s-]', '', text).strip()
            # Replace spaces with underscores
            text = re.sub(r'[-\s]+', '_', text)
            # Truncate to a reasonable length
            return text[:50] if text else "unnamed_media"

        # --- Job Queue Callback (Handles the processing after a delay) ---
        # FIX: The job queue passes the CallbackContext, not the Job object directly.
        async def process_media_group_job(context: ContextTypes.DEFAULT_TYPE) -> None:
            """
            Processes a complete media group after a short delay.
            This function is called by the job queue.
            """
            # Retrieve the job object from the context
            job = context.job
            if not job:
                print("ERROR: Job object not found in context.")
                return

            # Retrieve chat_id and group_id from the job data (now accessible via context.job.data)
            chat_id, group_id = job.data

            # Retrieve the bot instance directly from the context
            bot = context.bot

            # Pop the buffer, ensuring this group is not processed again.
            buf = media_groups.pop((chat_id, group_id), [])
            if not buf:
                # This can happen if the job runs but another job processed it already.
                print(f"DEBUG: Buffer for group {group_id} was empty.")
                return

            saved_count = 0
            file_group_name = ""
            for msg, file, safe_name_base in buf:
                if safe_name_base != "unnamed":
                    file_group_name = safe_name_base
                    break

            # Download all files in the collected buffer
            for msg, file, safe_name_base in buf:
                if file_group_name != "":
                    safe_name_base = file_group_name
                try:
                    # Construct a unique filename
                    filename = f"{safe_name_base}_{msg.message_id}.jpg"
                    path = os.path.join(FOLDER, filename)

                    # The 'file' object in the buffer is the File object fetched earlier.
                    await file.download_to_drive(path)
                    saved_count += 1
                    print(f"Successfully downloaded1: {filename}")
                except Exception as e:
                    print(f"ERROR downloading file {msg.message_id}: {e}")

            # Send a single confirmation message for the whole group
            await bot.send_message(chat_id, f"✅ Saved {saved_count} photos from media group (ID: {group_id}).")

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

        # --- Handler Function ---
        async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            """
            Handles incoming photos, buffering media groups and saving single photos immediately.
            """
            msg = update.message

            user_id = msg.from_user.id
            if user_id not in AUTHORIZED_USERS:
                # Inform the unauthorized user and stop processing
                await msg.reply_text(f"🛑 Access Denied. Your user ID ({user_id}) is not authorized to use this bot.")
                print(f"ACCESS DENIED: User ID {user_id} attempted to use the bot.")
                return
            #

            group_id = msg.media_group_id

            # Use the caption for the base name, default to "unnamed"
            caption = msg.caption or "unnamed"
            safe_name_base = sanitize_filename(caption)

            # Get the highest resolution file object
            # The photo list is sorted by size; [-1] is the largest.
            file = await msg.photo[-1].get_file()

            if group_id:
                # 1. Add the photo to the temporary buffer
                buf = media_groups.setdefault((msg.chat_id, group_id), [])
                buf.append((msg, file, safe_name_base))

                # 2. Schedule the processing job only when the FIRST photo arrives
                if len(buf) == 1:
                    # Schedule the job to run after 1 second (to allow time for all group members to arrive)
                    context.application.job_queue.run_once(
                        process_media_group_job,
                        1.0,  # Delay in seconds
                        data=(msg.chat_id, group_id),
                        name=f"media_group_{group_id}"
                    )

            else:
                # Handle single photos immediately
                filename = f"{safe_name_base}_{msg.message_id}.jpg"
                path = os.path.join(FOLDER, filename)

                try:
                    await file.download_to_drive(path)
                    await msg.reply_text(f"✅ Saved single photo as `{filename}`", parse_mode='Markdown')
                    print(f"Successfully downloaded single photo: {filename}")
                except Exception as e:
                    await msg.reply_text(f"❌ Failed to save photo: {e}")
                    print(f"ERROR downloading single photo {msg.message_id}: {e}")


        print("🤖 Bot is starting... Press Ctrl+C to stop.")
        # Includes job_queue by default for scheduling tasks
        app = ApplicationBuilder().token(BOT_TOKEN).build()

        # Add handler for photos (handles both single and media group photos)
        app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        app.add_handler(MessageHandler(filters.COMMAND, handle_command))

        # print("🤖 Bot is starting... Press Ctrl+C to stop.")
        app.run_polling()

    if not BOT_TOKEN:
        print("Bot token not set in config.yaml, NOT starting bot.")
    else:
        bot_process = multiprocessing.Process(target=run_bot)
        bot_process.start()

    pygame.init()
    screen = pygame.display.set_mode((800, 600), pygame.RESIZABLE)
    sw, sh = screen.get_size()
    font = pygame.font.SysFont(None, font_size)

    def load_image(path):
        """
        Carga una imagen, redimensiona si es demasiado grande según la pantalla
        y guarda el resultado en el mismo archivo.
        """
        # Inicializar pantalla temporal para obtener resolución
        pygame.init()
        info = pygame.display.Info()
        screen_width, screen_height = info.current_w, info.current_h

        img = pygame.image.load(path).convert_alpha()
        w, h = img.get_size()
        new_w, new_h = w, h

        # Determinar si hay que redimensionar según orientación
        if w >= h:  # horizontal
            if w > 2 * screen_width:
                new_w = screen_width
                new_h = int(h * (screen_width / w))
        else:  # vertical
            if h > 2 * screen_height:
                new_h = screen_height
                new_w = int(w * (screen_height / h))

        if (new_w, new_h) != (w, h):
            img = pygame.transform.smoothscale(img, (new_w, new_h))
            # Guardar imagen redimensionada con el mismo nombre
            pygame.image.save(img, path)

        return img

    def calc_target_scale(img):
        iw, ih = img.get_size()
        return max(sw / iw, sh / ih)

    def load_file_list():
        lst = []
        for f in os.listdir(FOLDER):
            p = Path(FOLDER) / f
            if p.suffix.lower() in [".jpg", ".jpeg", ".png", ".bmp", ".gif"]:
                lst.append(p)
        random.shuffle(lst)
        return lst

    files = load_file_list()
    while len(files) == 0:
        print(f"No images found in {FOLDER}. Waiting...")
        time.sleep(5)
        files = load_file_list()

    index = 0
    shown_count = 1
    total_count = len(files)

    current_img = load_image(str(files[index]))
    zoom_scale = 0.3
    target_scale = calc_target_scale(current_img)
    zoom_done_time = None

    clock = pygame.time.Clock()
    running = True
    message = ""
    force_reload = False
    forward = False

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_RIGHT:
                forward = True
            if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                force_reload = True


        if zoom_scale < target_scale and not forward:
            zoom_scale += ZOOM_SPEED * clock.get_time()
            if zoom_scale > target_scale:
                zoom_scale = target_scale
                zoom_done_time = pygame.time.get_ticks()
        else:
            if forward or (zoom_done_time and pygame.time.get_ticks() - zoom_done_time > DELAY_AFTER_ZOOM):
                forward = False
                index += 1
                shown_count += 1
                if index >= len(files) or force_reload:
                    force_reload = False
                    files = load_file_list()
                    total_count = len(files)
                    index = 0
                    shown_count = 1
                current_img = load_image(str(files[index]))
                zoom_scale = 0.3
                target_scale = calc_target_scale(current_img)
                zoom_done_time = None

        iw, ih = current_img.get_size()
        new_size = (int(iw * zoom_scale), int(ih * zoom_scale))
        scaled = pygame.transform.smoothscale(current_img, new_size)

        x = (sw - new_size[0]) // 2
        y = (sh - new_size[1]) // 2

        screen.fill((0, 0, 0))
        screen.blit(scaled, (x, y))
        name = files[index].name
        if name.startswith("unnamed_"):
            name = ""
        else:
            name = name.split("_")[0]

        filename_text = font.render(name, True, (255, 255, 255))
        screen.blit(filename_text, (20, 20))
        if show_remaining:
            counter_text = font.render(f"{shown_count}/{total_count}", True, (255, 255, 255))
            screen.blit(counter_text, (sw - counter_text.get_width() - 20, sh - counter_text.get_height() - 20))

        if show_time:
            t = time.localtime()
            current_time = time.strftime("%H:%M", t)
            time_text = font.render(current_time, True, (255, 255, 255))
            screen.blit(time_text, (sw - time_text.get_width() - 20, 20))

        if queue.qsize() > 0:
            fields = queue.get().split(" ")
            command = fields[0]
            text = " ".join(fields[1:])
            if command == "/m":
                message = text
            elif command == "/reset":
                message = ""
            elif command == "/shuffle":
                force_reload = True  # force reload

        hola_text = font.render(message, True, (255, 255, 255))
        hx = 20
        hy = sh - hola_text.get_height() - 20
        screen.blit(hola_text, (hx, hy))

        pygame.display.flip()
        clock.tick(hz)

    pygame.quit()

if __name__ == "__main__":
    main()