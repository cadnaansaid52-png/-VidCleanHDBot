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

# Nidaamka diiwaangelinta xaaladda bot-ka
logging.basicConfig(level=logging.INFO)

# Aqoonsiga Bot-ka iyo Admin-ka
BOT_TOKEN = os.getenv("BOT_TOKEN")
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
except ValueError:
    ADMIN_ID = 0

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ==========================================
# 1. DATABASE-KA (SQLite) - Xafidida Xogta
# ==========================================
async def init_db():
    async with aiosqlite.connect('bot_database.db') as db:
        # Miiska Macaamiisha
        await db.execute('''CREATE TABLE IF NOT EXISTS users 
                            (user_id INTEGER PRIMARY KEY, downloads INTEGER DEFAULT 0, is_blocked BOOLEAN DEFAULT 0, is_premium BOOLEAN DEFAULT 0)''')
        # Miiska Xogta Bot-ka (Sida Channel-ka lagu xirayo)
        await db.execute('''CREATE TABLE IF NOT EXISTS settings 
                            (key TEXT PRIMARY KEY, value TEXT)''')
        # Geli Channel asalka ah haddii uusan jirin
        await db.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("force_channel", "None")')
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT downloads, is_blocked, is_premium FROM users WHERE user_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone()

async def get_setting(key):
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT value FROM settings WHERE key = ?', (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

# ==========================================
# 2. ADMIN PANEL (Awoodahaaga Gaarka ah)
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
            
    current_channel = await get_setting("force_channel")

    text = (
        "👑 <b>VidClean HD - Admin Dashboard</b>\n\n"
        f"👥 <b>Total Users:</b> {total_users}\n"
        f"📥 <b>Total Downloads:</b> {total_downloads}\n"
        f"📢 <b>Current Channel:</b> {current_channel}\n\n"
        "<b>🛠 Admin Commands (Sida Loo Isticmaalo):</b>\n"
        "<code>/setchannel @ChannelUsername</code> - (Ku xir channel-ka cusub)\n"
        "<code>/addpremium UserID</code> - (Qofka ka dhig Premium)\n"
        "<code>/broadcast fariintaada</code> - (Fariin u dir dadka dhan)\n"
        "<code>/block UserID</code> - (Qofka ka xiro bot-ka)\n"
        "<code>/unblock UserID</code> - (Qofka ka fur bot-ka)"
    )
    await message.answer(text)

@dp.message(Command("setchannel"))
async def set_channel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("❌ Fadlan raaci magaca channel-ka: /setchannel @Magaca")
    
    new_channel = args[1]
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('UPDATE settings SET value = ? WHERE key = "force_channel"', (new_channel,))
        await db.commit()
    await message.answer(f"✅ Channel-ka cusub ee dadka lagu qasbayo waa: {new_channel}\n\n(Fiiro gaar ah: Waa in bot-ku uu Admin ka yahay channel-kaas si uu u hubiyo in dadku ku biireen!)")

