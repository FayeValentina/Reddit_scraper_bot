# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Reddit-to-Twitter bot system that scrapes Reddit comments and posts them to Twitter via a Telegram bot interface. The system consists of five main components:

1. **Reddit Scraper** (`reddit_scraper.py`) - Uses PRAW to scrape Reddit posts and comments with 6 sorting methods
2. **Telegram Bot** (`bot.py`) - Main interface for user interaction, Twitter posting, and automated workflows
3. **Data Processor** (`data_processor.py`) - Handles SQLite database operations for storing comments with Twitter metadata
4. **Configuration Manager** (`config_manager.py`) - Manages bot settings and automated scraper configuration
5. **AI Quality Filter** - Uses Google Gemini 2.5 Flash-Lite Preview to filter high-quality comments

## Core Architecture

### Bot Flow (bot.py)
- **Manual Posting**: User sends message to Telegram bot → Bot shows confirmation → User confirms → Message posted to Twitter
- **Manual Reddit Workflow**: Use `/scrape_now` from `/status` menu → System uses configured subreddits and settings → AI filters comments → Auto-posts to Twitter (when enabled)
- **Automated Workflow**: Background scraper runs at configurable intervals → AI filters comments → Auto-posts to Twitter (when enabled)
- **Duplicate Detection**: System checks last 7 days for duplicate content before posting
- **Twitter API Diagnostics**: `/test_twitter` command provides comprehensive API status and permissions check
- All posted content is saved to SQLite database with tweet_id and sent_at timestamp
- AI Quality Filter: Sorts comments by score, takes top N (configurable), then uses Gemini 2.5 Flash-Lite Preview to assess quality with confidence score > 0.8, randomly selects 10 from qualified comments

### Data Flow
1. Reddit scraper fetches posts/comments using PRAW with 6 sorting methods (hot, new, top, controversial, rising, gilded)
2. Data processor saves to SQLite database (`reddit_data.db`) with Twitter integration fields
3. Comments are sorted by score, top N are selected (configurable via TOP_COMMENTS_COUNT)
4. AI Quality Filter evaluates top N comments using Gemini API in batches
5. Duplicate detection checks against last 7 days of posted content
6. **Unified Mode**: Both manual `/scrape_now` and automated workflows use the same process
7. **Auto-posting**: System automatically posts selected comments (no manual selection interface)
8. Bot posts to Twitter via Tweepy with comprehensive error handling and saves tweet metadata

### Database Schema
- `reddit_comments`: Comments with Twitter integration fields (`tweet_id`, `sent_at`, `confidence`, `reason`, `api_call_count`)
  - Primary table for storing posted comments with AI quality assessment metadata
- `bot_config`: Configuration management table for automated scraper and bot settings
  - Stores configurable parameters like sorting methods, intervals, and feature toggles

## Key Commands

### Development
```bash
# Install dependencies
pip install -r requirements.txt

# Test configuration and connections (Note: test_bot.py not currently present)
# Use the bot's built-in diagnostic commands instead

# Run the main Telegram bot
python bot.py

# Run standalone Reddit scraper
python reddit_scraper.py
```

### Configuration
**Environment Variables** (in `.env`):
- Reddit API: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`, `REDDIT_USERNAME`, `REDDIT_PASSWORD`
- Telegram: `TELEGRAM_BOT_TOKEN`, `AUTHORIZED_USER_ID`
- Twitter: `TWITTER_API_KEY`, `TWITTER_API_SECRET`, `TWITTER_ACCESS_TOKEN`, `TWITTER_ACCESS_TOKEN_SECRET` (OAuth 1.0a)
- Gemini AI: `GEMINI_API_KEY` (for comment quality filtering)
- Optional: `TWEET_INTERVAL` (seconds between posts), `APP_URL` (for keep-alive), `TWITTER_WEBHOOK_SECRET`

**Runtime Configuration** (via `/settings` command):
- `GEMINI_BATCH_SIZE` - Batch size for AI API calls (default: 10)
- `TOP_COMMENTS_COUNT` - Number of top comments to filter (default: 50)
- `REDDIT_POST_FETCH_COUNT` - Posts per subreddit (default: 50)
- `REDDIT_SORT_METHOD` - Sorting: hot, new, top, controversial, rising, gilded (default: hot)
- `REDDIT_TIME_FILTER` - Time filter for top/controversial: all, year, month, week, day, hour (default: day)
- `REDDIT_COMMENTS_PER_POST` - Comments per post limit (default: 20)
- `REDDIT_FETCH_INTERVAL` - Auto-scraper interval in minutes (default: 60)
- `REDDIT_SUBREDDITS` - Comma-separated subreddit list (default: python,programming,MachineLearning,artificial,technology)
- `AUTO_SCRAPER_ENABLED` - Enable/disable automated scraping (default: false)

## Dependencies

Key external libraries:
- `praw` - Python Reddit API Wrapper
- `tweepy` - Twitter API client
- `python-telegram-bot` - Telegram bot framework
- `google-genai` - Google Gemini AI API client
- `sqlite3` - Database operations (built-in)
- `aiohttp` - Async HTTP for keep-alive and webhooks

## Important Implementation Details

### Authentication Flow
- Bot restricts access to single authorized Telegram user via `AUTHORIZED_USER_ID`
- Twitter posting uses OAuth 1.0a + API v1.1 (fully compatible with X.com Free Tier)
- Reddit can work with or without username/password authentication
- Gemini AI requires API key for comment quality assessment

### Error Handling
- **Twitter API**: Comprehensive error categorization (duplicate content, permissions, rate limits) with specific user feedback
- **Duplicate Detection**: Checks last 7 days before posting, skips duplicates with notification
- **Reddit Scraping**: Errors are handled gracefully without crashing the bot
- **Database Operations**: Silent failure mode with TODO notes for proper logging system
- **Gemini AI**: Failures fallback to score-based sorting (avoids blocking the flow)
- **Configuration**: Robust parsing with fallback to defaults for malformed settings

### Rate Limiting
- Twitter posts have configurable interval (`TWEET_INTERVAL`)
- Reddit scraping includes 1-second delays between requests
- Twitter client uses `wait_on_rate_limit=True`
- Gemini AI calls use batch processing (configurable via GEMINI_BATCH_SIZE) to reduce API calls by 90%

### Media Processing
- Images are automatically resized and optimized for Twitter
- Comments over 280 characters are truncated with "..."
- Image posts support both image and caption text
- AI quality filtering ensures only meaningful comments are selected

## Testing

**Built-in Diagnostics:**
- `/test_twitter` - Comprehensive Twitter API testing with permission checks
- `/status` - Bot status, configuration summary, and database statistics
- `/settings` - Runtime configuration management and validation

**Manual Testing:**
- Start bot with `python bot.py`
- Use `/scrape_now` from `/status` menu to test scraping and AI filtering
- Configure subreddits and parameters via `/settings`
- Verify database operations through posted content tracking

## File Structure

**Core Files:**
- `bot.py` - Main Telegram bot with Twitter integration, AI quality filtering, and automated workflows (82KB)
- `reddit_scraper.py` - Reddit scraping with 6 sorting methods and time filters (6.4KB)
- `data_processor.py` - Database operations for comment storage with Twitter metadata (3.6KB)
- `config_manager.py` - Runtime configuration management with SQLite backend (7.3KB)
- `config.py` - Environment variable loading (1KB)
- `requirements.txt` - Cleaned Python dependencies (108 bytes)

**Data & Documentation:**
- `reddit_data.db` - SQLite database with comments and configuration tables (897KB)
- `CLAUDE.md` - Project documentation and user guide (9.2KB)
- `Oracle Cloud Always Free 服务的完整列表.txt` - Reference documentation (2.8KB)
- `.env` - Environment configuration (not in repo)

**Note:** Project has been optimized and cleaned - removed debug print statements, Python cache files, and unused code. Total size: ~1MB excluding virtual environment.

# User Guide

## Quick Start

### 1. Environment Configuration

Ensure your `.env` file contains the following configuration:

```env
# Reddit API
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here
REDDIT_USER_AGENT=YourApp/1.0
REDDIT_USERNAME=your_username_here
REDDIT_PASSWORD=your_password_here

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
AUTHORIZED_USER_ID=your_telegram_user_id_here

# Twitter API
TWITTER_API_KEY=your_twitter_api_key_here
TWITTER_API_SECRET=your_twitter_api_secret_here
TWITTER_ACCESS_TOKEN=your_twitter_access_token_here
TWITTER_ACCESS_TOKEN_SECRET=your_twitter_access_token_secret_here
# Twitter Bearer Token not required for OAuth 1.0a (Free Tier compatible)

# Gemini AI API (for comment quality filtering)
GEMINI_API_KEY=your_gemini_api_key_here

