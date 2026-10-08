import asyncio
import os
import logging
import time
import aiosqlite
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode, ChatAction
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiohttp import web

logging.basicConfig(level=logging.INFO)

# Aqoonsiga Bot-ka iyo Admin-ka
BOT_TOKEN = os.getenv("BOT_TOKEN")
try:
    MASTER_ADMIN = int(os.getenv("ADMIN_ID", 0))
except ValueError:
    MASTER_ADMIN = 0

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ==========================================
# 1. NIDAAMKA XAALADAHA (FSM)
# ==========================================
class AdminStates(StatesGroup):
    waiting_for_channel = State()
    waiting_for_block = State()
    waiting_for_unblock = State()
    waiting_for_broadcast = State()
    waiting_for_limit = State()
    waiting_for_start_msg = State()

# ==========================================
# 2. DATABASE (SQLite)
# ==========================================
async def init_db():
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users 
                            (user_id INTEGER PRIMARY KEY, downloads INTEGER DEFAULT 0, is_blocked BOOLEAN DEFAULT 0, last_active INTEGER DEFAULT 0)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS settings 
                            (key TEXT PRIMARY KEY, value TEXT)''')
        
        # Qoraalka soo dhaweynta ee asalka ah (Sidaad u dalbatay)
        default_welcome = (
            "👋 Welcome <b>{name}</b> to <b>VidClean HD</b>!\n\n"
            "Your premium tool to download TikTok videos in high quality, completely without watermarks. 🚀\n\n"
            "You can also subscribe to our channel to get the latest news about bot status and updates!\n"
            "📢 {channel}\n\n"
            "👇 <i>Please send your TikTok video link below to begin!</i>"
        )
        
        await db.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("force_channel", "@cadnaanchannel")')
        await db.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("download_limit", "3")')
        await db.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("total_links_downloaded", "0")')
        await db.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("welcome_text", ?)', (default_welcome,))
        await db.commit()

async def update_activity(user_id):
    current_time = int(time.time())
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
        await db.execute('UPDATE users SET last_active = ? WHERE user_id = ?', (current_time, user_id))
        await db.commit()

async def get_setting(key):
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT value FROM settings WHERE key = ?', (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

# ==========================================
# 3. WAJIGA ADMIN PANEL (Dashboard Command)
# ==========================================
async def get_dashboard_text():
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT COUNT(*) FROM users') as cursor:
            total_users = (await cursor.fetchone())[0]
        async with db.execute('SELECT COUNT(*) FROM users WHERE is_blocked = 1') as cursor:
            total_blocked = (await cursor.fetchone())[0]
        yesterday = int(time.time()) - 86400
        async with db.execute('SELECT COUNT(*) FROM users WHERE last_active > ?', (yesterday,)) as cursor:
            online_users = (await cursor.fetchone())[0]
            
    total_links = await get_setting("total_links_downloaded")
    dl_limit = await get_setting("download_limit")
    current_channel = await get_setting("force_channel")

    text = (
        "🤖 <b>Your Admin Dashboard</b>\n\n"
        f"👥 <b>Total Users:</b> {total_users}\n"
        f"🔗 <b>Total Links Processed:</b> {total_links}\n"
        f"🟢 <b>Online Users (24h):</b> {online_users}\n"
        f"🚫 <b>Blocked Users:</b> {total_blocked}\n\n"
        f"📢 <b>Channel:</b> {current_channel}\n"
        f"⚙️ <b>Current Limit:</b> {dl_limit} downloads"
    )
    return text

def get_dashboard_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 User Management", callback_data="adm_users")
    builder.button(text="📢 Add Channel", callback_data="adm_channel")
    builder.button(text="📝 Start Message", callback_data="adm_startmsg")
    builder.button(text="⚙️ Limits", callback_data="adm_limits")
    builder.button(text="✉️ Broadcast", callback_data="adm_broadcast")
    builder.button(text="🔄 Refresh", callback_data="adm_refresh")
    builder.adjust(1, 2, 2, 1) # Nidaaminta badhamada sidii website-ka
    return builder.as_markup()

@dp.message(Command("admin"))
async def admin_dashboard_cmd(message: types.Message):
    if message.from_user.id != MASTER_ADMIN:
        return
    text = await get_dashboard_text()
    await message.answer(text, reply_markup=get_dashboard_keyboard())

# --- Callbacks-ka Admin Panel-ka ---
@dp.callback_query(F.data == "adm_refresh")
async def refresh_dash(callback: types.CallbackQuery):
    if callback.from_user.id != MASTER_ADMIN: return
    text = await get_dashboard_text()
    try:
        await callback.message.edit_text(text, reply_markup=get_dashboard_keyboard())
    except:
        pass
    await callback.answer("✅ Refreshed")

@dp.callback_query(F.data == "adm_channel")
async def ask_channel(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != MASTER_ADMIN: return
    await callback.message.answer("Fadlan soo dir magaca channel-ka aad ku xirayso bot-ka (tusaale: @cadnaanchannel):")
    await state.set_state(AdminStates.waiting_for_channel)
    await callback.answer()

@dp.callback_query(F.data == "adm_users")
async def user_mgmt_menu(callback: types.CallbackQuery):
    if callback.from_user.id != MASTER_ADMIN: return
    builder = InlineKeyboardBuilder()
    builder.button(text="🚫 Block User", callback_data="adm_block")
    builder.button(text="✅ Unblock User", callback_data="adm_unblock")
    builder.adjust(2)
    await callback.message.answer("👥 <b>User Management</b>\nFadlan dooro tillaabada aad qaadayso:", reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "adm_block")
async def ask_block(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Fadlan soo dir ID-ga qofka aad Block saarayso:")
    await state.set_state(AdminStates.waiting_for_block)
    await callback.answer()

@dp.callback_query(F.data == "adm_unblock")
async def ask_unblock(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Fadlan soo dir ID-ga qofka aad Block-ga ka qaadayso:")
    await state.set_state(AdminStates.waiting_for_unblock)
    await callback.answer()

@dp.callback_query(F.data == "adm_broadcast")
async def ask_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != MASTER_ADMIN: return
    await callback.message.answer("Fadlan soo dir fariinta aad rabto in loo diro dadka oo dhan:")
    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.answer()

@dp.callback_query(F.data == "adm_limits")
async def ask_limit(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != MASTER_ADMIN: return
    await callback.message.answer("Fadlan soo dir tirada limit-ka cusub (tusaale: 3 ama 100):")
    await state.set_state(AdminStates.waiting_for_limit)
    await callback.answer()

@dp.callback_query(F.data == "adm_startmsg")
async def ask_welcome_text(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != MASTER_ADMIN: return
    info_text = (
        "Fadlan soo dir qoraalka cusub ee soo dhaweynta (/start).\n\n"
        "💡 <b>Talo:</b> Isticmaal tags-kan si otomaatig ah:\n"
        "<code>{name}</code> - Wuxuu isu beddelayaa magaca qofka.\n"
        "<code>{channel}</code> - Wuxuu isu beddelayaa channel-ka bot-ka."
    )
    await callback.message.answer(info_text)
    await state.set_state(AdminStates.waiting_for_start_msg)
    await callback.answer()

# --- Qabashada Qoraalada Admin-ka (FSM) ---
@dp.message(AdminStates.waiting_for_channel)
async def set_new_channel(message: types.Message, state: FSMContext):
    new_channel = message.text.strip()
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('UPDATE settings SET value = ? WHERE key = "force_channel"', (new_channel,))
        await db.commit()
    await message.answer(f"✅ Channel-ka cusub waa la xiray: {new_channel}")
    await state.clear()

@dp.message(AdminStates.waiting_for_block)
async def process_block(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        async with aiosqlite.connect('bot_database.db') as db:
            await db.execute('UPDATE users SET is_blocked = 1 WHERE user_id = ?', (int(message.text),))
            await db.commit()
        await message.answer(f"✅ User {message.text} waa la block-gareeyay.")
    else:
        await message.answer("❌ Fadlan ID sax ah soo dir (nambar).")
    await state.clear()

@dp.message(AdminStates.waiting_for_unblock)
async def process_unblock(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        async with aiosqlite.connect('bot_database.db') as db:
            await db.execute('UPDATE users SET is_blocked = 0 WHERE user_id = ?', (int(message.text),))
            await db.commit()
        await message.answer(f"✅ User {message.text} waa laga furay block-ga.")
    else:
        await message.answer("❌ Fadlan ID sax ah soo dir (nambar).")
    await state.clear()

@dp.message(AdminStates.waiting_for_broadcast)
async def process_broadcast(message: types.Message, state: FSMContext):
    success = 0
    await message.answer("⏳ Fariinta ayaa la dirayaa...")
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT user_id FROM users') as cursor:
            users = await cursor.fetchall()
            for user in users:
                try:
                    await bot.send_message(user[0], message.html_text)
                    success += 1
                    await asyncio.sleep(0.05)
                except:
                    pass
    await message.answer(f"✅ Fariinta waxa si guul ah u helay {success} qof.")
    await state.clear()

@dp.message(AdminStates.waiting_for_limit)
async def process_limit(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        async with aiosqlite.connect('bot_database.db') as db:
            await db.execute('UPDATE settings SET value = ? WHERE key = "download_limit"', (message.text,))
            await db.commit()
        await message.answer(f"✅ Limit-ka cusub waa: {message.text}")
    else:
        await message.answer("❌ Fadlan nambar keliya soo dir.")
    await state.clear()

@dp.message(AdminStates.waiting_for_start_msg)
async def process_welcome_text(message: types.Message, state: FSMContext):
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('UPDATE settings SET value = ? WHERE key = "welcome_text"', (message.html_text,))
        await db.commit()
    await message.answer("✅ Qoraalka soo dhaweynta si guul ah ayaa loo beddelay!")
    await state.clear()

# ==========================================
# 4. USER INTERFACE & TIKTOK DOWNLOADER
# ==========================================
@dp.message(CommandStart())
async def send_welcome(message: types.Message):
    user_id = message.from_user.id
    await update_activity(user_id)
    
    # Dirida Sticker-ka
    try:
        await message.answer_sticker("CAACAgIAAxkBAAE... (Geli ID-ga Sticker-kaaga halkan)")
    except:
        pass 
    
    current_channel = await get_setting("force_channel")
    raw_welcome = await get_setting("welcome_text")
    
    # Isku beddelka xogta
    welcome_text = raw_welcome.replace("{name}", message.from_user.first_name).replace("{channel}", current_channel)
    
    await message.answer(text=welcome_text)

@dp.message(F.text.contains("http"))
async def process_video(message: types.Message):
    user_id = message.from_user.id
    await update_activity(user_id)
    
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT is_blocked, downloads FROM users WHERE user_id = ?', (user_id,)) as cursor:
            user_data = await cursor.fetchone()
            
    if user_data and user_data[0] == 1: 
        return
        
    downloads = user_data[1] if user_data else 0
    limit = int(await get_setting("download_limit"))
    current_channel = await get_setting("force_channel")
    
    if downloads >= limit:
        builder = InlineKeyboardBuilder()
        clean_url = current_channel.replace('@', '')
        builder.button(text="✅ Subscribe", url=f"https://t.me/{clean_url}")
        limit_txt = (
            "⚠️ <b>Limit reached!</b>\n\n"
            f"Please subscribe to our channel below to continue using the bot.\n\n"
            f"📢 {current_channel}"
        )
        return await message.answer(limit_txt, reply_markup=builder.as_markup())

    # KALIYA Chat Action (Typing/Uploading Video) - Qoraal "sending a video" waa laga saaray
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_VIDEO)

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

            builder = InlineKeyboardBuilder()
            builder.button(text=f"❤️ {likes:,}", callback_data="noop")
            builder.button(text=f"👁 {views:,}", callback_data="noop")
            if music_url:
                builder.button(text="🎵 Get Sound", url=music_url)
            builder.adjust(2, 1)
            
            await bot.send_video(chat_id=message.chat.id, video=video_url, reply_markup=builder.as_markup())
            
            async with aiosqlite.connect('bot_database.db') as db:
                await db.execute('UPDATE users SET downloads = downloads + 1 WHERE user_id = ?', (user_id,))
                await db.execute('UPDATE settings SET value = CAST(value AS INTEGER) + 1 WHERE key = "total_links_downloaded"')
                await db.commit()
        else:
            await message.answer("❌ Invalid TikTok link. Please try again.")
            
    except Exception as e:
        await message.answer("❌ Server error. Please try again later.")

@dp.callback_query(F.data == "noop")
async def noop_callback(callback: types.CallbackQuery):
    await callback.answer()

# ==========================================
# 5. WEB SERVER (Render Background Fix)
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
    
    print("Bot is ready and running!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
