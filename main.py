import asyncio
import os
import logging
import time
import re
import aiosqlite
import aiohttp
from datetime import datetime
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
    waiting_for_user_info = State() # Feature-ka cusub

# ==========================================
# 1. DATABASE
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
        
        await db.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("force_channel", "None")')
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
# 2. ADMIN PANEL
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
    channel_display = "Disabled ❌" if current_channel == "None" else current_channel

    text = (
        "🤖 <b>Master Admin Dashboard</b>\n\n"
        f"👥 <b>Total Users:</b> {total_users}\n"
        f"🔗 <b>Total Links Processed:</b> {total_links}\n"
        f"🟢 <b>Online Users (24h):</b> {online_users}\n"
        f"🚫 <b>Blocked Users:</b> {total_blocked}\n\n"
        f"📢 <b>Current Channel:</b> {channel_display}\n"
        f"⚙️ <b>Download Limit:</b> {dl_limit} downloads\n"
        f"🛠 <b>Maintenance Mode:</b> {maint_status}"
    )
    return text

def get_dashboard_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 User Management", callback_data="adm_users")
    builder.button(text="🔍 User Info", callback_data="adm_userinfo")
    builder.button(text="📢 Set Channel", callback_data="adm_channel")
    builder.button(text="📝 Edit Welcome", callback_data="adm_startmsg")
    builder.button(text="⚙️ Set Limits", callback_data="adm_limits")
    builder.button(text="✉️ Broadcast", callback_data="adm_broadcast")
    builder.button(text="➕ Add Admin", callback_data="adm_addadmin")
    builder.button(text="📁 Export Data", callback_data="adm_export")
    builder.button(text="🛑 Maintenance", callback_data="adm_maint")
    builder.button(text="🔄 Refresh", callback_data="adm_refresh")
    builder.adjust(2, 2, 2, 2, 2)
    return builder.as_markup()

