import os
import asyncio
import base64
import aiohttp
import logging
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from motor.motor_asyncio import AsyncIOMotorClient
from flask import Flask
from threading import Thread

# লগিং সেটআপ
logging.basicConfig(level=logging.ERROR)

# ================== ১. কনফিগারেশন (Environment Variables) ==================
API_ID = int(os.environ.get("API_ID", "1234567"))
API_HASH = os.environ.get("API_HASH", "your_api_hash")
MASTER_TOKEN = os.environ.get("BOT_TOKEN", "your_master_token")
DB_URL = os.environ.get("DB_URL", "")
DB_NAME = "Full_Featured_FileStore_Bot"
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "0"))

# ওনার ডিটেইলস
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "Telegram")
OWNER_CHANNEL = os.environ.get("OWNER_CHANNEL", "https://t.me/Telegram")
PORT = int(os.environ.get("PORT", 8080))

# ইউআরএল ভ্যালিডেশন ফাংশন (এরর সমাধান করার জন্য)
def fix_url(url_str):
    if not url_str: return "https://t.me/telegram"
    url_str = url_str.strip()
    if url_str.startswith("http"):
        return url_str
    # ইউজারনেম হলে লিঙ্কে রূপান্তর
    clean_name = url_str.replace("@", "")
    return f"https://t.me/{clean_name}"

# ================== ২. ডাটাবেস ও হেলথ চেক সার্ভার ==================
db_client = AsyncIOMotorClient(DB_URL)
db = db_client[DB_NAME]
clones_collection = db.clones
files_collection = db.files

app = Flask(__name__)
@app.route('/')
def home(): 
    return "🔥 Bot is Online! Fixed Version. 🔥"

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

user_states = {}

# ================== ৩. শর্টনার ফাংশন ==================
async def get_shortlink(url, api, link):
    if not api or not url: 
        return link
    endpoint = f"https://{url}/api?api={api}&url={link}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(endpoint, timeout=10) as resp:
                res = await resp.json()
                return res.get("shortenedUrl") or res.get("shortlink") or link
    except Exception as e:
        print(f"Shortener Error: {e}")
        return link

# ================== ৪. ক্লোন বটের ইঞ্জিন ==================
async def start_clone_bot(data):
    token = data['token']
    user_api = data.get('api', "")
    user_url = data.get('url', "")
    # চ্যানেল লিঙ্ক ফিক্স করা
    user_up_channel = fix_url(data.get('up_channel', OWNER_CHANNEL))

    try:
        clone = Client(
            name=f"session_{token[:10]}",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=token
        )

        @clone.on_message(filters.private & (filters.document | filters.video | filters.audio | filters.photo))
        async def handle_file_clone(c, m):
            try:
                fwd = await m.forward(CHANNEL_ID)
                db_id = base64.urlsafe_b64encode(str(fwd.id).encode()).decode().rstrip("=")
                await files_collection.insert_one({"file_id": db_id, "msid": fwd.id})
                
                bot_me = await c.get_me()
                raw_link = f"https://t.me/{bot_me.username}?start={db_id}"
                final_link = await get_shortlink(user_url, user_api, raw_link)
                
                await m.reply_text(
                    f"✅ **ফাইল সেভ হয়েছে!**\n\n🔗 **লিঙ্ক:** `{final_link}`",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("লিঙ্ক ওপেন করুন 🚀", url=final_link)]
                    ])
                )
            except Exception as e:
                print(f"Clone File Error: {e}")

        @clone.on_message(filters.command("start") & filters.private)
        async def handle_start_clone(c, m):
            if len(m.command) > 1:
                query = m.command[1]
                file_data = await files_collection.find_one({"file_id": query})
                
                if file_data:
                    await c.copy_message(m.chat.id, CHANNEL_ID, file_data['msid'], caption="")
                    
                    # বাটন লিঙ্ক ভ্যালিডেশন
                    u_chan = fix_url(user_up_channel)
                    u_owner = fix_url(OWNER_USERNAME)
                    
                    btns = [
                        [InlineKeyboardButton("বট আপডেট চ্যানেল 📢", url=u_chan)],
                        [InlineKeyboardButton("ওনারের সাথে যোগাযোগ 👤", url=u_owner)]
                    ]
                    await m.reply_text(
                        "✅ **আপনার ফাইলটি উপরে পাঠানো হয়েছে।**\n\nসবাই আমাদের বট আপডেট চ্যানেলে জয়েন দিয়ে পাশে থাকুন।",
                        reply_markup=InlineKeyboardMarkup(btns)
                    )
                    return
            await m.reply_text(f"👋 **হ্যালো!**\nআমি একটি ফাইল স্টোর বট। ফাইল পাঠান লিঙ্ক পাওয়ার জন্য।")

        await clone.start()
    except Exception as e:
        print(f"Clone {token[:5]} failed: {e}")

