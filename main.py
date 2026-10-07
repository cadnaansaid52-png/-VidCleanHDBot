import asyncio
import os
import logging
import time
import aiosqlite
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode, ChatAction
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiohttp import web

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
try:
    MASTER_ADMIN = int(os.getenv("ADMIN_ID", 0))
except ValueError:
    MASTER_ADMIN = 0

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Nidaamka Xaaladaha (FSM) ee Admin Panel-ka
class AdminStates(StatesGroup):
    waiting_for_channel = State()
    waiting_for_block = State()
    waiting_for_unblock = State()
    waiting_for_broadcast = State()
    waiting_for_limit = State()
    waiting_for_new_admin = State()

# ==========================================
# 1. DATABASE (SQLite)
# ==========================================
async def init_db():
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users 
                            (user_id INTEGER PRIMARY KEY, downloads INTEGER DEFAULT 0, is_blocked BOOLEAN DEFAULT 0, last_active INTEGER DEFAULT 0)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS settings 
                            (key TEXT PRIMARY KEY, value TEXT)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS admins 
                            (admin_id INTEGER PRIMARY KEY)''')
        
        await db.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("force_channel", "@cadnaanchannel")')
        await db.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("download_limit", "3")')
        await db.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("total_links_downloaded", "0")')
        await db.execute('INSERT OR IGNORE INTO admins (admin_id) VALUES (?)', (MASTER_ADMIN,))
        await db.commit()

async def is_admin(user_id):
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT admin_id FROM admins WHERE admin_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone() is not None

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
# 2. USER INTERFACE & DOWNLOADER
# ==========================================
@dp.message(CommandStart())
async def send_welcome(message: types.Message):
    user_id = message.from_user.id
    await update_activity(user_id)
    
    # 1. Soo dir Sticker (Haddii aad hayso ID sax ah ku beddel kan, haddii kale default emoji ayuu iska dirayaa)
    try:
        await message.answer_sticker("CAACAgIAAxkBAAE... (Ku beddel Sticker ID-gaaga)")
    except:
        pass # Wuu iska indha tirayaa haddii ID-gu yara qaldan yahay
    
    # 2. Badhanka Channel-ka ee la socda fariinta
    current_channel = await get_setting("force_channel")
    channel_url = f"https://t.me/{current_channel.replace('@', '')}"
    
    inline_kb = InlineKeyboardBuilder()
    inline_kb.button(text="📢 Join Channel", url=channel_url)
    
    # 3. Qoraalka soo dhaweynta oo gaaban
    welcome_text = (
        f"👋 Soo dhawoow <b>{message.from_user.first_name}</b>!\n\n"
        "Kani waa bot-kaaga rasmiga ah ee aad kala soo degi karto muuqaalada TikTok adigoon wax watermark ah lahayn. Soo dir link-ga si aan kuugu soo dejiyo!"
    )
    
    # 4. Hubi haddii qofku yahay Admin si loo siiyo badhanka (Feature-ka) Admin Panel
    if await is_admin(user_id):
        admin_kb = ReplyKeyboardBuilder()
        admin_kb.button(text="🛠 Admin Panel")
        
        await message.answer(text=welcome_text, reply_markup=inline_kb.as_markup())
        await message.answer("Awoodaha Admin-ka waxaad ka heli kartaa badhanka hoose 👇", reply_markup=admin_kb.as_markup(resize_keyboard=True))
    else:
        await message.answer(text=welcome_text, reply_markup=inline_kb.as_markup())

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
            "⚠️ <b>Limit-kii waad gaartay!</b>\n\n"
            f"Fadlan ku biir channel-keena hoose si aad u sii isticmaasho bot-ka.\n\n"
            f"📢 {current_channel}"
        )
        return await message.answer(limit_txt, reply_markup=builder.as_markup())

    # Chat Action: Wuxuu u ekaanayaa mid video soo diraya (Typing-ka baddalkiisa)
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

            # Badhamada Likes iyo Views dib baa loo soo celiyay
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
            await message.answer("❌ Fadlan soo dir link sax ah oo TikTok ah.")
            
    except Exception as e:
        await message.answer("❌ Culeys ayaa ka jira server-ka soo-dejinta, fadlan isku day goor dhow.")

# Si uusan error u dhicin marka qofku taabto badhanka Likes/Views
@dp.callback_query(F.data == "noop")
async def noop_callback(callback: types.CallbackQuery):
    await callback.answer()

# ==========================================
# 3. ADMIN PANEL (Feature Button)
# ==========================================
@dp.message(F.text == "🛠 Admin Panel")
async def admin_dashboard_btn(message: types.Message):
    if not await is_admin(message.from_user.id):
        return

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
        "👑 <b>VidClean HD - Admin Dashboard</b>\n\n"
        f"👥 <b>Total Users:</b> {total_users}\n"
        f"🔗 <b>Total Links:</b> {total_links}\n"
        f"🟢 <b>Online Users (24h):</b> {online_users}\n"
        f"🚫 <b>Total Blocked:</b> {total_blocked}\n\n"
        f"📢 <b>Current Channel:</b> {current_channel}\n"
        f"⚙️ <b>Current Limit:</b> {dl_limit} downloads"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="📢 Add Channel", callback_data="admin_add_channel")
    builder.button(text="👥 User Management", callback_data="admin_user_mgmt")
    builder.button(text="✉️ Broadcast", callback_data="admin_broadcast")
    builder.button(text="⚙️ Set Limit", callback_data="admin_set_limit")
    builder.button(text="➕ Add Admin", callback_data="admin_add_admin")
    builder.adjust(2, 2, 1)

    await message.answer(text, reply_markup=builder.as_markup())

# --- Callbacks-ka Admin Panel-ka ---
@dp.callback_query(F.data == "admin_add_channel")
async def ask_channel(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Fadlan soo dir channel-ka aad ku xirayso bot-ka (tusaale: @cadnaanchannel):")
    await state.set_state(AdminStates.waiting_for_channel)
    await callback.answer()

@dp.callback_query(F.data == "admin_user_mgmt")
async def user_mgmt_menu(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="🚫 Block User", callback_data="admin_block")
    builder.button(text="✅ Unblock User", callback_data="admin_unblock")
    builder.adjust(2)
    await callback.message.answer("Fadlan dooro tillaabada aad qaadayso:", reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "admin_block")
async def ask_block(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Fadlan soo dir ID-ga qofka aad Block saarayso:")
    await state.set_state(AdminStates.waiting_for_block)
    await callback.answer()

@dp.callback_query(F.data == "admin_unblock")
async def ask_unblock(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Fadlan soo dir ID-ga qofka aad Block-ga ka qaadayso:")
    await state.set_state(AdminStates.waiting_for_unblock)
    await callback.answer()

@dp.callback_query(F.data == "admin_broadcast")
async def ask_broadcast(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Fadlan soo dir fariinta aad rabto in loo diro dadka oo dhan:")
    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.answer()

@dp.callback_query(F.data == "admin_set_limit")
async def ask_limit(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Fadlan soo dir tirada limit-ka cusub ee aad rabto (tusaale: 3 ama 100):")
    await state.set_state(AdminStates.waiting_for_limit)
    await callback.answer()

@dp.callback_query(F.data == "admin_add_admin")
async def ask_admin(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Fadlan soo dir ID-ga qofka aad ka dhigayso Admin cusub:")
    await state.set_state(AdminStates.waiting_for_new_admin)
    await callback.answer()

# --- Qabashada Jawaabaha Admin-ka ---
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
        await message.answer(f"✅ User {message.text} si guul ah ayaa loo block-gareeyay.")
    else:
        await message.answer("❌ ID-gu waa inuu noqdaa nambar.")
    await state.clear()

@dp.message(AdminStates.waiting_for_unblock)
async def process_unblock(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        async with aiosqlite.connect('bot_database.db') as db:
            await db.execute('UPDATE users SET is_blocked = 0 WHERE user_id = ?', (int(message.text),))
            await db.commit()
        await message.answer(f"✅ User {message.text} waa laga furay block-ga.")
    else:
        await message.answer("❌ ID-gu waa inuu noqdaa nambar.")
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
                    await bot.send_message(user[0], message.text)
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

@dp.message(AdminStates.waiting_for_new_admin)
async def process_new_admin(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        async with aiosqlite.connect('bot_database.db') as db:
            await db.execute('INSERT OR IGNORE INTO admins (admin_id) VALUES (?)', (int(message.text),))
            await db.commit()
        await message.answer(f"✅ Admin cusub ayaa lagu daray: {message.text}")
    else:
        await message.answer("❌ ID-gu waa inuu noqdaa nambar.")
    await state.clear()

# ==========================================
# 4. WEB SERVER (Render Fix)
# ==========================================
async def health_check(request):
    return web.Response(text="Bot is running!")

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
    
