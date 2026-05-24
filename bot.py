import os
import asyncio
import logging
from datetime import datetime, timedelta
from aiohttp import web
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
PORT = int(os.environ.get("PORT", "8080"))
BASE_URL = os.environ.get("BASE_URL", "")
DIRECT_LINK = "https://omg10.com/4/11025392"

video_list = []
SESSION_TIMEOUT_HOURS = 2

# ✅ User tracker — সব user এখানে রাখা হবে
# { user_id: {"last_active": datetime, "message_ids": [], "name": ""} }
user_sessions = {}
all_users = {}  # কখনো delete হবে না — total count এর জন্য


def ad_page_html(step, video_index, bot_username):
    if step == 1:
        next_url = f"{BASE_URL}/ad?step=2&v={video_index}&bot={bot_username}"
    else:
        next_url = f"https://t.me/{bot_username}?start=done_{video_index}"

    return f"""<!DOCTYPE html>
<html lang="bn">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Natok Hub</title>
  <style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:white;font-family:'Segoe UI',Arial,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center}}
    .card{{background:rgba(255,255,255,0.07);backdrop-filter:blur(10px);border:1px solid rgba(255,255,255,0.15);border-radius:20px;padding:30px 20px;max-width:400px;width:95%;text-align:center;box-shadow:0 8px 32px rgba(0,0,0,0.4)}}
    .logo{{font-size:30px;font-weight:900;color:#00d4ff;margin-bottom:4px}}
    .tagline{{font-size:13px;color:#aaa;margin-bottom:16px}}
    .step-badge{{display:inline-block;background:rgba(0,212,255,0.2);border:1px solid #00d4ff;color:#00d4ff;border-radius:20px;padding:4px 14px;font-size:12px;margin-bottom:16px}}
    .progress-bar{{width:100%;height:5px;background:rgba(255,255,255,0.1);border-radius:3px;margin-bottom:14px;overflow:hidden}}
    .progress-fill{{height:100%;background:#00d4ff;border-radius:3px;transition:width 1s linear}}
    #timer{{font-size:56px;font-weight:900;color:#00d4ff;margin:8px 0;text-shadow:0 0 20px rgba(0,212,255,0.5)}}
    #msg{{font-size:14px;color:#ccc;margin-bottom:14px}}
    #continueBtn{{display:none;width:100%;padding:16px;background:linear-gradient(135deg,#00d4ff,#0099cc);color:#000;border:none;border-radius:30px;font-size:18px;font-weight:700;cursor:pointer;margin-top:10px}}
    #continueBtn:active{{transform:scale(0.97)}}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">🎬 Natok Hub</div>
    <div class="tagline">আপনার প্রিয় নাটক একটাই জায়গায়</div>
    <div class="step-badge">ধাপ {step} / 2</div>
    <div class="progress-bar"><div class="progress-fill" id="pf" style="width:100%"></div></div>
    <div id="timer">5</div>
    <div id="msg">অপেক্ষা করুন...</div>
    <button id="continueBtn" onclick="goNext()">✅ Continue করুন →</button>
  </div>
  <script>
    const iframe = document.createElement('iframe');
    iframe.src = '{DIRECT_LINK}';
    iframe.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;border:none;z-index:9999;';
    document.body.appendChild(iframe);
    let t = 5;
    const tv = document.getElementById('timer');
    const mv = document.getElementById('msg');
    const bv = document.getElementById('continueBtn');
    const pv = document.getElementById('pf');
    const iv = setInterval(() => {{
      t--;
      tv.textContent = t;
      pv.style.width = (t / 5 * 100) + '%';
      if (t <= 0) {{
        clearInterval(iv);
        iframe.remove();
        tv.style.display = 'none';
        mv.style.display = 'none';
        bv.style.display = 'block';
      }}
    }}, 1000);
    function goNext() {{
      bv.disabled = true;
      bv.textContent = '⏳ লোড হচ্ছে...';
      window.location.href = '{next_url}';
    }}
  </script>
</body>
</html>"""


async def handle_ad(request):
    step = int(request.rel_url.query.get("step", "1"))
    video_index = int(request.rel_url.query.get("v", "0"))
    bot_username = request.rel_url.query.get("bot", "")
    html = ad_page_html(step, video_index, bot_username)
    return web.Response(text=html, content_type="text/html")


