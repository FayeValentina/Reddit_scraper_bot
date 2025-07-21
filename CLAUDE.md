# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a modular Reddit-to-Twitter bot system that scrapes Reddit comments and automatically posts high-quality content to Twitter via a Telegram bot interface. The system features **intelligent Twitter character counting**, AI-powered content filtering, advanced error handling, and comprehensive failure reporting with source context.

## Core Architecture

### Modular Design

The system consists of **9 specialized modules** + **unified utilities**:

1. **Main Bot Controller** (`bot.py`) - Telegram bot interface and command handling
2. **Twitter API Manager** (`twitter_manager.py`) - Twitter API operations with accurate character handling
3. **AI Quality Evaluator** (`ai_evaluator.py`) - Google Gemini 2.5 Flash-Lite integration for content assessment
4. **Auto Scraper Manager** (`auto_scraper_manager.py`) - Reddit scraping workflow with intelligent content filtering
5. **Health Monitor** (`health_monitor.py`) - HTTP server, webhooks, and system monitoring
6. **Reddit Scraper** (`reddit_scraper.py`) - Async Reddit API integration with concurrent processing
7. **Data Processor** (`data_processor.py`) - SQLite database operations and data management
8. **Configuration Manager** (`config_manager.py`) - Runtime configuration with GUI interface
9. **Database Manager** (`database_manager.py`) - Database connection management with WAL mode optimization
10. **Unified Utils** (`utils.py`) - Twitter text processing, error handling, time utilities, and database operations

### Key Innovations

#### **Intelligent Twitter Character Counting**
- **Official Library Integration**: Uses `twitter-text-parser` for accurate character calculation
- **Multi-language Support**: Properly handles Chinese, Japanese, Korean characters (CJK)
- **Content Pre-filtering**: Filters out oversized content before AI processing to avoid truncation
- **Consistent Processing**: Eliminates character counting discrepancies that caused 403 Forbidden errors

#### **Enhanced Content Processing Pipeline**
```
Reddit Comments → Length Validation → AI Quality Assessment → Duplicate Detection → Complete Tweet Posting
```

#### **Advanced Error Handling**
- **Content Display**: Shows exact content that failed to post (with source context)
- **Error Classification**: Categorizes errors (permission, authentication, duplicate, forbidden, etc.)
- **Resolution Guidance**: Provides specific troubleshooting steps for each error type
- **Source Information**: Displays Reddit metadata (subreddit, score, AI assessment)

### Bot Flow

- **Manual Posting**: Message → Character validation → Confirmation → Twitter post with intelligent error feedback
- **Manual Reddit Workflow**: `/scrape_now` → Concurrent scraping → Length filtering → AI assessment → Auto-posting
- **Automated Workflow**: Timer-based scraper → Multi-subreddit fetching → Content validation → AI filtering → Smart posting
- **Interactive Configuration**: `/settings` provides full GUI for runtime parameter adjustment
- **Comprehensive Diagnostics**: `/test_twitter` with detailed API permissions and connection testing
- **Twitter API Integration**: OAuth 1.0a with v1.1 media upload and v2 tweet creation
- **Health Monitoring**: Built-in HTTP server for uptime monitoring and webhook handling

### Enhanced Data Flow

1. **Concurrent Reddit Scraping**: AsyncRedditScraper fetches multiple subreddits simultaneously
2. **Length Pre-filtering**: TwitterTextUtils validates content length before processing
3. **AI Quality Assessment**: Batch processing with confidence scoring (>0.8 threshold)
4. **Smart Duplicate Detection**: 7-day content history check with exact matching
5. **Complete Content Posting**: No truncation - only posts content that fits Twitter limits
6. **Enhanced Error Handling**: Failed posts include content, source info, and resolution guidance
7. **Database Persistence**: All comments stored with AI assessment metadata
8. **Real-time Notifications**: Telegram notifications for all activities and detailed error reporting

### Database Schema

- `reddit_comments`: Core table with fields (`comment_id`, `post_id`, `author`, `body`, `score`, `created_utc`, `parent_id`, `is_submitter`, `subreddit`, `tweet_id`, `sent_at`, `confidence`, `reason`, `api_call_count`)
- `bot_config`: Runtime configuration table (`config_key`, `config_value`, `config_type`, `description`, `updated_at`)

## Key Commands

### Development
```bash
# Install dependencies (includes twitter-text-parser)
pip install -r requirements.txt

# Run the main Telegram bot (includes all functionality)
python bot.py

# Direct database inspection (SQLite with WAL mode)
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
- `GEMINI_BATCH_SIZE` - AI API batch processing size (default: 10)
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
- **`twitter-text-parser`** - Official Twitter character counting library for accurate text processing
- **Built-in**: `sqlite3` (database with WAL mode), `asyncio` (concurrency), `logging` (monitoring)

## Module Architecture

### 1. Main Bot Controller (`bot.py`)
**Responsibility**: Telegram bot interface and user interaction
- **Functions**: Command handling, user authentication, message processing, configuration GUI
- **Key Features**: Interactive settings, status monitoring, manual tweet posting with character validation
- **Dependencies**: All other modules for coordination

### 2. Twitter API Manager (`twitter_manager.py`)
**Responsibility**: Twitter API operations and media handling
- **Functions**: Tweet posting (text/image), API connection testing, error classification
- **Key Features**: OAuth 1.0a authentication, image optimization, intelligent character handling
- **Error Types**: permission, authentication, duplicate, forbidden, file_too_large

### 3. AI Quality Evaluator (`ai_evaluator.py`)
**Responsibility**: Content quality assessment using Google Gemini
- **Functions**: Single/batch comment evaluation, quality scoring, content filtering
- **Key Features**: Batch processing (90% cost reduction), confidence scoring, fallback mechanisms
- **Assessment Criteria**: Completeness, information value, standalone readability

### 4. Auto Scraper Manager (`auto_scraper_manager.py`)
**Responsibility**: Automated Reddit scraping and intelligent posting workflow
- **Functions**: Reddit content acquisition, length pre-filtering, AI filtering, duplicate detection, auto-posting
- **Key Features**: Concurrent scraping, intelligent content selection, enhanced error notifications
- **Content Processing**: Length validation → AI assessment → Duplicate check → Complete posting

### 5. Health Monitor (`health_monitor.py`)
**Responsibility**: System monitoring and webhook handling
- **Functions**: HTTP health server, Twitter webhooks, DM forwarding, keep-alive mechanism
- **Key Features**: Webhook signature verification, automatic uptime monitoring
- **Endpoints**: `/health`, `/webhook/twitter` (GET/POST)

### 6. Reddit Scraper (`reddit_scraper.py`)
**Responsibility**: Async Reddit API integration
- **Functions**: Concurrent subreddit scraping, multiple sorting methods, rate limiting
- **Key Features**: Semaphore-controlled concurrency, backward compatibility, performance optimization
- **Sorting Methods**: hot, new, top, controversial, rising, gilded

### 7. Data Processor (`data_processor.py`)
**Responsibility**: Database operations and data persistence
- **Functions**: Comment storage, metadata management, streamlined schema
- **Key Features**: SQLite integration, simplified table structure, Twitter metadata tracking

### 8. Configuration Manager (`config_manager.py`)
**Responsibility**: Runtime configuration management
- **Functions**: Dynamic config updates, type validation, default handling
- **Key Features**: GUI integration, type safety, persistent storage

### 9. Database Manager (`database_manager.py`)
**Responsibility**: Database connection and transaction management
- **Functions**: Thread-local connections, WAL mode optimization, transaction handling
- **Key Features**: Singleton pattern, connection pooling, automatic cleanup

### 10. Unified Utils (`utils.py`)
**Responsibility**: Shared utilities and Twitter text processing
- **Functions**: 
  - **TwitterTextUtils**: Official character counting, content validation, intelligent truncation
  - **UnifiedConfigManager**: Centralized configuration handling
  - **DatabaseOperationMixin**: Common database operations
  - **TimeUtils**: Standardized time handling
  - **Error Handling**: Unified error processing with notifications

## Authentication & Security

- **Single-user access**: Bot restricted to `AUTHORIZED_USER_ID` only
- **Twitter API**: OAuth 1.0a with v1.1 media uploads + v2 tweet creation (X.com Free Tier compatible)
- **Reddit API**: Optional username/password auth, supports read-only access
- **AI Processing**: Gemini API key required for quality assessment
- **Webhook Security**: HMAC-SHA256 signature verification for Twitter webhooks

## Advanced Error Handling

### Twitter Character Validation
**Intelligent Content Processing**:
- **Pre-filtering**: Removes oversized content before AI processing to avoid user confusion
- **Accurate Counting**: Uses official `twitter-text-parser` for CJK character support
- **Complete Posting**: No truncation - only posts content that naturally fits Twitter limits
- **User Experience**: Users see complete, unbroken tweets instead of truncated content

### Twitter Posting Failures
**Enhanced Error Reporting** with content context:

**Automatic Scraping Failures** (via `auto_scraper_manager.py`):
- **Content Display**: Shows up to 200 characters of the failed content
- **Source Information**: Reddit subreddit, score, AI confidence, and reasoning
- **Error Classification**: Specific error types with tailored resolution guidance
- **Context Preservation**: Complete posting context for debugging

**Manual Tweet Failures** (via `bot.py`):
- **Content Display**: Shows up to 150 characters of the failed content  
- **Character Count**: Displays actual Twitter character count vs limit
- **Error Types**: Authentication, permission, duplicate, forbidden, file size, unknown
- **User Guidance**: Specific troubleshooting steps for each error category

### Error Categories
- **Permission Errors**: API access level insufficient (detailed API tier guidance)
- **Authentication Errors**: Invalid or expired credentials
- **Content Violations**: Community guidelines violations with content context
- **Duplicate Content**: Twitter's duplicate detection with source information
- **Character Limit**: Accurate character count with CJK support
- **Technical Errors**: File size, network, or system issues
- **Unknown Errors**: New or unclassified error types

## Performance Optimizations

- **Concurrent Processing**: Async Reddit scraping with semaphore-controlled rate limiting
- **Intelligent Pre-filtering**: Early content validation saves AI API costs and processing time
- **Batch AI Processing**: Configurable batch sizes reduce Gemini API calls by 90%
- **Smart Caching**: 7-day duplicate detection with optimized database queries
- **Resource Management**: Automatic connection pooling and cleanup
- **Health Monitoring**: Built-in HTTP server for uptime monitoring (port 8000)
- **Database Optimization**: WAL mode for improved concurrent performance

## Content Processing Pipeline

1. **Multi-subreddit Scraping**: Concurrent fetching from configured subreddits
2. **Length Pre-validation**: TwitterTextUtils filters oversized content early
3. **Score-based Pre-filtering**: Extract top N comments by Reddit score  
4. **AI Quality Assessment**: Batch processing with confidence scoring (>0.8 threshold)
5. **Duplicate Prevention**: 7-day content history check with exact matching
6. **Complete Content Posting**: Direct posting without truncation for better user experience
7. **Enhanced Error Handling**: Failed posts include content and comprehensive diagnostic information

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

# 2. Test Twitter integration with character validation
# Use /test_twitter command in Telegram

# 3. Test Reddit scraping with length filtering
# Use /scrape_now command to trigger manual scrape

# 4. Configure system parameters
# Use /settings for interactive configuration

# 5. Monitor automated operations
# Use /status to check scraper timing and performance
```

**Database Inspection:**
```bash
# View database schema (WAL mode)
sqlite3 reddit_data.db ".schema"

# Check recent comments with AI metadata
sqlite3 reddit_data.db "SELECT comment_id, body, confidence, reason FROM reddit_comments ORDER BY scraped_at DESC LIMIT 10;"

# View configuration
sqlite3 reddit_data.db "SELECT * FROM bot_config;"
```

## File Structure

**Core Application Files:**
- `bot.py` (1047 lines) - Main Telegram bot with intelligent character validation
- `twitter_manager.py` (202 lines) - Twitter API operations with official character counting
- `ai_evaluator.py` (225 lines) - Google Gemini integration for content quality assessment
- `auto_scraper_manager.py` (444 lines) - Automated scraping with intelligent content filtering
- `health_monitor.py` (179 lines) - System monitoring, webhooks, and health endpoints
- `reddit_scraper.py` (282 lines) - Async Reddit scraper with concurrent processing
- `data_processor.py` (63 lines) - Streamlined database operations and data persistence
- `config_manager.py` (154 lines) - Runtime configuration management
- `database_manager.py` (118 lines) - Database connection management with WAL optimization
- `utils.py` (426 lines) - Unified utilities including TwitterTextUtils for accurate character handling

**Dependencies & Data:**
- `requirements.txt` (8 lines) - Enhanced Python dependencies including twitter-text-parser
- `reddit_data.db` - SQLite database with WAL mode optimization
- `CLAUDE.md` - Comprehensive project documentation
- `.env` - Environment configuration (not in repository)
- `venv/` - Python virtual environment directory

**Architecture Notes:**
- **Modular Design**: Clear separation of concerns with specialized modules
- **Async-first**: All I/O operations use asyncio for optimal performance
- **Intelligent Character Handling**: Official Twitter text processing eliminates 403 errors
- **Enhanced Error Handling**: Comprehensive failure reporting with content and source context
- **No Content Truncation**: Pre-filtering ensures complete, readable tweets
- **Production-ready**: Comprehensive error handling, logging, health monitoring, and graceful shutdown

## User Guide

### Quick Start

#### 1. Environment Configuration

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

#### 2. Installation & Startup

```bash
# Install dependencies (includes twitter-text-parser for accurate character counting)
pip install -r requirements.txt

# Start the bot
python bot.py
```

#### 3. Bot Commands & Usage

**Primary Commands:**
- `/start` - Initialize bot and show welcome message
- `/help` - Display comprehensive help information  
- `/status` - Real-time bot status, scraper status, and performance metrics
- `/settings` - Interactive GUI for configuration management
- `/test_twitter` - Comprehensive Twitter API diagnostics
- `/scrape_now` - Manual trigger for immediate Reddit scraping and posting

**Manual Tweet Posting:**
1. Send text message to bot → Character validation → Confirmation → Posted to Twitter
2. Send image with caption → Character validation → Confirmation → Posted with media
3. Intelligent character limit handling with CJK support
4. **Enhanced Error Reporting**: Failed posts show content and specific error guidance

**Automated Reddit-to-Twitter Workflow:**
1. **Configuration**: Use `/settings` to configure subreddits, intervals, and AI parameters
2. **Activation**: Use `/start_scraper` or enable via `/settings` → `AUTO_SCRAPER_ENABLED`
3. **Processing Pipeline**: 
   - Concurrent scraping from configured subreddits
   - Length pre-filtering (removes oversized content)
   - Score-based pre-filtering (top N comments)
   - AI quality assessment (confidence > 0.8)
   - Duplicate detection (7-day history)
   - Complete content posting (no truncation)
4. **Monitoring**: Use `/status` to track progress and performance
5. **Error Handling**: Failed posts include content, source info, and resolution guidance

## Advanced Configuration

### AI Quality Assessment System
**Intelligent Content Filtering:**
- **Gemini 2.5 Flash-Lite Preview**: Advanced language model for content quality evaluation
- **Batch Processing**: Process up to 10 comments per API call (90% cost reduction)
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

### Twitter Character Handling
**Intelligent Text Processing:**
- **Official Library**: Uses `twitter-text-parser` for accurate character calculation
- **Multi-language Support**: Proper handling of Chinese, Japanese, Korean characters
- **Pre-filtering**: Content validation before AI processing
- **No Truncation**: Only posts naturally fitting content for better user experience

### Security & Access Control
- **Single-user authorization**: Restricted to `AUTHORIZED_USER_ID` only
- **API key protection**: All credentials stored in environment variables
- **Webhook security**: HMAC-SHA256 signature verification for Twitter webhooks
- **Rate limiting**: Built-in throttling and `wait_on_rate_limit` for all APIs
- **Content validation**: Intelligent character limit handling with CJK support

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

**❌ Twitter Posting Failures**
- **Enhanced Error Reporting**: Bot now shows failed content with character count and specific resolution guidance
- **Character Issues**: System displays actual Twitter character count for CJK text
- **API Issues**: Verify credentials and permissions using `/test_twitter`
- **Content Validation**: Pre-filtering prevents oversized content from reaching Twitter API

**⚙️ Configuration Problems**
- Configuration validation is built-in - invalid values show specific error messages
- Use `/settings` GUI instead of manual database editing
- Minimum values enforced: `REDDIT_FETCH_INTERVAL >= 5 minutes`
- Boolean values accept: `true/false`, `1/0`, `yes/no`, `on/off`

**🔄 Automated Scraper Issues**
- Verify `AUTO_SCRAPER_ENABLED = true` via `/settings`
- Check `/status` for next scheduled run time and current status
- First run occurs after one full interval (default: 60 minutes)
- Review logs for content length filtering and AI assessment results

**🤖 AI Filtering Issues**
- No `GEMINI_API_KEY`: System falls back to score-based sorting automatically
- No qualifying comments: Check length filtering logs and adjust `TOP_COMMENTS_COUNT`
- High API costs: Reduce `GEMINI_BATCH_SIZE` or `TOP_COMMENTS_COUNT`
- Pre-filtering removes oversized content before AI processing

**📄 Content Duplication**
- System checks last 7 days automatically to prevent duplicate posts
- Enhanced duplicate detection uses exact content matching
- Try different subreddits, sorting methods, or time filters for fresh content
- Use `/scrape_now` to test with current configuration

**🔐 Permission Errors**
- Twitter: Ensure app has "Read and Write" permissions (not just "Read")
- Reddit: Username/password optional for read-only access
- Telegram: Bot must be able to send messages to authorized user

**📝 Character Limit Issues**
- Bot displays accurate character count for all languages including CJK
- Pre-filtering removes oversized content before processing
- No truncation - only complete, readable content is posted
- Use `/test_twitter` to verify character counting accuracy

### Performance Optimization

**Memory Usage:**
- SQLite database with WAL mode for improved concurrent access
- Async operations prevent blocking during I/O operations
- Connection pooling built into asyncpraw and aiohttp clients
- Modular architecture reduces memory footprint

**API Rate Limits:**
- All APIs configured with `wait_on_rate_limit=True`
- Semaphore-controlled concurrent processing (5 subreddits, 10 posts simultaneously)
- Batch AI processing reduces Gemini API calls by 90%
- Pre-filtering saves API costs by removing oversized content early

**Content Processing:**
- Length validation before AI processing saves computational resources
- Intelligent duplicate detection with optimized database queries
- Smart content selection prioritizes quality over quantity

**Monitoring:**
- Health endpoint available at `http://localhost:8000/health`
- Comprehensive logging with structured error information and content context
- Real-time status via `/status` command with performance metrics
- Enhanced error reporting for all failure scenarios with source information