# Optional configuration
TWEET_INTERVAL=60  # Tweet sending interval (seconds)
```

### 2. Bot Usage

**Commands:**
- `/start` - Start using the bot
- `/help` - Display help information
- `/status` - Check bot status with detailed scraping information and immediate scrape option
- `/scrape_now` - Trigger immediate Reddit scraping (from status menu)
- `/settings` - Configure automated scraper and bot parameters
- `/test_twitter` - Comprehensive Twitter API diagnostics and permissions check
- `/scrape_now` - Trigger immediate Reddit scraping (from status menu)

**Manual Reddit Scraping Workflow (via `/scrape_now`):**
1. **Uses configured subreddits**: From REDDIT_SUBREDDITS setting (no manual input needed)
2. **Uses configured settings**: POST_FETCH_COUNT, SORT_METHOD, TIME_FILTER, COMMENTS_PER_POST
3. **Score-based filtering**: Sorts all comments by score, takes top N (configurable via TOP_COMMENTS_COUNT)
4. **AI quality filtering**: 🤖 Evaluates top N comments, keeps those with confidence > 0.8
5. **Duplicate detection**: Checks against last 7 days of posted content
6. **Random selection**: Randomly selects up to 10 non-duplicate, qualified comments
7. **Auto-posting**: Automatically posts selected comments to Twitter (when enabled)
8. **No manual selection**: Fully automated process using configured parameters

**Automated Scraping Workflow:**
1. **Background timer**: Runs at configured interval (default: 60 minutes, with initial delay)
2. **Uses configured subreddits**: From REDDIT_SUBREDDITS setting
3. **Applies sorting method**: Configurable via REDDIT_SORT_METHOD (6 options available)
4. **AI filtering and duplicate detection**: Same as manual workflow
5. **Auto-posting**: Automatically posts selected comments when AUTO_SCRAPER_ENABLED is true

**Tweet Posting:**
- Send text/image messages → Bot shows confirmation → Confirm → Posted to Twitter
- Comments over 280 characters are automatically truncated
- All posted content is saved to database with tweet_id and timestamp

## Advanced Configuration

### AI Quality Filtering
**Environment Variables:**
```env
GEMINI_API_KEY=your_gemini_api_key_here
```

**Runtime Configuration (via /settings):**
- `GEMINI_BATCH_SIZE=10` - Batch size for API calls (default: 10)
- `TOP_COMMENTS_COUNT=50` - Number of top comments to filter (default: 50)

**Notes:**
- If GEMINI_API_KEY is not set, bot will skip AI filtering and show top 10 comments sorted by score
- **Configurable filtering scope**: TOP_COMMENTS_COUNT controls how many top-scored comments to send for AI filtering
- AI filtering evaluates the top N comments by score, keeping those with confidence > 0.8
- **Batch processing**: GEMINI_BATCH_SIZE controls how many comments are processed per API call (reduces costs by 90%)
- **API call tracking**: Bot displays total number of Gemini API calls used during filtering
- Optimized token usage: only processes N highest-scored comments instead of all comments
- Filtering process adds processing time but significantly improves tweet quality

### Security
- Only `AUTHORIZED_USER_ID` specified user can use the bot
- All API keys must be kept secure and not committed to version control
- Follow platform usage terms and avoid sending sensitive content

### Reddit Sorting Methods
The bot supports all 6 PRAW sorting methods (configurable via `/settings`):
- `hot` - Currently trending posts (default)
- `new` - Most recently posted
- `top` - Highest scored posts (supports time filters)
- `controversial` - Most controversial posts (supports time filters) 
- `rising` - Posts gaining traction
- `gilded` - Posts with Reddit awards

**Time Filters** (for top/controversial only):
- `all` - All time
- `year` - Past year
- `month` - Past month  
- `week` - Past week
- `day` - Past day (default)
- `hour` - Past hour

## Troubleshooting

**Q: Bot not responding?**
A: Check bot token and ensure bot is running. Use `/status` to verify bot state.

**Q: Tweet posting fails?**
A: Use `/test_twitter` for comprehensive API diagnostics. Check permissions and rate limits.

**Q: Getting "update config failed" in settings?**
A: This was a known bug with underscore-containing config keys, now fixed.

**Q: All scraped content shows as duplicates?**
A: Bot checks last 7 days for duplicates. Try different subreddits or longer time ranges.

**Q: Auto-scraper not working?**
A: Check AUTO_SCRAPER_ENABLED setting and REDDIT_FETCH_INTERVAL. Auto-scraper waits for one interval before first run.

**Q: AI filtering finds no quality comments?**
A: Try longer time ranges or more active subreddits. Adjust TOP_COMMENTS_COUNT and sorting method.

**Q: Can I disable AI filtering?**
A: Yes, don't set GEMINI_API_KEY to use score-based sorting only.

**Q: How do I change Reddit sorting method?**
A: Use `/settings` → REDDIT_SORT_METHOD to choose from 6 options (hot, new, top, controversial, rising, gilded).

**Q: Twitter permission errors?**
A: Ensure API v1.1 and v2 access. Use `/test_twitter` to check specific permission issues.