import asyncio
import os
import logging
import aiosqlite
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0)) 

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ==========================================
# 1. DATABASE (SQLite) - Xogta Macaamiisha
# ==========================================
async def init_db():
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users 
                            (user_id INTEGER PRIMARY KEY, downloads INTEGER DEFAULT 0, is_blocked BOOLEAN DEFAULT 0, is_premium BOOLEAN DEFAULT 0)''')
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT downloads, is_blocked, is_premium FROM users WHERE user_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone()

# ==========================================
# 2. ADMIN PANEL (Website-style Features)
# ==========================================
@dp.message(Command("admin"))
async def admin_dashboard(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT COUNT(*), SUM(downloads) FROM users') as cursor:
            data = await cursor.fetchone()
            total_users = data[0]
            total_downloads = data[1] if data[1] else 0

    text = (
        "👑 <b>VidClean HD - Admin Dashboard</b>\n\n"
        f"👥 <b>Total Users:</b> {total_users}\n"
        f"📥 <b>Total Downloads:</b> {total_downloads}\n\n"
        "<b>🛠 Admin Commands:</b>\n"
        "<code>/broadcast fariintaada</code> - Send msg to all\n"
        "<code>/block UserID</code> - Block a user\n"
        "<code>/unblock UserID</code> - Unblock a user"
    )
    await message.answer(text)

@dp.message(Command("broadcast"))
async def broadcast_msg(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    msg_text = message.text.replace("/broadcast ", "")
    if msg_text == "/broadcast":
        return await message.answer("Fadlan raaci fariinta: /broadcast salaam!")
    
    success = 0
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT user_id FROM users') as cursor:
            users = await cursor.fetchall()
            for user in users:
                try:
                    await bot.send_message(user[0], f"📢 <b>Admin Message:</b>\n\n{msg_text}")
                    success += 1
                except:
                    pass
    await message.answer(f"✅ Message sent to {success} users.")

@dp.message(Command("block"))
async def block_user(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        target_id = int(message.text.split(" ")[1])
        async with aiosqlite.connect('bot_database.db') as db:
            await db.execute('UPDATE users SET is_blocked = 1 WHERE user_id = ?', (target_id,))
            await db.commit()
        await message.answer(f"🚫 User {target_id} has been blocked.")

# ==========================================
# 3. USER INTERFACE (Wajiga Macmiilka)
# ==========================================
@dp.message(CommandStart())
async def send_welcome(message: types.Message):
    user_id = message.from_user.id
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
        await db.commit()

    # Naqshadda Casriga ah ee aad dalbatay
    builder = InlineKeyboardBuilder()
    builder.button(text="📢 Join Channel", url="https://t.me/YourChannel")
    builder.button(text="👑 Buy Premium", callback_data="buy_prem")
    builder.button(text="🆘 Help", callback_data="help")
    builder.adjust(1, 2)

    welcome_text = (
        f"🤖 <b>Welcome to No Watermark Downloader, {message.from_user.first_name}!</b>\n\n"
        "This bot allows you to download videos from TikTok <b>without watermark</b>.\n\n"
        "👇 <i>Just send any video link below to get started!</i>"
    )
    await message.answer("https://t.me/telegram/183", text=welcome_text, reply_markup=builder.as_markup()) # Replace with your sticker ID if needed

# ==========================================
# 4. TIKTOK DOWNLOADER (Free API & Likes/Views)
# ==========================================
@dp.message(F.text.contains("tiktok.com"))
async def process_tiktok(message: types.Message):
    user_id = message.from_user.id
    user_data = await get_user(user_id)
    
    if user_data and user_data[1] == 1: # Haddii uu Block yahay
        return await message.answer("🚫 You are blocked from using this bot.")
        
    downloads = user_data[0] if user_data else 0
    if downloads >= 3 and not (user_data and user_data[2]): # Limits Rule
        return await message.answer("⚠️ <b>Free limit reached (3/3)!</b>\nPlease Join our channel to continue.")

    status_msg = await message.answer("🔄 <i>>> sending a video...</i>")

    # Wacida API-ga Bilaashka ah (TikWM)
    api_url = f"https://www.tikwm.com/api/?url={message.text}&hd=1"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(api_url) as response:
            data = await response.json()

    if data.get("code") == 0: # Haddii muuqaalka la helay
        video_url = data["data"]["play"]
        music_url = data["data"]["music"]
        likes = data["data"]["digg_count"]
        views = data["data"]["play_count"]

        # Naqshadda Badhamada Likes/Views ee aad dalbatay
        builder = InlineKeyboardBuilder()
        builder.button(text=f"❤️ {likes:,}", callback_data="none")
        builder.button(text=f"👁 {views:,}", callback_data="none")
        builder.button(text="🎵 Get Sound", url=music_url)
        builder.adjust(2, 1)

        await bot.send_video(chat_id=message.chat.id, video=video_url, reply_markup=builder.as_markup())
        await status_msg.delete()
        
        # Kordhi tirada (Downloads)
        async with aiosqlite.connect('bot_database.db') as db:
            await db.execute('UPDATE users SET downloads = downloads + 1 WHERE user_id = ?', (user_id,))
            await db.commit()
    else:
        await status_msg.edit_text("❌ Error downloading video. Check the link.")

# ==========================================
# 5. DUMMY WEB SERVER (Xalka Render)
# ==========================================
async def health_check(request):
    return web.Response(text="Bot is online!")

async def main():
    await init_db()
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get('PORT', 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    print("Bot is ready and running!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