# ================== ৫. মাস্টার বট লজিক ==================
master = Client("MasterBot", api_id=API_ID, api_hash=API_HASH, bot_token=MASTER_TOKEN)

@master.on_message(filters.command("start") & filters.private)
async def handle_master_start(c, m):
    # ইউআরএল ফিক্স করা এরর এড়াতে
    chan_url = fix_url(OWNER_CHANNEL)
    owner_url = fix_url(OWNER_USERNAME)
    
    welcome_text = (
        "👋 **ফাইল স্টোর ক্লোনার বটে স্বাগতম!**\n\n"
        "এখানে আপনি নিজের টোকেন দিয়ে একদম ফ্রিতে একটি ফাইল স্টোর বট বানাতে পারবেন।"
    )
    btns = [
        [InlineKeyboardButton("➕ নিজের বট তৈরি করুন", callback_data="create_bot")],
        [InlineKeyboardButton("⚙️ আপডেট চ্যানেল সেট করুন", callback_data="setup_channel")],
        [InlineKeyboardButton("📢 ওনার চ্যানেল", url=chan_url)],
        [InlineKeyboardButton("👤 ওনার কন্টাক্ট", url=owner_url)]
    ]
    await m.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(btns))

@master.on_callback_query()
async def master_callback(c, q: CallbackQuery):
    u_id = q.from_user.id
    if q.data == "create_bot":
        user_states[u_id] = {"step": "token"}
        await q.message.edit_text("🤖 **ধাপ ১:**\nআপনার বটের **Bot Token** টি পাঠান।")
    elif q.data == "setup_channel":
        check = await clones_collection.find_one({"user_id": u_id})
        if not check:
            return await q.answer("আগে একটি বট ক্লোন করুন!", show_alert=True)
        user_states[u_id] = {"step": "up_link"}
        await q.message.edit_text("🔗 আপনার আপডেট চ্যানেল লিঙ্কটি পাঠান।")

@master.on_message(filters.private & filters.text & ~filters.command("start"))
async def master_inputs(c, m):
    u_id = m.from_user.id
    if u_id not in user_states: return
    
    state = user_states[u_id]
    if state["step"] == "token":
        state.update({"token": m.text, "step": "api"})
        await m.reply_text("🔑 **ধাপ ২:**\nআপনার শর্টনার **API Key** পাঠান।")
    elif state["step"] == "api":
        state.update({"api": m.text, "step": "url"})
        await m.reply_text("🌐 **ধাপ ৩:**\nশর্টনার **Domain** পাঠান (উদা: gplinks.in)।")
    elif state["step"] == "url":
        state.update({"url": m.text, "user_id": u_id, "up_channel": OWNER_CHANNEL})
        await clones_collection.update_one({"user_id": u_id}, {"$set": state}, upsert=True)
        asyncio.create_task(start_clone_bot(state))
        del user_states[u_id]
        await m.reply_text("✅ **সফল হয়েছে!** আপনার বটের ইউজারনেমে গিয়ে স্টার্ট দিন।")
    elif state["step"] == "up_link":
        await clones_collection.update_one({"user_id": u_id}, {"$set": {"up_channel": m.text}})
        del user_states[u_id]
        await m.reply_text("✅ **সফল!** আপডেট চ্যানেল লিঙ্ক পরিবর্তন করা হয়েছে।")

async def boot_all_clones():
    async for clone_data in clones_collection.find({}):
        asyncio.create_task(start_clone_bot(clone_data))

if __name__ == "__main__":
    Thread(target=run_flask).start()
    master.start()
    loop = asyncio.get_event_loop()
    loop.create_task(boot_all_clones())
    print(">>> Master Bot & Clones are Live! <<<")
    asyncio.get_event_loop().run_forever()