async def handle_health(request):
    return web.Response(text="Natok Hub Bot is running!")


# ✅ User track করার function
def track_user(user_id, message_id, name=""):
    # সব user এর record রাখি
    if user_id not in all_users:
        all_users[user_id] = {"name": name, "joined": datetime.now()}

    # Active session track
    if user_id not in user_sessions:
        user_sessions[user_id] = {"last_active": datetime.now(), "message_ids": []}
    user_sessions[user_id]["last_active"] = datetime.now()
    user_sessions[user_id]["message_ids"].append(message_id)


# ✅ ২ ঘন্টা পরে auto reset
async def auto_reset_task(bot):
    while True:
        await asyncio.sleep(1800)  # ৩০ মিনিট পরপর চেক
        now = datetime.now()
        timeout = timedelta(hours=SESSION_TIMEOUT_HOURS)

        for user_id, data in list(user_sessions.items()):
            if now - data["last_active"] >= timeout:
                try:
                    # পুরনো message delete করো
                    for msg_id in data["message_ids"]:
                        try:
                            await bot.delete_message(chat_id=user_id, message_id=msg_id)
                        except Exception:
                            pass

                    # নতুন বাটন পাঠাও
                    await bot.send_message(
                        chat_id=user_id,
                        text="🔄 *সেশন শেষ হয়েছে!*\n\nনতুন ভিডিও দেখতে নিচের বাটনে চাপ দিন 👇",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🎬 ভিডিও লিস্ট দেখুন", callback_data="refresh_list")
                        ]])
                    )
                    del user_sessions[user_id]
                    logger.info(f"✅ Reset: {user_id}")

                except TelegramError as e:
                    logger.error(f"Reset error {user_id}: {e}")


async def start(update, context):
    args = context.args
    user = update.effective_user
    user_id = user.id
    name = user.full_name or ""

    if args and args[0].startswith("done_"):
        try:
            video_index = int(args[0].split("_")[1])
            sent = await update.message.reply_text("✅ সম্পন্ন! ভিডিও পাঠানো হচ্ছে...")
            track_user(user_id, sent.message_id, name)
            await send_video_to_user(context, user_id, video_index)
        except (ValueError, IndexError):
            await show_video_list(update, context)
        return

    await show_video_list(update, context)


async def show_video_list(update, context):
    user = update.effective_user
    user_id = user.id
    name = user.full_name or ""

    if not video_list:
        sent = await update.message.reply_text(
            "🎬 *Natok Hub বটে স্বাগতম!*\n\nএখনো কোনো ভিডিও আপলোড হয়নি।\nশীঘ্রই আসছে! 🔜",
            parse_mode="Markdown"
        )
        track_user(user_id, sent.message_id, name)
        return

    keyboard = []
    for i, (msg_id, caption) in enumerate(video_list):
        short = caption[:45] + "..." if len(caption) > 45 else caption
        keyboard.append([InlineKeyboardButton(f"🎬 {short}", callback_data=f"watch_{i}")])

    sent = await update.message.reply_text(
        "🎬 *Natok Hub*\n\nনিচের তালিকা থেকে নাটক সিলেক্ট করুন:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    track_user(user_id, sent.message_id, name)


async def button_handler(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "refresh_list":
        if not video_list:
            await query.edit_message_text("এখনো কোনো ভিডিও নেই। পরে আসুন!")
            return
        keyboard = []
        for i, (msg_id, caption) in enumerate(video_list):
            short = caption[:45] + "..." if len(caption) > 45 else caption
            keyboard.append([InlineKeyboardButton(f"🎬 {short}", callback_data=f"watch_{i}")])
        await query.edit_message_text(
            "🎬 *Natok Hub*\n\nনিচের তালিকা থেকে নাটক সিলেক্ট করুন:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return

    if data.startswith("watch_"):
        video_index = int(data.split("_")[1])
        bot_username = (await context.bot.get_me()).username
        ad_url = f"{BASE_URL}/ad?step=1&v={video_index}&bot={bot_username}"
        await query.edit_message_text(
            "⏳ *ভিডিও প্রস্তুত হচ্ছে...*\n\nনিচের বাটনে ক্লিক করুন:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("👉 ভিডিও পাবেন এখানে চাপ দিন", url=ad_url)
            ]]),
            parse_mode="Markdown"
        )