@dp.message(Command("addpremium"))
async def add_premium(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        target_id = int(message.text.split()[1])
        async with aiosqlite.connect('bot_database.db') as db:
            await db.execute('UPDATE users SET is_premium = 1 WHERE user_id = ?', (target_id,))
            await db.commit()
        await message.answer(f"✅ User {target_id} is now Premium (Unlimited Downloads).")
    except:
        await message.answer("❌ Qalad: Fadlan raaci User ID sax ah. Tusaale: /addpremium 12345")

@dp.message(Command("broadcast"))
async def broadcast_msg(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    msg_text = message.text.replace("/broadcast", "").strip()
    if not msg_text:
        return await message.answer("❌ Fadlan raaci fariinta: /broadcast Salaan dhamaantiin!")
    
    success = 0
    await message.answer("⏳ Fariinta ayaa la dirayaa...")
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT user_id FROM users') as cursor:
            users = await cursor.fetchall()
            for user in users:
                try:
                    await bot.send_message(user[0], f"📢 <b>Admin Message:</b>\n\n{msg_text}")
                    success += 1
                    await asyncio.sleep(0.05) # Si aanu Telegram inoo xannibin xawaaraha darteed
                except:
                    pass
    await message.answer(f"✅ Fariinta waxa si guul ah u helay {success} qof.")

@dp.message(Command("block"))
async def block_user(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        target_id = int(message.text.split()[1])
        async with aiosqlite.connect('bot_database.db') as db:
            await db.execute('UPDATE users SET is_blocked = 1 WHERE user_id = ?', (target_id,))
            await db.commit()
        await message.answer(f"🚫 User {target_id} waa la block-gareeyay.")
    except:
        await message.answer("❌ Qalad: /block UserID")

@dp.message(Command("unblock"))
async def unblock_user(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        target_id = int(message.text.split()[1])
        async with aiosqlite.connect('bot_database.db') as db:
            await db.execute('UPDATE users SET is_blocked = 0 WHERE user_id = ?', (target_id,))
            await db.commit()
        await message.answer(f"✅ User {target_id} waa laga furay block-ga.")
    except:
        pass

# ==========================================
# 3. USER INTERFACE (Wajiga Macmiilka)
# ==========================================
@dp.message(CommandStart())
async def send_welcome(message: types.Message):
    user_id = message.from_user.id
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
        await db.commit()

    current_channel = await get_setting("force_channel")
    channel_url = f"https://t.me/{current_channel.replace('@', '')}" if current_channel != "None" else "https://t.me/telegram"

    # Naqshadda Casriga ah
    builder = InlineKeyboardBuilder()
    builder.button(text="📢 Join Channel", url=channel_url)
    builder.button(text="👑 Buy Premium", callback_data="buy_prem")
    builder.button(text="🆘 Help", callback_data="help")
    builder.adjust(1, 2)

    welcome_text = (
        f"🤖 <b>Welcome to VidClean HD, {message.from_user.first_name}!</b>\n\n"
        "This bot allows you to download videos from TikTok <b>without watermark</b>.\n\n"
        "👇 <i>Just send any video link below to get started!</i>"
    )
    
    # Halkan waa halkii ay ciladdu kaga jirtay koodhkii hore, hadda 100% way saxan tahay
    await message.answer(text=welcome_text, reply_markup=builder.as_markup())

@dp.callback_query(F.data == "buy_prem")
async def premium_info(callback: types.CallbackQuery):
    await callback.message.answer("🌟 <b>Buy Premium</b>\n\nFor $5/month, get unlimited downloads and no channel requirements!\nContact Admin to upgrade.")
    await callback.answer()

@dp.callback_query(F.data == "help")
async def help_info(callback: types.CallbackQuery):
    await callback.message.answer("💡 <b>How to use:</b>\n1. Go to TikTok.\n2. Click 'Share' -> 'Copy Link'.\n3. Paste the link here in the chat.")
    await callback.answer()

# ==========================================
# 4. TIKTOK DOWNLOADER (Free API & Likes/Views)
# ==========================================
@dp.message(F.text.contains("http"))
async def process_video(message: types.Message):
    user_id = message.from_user.id
    user_data = await get_user(user_id)
    
    # Haddii qofka la xiray
    if user_data and user_data[1] == 1: 
        return await message.answer("🚫 Waa lagaa xiray adeegsiga bot-kan.")
        
    downloads = user_data[0] if user_data else 0
    is_premium = user_data[2] if user_data else 0
    
    # Sharciga Limits-ka
    if downloads >= 3 and not is_premium:
        current_channel = await get_setting("force_channel")
        limit_txt = (
            "⚠️ <b>Free limit reached (3/3)!</b>\n\n"
            f"Fadlan ku biir channel-keena <b>{current_channel}</b> ama iibso Premium si aad usii isticmaasho bot-ka."
        )
        return await message.answer(limit_txt)

    # Fariinta soo-dejinta oo u eg tii sawirka
    status_msg = await message.answer("🔄 <i>>> sending a video...</i>")

    # Wacida API-ga TikWM
    api_url = f"https://www.tikwm.com/api/?url={message.text}&hd=1"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                data = await response.json()

        if data.get("code") == 0: 
            video_url = data["data"]["play"]
            music_url = data["data"].get("music", "")
            likes = data["data"].get("digg_count", 0)
            views = data["data"].get("play_count", 0)

            # Badhamada Likes, Views, Audio (Sida aad codsatay)
            builder = InlineKeyboardBuilder()
            builder.button(text=f"❤️ {likes:,}", callback_data="none")
            builder.button(text=f"👁 {views:,}", callback_data="none")
            if music_url:
                builder.button(text="🎵 Get Sound", url=music_url)
            builder.adjust(2, 1)

            # Dirida Muuqaalka
            await bot.send_video(chat_id=message.chat.id, video=video_url, reply_markup=builder.as_markup())
            await status_msg.delete()
            
            # Kordhi tirada (Downloads)
            async with aiosqlite.connect('bot_database.db') as db:
                await db.execute('UPDATE users SET downloads = downloads + 1 WHERE user_id = ?', (user_id,))
                await db.commit()
        else:
            await status_msg.edit_text("❌ Kani maaha Link sax ah oo TikTok ah, ama muuqaalku cilad buu leeyahay.")
            
    except Exception as e:
        await status_msg.edit_text("❌ Culeys ayaa ka jira server-ka soo-dejinta, fadlan isku day goor dhow.")

# ==========================================
# 5. DUMMY WEB SERVER (Xalka Render)
# ==========================================
async def health_check(request):
    return web.Response(text="VidClean HD Bot is running perfectly!")

async def main():
    await init_db()
    
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get('PORT', 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    print("VidClean HD is ready and running!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
