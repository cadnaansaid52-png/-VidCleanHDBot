import asyncio
import os
import logging
import time
import re
import aiosqlite
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode, ChatAction
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile
from aiohttp import web

logging.basicConfig(level=logging.INFO)

# ==========================================
# 1. BOT SETUP & ADMIN IDENTIFICATION
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
try:
    MASTER_ADMIN = int(os.getenv("ADMIN_ID", 0))
except ValueError:
    MASTER_ADMIN = 0

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

class AdminStates(StatesGroup):
    waiting_for_channel = State()
    waiting_for_block = State()
    waiting_for_unblock = State()
    waiting_for_broadcast = State()
    waiting_for_limit = State()
    waiting_for_start_msg = State()
    waiting_for_new_admin = State()

# ==========================================
# 2. DATABASE SYSTEM (SQLite)
# ==========================================
async def init_db():
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users 
                            (user_id INTEGER PRIMARY KEY, downloads INTEGER DEFAULT 0, is_blocked BOOLEAN DEFAULT 0, last_active INTEGER DEFAULT 0)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS settings 
                            (key TEXT PRIMARY KEY, value TEXT)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS admins 
                            (admin_id INTEGER PRIMARY KEY)''')
        
        default_welcome = (
            "👋 Welcome <b>{name}</b>!\n\n"
            "I am <b>VidClean HD</b>, your premium and lightning-fast video downloader. ⚡️\n\n"
            "With me, you can download any video from TikTok in High Quality (HD) and completely <b>without a watermark</b>. 🚀\n\n"
            "You can also subscribe to our channel to get the latest news about bot status and updates!\n"
            "📢 {channel}\n\n"
            "👇 <i>Please send your TikTok video link below to begin!</i>"
        )
        
        await db.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("force_channel", "@cadnaanchannel")')
        await db.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("download_limit", "3")')
        await db.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("total_links", "0")')
        await db.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("welcome_text", ?)', (default_welcome,))
        await db.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("maintenance", "0")')
        await db.execute('INSERT OR IGNORE INTO admins (admin_id) VALUES (?)', (MASTER_ADMIN,))
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

async def set_setting(key, value):
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('UPDATE settings SET value = ? WHERE key = ?', (value, key))
        await db.commit()

async def is_admin(user_id):
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT admin_id FROM admins WHERE admin_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone() is not None

# ==========================================
# 3. ADMIN PANEL DASHBOARD (100% ENGLISH)
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
            
    total_links = await get_setting("total_links")
    dl_limit = await get_setting("download_limit")
    current_channel = await get_setting("force_channel")
    maint_status = "ON 🔴" if await get_setting("maintenance") == "1" else "OFF 🟢"

    text = (
        "🤖 <b>Admin Dashboard</b>\n\n"
        f"👥 <b>Total Users:</b> {total_users}\n"
        f"🔗 <b>Total Links Processed:</b> {total_links}\n"
        f"🟢 <b>Online Users (24h):</b> {online_users}\n"
        f"🚫 <b>Blocked Users:</b> {total_blocked}\n\n"
        f"📢 <b>Current Channel:</b> {current_channel}\n"
        f"⚙️ <b>Download Limit:</b> {dl_limit} limit\n"
        f"🛠 <b>Maintenance Mode:</b> {maint_status}"
    )
    return text

def get_dashboard_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 User Management", callback_data="adm_users")
    builder.button(text="📢 Set Channel", callback_data="adm_channel")
    builder.button(text="📝 Edit Welcome", callback_data="adm_startmsg")
    builder.button(text="⚙️ Set Limits", callback_data="adm_limits")
    builder.button(text="✉️ Broadcast", callback_data="adm_broadcast")
    builder.button(text="➕ Add Admin", callback_data="adm_addadmin")
    builder.button(text="📁 Export Users", callback_data="adm_export")
    builder.button(text="🛑 Maintenance", callback_data="adm_maint")
    builder.button(text="🔄 Refresh", callback_data="adm_refresh")
    builder.adjust(1, 2, 2, 2, 2)
    return builder.as_markup()

# Xalkii bug-ga /admin: Hadda state=clear ayaa la raaciyay si uusan u xannibmin marnaba
@dp.message(Command("admin"))
async def admin_dashboard_cmd(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    await state.clear() # <- Tani waxay xallisay in 2 jeer la qoro /admin
    text = await get_dashboard_text()
    await message.answer(text, reply_markup=get_dashboard_keyboard())

# --- Admin Panel Features (Callbacks) ---
@dp.callback_query(F.data == "adm_refresh")
async def refresh_dash(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id): return
    text = await get_dashboard_text()
    try:
        await callback.message.edit_text(text, reply_markup=get_dashboard_keyboard())
    except:
        pass
    await callback.answer("✅ Dashboard Refreshed")

@dp.callback_query(F.data == "adm_channel")
async def ask_channel(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id): return
    await callback.message.answer("Please send the new channel username (e.g., @yourchannel):")
    await state.set_state(AdminStates.waiting_for_channel)
    await callback.answer()

@dp.callback_query(F.data == "adm_users")
async def user_mgmt_menu(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id): return
    builder = InlineKeyboardBuilder()
    builder.button(text="🚫 Block User", callback_data="adm_block")
    builder.button(text="✅ Unblock User", callback_data="adm_unblock")
    builder.adjust(2)
    await callback.message.answer("👥 <b>User Management</b>\nPlease choose an action:", reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "adm_block")
async def ask_block(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Please send the User ID you want to Block:")
    await state.set_state(AdminStates.waiting_for_block)
    await callback.answer()

@dp.callback_query(F.data == "adm_unblock")
async def ask_unblock(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Please send the User ID you want to Unblock:")
    await state.set_state(AdminStates.waiting_for_unblock)
    await callback.answer()

@dp.callback_query(F.data == "adm_broadcast")
async def ask_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id): return
    await callback.message.answer("Please send the message you want to broadcast (Text, Photo, or Video):")
    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.answer()

@dp.callback_query(F.data == "adm_limits")
async def ask_limit(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id): return
    await callback.message.answer("Please send the new download limit number (e.g., 3 or 100):")
    await state.set_state(AdminStates.waiting_for_limit)
    await callback.answer()

@dp.callback_query(F.data == "adm_startmsg")
async def ask_welcome_text(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id): return
    info_text = (
        "Please send the new welcome message text.\n\n"
        "💡 <b>Variables you can use:</b>\n"
        "<code>{name}</code> - Replaces with user's name.\n"
        "<code>{channel}</code> - Replaces with forced channel."
    )
    await callback.message.answer(info_text)
    await state.set_state(AdminStates.waiting_for_start_msg)
    await callback.answer()

@dp.callback_query(F.data == "adm_addadmin")
async def ask_admin(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id): return
    await callback.message.answer("Please send the Telegram User ID to promote to Admin:")
    await state.set_state(AdminStates.waiting_for_new_admin)
    await callback.answer()

@dp.callback_query(F.data == "adm_export")
async def export_users_cmd(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id): return
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT user_id FROM users') as cursor:
            users = await cursor.fetchall()
    content = "\n".join([str(u[0]) for u in users])
    file = BufferedInputFile(content.encode('utf-8'), filename="VidClean_Users.txt")
    await bot.send_document(chat_id=callback.from_user.id, document=file, caption=f"📁 Total Extracted Users: {len(users)}")
    await callback.answer()

@dp.callback_query(F.data == "adm_maint")
async def toggle_maintenance(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id): return
    current = await get_setting("maintenance")
    new_val = "1" if current == "0" else "0"
    await set_setting("maintenance", new_val)
    status = "ON" if new_val == "1" else "OFF"
    await callback.answer(f"Maintenance Mode is now {status}", show_alert=True)
    text = await get_dashboard_text()
    try:
        await callback.message.edit_text(text, reply_markup=get_dashboard_keyboard())
    except:
        pass

# --- Qabashada Jawaabaha Admin-ka (FSM Handlers) ---
@dp.message(AdminStates.waiting_for_channel)
async def process_channel(message: types.Message, state: FSMContext):
    if message.text.startswith('/'): return await message.answer("❌ Invalid input. Please send text, not a command.")
    await set_setting("force_channel", message.text.strip())
    await message.answer(f"✅ Force channel successfully updated to: {message.text}")
    await state.clear()

@dp.message(AdminStates.waiting_for_block)
async def process_block(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        async with aiosqlite.connect('bot_database.db') as db:
            await db.execute('UPDATE users SET is_blocked = 1 WHERE user_id = ?', (int(message.text),))
            await db.commit()
        await message.answer(f"✅ User {message.text} has been blocked.")
    else:
        await message.answer("❌ Invalid input. Please send a valid numeric ID.")
    await state.clear()

@dp.message(AdminStates.waiting_for_unblock)
async def process_unblock(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        async with aiosqlite.connect('bot_database.db') as db:
            await db.execute('UPDATE users SET is_blocked = 0 WHERE user_id = ?', (int(message.text),))
            await db.commit()
        await message.answer(f"✅ User {message.text} has been unblocked.")
    else:
        await message.answer("❌ Invalid input. Please send a valid numeric ID.")
    await state.clear()

@dp.message(AdminStates.waiting_for_broadcast)
async def process_broadcast(message: types.Message, state: FSMContext):
    if message.text and message.text.startswith('/'): return await message.answer("❌ Commands cannot be broadcasted.")
    success = 0
    await message.answer("⏳ Sending broadcast...")
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT user_id FROM users') as cursor:
            users = await cursor.fetchall()
            for user in users:
                try:
                    await bot.copy_message(chat_id=user[0], from_chat_id=message.chat.id, message_id=message.message_id)
                    success += 1
                    await asyncio.sleep(0.05)
                except:
                    pass
    await message.answer(f"✅ Broadcast successfully sent to {success} users.")
    await state.clear()

@dp.message(AdminStates.waiting_for_limit)
async def process_limit(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        await set_setting("download_limit", message.text)
        await message.answer(f"✅ Limit successfully updated to: {message.text}")
    else:
        await message.answer("❌ Invalid input. Please send a valid number.")
    await state.clear()

@dp.message(AdminStates.waiting_for_start_msg)
async def process_welcome_text(message: types.Message, state: FSMContext):
    # Xalkii bug-ga /start is-kaydinaysay
    if not message.text or message.text.startswith('/'):
        return await message.answer("❌ Invalid input. Please send proper text, not a command.")
    await set_setting("welcome_text", message.html_text)
    await message.answer("✅ Welcome message successfully updated!")
    await state.clear()

@dp.message(AdminStates.waiting_for_new_admin)
async def process_new_admin(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        async with aiosqlite.connect('bot_database.db') as db:
            await db.execute('INSERT OR IGNORE INTO admins (admin_id) VALUES (?)', (int(message.text),))
            await db.commit()
        await message.answer(f"✅ New admin added: {message.text}")
    else:
        await message.answer("❌ Invalid input. Please send a valid numeric ID.")
    await state.clear()

# ==========================================
# 4. BOT DOWNLOADER & LIMITS LOGIC
# ==========================================
async def check_subscription(user_id, channel_username):
    if not channel_username or channel_username == "None":
        return True
    try:
        member = await bot.get_chat_member(chat_id=channel_username, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception:
        # Haddii bot-ku uusan admin ahayn channel-ka, qofka wuu fasaxayaa si uusan bot-ku u xannibmin.
        return True 

@dp.message(CommandStart())
async def send_welcome(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    await update_activity(user_id)
    
    # 1. Sticker (Beddel ID-ga haddii aad rabto mid gaar ah)
    try:
        await message.answer_sticker("CAACAgIAAxkBAAE... (Geli ID-ga Sticker-kaaga)")
    except:
        pass 
    
    # 2. Qoraalka
    current_channel = await get_setting("force_channel")
    raw_welcome = await get_setting("welcome_text")
    welcome_text = raw_welcome.replace("{name}", message.from_user.first_name).replace("{channel}", current_channel)
    await message.answer(text=welcome_text)

@dp.message(F.text)
async def process_video(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        return 

    # Hubi inuu link yahay
    url_match = re.search(r'(https?://[^\s]+)', message.text)
    if not url_match or "tiktok" not in url_match.group(1).lower():
        return 
    
    extracted_url = url_match.group(1)
    user_id = message.from_user.id
    await update_activity(user_id)
    
    # Hubi Maintenance
    if await get_setting("maintenance") == "1" and not await is_admin(user_id):
        return await message.answer("⚙️ <b>Bot is currently under maintenance!</b>\nWe are upgrading our servers. Please try again later.")

    # Hubi Block & Downloads
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT is_blocked, downloads FROM users WHERE user_id = ?', (user_id,)) as cursor:
            user_data = await cursor.fetchone()
            
    if user_data and user_data[0] == 1: 
        return
        
    downloads = user_data[1] if user_data else 0
    limit = int(await get_setting("download_limit"))
    current_channel = await get_setting("force_channel")
    
    # Sharciga Limit-ka 100% saxan
    if limit > 0 and downloads >= limit:
        is_subbed = await check_subscription(user_id, current_channel)
        if not is_subbed:
            builder = InlineKeyboardBuilder()
            clean_url = current_channel.replace('@', '')
            builder.button(text="✅ Subscribe", url=f"https://t.me/{clean_url}")
            limit_txt = (
                "⚠️ <b>Download Limit Reached!</b>\n\n"
                f"Please subscribe to our channel below to unlock unlimited downloads.\n\n"
                f"📢 {current_channel}"
            )
            return await message.answer(limit_txt, reply_markup=builder.as_markup())

    # Chat Action oo kaliya, fariin ma jirto
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_VIDEO)

    api_url = f"https://www.tikwm.com/api/?url={extracted_url}&hd=1"
    
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
                await db.execute('UPDATE settings SET value = CAST(value AS INTEGER) + 1 WHERE key = "total_links"')
                await db.commit()
        else:
            await message.answer("❌ Invalid TikTok link or video is private. Please try again.")
            
    except Exception:
        await message.answer("❌ Connection error. Please try again later.")

@dp.c
