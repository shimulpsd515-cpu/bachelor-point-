import os
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from telegram.error import TelegramError

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8254834483:AAGXikQMaGCzyh1HuZh5B1iymo0BXYqtXF0")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "7200936473"))
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003884329619"))
MONETAG_SDK = os.environ.get("MONETAG_SDK", "show_10924924")

# In-memory video store: {list of (message_id, caption)}
video_list = []

# Pending users waiting for ad flow: {user_id: video_index}
pending_users = {}

# Ad flow state: {user_id: {"step": 1or2, "video_index": int, "message_id": int}}
ad_states = {}


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def get_ad_html(step: int, video_index: int) -> str:
    """Generate Monetag ad HTML page (step 1 = first ad, step 2 = second ad)."""
    continue_callback = f"ad_done_{video_index}_{step}"
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Loading...</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ background: #1a1a2e; color: white; font-family: Arial, sans-serif;
            display: flex; flex-direction: column; align-items: center;
            justify-content: center; min-height: 100vh; padding: 20px; }}
    .container {{ text-align: center; max-width: 400px; width: 100%; }}
    .logo {{ font-size: 28px; font-weight: bold; color: #00d4ff; margin-bottom: 10px; }}
    .sub {{ font-size: 14px; color: #aaa; margin-bottom: 30px; }}
    #adBox {{ width: 100%; min-height: 200px; background: #0f3460;
               border-radius: 12px; margin-bottom: 20px;
               display: flex; align-items: center; justify-content: center;
               overflow: hidden; }}
    #timer {{ font-size: 48px; font-weight: bold; color: #00d4ff; margin: 20px 0; }}
    #continueBtn {{ display: none; background: #00d4ff; color: #000;
                    border: none; padding: 15px 40px; border-radius: 30px;
                    font-size: 18px; font-weight: bold; cursor: pointer;
                    width: 100%; max-width: 300px; }}
    #continueBtn:hover {{ background: #00b8d9; }}
    .step-info {{ font-size: 12px; color: #666; margin-top: 15px; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="logo">🎬 Natok Hub</div>
    <div class="sub">ভিডিও লোড হচ্ছে...</div>
    <div id="adBox">
      <!-- Monetag Ad loads here -->
    </div>
    <div id="timer">15</div>
    <button id="continueBtn" onclick="continueAction()">✅ Continue করুন</button>
    <div class="step-info">ধাপ {step}/2</div>
  </div>

  <script>
    // Monetag SDK
    (function(d,z,s){{s.src='https://'+d+'/401/'+z;try{{(document.body||document.documentElement).appendChild(s)}}catch(e){{}}}})('{MONETAG_SDK}.monetag.io',{MONETAG_SDK.replace('show_', '')},document.createElement('script'));

    let seconds = 15;
    const timerEl = document.getElementById('timer');
    const btnEl = document.getElementById('continueBtn');

    const interval = setInterval(() => {{
      seconds--;
      timerEl.textContent = seconds;
      if (seconds <= 0) {{
        clearInterval(interval);
        timerEl.style.display = 'none';
        btnEl.style.display = 'block';
      }}
    }}, 1000);

    function continueAction() {{
      btnEl.disabled = true;
      btnEl.textContent = '⏳ অপেক্ষা করুন...';
      // Notify Telegram bot via deep link
      window.location.href = 'https://t.me/{{}}&start={continue_callback}';
    }}
  </script>
</body>
</html>"""


async def send_video_to_user(context: ContextTypes.DEFAULT_TYPE, user_id: int, video_index: int):
    """Forward video from channel to user."""
    if video_index < 0 or video_index >= len(video_list):
        await context.bot.send_message(user_id, "⚠️ ভিডিওটি পাওয়া যাচ্ছে না।")
        return

    msg_id, caption = video_list[video_index]
    try:
        await context.bot.forward_message(
            chat_id=user_id,
            from_chat_id=CHANNEL_ID,
            message_id=msg_id
        )
        await context.bot.send_message(
            user_id,
            f"✅ ভিডিও সফলভাবে পাঠানো হয়েছে!\n\n"
            f"📌 {caption}\n\n"
            f"⬆️ উপরের ভিডিওটি দেখুন বা ডাউনলোড করুন।"
        )
    except TelegramError as e:
        logger.error(f"Error forwarding video: {e}")
        await context.bot.send_message(user_id, "⚠️ ভিডিও পাঠাতে সমস্যা হয়েছে।")


# ─────────────────────────────────────────────
# COMMAND HANDLERS
# ─────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    # Handle ad completion deep link
    if args:
        param = args[0]
        if param.startswith("ad_done_"):
            parts = param.split("_")
            if len(parts) == 4:
                try:
                    video_index = int(parts[2])
                    step = int(parts[3])
                    if step == 1:
                        # Show second ad page
                        await show_ad_step(update, context, user.id, video_index, step=2)
                    elif step == 2:
                        # Both ads done, send video
                        await context.bot.send_message(
                            user.id,
                            "✅ সম্পন্ন! আপনার ভিডিও পাঠানো হচ্ছে..."
                        )
                        await send_video_to_user(context, user.id, video_index)
                    return
                except (ValueError, IndexError):
                    pass

    # Show video list
    await show_video_list(update, context)


async def show_video_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not video_list:
        await update.message.reply_text(
            "🎬 *Natok Hub বটে স্বাগতম!*\n\n"
            "এখনো কোনো ভিডিও আপলোড হয়নি।\n"
            "শীঘ্রই আসছে! 🔜",
            parse_mode="Markdown"
        )
        return

    keyboard = []
    for i, (msg_id, caption) in enumerate(video_list):
        short_caption = caption[:40] + "..." if len(caption) > 40 else caption
        keyboard.append([InlineKeyboardButton(
            f"🎬 {short_caption}",
            callback_data=f"watch_{i}"
        )])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🎬 *Natok Hub*\n\n"
        "নিচের তালিকা থেকে ভিডিও সিলেক্ট করুন:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def show_ad_step(update_or_query, context: ContextTypes.DEFAULT_TYPE,
                       user_id: int, video_index: int, step: int):
    """Send ad link as inline button."""
    bot_username = (await context.bot.get_me()).username
    ad_url = f"https://t.me/{bot_username}?start=ad_done_{video_index}_{step}"

    if step == 1:
        text = (
            "⏳ *ভিডিও প্রস্তুত হচ্ছে...*\n\n"
            "নিচের বাটনে ক্লিক করুন এবং ১৫ সেকেন্ড অপেক্ষা করুন।"
        )
    else:
        text = (
            "✅ *প্রায় শেষ!*\n\n"
            "আরেকটি ধাপ বাকি। নিচের বাটনে ক্লিক করুন।"
        )

    keyboard = [[InlineKeyboardButton("👉 এখানে ক্লিক করুন", url=ad_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if hasattr(update_or_query, 'message') and update_or_query.message:
        await update_or_query.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await context.bot.send_message(user_id, text, reply_markup=reply_markup, parse_mode="Markdown")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data.startswith("watch_"):
        video_index = int(data.split("_")[1])
        await query.edit_message_text("⏳ লোড হচ্ছে...")
        await show_ad_step(update, context, user_id, video_index, step=1)


# ─────────────────────────────────────────────
# CHANNEL POST HANDLER — Auto-sync videos
# ─────────────────────────────────────────────

async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Automatically add new videos from private channel."""
    post = update.channel_post
    if not post:
        return

    # Only handle from our channel
    if post.chat.id != CHANNEL_ID:
        return

    if post.video or post.document:
        caption = post.caption or post.text or f"ভিডিও #{len(video_list) + 1}"
        video_list.append((post.message_id, caption))
        logger.info(f"New video added: msg_id={post.message_id}, caption={caption[:30]}")

        # Notify admin
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"✅ নতুন ভিডিও যোগ হয়েছে!\n\n"
                f"📌 {caption[:50]}\n"
                f"📊 মোট ভিডিও: {len(video_list)}"
            )
        except TelegramError:
            pass


# ─────────────────────────────────────────────
# ADMIN COMMANDS
# ─────────────────────────────────────────────

async def admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not video_list:
        await update.message.reply_text("কোনো ভিডিও নেই।")
        return
    text = f"📊 মোট ভিডিও: {len(video_list)}\n\n"
    for i, (msg_id, caption) in enumerate(video_list):
        text += f"{i+1}. [{msg_id}] {caption[:40]}\n"
    await update.message.reply_text(text)


async def admin_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    video_list.clear()
    await update.message.reply_text("✅ সব ভিডিও মুছে ফেলা হয়েছে।")


async def admin_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually add video: /addvideo <message_id> <caption>"""
    if update.effective_user.id != ADMIN_ID:
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("ব্যবহার: /addvideo <message_id> <caption>")
        return
    try:
        msg_id = int(args[0])
        caption = " ".join(args[1:])
        video_list.append((msg_id, caption))
        await update.message.reply_text(f"✅ ভিডিও যোগ হয়েছে: {caption}")
    except ValueError:
        await update.message.reply_text("⚠️ সঠিক message_id দিন।")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", admin_list))
    app.add_handler(CommandHandler("clear", admin_clear))
    app.add_handler(CommandHandler("addvideo", admin_add))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & (filters.VIDEO | filters.Document.ALL),
        channel_post_handler
    ))

    logger.info("Bot started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
