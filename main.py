import asyncio
import os
import logging
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiohttp import web

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0)) 

# Halkan ayaan ku saxnay isbeddelka cusub ee aiogram 3.7.0+
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- 1. NIDAAMKA DATABASE-KA (SQLite) ---
async def init_db():
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users 
                            (user_id INTEGER PRIMARY KEY, downloads INTEGER DEFAULT 0, is_premium BOOLEAN DEFAULT 0)''')
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT downloads, is_premium FROM users WHERE user_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone()

async def update_user_downloads(user_id):
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
        await db.execute('UPDATE users SET downloads = downloads + 1 WHERE user_id = ?', (user_id,))
        await db.commit()

# --- 2. ADMIN PANEL (Adiga Keliya) ---
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("❌ You are not authorized to use this command.")
    
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT COUNT(*) FROM users') as cursor:
            total_users = (await cursor.fetchone())[0]
            
    admin_text = (
        "🔧 <b>VidClean HD Admin Panel</b>\n\n"
        f"👥 Total Users: <b>{total_users}</b>\n"
        "<i>(More features like Broadcast & Force Sub setup will be added here)</i>"
    )
    await message.answer(admin_text)

# --- 3. WAJIGA MACMIILKA & LIMITS-KA ---
@dp.message(CommandStart())
async def command_start_handler(message: types.Message):
    sticker_id = "CAACAgIAAxkBAAE..." # Dib ayaad ka beddeli doontaa
    welcome_text = (
        f"Welcome <b>{message.from_user.full_name}</b>!\n\n"
        "I am your premium video downloader bot. "
        "Send me any video link (TikTok, Instagram, etc.) and I will download it for you in HD without a watermark. 📥"
    )
    try:
        await message.answer_sticker(sticker_id)
    except:
        pass
    await message.answer(welcome_text)

@dp.message(F.text.contains("http"))
async def process_video_link(message: types.Message):
    user_id = message.from_user.id
    
    # Hubi xogta macmiilka
    user_data = await get_user(user_id)
    if not user_data:
        async with aiosqlite.connect('bot_database.db') as db:
            await db.execute('INSERT INTO users (user_id) VALUES (?)', (user_id,))
            await db.commit()
        downloads, is_premium = 0, 0
    else:
        downloads, is_premium = user_data

    # Sharciga Limits-ka (3 Download)
    if downloads >= 3 and not is_premium:
        limit_text = (
            "⚠️ <b>Free limit reached (3/3)!</b>\n\n"
            "You have used your free video downloads. "
            "Please join our channel <b>@ChannelName</b> or buy Premium for $5/month to continue."
        )
        return await message.answer(limit_text)

    processing_msg = await message.answer("🔎 <i>Processing your video, please wait...</i>")
    
    # API Placeholder
    await asyncio.sleep(2) 
    
    # Kordhi tirada downloads-ka marka uu guulaysto
    await update_user_downloads(user_id)
    await processing_msg.edit_text("✅ Video downloaded successfully! (RapidAPI code goes here)")

# --- 4. DUMMY WEB SERVER (Xalka Render) ---
async def health_check(request):
    return web.Response(text="VidClean HD Bot is running securely!")

async def main():
    await init_db()
    
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get('PORT', 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    print("Bot and Dummy Web Server are running!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
                                 
