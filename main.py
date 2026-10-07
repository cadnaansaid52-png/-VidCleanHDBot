import asyncio
import os
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# 1. Qaybta Soo-dhaweynta (Start Command)
@dp.message(CommandStart())
async def command_start_handler(message: types.Message):
    # Geli Sticker ID-ga rasmiga ah ee aad rabto inaad isticmaasho
    sticker_id = "CAACAgIAAxkBAAE... (Geli ID-ga Sticker-kaaga halkan)" 
    
    welcome_text = (
        f"Welcome <b>{message.from_user.full_name}</b>!\n\n"
        "I am your premium video downloader bot. "
        "Send me any video link (TikTok, Instagram, etc.) and I will download it for you in HD without a watermark.\n\n"
        "Please send your link below 👇"
    )
    
    # Koodhkani marka hore Sticker-ka ayuu dirayaa, kadibna qoraalka
    try:
        await message.answer_sticker(sticker_id)
    except:
        pass # Haddii aad ID sax ah geliso wuu dirayaa
        
    await message.answer(welcome_text)

# 2. Qaybta Qabanaysa Link-ga (Video Processing)
# Wuxuu eegayaa in fariintu ay ku jirto erayga 'http' si uu u garto inuu link yahay
@dp.message(F.text.contains("http"))
async def process_video_link(message: types.Message):
    processing_msg = await message.answer("🔎 <i>Processing your video, please wait...</i>")
    
    # Halkan waa meeshii aan dib uga soo gelin lahayn mashiinka API-ga ee soo dejinaya muuqaalka
    await asyncio.sleep(2) # Tani waa tijaabo kaliya inuu iska dhigo mid wax soo dejinaya
    
    # Marka uu soo dejiyo wuxuu tirtirayaa fariintii 'please wait', wuxuuna soo dirayaa muuqaalka
    await processing_msg.edit_text("✅ Video downloaded successfully! (API Code will be added here)")

# 3. Qaybta fariimaha aan Link-ga ahayn
@dp.message(~F.text.contains("http") & F.text)
async def not_a_link(message: types.Message):
    await message.answer("Please send a valid video link (URL) starting with http/https.")

async def main():
    print("VidClean HD Bot is running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
