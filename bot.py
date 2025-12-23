import os
import asyncio
import base64
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from motor.motor_asyncio import AsyncIOMotorClient
from flask import Flask
from threading import Thread

# ================== ১. কনফিগারেশন (Environment Variables) ==================
API_ID = int(os.environ.get("API_ID", "12345"))
API_HASH = os.environ.get("API_HASH", "")
MASTER_TOKEN = os.environ.get("BOT_TOKEN", "")
DB_URL = os.environ.get("DB_URL", "")
DB_NAME = "Professional_File_Store"
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "0"))
PORT = int(os.environ.get("PORT", 8080))

# ================== ২. ডাটাবেস ও ফ্ল্যাস্ক সেটআপ ==================
db_client = AsyncIOMotorClient(DB_URL)
db = db_client[DB_NAME]
clones_collection = db.clones
files_collection = db.files

app = Flask(__name__)
@app.route('/')
def home(): return "Bot is Alive"

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

# ইউজার স্টেট ট্র্যাকিং
user_states = {}

# ================== ৩. হেল্পার ফাংশন (শর্টনার) ==================
async def get_shortlink(url, api, link):
    if not api or not url: return link
    endpoint = f"https://{url}/api?api={api}&url={link}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(endpoint, timeout=10) as resp:
                res = await resp.json()
                return res.get("shortenedUrl") or res.get("shortlink") or link
    except: return link

# ================== ৪. ক্লোন বটের মূল ইঞ্জিন ==================
async def start_clone_bot(data):
    token = data['token']
    user_id = data['user_id']
    short_api = data.get('api')
    short_url = data.get('url')
    up_channel = data.get('up_channel', "https://t.me/UpdateChannel")

    try:
        # প্রতিটি ক্লোন বটের জন্য আলাদা ক্লায়েন্ট সেশন
        clone = Client(f"session_{token[:10]}", api_id=API_ID, api_hash=API_HASH, bot_token=token)

        #--- ফাইল গ্রহণ ও স্টোর করা ---
        @clone.on_message(filters.private & (filters.document | filters.video | filters.audio | filters.photo))
        async def handle_file(c, m):
            try:
                # চ্যানেলে ফাইল ফরওয়ার্ড করা
                fwd = await m.forward(CHANNEL_ID)
                # মেসেজ আইডি এনকোড করে ইউনিক আইডি তৈরি
                db_id = base64.urlsafe_b64encode(str(fwd.id).encode()).decode().rstrip("=")
                
                # ডাটাবেসে ফাইল সেভ
                await files_collection.insert_one({"file_id": db_id, "msid": fwd.id})
                
                me = await c.get_me()
                raw_link = f"https://t.me/{me.username}?start={db_id}"
                
                # লিঙ্ক শর্ট করা
                final_link = await get_shortlink(short_url, short_api, raw_link)
                
                await m.reply_text(
                    f"✅ **ফাইল সেভ হয়েছে!**\n\n🔗 আপনার লিঙ্ক: `{final_link}`",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("লিঙ্ক ওপেন করুন 🚀", url=final_link)]])
                )
            except Exception as e:
                print(f"File handling error: {e}")

        #--- লিঙ্ক থেকে ফাইল পাঠানো ---
        @clone.on_start() # এই ডেকোরেটরটি পাইরোগ্রাম সেশনে কাজ করে না, তাই নিচে ম্যানুয়ালি হ্যান্ডেল করা হয়েছে
        @clone.on_message(filters.command("start") & filters.private)
        async def send_file(c, m):
            if len(m.command) > 1:
                f_data = await files_collection.find_one({"file_id": m.command[1]})
                if f_data:
                    # ১. ফাইল পাঠানো (ক্যাপশন সম্পূর্ণ ডিলিট করে)
                    await c.copy_message(m.chat.id, CHANNEL_ID, f_data['msid'], caption="")
                    
                    # ২. জয়েন মেসেজ ও বাটন
                    btn = InlineKeyboardMarkup([[InlineKeyboardButton("বট আপডেট চ্যানেল 📢", url=up_channel)]])
                    await m.reply_text(
                        "✅ **সব ফাইল পাঠানো শেষ হয়েছে।**\n\nসবাই আমাদের বট আপডেট চ্যানেলে জয়েন দিন।",
                        reply_markup=btn
                    )
                    return
            await m.reply_text("👋 এই বট ব্যবহার করে আপনি ফাইল স্টোর করতে পারেন। ফাইল পাঠান লিঙ্ক পেতে।")

        await clone.start()
        print(f"Successfully started clone for: {token[:10]}")
    except Exception as e:
        print(f"Failed to start clone {token[:10]}: {e}")

# ================== ৫. মাস্টার বট লজিক ==================
master = Client("MasterBot", api_id=API_ID, api_hash=API_HASH, bot_token=MASTER_TOKEN)

@master.on_message(filters.command("start") & filters.private)
async def master_start(c, m):
    btns = [
        [InlineKeyboardButton("➕ নিজের বট তৈরি করুন", callback_data="create_bot")],
        [InlineKeyboardButton("⚙️ আপডেট চ্যানেল সেট করুন", callback_data="setup_channel")],
        [InlineKeyboardButton("📢 সাপোর্ট গ্রুপ", url="https://t.me/your_support_link")]
    ]
    await m.reply_text(
        "👋 **ফাইল স্টোর ক্লোনার বটে স্বাগতম!**\n\nনিচের বাটনগুলো ব্যবহার করে আপনার প্রজেক্ট শুরু করুন।",
        reply_markup=InlineKeyboardMarkup(btns)
    )

@master.on_callback_query()
async def cb_handler(c, q: CallbackQuery):
    u_id = q.from_user.id
    if q.data == "create_bot":
        user_states[u_id] = {"step": "token"}
        await q.message.edit_text("🤖 **ধাপ ১:**\nপ্রথমে @BotFather থেকে পাওয়া আপনার বটের **Token** পাঠান।")
    
    elif q.data == "setup_channel":
        check = await clones_collection.find_one({"user_id": u_id})
        if not check:
            return await q.answer("আগে একটি বট ক্লোন করুন!", show_alert=True)
        user_states[u_id] = {"step": "up_link"}
        await q.message.edit_text("🔗 ফাইলের শেষে কোন চ্যানেল বাটন দেখাতে চান? তার লিঙ্ক পাঠান।\n(উদা: https://t.me/MyChannel)")

@master.on_message(filters.private & filters.text & ~filters.command("start"))
async def input_handler(c, m):
    u_id = m.from_user.id
    if u_id not in user_states: return
    
    state = user_states[u_id]
    step = state["step"]

    if step == "token":
        state["token"] = m.text
        state["step"] = "api"
        await m.reply_text("🔑 **ধাপ ২:**\nআপনার শর্টনার সাইটের **API Key** পাঠান।")
    
    elif step == "api":
        state["api"] = m.text
        state["step"] = "url"
        await m.reply_text("🌐 **ধাপ ৩:**\nআপনার শর্টনার সাইটের **Domain** পাঠান।\n(যেমন: gplinks.in বা droplink.co)")
    
    elif step == "url":
        state["url"] = m.text
        state["user_id"] = u_id
        state["up_channel"] = "https://t.me/UpdateChannel" # Default
        
        # ডাটাবেসে সেভ
        await clones_collection.update_one({"user_id": u_id}, {"$set": state}, upsert=True)
        
        # ক্লোন চালু করা
        asyncio.create_task(start_clone_bot(state))
        
        del user_states[u_id]
        await m.reply_text("✅ **সফল হয়েছে!** আপনার বটটি এখন সচল। আপনার বটের ইউজারনেমে গিয়ে টেস্ট করুন।")

    elif step == "up_link":
        new_link = m.text
        await clones_collection.update_one({"user_id": u_id}, {"$set": {"up_channel": new_link}})
        del user_states[u_id]
        await m.reply_text("✅ **আপডেট চ্যানেল লিঙ্ক সেট হয়েছে!**\nবটটি রিস্টার্ট হলে এটি কার্যকর হবে।")

# রিস্টার্টে সব ক্লোন চালু করার লজিক
async def restart_all_clones():
    async for clone_data in clones_collection.find({}):
        asyncio.create_task(start_clone_bot(clone_data))

# ================== ৬. মেইন এক্সিকিউশন (রেন্ডারের জন্য) ==================
if __name__ == "__main__":
    # ১. ফ্ল্যাস্ক হেলথ চেক স্টার্ট
    Thread(target=run_flask).start()
    
    # ২. মাস্টার বট স্টার্ট
    master.start()
    print(">>> Master Bot Live!")
    
    # ৩. ডাটাবেস থেকে সব ক্লোন রিস্টার্ট
    loop = asyncio.get_event_loop()
    loop.create_task(restart_all_clones())
    
    # ৪. লুপ চালু রাখা
    asyncio.get_event_loop().run_forever()
