import os
import asyncio
import urllib.request
import urllib.parse
import json
from database import users_collection
from notifications import send_telegram

BOT_USERNAME = "makquizhub_bot"

def get_bot_username():
    return BOT_USERNAME

def _get_me_sync(token):
    url = f"https://api.telegram.org/bot{token}/getMe"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))

def _get_updates_sync(token, offset, timeout=10):
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = {"timeout": timeout}
    if offset:
        params["offset"] = offset
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=timeout+5) as response:
        return json.loads(response.read().decode("utf-8"))

async def telegram_polling_worker():
    """
    Background worker that polls getUpdates from Telegram Bot API.
    Matches incoming messages with users' telegram usernames or ids in MongoDB and saves chat_id.
    """
    global BOT_USERNAME
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token == "YOUR_BOT_TOKEN":
        print("[Telegram Bot] Bot token is not configured. Polling task bypassed.")
        return
        
    # Dynamically fetch bot username from token
    try:
        me_res = await asyncio.to_thread(_get_me_sync, token)
        if me_res.get("ok"):
            BOT_USERNAME = me_res["result"]["username"]
            print(f"[Telegram Bot] Token loaded, bot @{BOT_USERNAME} starting polling...")
    except Exception as e:
        print(f"[Telegram Bot] Failed to fetch bot username: {e}. Defaulting to @{BOT_USERNAME}")

    print("[Telegram Bot] Starting getUpdates polling worker...")
    offset = None
    
    while True:
        try:
            updates_res = await asyncio.to_thread(_get_updates_sync, token, offset)
            if not updates_res.get("ok"):
                await asyncio.sleep(10)
                continue
                
            updates = updates_res.get("result", [])
            if updates:
                print(f"[Telegram Bot] Received {len(updates)} updates.")
            for update in updates:
                offset = update["update_id"] + 1
                
                message = update.get("message")
                if not message:
                    continue
                    
                chat = message.get("chat", {})
                chat_id = chat.get("id")
                tg_username = chat.get("username", "") # Can be None
                text = message.get("text", "")
                
                print(f"[Telegram Bot] Processing message from chat_id={chat_id}, username={tg_username}, text='{text}'")
                
                if not chat_id:
                    continue
                
                user_id_or_email = None
                if text.startswith("/start "):
                    parts = text.split(" ", 1)
                    if len(parts) > 1:
                        user_id_or_email = parts[1].strip()
                
                print(f"[Telegram Bot] Parsed user_id_or_email: {user_id_or_email}")
                
                user = None
                if user_id_or_email:
                    from bson import ObjectId
                    query = {}
                    if "_at_" in user_id_or_email:
                        email_decoded = user_id_or_email.replace("_at_", "@").replace("_dot_", ".")
                        query = {"email": email_decoded}
                    elif "@" in user_id_or_email:
                        query = {"email": user_id_or_email}
                    else:
                        try:
                            query = {"_id": ObjectId(user_id_or_email)}
                        except:
                            pass
                    if query:
                        print(f"[Telegram Bot] Searching DB with query: {query}")
                        user = await users_collection.find_one(query)
                
                if not user and tg_username:
                    clean_username = tg_username.lower().lstrip("@")
                    print(f"[Telegram Bot] User not found by start param, searching by username: {clean_username}")
                    user = await users_collection.find_one({
                        "$or": [
                            {"profile.telegram": clean_username},
                            {"profile.telegram": "@" + clean_username},
                            {"profile.telegram": tg_username}
                        ]
                    })
                
                if user:
                    print(f"[Telegram Bot] Found matching user in DB: {user['email']}. Saving chat_id={chat_id}...")
                    await users_collection.update_one(
                        {"_id": user["_id"]},
                        {"$set": {"telegram_chat_id": chat_id}}
                    )
                    user_name = user.get("profile", {}).get("name", user.get("name", "Ученик"))
                    welcome_msg = (
                        f"🎉 Привет, {user_name}!\n\n"
                        f"Ваш Telegram-аккаунт успешно подключен к платформе Mentoria Hub.\n"
                        f"Теперь вы будете получать уведомления о дедлайнах и сертификатах прямо сюда!"
                    )
                    ok = await send_telegram(chat_id, welcome_msg)
                    print(f"[Telegram Bot] Linked chat_id. Welcome msg sent status: {ok}")
                else:
                    print(f"[Telegram Bot] No matching user found in DB for message.")
                    if text.startswith("/start"):
                        instructions = (
                            "👋 Добро пожаловать в Mentoria Hub Bot!\n\n"
                            "Чтобы связать этот аккаунт со своим профилем на платформе:\n"
                            "1. Перейдите в настройки профиля на сайте.\n"
                            "2. Укажите ваше имя пользователя Telegram (username).\n"
                            "3. Нажмите кнопку сохранения.\n\n"
                            "Или используйте специальную ссылку «Подключить Telegram» из вашего личного кабинета."
                        )
                        ok = await send_telegram(chat_id, instructions)
                        print(f"[Telegram Bot] Instructions sent status: {ok}")
                        
        except asyncio.CancelledError:
            print("[Telegram Bot] Polling worker task cancelled.")
            break
        except Exception as e:
            print(f"[Telegram Bot Error] Polling encountered an error: {e}")
            await asyncio.sleep(10)
