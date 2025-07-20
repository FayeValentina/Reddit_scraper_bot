import os
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv('REDDIT_CLIENT_ID')
CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET')
USER_AGENT = os.getenv('REDDIT_USER_AGENT', 'RedditScraper/1.0')
USERNAME = os.getenv('REDDIT_USERNAME')
PASSWORD = os.getenv('REDDIT_PASSWORD')

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Twitter API Configuration
TWITTER_API_KEY = os.getenv('TWITTER_API_KEY')
TWITTER_API_SECRET = os.getenv('TWITTER_API_SECRET')
TWITTER_ACCESS_TOKEN = os.getenv('TWITTER_ACCESS_TOKEN')
TWITTER_ACCESS_TOKEN_SECRET = os.getenv('TWITTER_ACCESS_TOKEN_SECRET')
TWITTER_BEARER_TOKEN = os.getenv('TWITTER_BEARER_TOKEN')

# Authorized User ID
AUTHORIZED_USER_ID = os.getenv('AUTHORIZED_USER_ID')

# Application URL
APP_URL = os.getenv('APP_URL')

# Twitter Webhook Secret
TWITTER_WEBHOOK_SECRET = os.getenv('TWITTER_WEBHOOK_SECRET')

# Bot Configuration
TWEET_INTERVAL = int(os.getenv('TWEET_INTERVAL', '60'))

DATABASE_PATH = os.getenv('DATABASE_PATH', 'reddit_data.db')