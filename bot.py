import os
import asyncio
import logging
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


async def handle_health(request):
    return web.Response(text="Natok Hub Bot is running!")


async def start(update, context):
    args = context.args
    if args and args[0].startswith("done_"):
        try:
            video_index = int(args[0].split("_")[1])
            await update.message.reply_text("✅ সম্পন্ন! ভিডিও পাঠানো হচ্ছে...")
            await send_video_to_user(context, update.effective_user.id, video_index)
        except (ValueError, IndexError):
            await show_video_list(update, context)
        return
    await show_video_list(update, context)


async def show_video_list(update, context):
    if not video_list:
        await update.message.reply_text(
            "🎬 *Natok Hub বটে স্বাগতম!*\n\nএখনো কোনো ভিডিও আপলোড হয়নি।\nশীঘ্রই আসছে! 🔜",
            parse_mode="Markdown"
        )
        return
    keyboard = []
    for i, (msg_id, caption) in enumerate(video_list):
        short = caption[:45] + "..." if len(caption) > 45 else caption
        keyboard.append([InlineKeyboardButton(f"🎬 {short}", callback_data=f"watch_{i}")])
    await update.message.reply_text(
        "🎬 *Natok Hub*\n\nনিচের তালিকা থেকে নাটক সিলেক্ট করুন:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def button_handler(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("watch_"):
        video_index = int(data.split("_")[1])
        await query.edit_message_text(
            "🎬 *ভিডিও পেতে ২টি ধাপ সম্পন্ন করুন*\n\n"
            "👇 প্রথমে নিচের বাটনে ক্লিক করুন:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👉 ধাপ ১: এখানে ক্লিক করুন", url=DIRECT_LINK)],
                [InlineKeyboardButton("✅ ধাপ ১ শেষ, এগিয়ে যান →", callback_data=f"step2_{video_index}")]
            ]),
            parse_mode="Markdown"
        )

    elif data.startswith("step2_"):
        video_index = int(data.split("_")[1])
        await query.edit_message_text(
            "✅ *ধাপ ১ সম্পন্ন!*\n\n"
            "👇 এখন ধাপ ২ সম্পন্ন করুন:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👉 ধাপ ২: এখানে ক্লিক করুন", url=DIRECT_LINK)],
                [InlineKeyboardButton("🎬 ভিডিও নিন →", callback_data=f"getvideo_{video_index}")]
            ]),
            parse_mode="Markdown"
        )

    elif data.startswith("getvideo_"):
        video_index = int(data.split("_")[1])
        await query.edit_message_text("✅ *ভিডিও পাঠানো হচ্ছে...*", parse_mode="Markdown")
        await send_video_to_user(context, query.from_user.id, video_index)


async def send_video_to_user(context, user_id, video_index):
    if video_index < 0 or video_index >= len(video_list):
        await context.bot.send_message(user_id, "⚠️ ভিডিওটি পাওয়া যাচ্ছে না।")
        return
    msg_id, caption = video_list[video_index]
    try:
        await context.bot.forward_message(chat_id=user_id, from_chat_id=CHANNEL_ID, message_id=msg_id)
        await context.bot.send_message(
            user_id,
            f"✅ *{caption}*\n\nউপরের ভিডিওটি দেখুন বা ডাউনলোড করুন! 🎬",
            parse_mode="Markdown"
        )
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


async def main():
    web_app = web.Application()
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
    bot_app.add_handler(CallbackQueryHandler(button_handler))
    bot_app.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & (filters.VIDEO | filters.Document.ALL),
        channel_post_handler
    ))
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
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