@dp.message(Command("admin"))
async def admin_dashboard_cmd(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    await state.clear()
    text = await get_dashboard_text()
    await message.answer(text, reply_markup=get_dashboard_keyboard())

@dp.callback_query(F.data == "adm_refresh")
async def refresh_dash(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id): return
    text = await get_dashboard_text()
    try:
        await callback.message.edit_text(text, reply_markup=get_dashboard_keyboard())
    except:
        pass
    await callback.answer("✅ Refreshed")

@dp.callback_query(F.data == "adm_userinfo")
async def ask_userinfo(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id): return
    await callback.message.answer("🔍 Please send the User ID to check their stats:")
    await state.set_state(AdminStates.waiting_for_user_info)
    await callback.answer()

@dp.callback_query(F.data == "adm_channel")
async def ask_channel(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id): return
    await callback.message.answer("📢 Send the new channel username (e.g., @yourchannel).\n\n<i>Reply with <b>None</b> to disable force subscription.</i>")
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
    await callback.message.answer("🚫 Send the User ID you want to Block:")
    await state.set_state(AdminStates.waiting_for_block)
    await callback.answer()

@dp.callback_query(F.data == "adm_unblock")
async def ask_unblock(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("✅ Send the User ID you want to Unblock:")
    await state.set_state(AdminStates.waiting_for_unblock)
    await callback.answer()

@dp.callback_query(F.data == "adm_broadcast")
async def ask_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id): return
    await callback.message.answer("✉️ Send the message you want to broadcast (Text, Photo, or Video):")
    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.answer()

@dp.callback_query(F.data == "adm_limits")
async def ask_limit(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id): return
    await callback.message.answer("⚙️ Send the new download limit number (e.g., 3 or 100):")
    await state.set_state(AdminStates.waiting_for_limit)
    await callback.answer()

@dp.callback_query(F.data == "adm_startmsg")
async def ask_welcome_text(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id): return
    info_text = (
        "📝 Please send the new welcome message text.\n\n"
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
    await callback.message.answer("➕ Send the Telegram User ID to promote to Admin:")
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

# --- Admin State Handlers ---
@dp.message(AdminStates.waiting_for_user_info)
async def process_user_info(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Invalid input. Please send a numeric ID.")
    user_id = int(message.text)
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT downloads, is_blocked, last_active FROM users WHERE user_id = ?', (user_id,)) as cursor:
            user_data = await cursor.fetchone()
    if user_data:
        is_blocked = "Yes 🔴" if user_data[1] == 1 else "No 🟢"
        last_seen = datetime.fromtimestamp(user_data[2]).strftime('%Y-%m-%d %H:%M:%S') if user_data[2] > 0 else "Never"
        info = (
            f"🔍 <b>User Information</b>\n\n"
            f"👤 <b>ID:</b> <code>{user_id}</code>\n"
            f"📥 <b>Total Downloads:</b> {user_data[0]}\n"
            f"🚫 <b>Blocked:</b> {is_blocked}\n"
            f"⏱ <b>Last Active:</b> {last_seen}"
        )
        await message.answer(info)
    else:
        await message.answer("⚠️ User not found in database.")
    await state.clear()

@dp.message(AdminStates.waiting_for_channel)
async def process_channel(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text.startswith('/') and text != "/start": 
        return await message.answer("❌ Invalid input.")
    if text.lower() == "none" or text.lower() == "off":
        await set_setting("force_channel", "None")
        await message.answer("✅ Force channel has been <b>DISABLED</b>.")
    else:
        if not text.startswith('@') and not text.startswith('http'):
            text = f"@{text}" # Si toos ah @ ugu dar haddii uu iloobo
        await set_setting("force_channel", text)
        await message.answer(f"✅ Force channel successfully updated to: {text}")
    await state.clear()

@dp.message(AdminStates.waiting_for_block)
async def process_block(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        target_id = int(message.text)
        async with aiosqlite.connect('bot_database.db') as db:
            await db.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (target_id,))
            await db.execute('UPDATE users SET is_blocked = 1 WHERE user_id = ?', (target_id,))
            await db.commit()
        await message.answer(f"✅ User {target_id} has been blocked.")
    else:
        await message.answer("❌ Invalid input. Please send a valid numeric ID.")
    await state.clear()

@dp.message(AdminStates.waiting_for_unblock)
async def process_unblock(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        target_id = int(message.text)
        async with aiosqlite.connect('bot_database.db') as db:
            await db.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (target_id,))
            await db.execute('UPDATE users SET is_blocked = 0 WHERE user_id = ?', (target_id,))
            await db.commit()
        await message.answer(f"✅ User {target_id} has been unblocked.")
    else:
        await message.answer("❌ Invalid input.")
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
    if not message.text or message.text.startswith('/'):
        return await message.answer("❌ Invalid input. Please send proper text, not a command.")
    await set_setting("welcome_text", message.html_text)
    
    # Horudhac (Preview) tus admin-ka
    current_channel = await get_setting("force_channel")
    channel_display = "" if current_channel == "None" else current_channel
    preview = message.html_text.replace("{name}", message.from_user.first_name).replace("{channel}", channel_display)
    
    await message.answer("✅ Welcome message successfully updated! Here is a preview:")
    await message.answer(preview)
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
# 3. USER INTERFACE & DOWNLOADER
# ==========================================
async def check_subscription(user_id, channel_username):
    if not channel_username or channel_username == "None":
        return True
    
    clean_username = channel_username if channel_username.startswith('@') else f"@{channel_username}"
    try:
        member = await bot.get_chat_member(chat_id=clean_username, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        return True # Hadii botku uusan admin ahayn channelka, wuu fasaxayaa qofka

@dp.message(CommandStart())
async def send_welcome(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    await update_activity(user_id)
    
    try:
        await message.answer_sticker("CAACAgIAAxkBAAE... (Geli Sticker ID)")
    except:
        pass 
    
    current_channel = await get_setting("force_channel")
    channel_display = "" if current_channel == "None" else current_channel
    raw_welcome = await get_setting("welcome_text")
    welcome_text = raw_welcome.replace("{name}", message.from_user.first_name).replace("{channel}", channel_display)
    
    await message.answer(text=welcome_text)

@dp.message(F.text)
async def process_video(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None: return 

    url_match = re.search(r'(https?://[^\s]+)', message.text)
    if not url_match or "tiktok" not in url_match.group(1).lower(): return 
    
    extracted_url = url_match.group(1)
    user_id = message.from_user.id
    await update_activity(user_id)
    
    if await get_setting("maintenance") == "1" and not await is_admin(user_id):
        return await message.answer("⚙️ <b>Bot is currently under maintenance!</b>\nWe are upgrading our servers. Please try again later.")

    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT is_blocked, downloads FROM users WHERE user_id = ?', (user_id,)) as cursor:
            user_data = await cursor.fetchone()
            
    if user_data and user_data[0] == 1: return
        
    downloads = user_data[1] if user_data else 0
    limit = int(await get_setting("download_limit"))
    current_channel = await get_setting("force_channel")
    
    # Admins bypass the limit and channel check
    if not await is_admin(user_id):
        if limit > 0 and downloads >= limit:
