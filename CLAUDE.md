# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Reddit-to-Twitter bot system that scrapes Reddit comments and automatically posts high-quality content to Twitter via a Telegram bot interface. The system consists of five main components:

1. **Reddit Scraper** (`reddit_scraper.py`) - Async Reddit scraper using asyncpraw with 6 sorting methods and concurrent processing
2. **Telegram Bot** (`bot.py`) - Main bot interface with comprehensive user interaction, Twitter posting, and automated workflows
3. **Data Processor** (`data_processor.py`) - SQLite database operations for storing comments with Twitter metadata and AI assessment data
4. **Configuration Manager** (`config_manager.py`) - Runtime configuration management with GUI interface via Telegram
5. **AI Quality Filter** - Google Gemini 2.5 Flash-Lite Preview for intelligent comment quality assessment

## Core Architecture

### Bot Flow (bot.py:1886 lines)
- **Manual Posting**: User sends message → Bot confirmation → User confirms → Twitter post with database logging
- **Manual Reddit Workflow**: `/scrape_now` command → Uses configured subreddits → AI filtering → Auto-posts best comments
- **Automated Workflow**: Background timer-based scraper → AI quality assessment → Smart duplicate detection → Auto-posting
- **Interactive Configuration**: `/settings` provides full GUI for runtime parameter adjustment
- **Comprehensive Diagnostics**: `/test_twitter` with detailed API permissions and connection testing
- **Twitter API Integration**: OAuth 1.0a with v1.1 media upload and v2 tweet creation
- **Health Monitoring**: Built-in HTTP server for uptime monitoring and webhook handling

### Data Flow
1. **Concurrent Reddit Scraping**: AsyncRedditScraper fetches multiple subreddits simultaneously using asyncpraw
2. **Intelligent Filtering**: Score-based pre-filtering → AI batch processing → Confidence-based selection
3. **Smart Duplicate Detection**: 7-day content history check before posting to prevent repetition
4. **Database Persistence**: All comments stored with AI assessment metadata and Twitter integration fields
5. **Real-time Notifications**: Telegram notifications for all bot activities and errors
6. **Performance Optimization**: Batch API calls, concurrent processing, semaphore-controlled rate limiting

### Database Schema
- `reddit_comments`: Core table with fields (`comment_id`, `post_id`, `author`, `body`, `score`, `created_utc`, `parent_id`, `is_submitter`, `subreddit`, `tweet_id`, `sent_at`, `confidence`, `reason`, `api_call_count`)
- `bot_config`: Runtime configuration table (`config_key`, `config_value`, `config_type`, `description`, `updated_at`)

## Key Commands

### Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run the main Telegram bot (includes all functionality)
python bot.py

# Direct database inspection (SQLite)
sqlite3 reddit_data.db ".schema"
```

### Configuration
**Environment Variables** (in `.env`):
- **Reddit API**: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`, `REDDIT_USERNAME`, `REDDIT_PASSWORD`
- **Telegram**: `TELEGRAM_BOT_TOKEN`, `AUTHORIZED_USER_ID`  
- **Twitter**: `TWITTER_API_KEY`, `TWITTER_API_SECRET`, `TWITTER_ACCESS_TOKEN`, `TWITTER_ACCESS_TOKEN_SECRET`, `TWITTER_BEARER_TOKEN`
- **AI Processing**: `GEMINI_API_KEY` (for intelligent comment quality assessment)
- **Optional**: `TWEET_INTERVAL`, `APP_URL` (health monitoring), `TWITTER_WEBHOOK_SECRET`, `DATABASE_PATH`

**Runtime Configuration** (via `/settings` Telegram GUI):
- `GEMINI_BATCH_SIZE` - AI API batch processing size (default: 10, reduces API costs by 90%)
- `TOP_COMMENTS_COUNT` - Top comments for AI filtering (default: 50)
- `REDDIT_POST_FETCH_COUNT` - Posts per subreddit (default: 50)
- `REDDIT_SORT_METHOD` - 6 sorting options: hot, new, top, controversial, rising, gilded (default: hot)
- `REDDIT_TIME_FILTER` - Time filters for top/controversial: all, year, month, week, day, hour (default: day)
- `REDDIT_COMMENTS_PER_POST` - Comment extraction limit per post (default: 20)
- `REDDIT_FETCH_INTERVAL` - Automated scraping interval in minutes (default: 60, minimum: 5)
- `REDDIT_SUBREDDITS` - Target subreddit list (default: python,programming,MachineLearning,artificial,technology)
- `AUTO_SCRAPER_ENABLED` - Automated scraping toggle (default: false)

## Dependencies

**Core Libraries** (requirements.txt):
- `asyncpraw` - Async Python Reddit API Wrapper for concurrent scraping
- `tweepy>=4.14.0` - Twitter API client with OAuth 1.0a and v2 support
- `python-telegram-bot>=20.0` - Async Telegram bot framework
- `google-genai>=0.3.0` - Google Gemini AI API client for quality assessment
- `aiohttp>=3.8.0` - Async HTTP client for health monitoring and webhooks
- `Pillow>=9.0.0` - Image processing for Twitter media uploads
- `python-dotenv` - Environment variable management
- **Built-in**: `sqlite3` (database), `asyncio` (concurrency), `logging` (monitoring)

## Implementation Architecture

### Authentication & Security
- **Single-user access**: Bot restricted to `AUTHORIZED_USER_ID` only
- **Twitter API**: OAuth 1.0a with v1.1 media uploads + v2 tweet creation (X.com Free Tier compatible)
- **Reddit API**: Optional username/password auth, supports read-only access
- **AI Processing**: Gemini API key required for quality assessment
- **Webhook Security**: HMAC-SHA256 signature verification for Twitter webhooks

### Advanced Error Handling
- **Twitter API**: Categorized error responses (401/403/duplicate) with actionable user feedback
- **Intelligent Fallback**: AI failures → score-based sorting, maintains service continuity
- **Graceful Degradation**: Reddit scraping errors don't crash bot, continue with available data
- **Smart Retry Logic**: Automatic retry for transient failures, exponential backoff
- **Comprehensive Logging**: All operations logged with structured error context

### Performance Optimizations
- **Concurrent Processing**: Async Reddit scraping with semaphore-controlled rate limiting
- **Batch AI Processing**: Configurable batch sizes reduce Gemini API calls by 90%
- **Smart Caching**: 7-day duplicate detection with optimized database queries
- **Resource Management**: Automatic connection pooling and cleanup
- **Health Monitoring**: Built-in HTTP server for uptime monitoring (port 8000)

### Content Processing Pipeline
1. **Multi-subreddit Scraping**: Concurrent fetching from configured subreddits
2. **Score-based Pre-filtering**: Extract top N comments by Reddit score
3. **AI Quality Assessment**: Batch processing with confidence scoring (>0.8 threshold)
4. **Duplicate Prevention**: 7-day content history check with exact matching
5. **Smart Posting**: Automatic content truncation and Twitter optimization

## Testing & Diagnostics

**Built-in Diagnostic Commands:**
- `/test_twitter` - Comprehensive Twitter API connection, permissions, and OAuth testing
- `/status` - Real-time bot status, scraper status, configuration summary, database statistics
- `/settings` - Interactive GUI for runtime configuration with validation
- `/scrape_now` - Manual trigger for complete scraping workflow testing

**Manual Testing Workflow:**
```bash
# 1. Start the bot
python bot.py

# 2. Test Twitter integration
# Use /test_twitter command in Telegram

# 3. Test Reddit scraping and AI filtering
# Use /scrape_now command to trigger manual scrape

# 4. Configure system parameters
# Use /settings for interactive configuration

# 5. Monitor automated operations
# Use /status to check scraper timing and performance
```

**Database Inspection:**
```bash
# View database schema
sqlite3 reddit_data.db ".schema"

# Check recent comments
sqlite3 reddit_data.db "SELECT * FROM reddit_comments ORDER BY scraped_at DESC LIMIT 10;"

# View configuration
sqlite3 reddit_data.db "SELECT * FROM bot_config;"
```

## File Structure

**Core Application Files:**
- `bot.py` (1,886 lines) - Complete Telegram bot with Twitter integration, async Reddit scraping coordination, AI filtering, automated workflows, interactive configuration GUI, health monitoring, and webhook handling
- `reddit_scraper.py` (296 lines) - Async Reddit scraper with concurrent subreddit processing, 6 sorting methods, semaphore-controlled rate limiting, and backward compatibility
- `config_manager.py` (194 lines) - SQLite-based configuration management with type validation, default value handling, and runtime parameter updates
- `data_processor.py` (90 lines) - Database operations for comment storage with Twitter metadata, AI assessment data, and automatic schema updates
- `config.py` (34 lines) - Environment variable loading and configuration constants

**Dependencies & Data:**
- `requirements.txt` (7 lines) - Async-focused Python dependencies with version constraints
- `reddit_data.db` - SQLite database with `reddit_comments` and `bot_config` tables
- `CLAUDE.md` - Comprehensive project documentation with architecture details
- `.env` - Environment configuration (not in repository)
- `venv/` - Python virtual environment directory

**Architecture Notes:**
- **Async-first design**: All I/O operations use asyncio for optimal performance
- **Modular structure**: Clear separation of concerns between bot logic, scraping, data processing, and configuration
- **No external dependencies**: Uses SQLite for persistence, built-in HTTP server for monitoring
- **Production-ready**: Comprehensive error handling, logging, health monitoring, and graceful shutdown

# User Guide

## Quick Start

### 1. Environment Configuration

Create a `.env` file with the following configuration:

```env
# Reddit API (required)
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret  
REDDIT_USER_AGENT=RedditBot/1.0
REDDIT_USERNAME=your_reddit_username  # Optional for read-only access
REDDIT_PASSWORD=your_reddit_password  # Optional for read-only access

# Telegram Bot (required)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
AUTHORIZED_USER_ID=your_telegram_user_id

# Twitter API (required for posting)
TWITTER_API_KEY=your_twitter_api_key
TWITTER_API_SECRET=your_twitter_api_secret
TWITTER_ACCESS_TOKEN=your_twitter_access_token
TWITTER_ACCESS_TOKEN_SECRET=your_twitter_access_token_secret
TWITTER_BEARER_TOKEN=your_twitter_bearer_token

# AI Quality Assessment (recommended)
GEMINI_API_KEY=your_google_gemini_api_key

# Optional Configuration
TWEET_INTERVAL=60              # Seconds between posts
APP_URL=https://your-app.com   # For health monitoring
DATABASE_PATH=reddit_data.db   # Database file path
```

### 2. Installation & Startup

```bash
# Install dependencies
pip install -r requirements.txt

# Start the bot
python bot.py
```

### 3. Bot Commands & Usage

**Primary Commands:**
- `/start` - Initialize bot and show welcome message
- `/help` - Display comprehensive help information  
- `/status` - Real-time bot status, scraper status, and performance metrics
- `/settings` - Interactive GUI for configuration management
- `/test_twitter` - Comprehensive Twitter API diagnostics
- `/scrape_now` - Manual trigger for immediate Reddit scraping and posting

**Manual Tweet Posting:**
1. Send text message to bot → Confirmation prompt → Confirm → Posted to Twitter
2. Send image with caption → Confirmation prompt → Confirm → Posted with media
3. Automatic character limit handling (280 chars) and image optimization

**Automated Reddit-to-Twitter Workflow:**
1. **Configuration**: Use `/settings` to configure subreddits, intervals, and AI parameters
2. **Activation**: Use `/start_scraper` or enable via `/settings` → `AUTO_SCRAPER_ENABLED`
3. **Processing Pipeline**: 
   - Concurrent scraping from configured subreddits
   - Score-based pre-filtering (top N comments)
   - AI quality assessment (confidence > 0.8)
   - Duplicate detection (7-day history)
   - Smart selection and auto-posting
4. **Monitoring**: Use `/status` to track progress and performance

## Advanced Configuration

### AI Quality Assessment System
**Intelligent Content Filtering:**
- **Gemini 2.5 Flash-Lite Preview**: Advanced language model for content quality evaluation
- **Batch Processing**: Process up to 10 comments per API call (90% cost reduction vs individual calls)
- **Confidence Scoring**: Only posts comments with AI confidence > 0.8
- **Fallback Strategy**: Graceful degradation to score-based sorting if AI unavailable

**Configuration Parameters:**
- `GEMINI_BATCH_SIZE` (default: 10) - Comments per API batch call
- `TOP_COMMENTS_COUNT` (default: 50) - High-score comments sent for AI assessment
- AI assessment criteria: completeness, information value, standalone readability

### Reddit Data Acquisition
**Supported Sorting Methods** (via `/settings`):
- `hot` - Trending posts with engagement momentum (default)
- `new` - Most recently posted content
- `top` - Highest scored posts with time filter support
- `controversial` - High engagement with mixed reactions
- `rising` - Posts gaining rapid traction
- `gilded` - Award-recipient posts

**Time Filter Options** (top/controversial only):
- `all`, `year`, `month`, `week`, `day` (default), `hour`

**Performance Parameters:**
- `REDDIT_POST_FETCH_COUNT` (default: 50) - Posts per subreddit
- `REDDIT_COMMENTS_PER_POST` (default: 20) - Comment extraction limit
- `REDDIT_FETCH_INTERVAL` (default: 60, min: 5) - Automated scraping interval
- `REDDIT_SUBREDDITS` - Target communities (comma-separated)

### Security & Access Control
- **Single-user authorization**: Restricted to `AUTHORIZED_USER_ID` only
- **API key protection**: All credentials stored in environment variables
- **Webhook security**: HMAC-SHA256 signature verification for Twitter webhooks
- **Rate limiting**: Built-in throttling and `wait_on_rate_limit` for all APIs
- **Content sanitization**: Automatic character limit handling and content cleaning

## Troubleshooting Guide

### Common Issues & Solutions

**🔴 Bot Not Responding**
- Verify `TELEGRAM_BOT_TOKEN` and bot is running (`python bot.py`)
- Check authorized user ID matches your Telegram user ID
- Use `/status` to verify bot connection and health

**🐦 Twitter API Issues**
- Use `/test_twitter` for comprehensive diagnostics and permission analysis
- Ensure all 5 Twitter API credentials are configured (including `TWITTER_BEARER_TOKEN`)
- Verify OAuth 1.0a permissions: "Read and Write" access required
- Check rate limits and API tier access in Twitter Developer Portal

**⚙️ Configuration Problems**
- Configuration validation is built-in - invalid values will show specific error messages
- Use `/settings` GUI instead of manual database editing
- Minimum values enforced: `REDDIT_FETCH_INTERVAL >= 5 minutes`
- Boolean values accept: `true/false`, `1/0`, `yes/no`, `on/off`

**🔄 Automated Scraper Issues**
- Verify `AUTO_SCRAPER_ENABLED = true` via `/settings`
- Check `/status` for next scheduled run time and current status
- First run occurs after one full interval (default: 60 minutes)
- Review logs for specific error messages during scraping

**🤖 AI Filtering Issues**
- No `GEMINI_API_KEY`: System falls back to score-based sorting automatically
- No qualifying comments: Adjust `TOP_COMMENTS_COUNT` or try different subreddits/time ranges
- High API costs: Reduce `GEMINI_BATCH_SIZE` or `TOP_COMMENTS_COUNT`
- Check AI assessment criteria: standalone readability, information value, completeness

**📄 Content Duplication**
- System checks last 7 days automatically to prevent duplicate posts
- Try different subreddits, sorting methods, or time filters for fresh content
- Use `/scrape_now` to test with current configuration

**🔐 Permission Errors**
- Twitter: Ensure app has "Read and Write" permissions (not just "Read")
- Reddit: Username/password optional for read-only access
- Telegram: Bot must be able to send messages to authorized user

### Performance Optimization

**Memory Usage:**
- SQLite database auto-manages connections and cleanup
- Async operations prevent blocking during I/O operations
- Connection pooling built into asyncpraw and aiohttp clients

**API Rate Limits:**
- All APIs configured with `wait_on_rate_limit=True`
- Semaphore-controlled concurrent processing (5 subreddits, 10 posts simultaneously)
- Batch AI processing reduces Gemini API calls by 90%

**Monitoring:**
- Health endpoint available at `http://localhost:8000/health`
- Comprehensive logging to console with structured error information
- Real-time status via `/status` command with performance metrics