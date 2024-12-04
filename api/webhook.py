from http.server import BaseHTTPRequestHandler
import os
import json
import asyncio
import requests
import datetime
from telebot.async_telebot import AsyncTeleBot
import firebase_admin
from firebase_admin import credentials, firestore, storage
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# Get environment variables
BOT_TOKEN = os.environ.get('BOT_TOKEN')
FIREBASE_SERVICE_ACCOUNT = os.environ.get('FIREBASE_SERVICE_ACCOUNT')

if not BOT_TOKEN:
    raise EnvironmentError("Missing BOT_TOKEN environment variable.")

if not FIREBASE_SERVICE_ACCOUNT:
    raise EnvironmentError("Missing FIREBASE_SERVICE_ACCOUNT environment variable.")

try:
    firebase_config = json.loads(FIREBASE_SERVICE_ACCOUNT)
    cred = credentials.Certificate(firebase_config)
    firebase_admin.initialize_app(cred, {'storageBucket': 'telegram-mini-app-c9a1b.appspot.com'})
    db = firestore.client()
    bucket = storage.bucket()
except Exception as e:
    raise RuntimeError(f"Firebase initialization failed: {str(e)}")

# Initialize the bot
bot = AsyncTeleBot(BOT_TOKEN)

def generate_start_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Open Liarsbar App", web_app=WebAppInfo(url="https://miniappfrontend.netlify.app/")))
    return keyboard

@bot.message_handler(commands=['start'])
async def start(message):
    user_id = str(message.from_user.id)
    user_first_name = str(message.from_user.first_name)
    user_last_name = message.from_user.last_name
    user_username = message.from_user.username
    user_language_code = str(message.from_user.language_code)
    is_premium = getattr(message.from_user, 'is_premium', False)
    text = message.text.split()
    welcome_message = (
        f"Hi, {user_first_name}! 👋\n\n"
        f"Welcome to Liars Bar! 🥳\n\n"
        f"Here you can earn coins by mining them!\n\n"
        f"Invite friends to earn more coins together, and level up faster 🚀"
    )

    try:
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            photos = await bot.get_user_profile_photos(user_id, limit=1)
            user_image = None
            if photos.total_count > 0:
                file_id = photos.photos[0][-1].file_id
                file_info = await bot.get_file(file_id)
                file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"

                response = requests.get(file_url)
                if response.status_code == 200:
                    blob = bucket.blob(f"user_images/{user_id}.jpg")
                    blob.upload_from_string(response.content, content_type='image/jpeg')
                    user_image = blob.generate_signed_url(datetime.timedelta(days=365), method='GET')

            user_data = {
                'userImage': user_image,
                'firstName': user_first_name,
                'lastName': user_last_name,
                'username': user_username,
                'languageCode': user_language_code,
                'isPremium': is_premium,
                'referrals': {},
                'balance': 0,
                'mineRate': 0.001,
                'isMining': False,
                'miningStartedTime': None,
                'daily': {
                    'claimedTime': None,
                    'claimDay': 0,
                },
                'links': None,
            }

            if len(text) > 1 and text[1].startswith('ref_'):
                referrer_id = text[1][4:]
                referrer_ref = db.collection('users').document(referrer_id)
                referrer_doc = referrer_ref.get()

                if referrer_doc.exists:
                    user_data['referredBy'] = referrer_id

                    referrer_data = referrer_doc.to_dict()
                    bonus_amount = 500 if is_premium else 100

                    referrals = referrer_data.get('referrals', {})
                    referrals[user_id] = {
                        'addedValue': bonus_amount,
                        'firstName': user_first_name,
                        'lastName': user_last_name,
                        'userImage': user_image,
                    }

                    referrer_ref.update({
                        'balance': referrer_data.get('balance', 0) + bonus_amount,
                        'referrals': referrals
                    })
            user_ref.set(user_data)

        keyboard = generate_start_keyboard()
        await bot.reply_to(message, welcome_message, reply_markup=keyboard)

    except Exception as e:
        error_message = "An error occurred. Please try again later."
        await bot.reply_to(message, error_message)
        print(f"Error in /start: {str(e)}")

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            update_dict = json.loads(post_data.decode('utf-8'))

            asyncio.run(self.process_update(update_dict))

            self.send_response(200)
            self.end_headers()
        except Exception as e:
            print(f"Error in POST request: {str(e)}")
            self.send_response(500)
            self.end_headers()

    async def process_update(self, update_dict):
        try:
            update = types.Update.de_json(update_dict)
            await bot.process_new_updates([update])
        except Exception as e:
            print(f"Error in processing update: {str(e)}")

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