async def send_video_to_user(context, user_id, video_index):
    if video_index < 0 or video_index >= len(video_list):
        await context.bot.send_message(user_id, "⚠️ ভিডিওটি পাওয়া যাচ্ছে না।")
        return
    msg_id, caption = video_list[video_index]
    try:
        fwd = await context.bot.forward_message(
            chat_id=user_id, from_chat_id=CHANNEL_ID, message_id=msg_id
        )
        track_user(user_id, fwd.message_id)

        sent = await context.bot.send_message(
            user_id,
            f"✅ *{caption}*\n\nনতুন ভিডিও/অন্য বাকিগুলা দেখতে আবারে /start ক্লিক করুন 🎬",
            parse_mode="Markdown"
        )
        track_user(user_id, sent.message_id)

    except TelegramError as e:
        logger.error(f"Forward error: {e}")
        await context.bot.send_message(user_id, "⚠️ ভিডিও পাঠাতে সমস্যা হয়েছে।")


async def channel_post_handler(update, context):
    post = update.channel_post
    if not post or post.chat.id != CHANNEL_ID:
        return
    if post.video or post.document:
        caption = post.caption or post.text or f"নাটক #{len(video_list) + 1}"
        video_list.append((post.message_id, caption))
        logger.info(f"Video added: {caption[:30]}")
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"✅ নতুন ভিডিও যোগ হয়েছে!\n📌 {caption[:50]}\n📊 মোট: {len(video_list)}"
            )
        except TelegramError:
            pass


async def admin_list(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    if not video_list:
        await update.message.reply_text("কোনো ভিডিও নেই।")
        return
    text = f"📊 মোট ভিডিও: {len(video_list)}\n\n"
    for i, (msg_id, caption) in enumerate(video_list):
        text += f"{i+1}. {caption[:40]}\n"
    await update.message.reply_text(text)


async def admin_clear(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    video_list.clear()
    await update.message.reply_text("✅ সব ভিডিও মুছে ফেলা হয়েছে।")


async def admin_add(update, context):
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


# ✅ নতুন /stats কমান্ড — শুধু admin দেখতে পাবে
async def admin_stats(update, context):
    if update.effective_user.id != ADMIN_ID:
        return

    total = len(all_users)
    active_now = len(user_sessions)
    now = datetime.now()
    last_1h = sum(
        1 for d in user_sessions.values()
        if now - d["last_active"] <= timedelta(hours=1)
    )

    text = (
        f"📊 *বট স্ট্যাটিস্টিক্স*\n\n"
        f"👥 মোট User: *{total}* জন\n"
        f"🟢 এখন Active Session: *{active_now}* জন\n"
        f"⏱ শেষ ১ ঘন্টায় Active: *{last_1h}* জন\n"
        f"🎬 মোট ভিডিও: *{len(video_list)}* টি"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def main():
    web_app = web.Application()
    web_app.router.add_get("/ad", handle_ad)
    web_app.router.add_get("/", handle_health)
    web_app.router.add_get("/health", handle_health)
    runner = web.AppRunner(web_app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    logger.info(f"Web server on port {PORT}")

    bot_app = Application.builder().token(BOT_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("list", admin_list))
    bot_app.add_handler(CommandHandler("clear", admin_clear))
    bot_app.add_handler(CommandHandler("addvideo", admin_add))
    bot_app.add_handler(CommandHandler("stats", admin_stats))  # ✅ নতুন
    bot_app.add_handler(CallbackQueryHandler(button_handler))
    bot_app.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & (filters.VIDEO | filters.Document.ALL),
        channel_post_handler
    ))

    await bot_app.initialize()
    await bot_app.start()

    # ✅ Background task
    asyncio.create_task(auto_reset_task(bot_app.bot))

    await bot_app.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )
    logger.info("Bot started!")

    try:
        await asyncio.Event().wait()
    finally:
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
