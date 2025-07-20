import os
import logging
import tweepy
import asyncio
import aiohttp
import tempfile
import hmac
import hashlib
import base64
import json
import re
from datetime import datetime
from aiohttp import web
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from PIL import Image
import sqlite3
from datetime import datetime, timedelta
from data_processor import DataProcessor
from reddit_scraper import AsyncRedditScraper
from config_manager import ConfigManager
from google import genai

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TwitterBot:
    def __init__(self):
        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.twitter_api_key = os.getenv('TWITTER_API_KEY')
        self.twitter_api_secret = os.getenv('TWITTER_API_SECRET')
        self.twitter_access_token = os.getenv('TWITTER_ACCESS_TOKEN')
        self.twitter_access_token_secret = os.getenv('TWITTER_ACCESS_TOKEN_SECRET')
        self.twitter_bearer_token = os.getenv('TWITTER_BEARER_TOKEN')
        self.twitter_client_id = os.getenv('TWITTER_CLIENT_ID')
        self.twitter_client_secret = os.getenv('TWITTER_CLIENT_SECRET')
        self.authorized_user_id = os.getenv('AUTHORIZED_USER_ID')
        self.app_url = os.getenv('APP_URL')  # 添加应用URL环境变量
        self.webhook_secret = os.getenv('TWITTER_WEBHOOK_SECRET')
        self.tweet_interval = int(os.getenv('TWEET_INTERVAL', '60'))
        self.gemini_batch_size = int(os.getenv('GEMINI_BATCH_SIZE', '10'))  # Gemini API批量处理大小
        self.top_comments_count = int(os.getenv('TOP_COMMENTS_COUNT', '50'))  # 取前N条高分评论进行AI筛选
        
        # 初始化Reddit爬虫和数据处理器
        self.reddit_scraper = AsyncRedditScraper()
        self.data_processor = DataProcessor()
        self.config_manager = ConfigManager()
        
        # 初始化Gemini API客户端
        self.gemini_client = None
        gemini_api_key = os.getenv('GEMINI_API_KEY')
        if gemini_api_key:
            os.environ['GEMINI_API_KEY'] = gemini_api_key
            self.gemini_client = genai.Client()
            logger.info("Gemini API客户端初始化成功")
        else:
            logger.warning("GEMINI_API_KEY未设置，将跳过评论质量筛选")
        
        # 临时存储用户状态
        self.user_states = {}
        self.pending_tweets = {}
        
        # 自动爬取任务管理
        self.auto_scraper_task = None
        self.auto_scraper_running = False
        self.last_scrape_time = None  # 上一次爬取时间
        self.next_scrape_time = None  # 下一次预计爬取时间
        
        if not all([self.telegram_token, self.twitter_api_key, self.twitter_api_secret, 
                   self.twitter_access_token, self.twitter_access_token_secret, 
                   self.twitter_bearer_token, self.authorized_user_id]):
            raise ValueError("Missing required environment variables (including TWITTER_BEARER_TOKEN)")
        
        # 初始化Twitter客户端，使用V2 API + OAuth 1.0a
        try:
            self.twitter_client = tweepy.Client(
                bearer_token=self.twitter_bearer_token,
                consumer_key=self.twitter_api_key,
                consumer_secret=self.twitter_api_secret,
                access_token=self.twitter_access_token,
                access_token_secret=self.twitter_access_token_secret,
                wait_on_rate_limit=True
            )
            
            logger.info("Twitter API初始化成功（V2 API + OAuth 1.0a）")
        except Exception as e:
            logger.error(f"Twitter API初始化失败: {e}")
            self.twitter_client = None
    
    def is_authorized_user(self, user_id: int) -> bool:
        return str(user_id) == self.authorized_user_id
    
    def get_comment_quality_prompt(self, comment: str) -> str:
        """获取单条评论质量评估的提示词"""
        return f"""请评估以下评论是否适合作为独立主题使用。

评判标准：
✅ 表达完整，不依赖上下文就能理解
✅ 包含足够的信息量或明确观点
✅ 不是简单的语气词、问候语或无意义回复
❌ 过滤掉："太麻烦了"、"谢谢"、"哈哈"、"不知道"等

评论内容："{comment}"

请严格按照以下JSON格式返回评估结果，不要包含任何其他内容：
{{
    "result": "yes",
    "reason": "判断理由简短说明",
    "confidence": 0.9
}}

其中confidence请根据你的判断给出0.1到1.0之间的数值，越符合标准，confidence越接近于1。"""

    def get_batch_comment_quality_prompt(self, comments: list) -> str:
        """获取批量评论质量评估的提示词"""
        comment_list = ""
        for i, comment in enumerate(comments):
            comment_list += f"评论{i+1}: \"{comment['body']}\"\n"
        
        return f"""请批量评估以下{len(comments)}条评论是否适合作为独立主题使用。

评判标准：
✅ 表达完整，不依赖上下文就能理解
✅ 包含足够的信息量或明确观点
✅ 不是简单的语气词、问候语或无意义回复
❌ 过滤掉："太麻烦了"、"谢谢"、"哈哈"、"不知道"等

评论内容：
{comment_list}

请严格按照以下JSON格式返回评估结果，不要包含任何其他内容：
{{
    "results": [
        {{
            "index": 1,
            "result": "yes",
            "reason": "判断理由简短说明",
            "confidence": 0.9
        }},
        {{
            "index": 2,
            "result": "no", 
            "reason": "判断理由简短说明",
            "confidence": 0.3
        }}
    ]
}}

对于每条评论，confidence请根据你的判断给出0.1到1.0之间的数值，越符合标准，confidence越接近于1。
请确保返回的results数组包含{len(comments)}个评估结果，按顺序对应上述评论。"""

    async def assess_comment_quality(self, comment: str) -> dict:
        """使用Gemini API评估评论质量"""
        if not self.gemini_client:
            # 如果没有Gemini客户端，默认返回合格
            return {"result": "yes", "reason": "未启用质量筛选", "confidence": 0.5}
        
        try:
            response = self.gemini_client.models.generate_content(
                model="gemini-2.5-flash-lite-preview-06-17",
                contents=self.get_comment_quality_prompt(comment)
            )
            
            content = response.text.strip()
            
            # 尝试解析JSON
            try:
                # 清理content，移除可能的markdown格式
                clean_content = content.strip()
                if clean_content.startswith("```json"):
                    clean_content = clean_content[7:]
                if clean_content.endswith("```"):
                    clean_content = clean_content[:-3]
                clean_content = clean_content.strip()
                
                result_data = json.loads(clean_content)
                return {
                    "result": result_data.get("result", "no"),
                    "reason": result_data.get("reason", ""),
                    "confidence": float(result_data.get("confidence", 0.0))
                }
            except json.JSONDecodeError as e:
                logger.warning(f"JSON解析失败: {e}, 原始内容: {content[:200]}")
                # 如果JSON解析失败，从文本中提取信息
                result = "yes" if "yes" in content.lower() else "no"
                return {
                    "result": result,
                    "reason": content[:100],
                    "confidence": 0.5
                }
        except Exception as e:
            logger.error(f"评估评论质量时出错: {e}")
            # 出错时默认返回合格，避免阻塞流程
            return {"result": "yes", "reason": "评估失败", "confidence": 0.5}

    async def assess_batch_comment_quality(self, comments: list) -> list:
        """使用Gemini API批量评估评论质量"""
        if not self.gemini_client:
            # 如果没有Gemini客户端，默认返回合格
            return [{"result": "yes", "reason": "未启用质量筛选", "confidence": 0.5} for _ in comments]
        
        try:
            response = self.gemini_client.models.generate_content(
                model="gemini-2.5-flash-lite-preview-06-17",
                contents=self.get_batch_comment_quality_prompt(comments)
            )
            
            content = response.text.strip()
            
            # 尝试解析JSON
            try:
                # 清理content，移除可能的markdown格式
                clean_content = content.strip()
                if clean_content.startswith("```json"):
                    clean_content = clean_content[7:]
                if clean_content.endswith("```"):
                    clean_content = clean_content[:-3]
                clean_content = clean_content.strip()
                
                result_data = json.loads(clean_content)
                results = result_data.get("results", [])
                
                # 确保结果数量与输入评论数量一致
                if len(results) != len(comments):
                    logger.warning(f"批量评估结果数量不匹配: 期望{len(comments)}，得到{len(results)}")
                    # 如果数量不匹配，回退到默认结果
                    return [{"result": "yes", "reason": "结果数量不匹配", "confidence": 0.5} for _ in comments]
                
                # 转换结果格式
                formatted_results = []
                for i, result in enumerate(results):
                    formatted_results.append({
                        "result": result.get("result", "no"),
                        "reason": result.get("reason", ""),
                        "confidence": float(result.get("confidence", 0.0))
                    })
                
                return formatted_results
                
            except json.JSONDecodeError as e:
                logger.warning(f"批量评估JSON解析失败: {e}, 原始内容: {content[:200]}")
                # 如果JSON解析失败，回退到逐条处理
                logger.info("回退到逐条评估模式")
                batch_results = []
                for comment in comments:
                    single_result = await self.assess_comment_quality(comment['body'])
                    batch_results.append(single_result)
                return batch_results
                
        except Exception as e:
            logger.error(f"批量评估评论质量时出错: {e}")
            # 出错时回退到逐条处理
            logger.info("批量评估失败，回退到逐条评估模式")
            batch_results = []
            for comment in comments:
                try:
                    single_result = await self.assess_comment_quality(comment['body'])
                    batch_results.append(single_result)
                except:
                    # 如果逐条处理也失败，使用默认值
                    batch_results.append({"result": "yes", "reason": "评估失败", "confidence": 0.5})
            return batch_results
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
            
        await update.message.reply_text(
            "你好！发送任何消息给我，我会自动转发到你的Twitter账户。\n\n"
            "使用 /help 查看帮助信息。"
        )
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
            
        help_text = """
🤖 <b>Twitter Bot 使用说明</b>

📝 <b>基本功能:</b>
• 直接发送文本 → 发布到Twitter
• 发送图片（可带文字） → 发布图片到Twitter

🔄 <b>自动爬取功能:</b>
• /start_scraper → 启动自动爬取系统
• /stop_scraper → 停止自动爬取系统
• /status → 查看运行状态

⚙️ <b>配置管理:</b>
• /settings → 图形化配置界面
• /set [配置名] [新值] → 命令行配置（备用）
• /cancel → 取消当前操作

💡 <b>其他命令:</b>
• /start → 开始使用
• /help → 显示此帮助
• /test_twitter → 测试Twitter API连接

📝 <b>注意事项:</b>
• 消息长度限制280字符
• 图片自动压缩优化
• 默认自动爬取关闭，需手动启动
• 配置修改支持图形界面和命令行两种方式
        """
        await update.message.reply_text(help_text, parse_mode='HTML')
    
    async def tweet_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
        
        if not self.twitter_client:
            await update.message.reply_text("❌ Twitter API未正确配置，请检查环境变量。")
            return
            
        message_text = update.message.text
        
        if len(message_text) > 280:
            await update.message.reply_text("消息太长了！Twitter限制280字符以内。")
            return
        
        # 存储待发送的推文
        user_id = update.effective_user.id
        self.pending_tweets[user_id] = {
            'type': 'text',
            'content': message_text,
            'message_id': update.message.message_id
        }
        
        # 创建确认按钮
        keyboard = [
            [
                InlineKeyboardButton("✅ 发送到Twitter", callback_data=f"confirm_tweet_{user_id}"),
                InlineKeyboardButton("❌ 取消", callback_data=f"cancel_tweet_{user_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"📝 准备发送以下内容到Twitter:\n\n{message_text}\n\n是否确认发送？",
            reply_markup=reply_markup
        )
    
    async def tweet_with_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
        
        if not self.twitter_client:
            await update.message.reply_text("❌ Twitter API未正确配置，请检查环境变量。")
            return
            
        # 获取图片和文字描述
        photo = update.message.photo[-1]  # 获取最大尺寸的图片
        caption = update.message.caption or ""
        
        if len(caption) > 280:
            await update.message.reply_text("文字描述太长了！Twitter限制280字符以内。")
            return
        
        # 存储待发送的推文（包含图片信息）
        user_id = update.effective_user.id
        self.pending_tweets[user_id] = {
            'type': 'image',
            'content': caption,
            'photo_file_id': photo.file_id,
            'message_id': update.message.message_id
        }
        
        # 创建确认按钮
        keyboard = [
            [
                InlineKeyboardButton("✅ 发送到Twitter", callback_data=f"confirm_tweet_{user_id}"),
                InlineKeyboardButton("❌ 取消", callback_data=f"cancel_tweet_{user_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🖼️ 准备发送图片到Twitter:\n\n{caption if caption else '无描述'}\n\n是否确认发送？",
            reply_markup=reply_markup
        )
    
    async def handle_tweet_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理推文确认回调"""
        query = update.callback_query
        await query.answer()
        
        if not self.is_authorized_user(query.from_user.id):
            await query.edit_message_text("❌ 你没有权限使用此机器人。")
            return
        
        user_id = query.from_user.id
        data = query.data
        
        if data.startswith("confirm_tweet_"):
            # 确认发送推文
            if user_id in self.pending_tweets:
                tweet_data = self.pending_tweets[user_id]
                
                try:
                    if tweet_data['type'] == 'text':
                        # 发送文本推文（使用v1.1 API）
                        response = self.twitter_client.create_tweet(text=tweet_data['content'])
                        tweet_id = response.data['id']
                        
                        await query.edit_message_text(
                            f"✅ 推文发送成功！\n\n"
                            f"推文ID: {tweet_id}\n"
                            f"内容: {tweet_data['content']}"
                        )
                        
                    elif tweet_data['type'] == 'image':
                        # 发送图片推文
                        await self.send_image_tweet(query, tweet_data, context)
                        
                    # 清理待发送数据
                    del self.pending_tweets[user_id]
                    
                except Exception as e:
                    logger.error(f"发送推文时出错: {e}")
                    error_msg = str(e)
                    if "401" in error_msg or "Unauthorized" in error_msg:
                        await query.edit_message_text("❌ Twitter API认证失败，请检查API密钥和权限设置。")
                    else:
                        await query.edit_message_text(f"❌ 发送推文失败: {error_msg}")
            else:
                await query.edit_message_text("❌ 推文数据已过期，请重新发送。")
                
        elif data.startswith("cancel_tweet_"):
            # 取消发送推文
            if user_id in self.pending_tweets:
                del self.pending_tweets[user_id]
            await query.edit_message_text("❌ 推文发送已取消。")
    
    async def send_image_tweet(self, query, tweet_data, context):
        """发送图片推文的具体实现"""
        try:
            # 获取图片文件
            file = await context.bot.get_file(tweet_data['photo_file_id'])
            
            # 创建临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
                # 下载图片到临时文件
                await file.download_to_drive(temp_file.name)
                
                try:
                    # 使用Pillow优化图片
                    with Image.open(temp_file.name) as img:
                        # 转换为RGB（Twitter需要）
                        if img.mode != 'RGB':
                            img = img.convert('RGB')
                        
                        # 调整图片大小（Twitter限制5MB）
                        max_size = (2048, 2048)
                        img.thumbnail(max_size, Image.Resampling.LANCZOS)
                        
                        # 保存优化后的图片
                        optimized_path = temp_file.name.replace('.jpg', '_optimized.jpg')
                        img.save(optimized_path, 'JPEG', quality=85, optimize=True)
                    
                    # Upload media using V1.1 API (required for media upload)
                    auth = tweepy.OAuth1UserHandler(
                        self.twitter_api_key,
                        self.twitter_api_secret,
                        self.twitter_access_token,
                        self.twitter_access_token_secret
                    )
                    twitter_api_v1 = tweepy.API(auth)
                    media = twitter_api_v1.media_upload(optimized_path)
                    
                    # Create tweet with media using V2 API
                    response = self.twitter_client.create_tweet(
                        text=tweet_data['content'],
                        media_ids=[media.media_id]
                    )
                    
                    tweet_id = response.data['id']
                    
                    await query.edit_message_text(
                        f"✅ 图片推文发送成功！\n\n"
                        f"推文ID: {tweet_id}\n"
                        f"描述: {tweet_data['content'] if tweet_data['content'] else '无描述'}"
                    )
                    
                finally:
                    # 清理临时文件
                    try:
                        os.unlink(temp_file.name)
                        if 'optimized_path' in locals():
                            os.unlink(optimized_path)
                    except:
                        pass
                        
        except Exception as e:
            logger.error(f"发送图片推文时出错: {e}")
            error_msg = str(e)
            if "401" in error_msg or "Unauthorized" in error_msg:
                await query.edit_message_text("❌ Twitter API认证失败，请检查API密钥和权限设置。")
            elif "413" in error_msg or "too large" in error_msg.lower():
                await query.edit_message_text("❌ 图片太大，请发送较小的图片。")
            else:
                await query.edit_message_text(f"❌ 发送图片推文失败: {error_msg}")
    
    
    
    
    
    
    
    async def save_sent_comment(self, comment, tweet_id):
        """保存已发送的评论到数据库"""
        try:
            # 添加推文ID到评论数据
            comment['tweet_id'] = tweet_id
            comment['sent_at'] = datetime.now()
            
            # 保存到数据库
            self.data_processor.save_comments_to_database([comment])
            
        except Exception as e:
            logger.error(f"保存评论到数据库时出错: {e}")
    
    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理文本消息"""
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
        
        user_id = update.effective_user.id
        
        # 检查是否在配置输入状态
        if user_id in self.user_states and self.user_states[user_id]['state'] == 'waiting_config_input':
            await self.handle_config_input(update, context)
        else:
            # 直接处理为普通推文消息
            await self.tweet_message(update, context)

    async def handle_config_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理配置值输入"""
        try:
            user_id = update.effective_user.id
            new_value = update.message.text.strip()
            
            if not user_id in self.user_states:
                await update.message.reply_text("❌ 配置状态已过期，请重新开始。")
                return
            
            user_state = self.user_states[user_id]
            config_key = user_state['config_key']
            config_type = user_state['config_type']
            message_id = user_state['message_id']
            chat_id = user_state['chat_id']
            
            # 验证输入值
            validation_result = self._validate_config_value(config_key, new_value, config_type)
            if not validation_result['valid']:
                await update.message.reply_text(f"❌ 输入值无效: {validation_result['error']}")
                return
            
            # 更新配置
            success = self.config_manager.update_config(config_key, new_value)
            
            if success:
                # 清理用户状态
                del self.user_states[user_id]
                
                # 删除用户的输入消息
                try:
                    await update.message.delete()
                except:
                    pass
                
                # 显示成功消息并返回设置菜单
                success_message = f"""
✅ <b>配置更新成功</b>

<b>{config_key}:</b> <code>{new_value}</code>

配置已保存，正在返回设置菜单...
                """.strip()
                
                # 编辑原消息显示成功，然后返回设置菜单
                application = Application.builder().token(self.telegram_token).build()
                await application.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=success_message,
                    parse_mode='HTML'
                )
                
                # 等待一会儿然后显示设置菜单
                await asyncio.sleep(2)
                await self.show_settings_menu(chat_id, message_id, edit=True)
                
            else:
                await update.message.reply_text("❌ 更新配置失败，请重试。")
                
        except Exception as e:
            logger.error(f"处理配置输入时出错: {e}")
            await update.message.reply_text(f"❌ 处理配置输入失败: {str(e)}")

    def _validate_config_value(self, config_key, value, config_type):
        """验证配置值"""
        try:
            if config_type == 'int':
                int_value = int(value)
                if config_key in ['GEMINI_BATCH_SIZE', 'TOP_COMMENTS_COUNT', 'REDDIT_POST_FETCH_COUNT', 
                                'REDDIT_COMMENTS_PER_POST', 'REDDIT_FETCH_INTERVAL']:
                    if int_value <= 0:
                        return {'valid': False, 'error': '数值必须大于0'}
                    if config_key == 'REDDIT_FETCH_INTERVAL' and int_value < 5:
                        return {'valid': False, 'error': '爬取间隔不能少于5分钟'}
                return {'valid': True}
                
            elif config_type == 'bool':
                if value.lower() not in ['true', 'false', '1', '0', 'yes', 'no', 'on', 'off']:
                    return {'valid': False, 'error': '请输入 true/false, 1/0, yes/no, 或 on/off'}
                return {'valid': True}
                
            elif config_type == 'str':
                if config_key == 'REDDIT_SORT_METHOD':
                    valid_sorts = ['hot', 'new', 'top', 'controversial', 'rising', 'gilded']
                    if value.lower() not in valid_sorts:
                        return {'valid': False, 'error': f'排序方式只能是: {", ".join(valid_sorts)}'}
                elif config_key == 'REDDIT_TIME_FILTER':
                    valid_filters = ['all', 'year', 'month', 'week', 'day', 'hour']
                    if value.lower() not in valid_filters:
                        return {'valid': False, 'error': f'时间筛选只能是: {", ".join(valid_filters)}'}
                if len(value.strip()) == 0:
                    return {'valid': False, 'error': '值不能为空'}
                return {'valid': True}
                
            elif config_type == 'list':
                if config_key == 'REDDIT_SUBREDDITS':
                    subreddits = [s.strip() for s in value.split(',') if s.strip()]
                    if not subreddits:
                        return {'valid': False, 'error': '至少需要一个有效的板块名称'}
                    # 简单验证板块名称格式
                    for sub in subreddits:
                        if not sub.replace('_', '').replace('-', '').isalnum():
                            return {'valid': False, 'error': f'板块名称格式无效: {sub}'}
                return {'valid': True}
                
            return {'valid': True}
            
        except ValueError as e:
            return {'valid': False, 'error': f'数据类型错误: {str(e)}'}
        except Exception as e:
            return {'valid': False, 'error': f'验证失败: {str(e)}'}
    
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """验证Twitter webhook签名"""
        if not self.webhook_secret:
            return False
            
        try:
            # Twitter使用sha256 HMAC
            expected_signature = hmac.new(
                self.webhook_secret.encode('utf-8'),
                payload,
                hashlib.sha256
            ).digest()
            
            # Twitter发送的签名是base64编码的
            expected_signature_b64 = base64.b64encode(expected_signature).decode('utf-8')
            
            # 比较签名（常量时间比较，防止时间攻击）
            return hmac.compare_digest(signature, expected_signature_b64)
        except Exception as e:
            logger.error(f"验证webhook签名时出错: {e}")
            return False
    
    async def send_startup_notification(self):
        """发送启动通知给授权用户"""
        try:
            application = Application.builder().token(self.telegram_token).build()
            startup_message = f"""
🤖 <b>Twitter Bot 已启动</b>

✅ <b>状态:</b> 在线运行
🔗 <b>Twitter API:</b> 已连接
⏰ <b>启动时间:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📝 发送任何消息给我，我会自动转发到你的Twitter账户。
使用 /status 查看运行状态。
            """.strip()
            
            await application.bot.send_message(
                chat_id=self.authorized_user_id,
                text=startup_message,
                parse_mode='HTML'
            )
            logger.info("启动通知已发送")
        except Exception as e:
            logger.error(f"发送启动通知失败: {e}")

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示机器人状态"""
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
        
        try:
            # 检查Twitter API连接
            twitter_status = "✅ 正常" if self.twitter_client else "❌ 失败"
            
            # 检查自动爬取状态
            scraper_enabled = self.config_manager.get_config('AUTO_SCRAPER_ENABLED', False)
            scraper_running = self.auto_scraper_running
            
            if scraper_enabled and scraper_running:
                scraper_status = "🟢 运行中"
                fetch_interval = self.config_manager.get_config('REDDIT_FETCH_INTERVAL', 60)
                
                # 构建详细的爬取信息
                scraper_detail = f"🔄 间隔时间: {fetch_interval} 分钟\n"
                
                if self.last_scrape_time:
                    scraper_detail += f"📅 上次爬取: {self.last_scrape_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                else:
                    scraper_detail += f"📅 上次爬取: 尚未开始\n"
                
                if self.next_scrape_time:
                    now = datetime.now()
                    if self.next_scrape_time > now:
                        time_diff = self.next_scrape_time - now
                        minutes_left = int(time_diff.total_seconds() / 60)
                        hours_left = minutes_left // 60
                        mins_left = minutes_left % 60
                        
                        if hours_left > 0:
                            time_left_str = f"{hours_left}小时{mins_left}分钟"
                        else:
                            time_left_str = f"{mins_left}分钟"
                        
                        scraper_detail += f"⏰ 下次爬取: {self.next_scrape_time.strftime('%H:%M:%S')} (还有{time_left_str})"
                    else:
                        scraper_detail += f"⏰ 下次爬取: 即将开始"
                else:
                    scraper_detail += f"⏰ 下次爬取: 计算中..."
                
            elif scraper_enabled and not scraper_running:
                scraper_status = "🟡 启用但未运行"
                fetch_interval = self.config_manager.get_config('REDDIT_FETCH_INTERVAL', 60)
                scraper_detail = f"🔄 间隔时间: {fetch_interval} 分钟\n📅 等待系统启动"
            else:
                scraper_status = "🔴 已停止"
                scraper_detail = "使用 /start_scraper 启动"
            
            # 获取运行时间（简化版）
            uptime = "运行中"
            
            status_message = f"""
📊 <b>Bot 运行状态</b>

🤖 <b>Telegram Bot:</b> ✅ 在线
🐦 <b>Twitter API:</b> {twitter_status}
🔄 <b>自动爬取:</b> {scraper_status}
📝 <b>爬取详情:</b> {scraper_detail}
⏱️ <b>运行状态:</b> {uptime}
👤 <b>授权用户:</b> {update.effective_user.first_name}

💡 <b>使用提示:</b>
• 直接发送文本 → 发布推文
• 发送图片 → 发布图片推文
• /start_scraper → 启动自动爬取
• /stop_scraper → 停止自动爬取
• /scrape_now → 立即执行一次爬取
• /test_twitter → 测试Twitter API连接
• /settings → 查看配置
• /help → 查看帮助
            """.strip()
            
            await update.message.reply_text(status_message, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"获取状态时出错: {e}")
            await update.message.reply_text("❌ 获取状态失败")

    async def settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示和管理配置设置"""
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
        
        try:
            await self.show_settings_menu(update.message.chat_id, update.message.message_id)
            
        except Exception as e:
            logger.error(f"获取设置时出错: {e}")
            await update.message.reply_text("❌ 获取设置失败")

    async def show_settings_menu(self, chat_id, message_id=None, edit=False):
        """显示配置设置菜单"""
        try:
            configs = self.config_manager.get_all_configs()
            
            settings_message = "🛠️ <b>Bot 配置设置</b>\n\n"
            settings_message += "点击下方按钮修改对应配置：\n\n"
            
            # 创建内联键盘
            keyboard = []
            
            # 为每个配置项创建一个按钮
            for key, config_data in configs.items():
                value = config_data['value']
                description = config_data['description']
                
                # 格式化显示值
                if isinstance(value, list):
                    display_value = ', '.join(value) if value else '无'
                else:
                    display_value = str(value)
                
                # 限制显示值的长度
                if len(display_value) > 20:
                    display_value = display_value[:20] + "..."
                
                button_text = f"📝 {key}"
                callback_data = f"config_{key}"
                
                keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
                
                # 在消息中显示当前值和描述
                settings_message += f"<b>{key}:</b> <code>{display_value}</code>\n"
                settings_message += f"<i>{description}</i>\n\n"
            
            # 添加关闭按钮
            keyboard.append([InlineKeyboardButton("❌ 关闭", callback_data="close_settings")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if edit and message_id:
                application = Application.builder().token(self.telegram_token).build()
                await application.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=settings_message,
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
            else:
                application = Application.builder().token(self.telegram_token).build()
                await application.bot.send_message(
                    chat_id=chat_id,
                    text=settings_message,
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
            
        except Exception as e:
            logger.error(f"显示设置菜单时出错: {e}")
            application = Application.builder().token(self.telegram_token).build()
            await application.bot.send_message(chat_id=chat_id, text="❌ 显示设置菜单失败")

    async def set_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """设置配置值"""
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
        
        if len(context.args) < 2:
            await update.message.reply_text(
                "❌ 使用方法: /set [配置名] [新值]\n"
                "例如: /set REDDIT_FETCH_INTERVAL 30"
            )
            return
        
        try:
            config_key = context.args[0].upper()
            config_value = ' '.join(context.args[1:])
            
            # 验证配置键是否存在
            all_configs = self.config_manager.get_all_configs()
            if config_key not in all_configs:
                available_keys = '\n'.join(all_configs.keys())
                await update.message.reply_text(
                    f"❌ 未知的配置项: {config_key}\n\n"
                    f"可用的配置项:\n{available_keys}"
                )
                return
            
            # 更新配置
            if self.config_manager.update_config(config_key, config_value):
                await update.message.reply_text(
                    f"✅ 配置已更新:\n"
                    f"<b>{config_key}:</b> {config_value}\n\n"
                    f"💡 重启bot后生效（如果是关键配置）",
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text("❌ 更新配置失败")
            
        except Exception as e:
            logger.error(f"设置配置时出错: {e}")
            await update.message.reply_text(f"❌ 设置配置失败: {str(e)}")

    async def start_scraper_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """启动自动爬取系统"""
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
        
        try:
            # 检查当前状态
            current_status = self.config_manager.get_config('AUTO_SCRAPER_ENABLED', False)
            
            if current_status:
                await update.message.reply_text("ℹ️ 自动爬取系统已经在运行中")
                return
            
            # 启用自动爬取
            success = self.config_manager.update_config('AUTO_SCRAPER_ENABLED', 'true')
            
            if success:
                fetch_interval = self.config_manager.get_config('REDDIT_FETCH_INTERVAL', 60)
                await update.message.reply_text(
                    f"🚀 <b>自动爬取系统已启动</b>\n\n"
                    f"系统将在 {fetch_interval} 分钟后开始首次爬取，之后每 {fetch_interval} 分钟自动爬取一次。\n"
                    f"使用 /stop_scraper 停止自动爬取。",
                    parse_mode='HTML'
                )
                logger.info("用户启动了自动爬取系统")
            else:
                await update.message.reply_text("❌ 启动自动爬取系统失败")
                
        except Exception as e:
            logger.error(f"启动自动爬取系统时出错: {e}")
            await update.message.reply_text(f"❌ 启动失败: {str(e)}")

    async def stop_scraper_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """停止自动爬取系统"""
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
        
        try:
            # 检查当前状态
            current_status = self.config_manager.get_config('AUTO_SCRAPER_ENABLED', False)
            
            if not current_status:
                await update.message.reply_text("ℹ️ 自动爬取系统当前处于停止状态")
                return
            
            # 禁用自动爬取
            success = self.config_manager.update_config('AUTO_SCRAPER_ENABLED', 'false')
            
            if success:
                await update.message.reply_text(
                    "⏸️ <b>自动爬取系统已停止</b>\n\n"
                    "系统已停止自动爬取Reddit内容。\n"
                    "使用 /start_scraper 重新启动自动爬取。",
                    parse_mode='HTML'
                )
                logger.info("用户停止了自动爬取系统")
            else:
                await update.message.reply_text("❌ 停止自动爬取系统失败")
                
        except Exception as e:
            logger.error(f"停止自动爬取系统时出错: {e}")
            await update.message.reply_text(f"❌ 停止失败: {str(e)}")

    async def scrape_now_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """立即执行一次爬取"""
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
        
        try:
            await update.message.reply_text("🚀 <b>开始立即爬取</b>\n\n正在爬取Reddit内容并使用AI筛选...", parse_mode='HTML')
            
            # 执行爬取
            await self.auto_scrape_and_post()
            
            # 更新下次爬取时间（如果自动爬取正在运行）
            if self.auto_scraper_running:
                fetch_interval = self.config_manager.get_config('REDDIT_FETCH_INTERVAL', 60)
                self.next_scrape_time = datetime.now() + timedelta(minutes=fetch_interval)
            
            await update.message.reply_text(
                "✅ <b>立即爬取完成</b>\n\n"
                "已完成一次完整的爬取和发布流程。\n"
                "如果自动爬取正在运行，下次爬取时间已重新计算。",
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"立即爬取时出错: {e}")
            await update.message.reply_text(f"❌ 立即爬取失败: {str(e)}")

    async def test_twitter_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """测试Twitter API连接和权限"""
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
        
        try:
            await update.message.reply_text("🔍 正在测试Twitter API连接和权限...")
            
            if not self.twitter_client:
                await update.message.reply_text("❌ Twitter API未初始化，请检查API配置。")
                return
            
            # 测试API连接
            try:
                # 使用V2 API获取当前用户信息，需要指定user_fields参数
                user = self.twitter_client.get_me(user_fields=['public_metrics'])
                username = user.data.username
                user_id = user.data.id
                # 检查public_metrics是否存在
                followers_count = user.data.public_metrics.get('followers_count', 0) if hasattr(user.data, 'public_metrics') else 0
                
                await update.message.reply_text(
                    f"✅ <b>Twitter API连接测试成功</b>\n\n"
                    f"👤 <b>账户:</b> @{username}\n"
                    f"🆔 <b>用户ID:</b> {user_id}\n"
                    f"👥 <b>粉丝数:</b> {followers_count:,}\n"
                    f"🔑 <b>API方式:</b> OAuth 1.0a\n"
                    f"📡 <b>连接状态:</b> 已连接\n\n"
                    f"💡 <b>说明:</b>\n"
                    f"• 使用OAuth 1.0a认证\n"
                    f"• 完全兼容X.com免费版\n"
                    f"• 可以发布推文和上传媒体",
                    parse_mode='HTML'
                )
                
            except Exception as api_e:
                error_msg = str(api_e)
                if "403" in error_msg:
                    await update.message.reply_text(
                        f"🚫 <b>Twitter API权限测试失败</b>\n\n"
                        f"错误: {error_msg}\n\n"
                        f"📋 <b>解决步骤:</b>\n"
                        f"1. 登录 Twitter Developer Portal\n"
                        f"2. 检查应用权限设置\n"
                        f"3. 确保选择了 'Read and Write' 权限\n"
                        f"4. 重新生成 Access Token 和 Secret\n"
                        f"5. 更新 .env 文件中的令牌",
                        parse_mode='HTML'
                    )
                elif "401" in error_msg:
                    await update.message.reply_text(
                        f"🔐 <b>Twitter API认证失败</b>\n\n"
                        f"错误: {error_msg}\n\n"
                        f"请检查以下环境变量是否正确:\n"
                        f"• TWITTER_API_KEY\n"
                        f"• TWITTER_API_SECRET\n"
                        f"• TWITTER_ACCESS_TOKEN\n"
                        f"• TWITTER_ACCESS_TOKEN_SECRET"
                    )
                else:
                    await update.message.reply_text(f"❌ Twitter API测试失败: {error_msg}")
                    
        except Exception as e:
            logger.error(f"测试Twitter API时出错: {e}")
            await update.message.reply_text(f"❌ 测试失败: {str(e)}")

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """取消当前操作"""
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
        
        user_id = update.effective_user.id
        
        if user_id in self.user_states:
            state = self.user_states[user_id].get('state')
            del self.user_states[user_id]
            
            if state == 'waiting_config_input':
                await update.message.reply_text("❌ 配置修改已取消")
            else:
                await update.message.reply_text("❌ 当前操作已取消")
        else:
            await update.message.reply_text("ℹ️ 当前没有进行中的操作")

    async def handle_config_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理配置选择回调"""
        query = update.callback_query
        await query.answer()
        
        if not self.is_authorized_user(query.from_user.id):
            await query.edit_message_text("❌ 你没有权限使用此机器人。")
            return
        
        try:
            user_id = query.from_user.id
            data = query.data
            
            if data == "close_settings":
                # 关闭设置菜单
                await query.edit_message_text("✅ 设置菜单已关闭")
                if user_id in self.user_states:
                    del self.user_states[user_id]
                return
            
            elif data.startswith("config_"):
                # 选择了一个配置项
                config_key = data.replace("config_", "")
                
                # 获取配置信息
                all_configs = self.config_manager.get_all_configs()
                if config_key not in all_configs:
                    await query.edit_message_text("❌ 配置项不存在")
                    return
                
                config_data = all_configs[config_key]
                current_value = config_data['value']
                description = config_data['description']
                config_type = config_data['type']
                
                # 格式化当前值显示
                if isinstance(current_value, list):
                    display_value = ', '.join(current_value) if current_value else '无'
                else:
                    display_value = str(current_value)
                
                # 特殊处理AUTO_SCRAPER_ENABLED配置项
                if config_key == "AUTO_SCRAPER_ENABLED":
                    await self._handle_bool_config_selection(query, config_key, current_value, description)
                    return
                
                # 其他配置项的常规处理
                # 设置用户状态为等待配置输入
                self.user_states[user_id] = {
                    'state': 'waiting_config_input',
                    'config_key': config_key,
                    'config_type': config_type,
                    'message_id': query.message.message_id,
                    'chat_id': query.message.chat_id
                }
                
                # 提供输入提示
                input_hint = self._get_config_input_hint(config_key, config_type)
                
                edit_message = f"""
🔧 <b>修改配置: {config_key}</b>

📝 <b>当前值:</b> <code>{display_value}</code>
📖 <b>说明:</b> {description}
🔤 <b>类型:</b> {config_type}

{input_hint}

💡 请发送新的配置值，或发送 /cancel 取消修改。
                """.strip()
                
                # 添加返回和取消按钮
                keyboard = [
                    [InlineKeyboardButton("🔙 返回设置菜单", callback_data="back_to_settings")],
                    [InlineKeyboardButton("❌ 取消", callback_data="cancel_config")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(edit_message, parse_mode='HTML', reply_markup=reply_markup)
            
            elif data == "back_to_settings":
                # 返回设置菜单
                if user_id in self.user_states:
                    del self.user_states[user_id]
                await self.show_settings_menu(query.message.chat_id, query.message.message_id, edit=True)
            
            elif data == "cancel_config":
                # 取消配置修改
                if user_id in self.user_states:
                    del self.user_states[user_id]
                await query.edit_message_text("❌ 配置修改已取消")
                
            elif data.startswith("bool_config_"):
                # 处理布尔类型配置的按钮选择
                await self._handle_bool_config_button(query, data)
                
        except Exception as e:
            logger.error(f"处理配置选择时出错: {e}")
            await query.edit_message_text(f"❌ 处理配置选择失败: {str(e)}")

    async def _handle_bool_config_selection(self, query, config_key, current_value, description):
        """处理布尔类型配置的选择界面"""
        try:
            current_status = "🟢 已开启" if current_value else "🔴 已关闭"
            
            edit_message = f"""
🔧 <b>修改配置: {config_key}</b>

📝 <b>当前状态:</b> {current_status}
📖 <b>说明:</b> {description}

💡 请选择新的状态：
            """.strip()
            
            # 创建开启/关闭按钮
            keyboard = [
                [
                    InlineKeyboardButton("🟢 开启", callback_data=f"bool_config_{config_key}_true"),
                    InlineKeyboardButton("🔴 关闭", callback_data=f"bool_config_{config_key}_false")
                ],
                [InlineKeyboardButton("🔙 返回设置菜单", callback_data="back_to_settings")],
                [InlineKeyboardButton("❌ 取消", callback_data="cancel_config")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(edit_message, parse_mode='HTML', reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"处理布尔配置选择时出错: {e}")
            await query.edit_message_text(f"❌ 处理布尔配置失败: {str(e)}")

    async def _handle_bool_config_button(self, query, data):
        """处理布尔配置按钮点击"""
        try:
            user_id = query.from_user.id
            
            # 解析回调数据: bool_config_{config_key}_{value}
            # 因为config_key可能包含下划线（如AUTO_SCRAPER_ENABLED），需要特殊处理
            if not data.startswith("bool_config_"):
                await query.edit_message_text("❌ 无效的配置数据")
                return
            
            # 移除前缀
            remaining = data[12:]  # 移除 "bool_config_"
            
            # 从末尾找到最后一个下划线，之后的是value
            last_underscore_index = remaining.rfind("_")
            if last_underscore_index == -1:
                await query.edit_message_text("❌ 无效的配置数据")
                return
            
            config_key = remaining[:last_underscore_index]
            new_value = remaining[last_underscore_index + 1:]
            
            logger.info(f"解析布尔配置: data={data}, config_key={config_key}, new_value={new_value}")
            
            # 更新配置
            success = self.config_manager.update_config(config_key, new_value)
            
            if success:
                status_text = "🟢 已开启" if new_value == "true" else "🔴 已关闭"
                action_text = "开启" if new_value == "true" else "关闭"
                
                success_message = f"""
✅ <b>配置更新成功</b>

<b>{config_key}:</b> {status_text}

自动爬取系统已{action_text}，正在返回设置菜单...
                """.strip()
                
                await query.edit_message_text(success_message, parse_mode='HTML')
                
                # 等待一会儿然后返回设置菜单
                await asyncio.sleep(2)
                await self.show_settings_menu(query.message.chat_id, query.message.message_id, edit=True)
                
            else:
                await query.edit_message_text("❌ 更新配置失败，请重试。")
                
        except Exception as e:
            logger.error(f"处理布尔配置按钮时出错: {e}")
            await query.edit_message_text(f"❌ 处理配置按钮失败: {str(e)}")

    def _get_config_input_hint(self, config_key, config_type):
        """获取配置输入提示"""
        hints = {
            'GEMINI_BATCH_SIZE': '📝 输入数字 (建议: 5-20)',
            'TOP_COMMENTS_COUNT': '📝 输入数字 (建议: 20-100)', 
            'REDDIT_POST_FETCH_COUNT': '📝 输入数字 (建议: 10-100)',
            'REDDIT_SORT_METHOD': '📝 输入排序方式:\n• hot (热门，综合考虑得分和时间)\n• new (最新，按发布时间)\n• top (顶尖，按得分排序)\n• controversial (有争议，支持和反对都多)\n• rising (上升中，近期获得关注的新帖)\n• gilded (镀金，获得过奖励的帖子)',
            'REDDIT_TIME_FILTER': '📝 输入时间筛选范围 (仅对top和controversial有效):\n• all (全部时间)\n• year (过去一年)\n• month (过去一月)\n• week (过去一周)\n• day (过去一天)\n• hour (过去一小时)',
            'REDDIT_COMMENTS_PER_POST': '📝 输入数字 (建议: 10-50)',
            'REDDIT_FETCH_INTERVAL': '📝 输入分钟数 (建议: 30-180)',
            'REDDIT_SUBREDDITS': '📝 输入板块名称，用逗号分隔\n例如: python,programming,MachineLearning',
            'AUTO_SCRAPER_ENABLED': '📝 输入开关状态: true 或 false'
        }
        
        return hints.get(config_key, f'📝 输入新的{config_type}类型值')

    async def auto_scrape_and_post(self):
        """自动爬取Reddit评论并发布最佳评论到Twitter"""
        try:
            # 更新爬取时间戳
            self.last_scrape_time = datetime.now()
            logger.info(f"开始自动爬取... {self.last_scrape_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 从配置管理器获取参数
            subreddits = self.config_manager.get_config('REDDIT_SUBREDDITS', ['python'])
            post_fetch_count = self.config_manager.get_config('REDDIT_POST_FETCH_COUNT', 50)
            sort_method = self.config_manager.get_config('REDDIT_SORT_METHOD', 'hot')
            time_filter = self.config_manager.get_config('REDDIT_TIME_FILTER', 'day')
            comments_per_post = self.config_manager.get_config('REDDIT_COMMENTS_PER_POST', 20)
            top_comments_count = self.config_manager.get_config('TOP_COMMENTS_COUNT', 50)
            gemini_batch_size = self.config_manager.get_config('GEMINI_BATCH_SIZE', 10)
            
            logger.info(f"爬取配置: subreddits={subreddits}, posts={post_fetch_count}, sort={sort_method}, time_filter={time_filter}")
            
            all_comments = []
            total_api_calls = 0
            
            # 准备并发爬取配置
            subreddit_configs = []
            for subreddit in subreddits:
                config = {
                    'name': subreddit,
                    'limit': post_fetch_count,
                    'sort_by': sort_method,
                    'comments_limit': comments_per_post,
                    'time_filter': time_filter
                }
                subreddit_configs.append(config)
            
            logger.info(f"开始并发爬取 {len(subreddit_configs)} 个subreddit...")
            scrape_start_time = datetime.now()
            
            # 使用并发爬取所有subreddit
            try:
                scraped_data = await self.reddit_scraper.scrape_multiple_subreddits_concurrent(subreddit_configs)
                
                scrape_end_time = datetime.now()
                scrape_duration = (scrape_end_time - scrape_start_time).total_seconds()
                
                # 统计数据
                total_posts = 0
                successful_subreddits = 0
                
                # 合并所有评论数据
                for subreddit_name, (posts_data, comments_data) in scraped_data.items():
                    total_posts += len(posts_data) if posts_data else 0
                    
                    if comments_data:
                        logger.info(f"从 r/{subreddit_name} 获取了 {len(posts_data)} 个帖子，{len(comments_data)} 条评论")
                        all_comments.extend(comments_data)
                        successful_subreddits += 1
                    else:
                        logger.warning(f"从 r/{subreddit_name} 未获取到评论")
                
                # 性能统计
                comments_per_second = len(all_comments) / scrape_duration if scrape_duration > 0 else 0
                logger.info(
                    f"🚀 并发爬取完成：用时 {scrape_duration:.2f}秒，"
                    f"成功爬取 {successful_subreddits}/{len(subreddit_configs)} 个subreddit，"
                    f"总计 {total_posts} 个帖子，{len(all_comments)} 条评论，"
                    f"平均速度 {comments_per_second:.1f} 评论/秒"
                )
                        
            except Exception as e:
                logger.error(f"并发爬取时出错: {e}")
                await self.send_notification(f"❌ 并发爬取失败: {str(e)}")
                return
            
            if not all_comments:
                logger.warning("未获取到任何评论")
                await self.send_notification("⚠️ 自动爬取失败：未获取到任何评论")
                return
            
            logger.info(f"总共获取了 {len(all_comments)} 条评论")
            
            # 按分数排序，取前N条
            sorted_comments = sorted(all_comments, key=lambda x: x.get('score', 0), reverse=True)
            top_comments = sorted_comments[:top_comments_count]
            
            logger.info(f"选择前 {len(top_comments)} 条高分评论进行AI筛选")
            
            # AI质量筛选
            if self.gemini_client:
                filtered_comments, api_calls = await self.filter_comments_with_ai(top_comments, gemini_batch_size)
                total_api_calls = api_calls
                logger.info(f"AI筛选完成，使用了 {api_calls} 次API调用，获得 {len(filtered_comments)} 条高质量评论")
            else:
                # 如果没有Gemini API，直接使用评分排序的结果
                filtered_comments = top_comments[:10]
                for comment in filtered_comments:
                    comment['confidence'] = 0.9  # 默认置信度
                    comment['reason'] = '基于评分排序（未使用AI筛选）'
                logger.info("未配置Gemini API，使用评分排序")
            
            if not filtered_comments:
                logger.warning("AI筛选后无高质量评论")
                await self.send_notification("⚠️ AI筛选后无高质量评论可发布")
                return
            
            # 选择合适的评论发布（避免重复内容）
            result, selected_comment = await self.select_and_post_comment(filtered_comments, total_api_calls, scrape_duration)
            
            if result == "all_duplicate":
                logger.warning("本次爬取的所有内容都已经在Twitter发布过")
                await self.send_notification("📄 本次爬取的所有内容都已经在Twitter发布过！")
            elif result:
                logger.info("自动发布成功")
            else:
                logger.error("自动发布失败")
                
        except Exception as e:
            logger.error(f"自动爬取和发布时出错: {e}")
            await self.send_notification(f"❌ 自动爬取系统出错: {str(e)}")

    async def filter_comments_with_ai(self, comments, batch_size):
        """使用AI筛选评论质量"""
        filtered_comments = []
        total_api_calls = 0
        
        try:
            # 分批处理评论
            for i in range(0, len(comments), batch_size):
                batch = comments[i:i + batch_size]
                
                # 过滤太短的评论
                valid_batch = [c for c in batch if len(c.get('body', '')) >= 10]
                if not valid_batch:
                    continue
                
                # 使用批量评估方法（与get_batch_comment_quality_prompt相同的格式）
                batch_results = await self.assess_batch_comment_quality(valid_batch)
                total_api_calls += 1
                
                # 处理批量结果
                for comment, quality_result in zip(valid_batch, batch_results):
                    # 只保留result为"yes"且confidence大于0.8的评论
                    if quality_result['result'] == 'yes' and quality_result['confidence'] > 0.8:
                        comment['confidence'] = quality_result['confidence']
                        comment['reason'] = quality_result['reason']
                        filtered_comments.append(comment)
                
                # 批次间延迟
                if i + batch_size < len(comments):
                    await asyncio.sleep(0.5)
            
            return filtered_comments, total_api_calls
            
        except Exception as e:
            logger.error(f"AI筛选过程出错: {e}")
            return [], total_api_calls

    async def select_and_post_comment(self, filtered_comments, api_call_count, scrape_duration=0):
        """智能选择评论并发布，避免重复内容"""
        try:
            # 按置信度排序评论
            sorted_comments = sorted(filtered_comments, key=lambda x: x.get('confidence', 0), reverse=True)
            
            for i, comment in enumerate(sorted_comments):
                content = comment.get('body', '')
                if len(content) > 280:
                    content = content[:277] + "..."
                
                # 检查是否重复
                is_duplicate = await self.check_duplicate_content(content)
                
                if not is_duplicate:
                    # 找到非重复内容，直接发布
                    logger.info(f"选择第{i+1}优先评论发布，置信度: {comment.get('confidence', 0):.2f}")
                    success = await self.auto_post_to_twitter(comment, api_call_count, scrape_duration)
                    return success, comment
                else:
                    logger.info(f"第{i+1}优先评论重复，尝试下一个...")
            
            # 所有评论都重复，跳过发布
            if sorted_comments:
                logger.warning("所有高质量评论都重复，跳过本次发布")
                return "all_duplicate", None
            
            return False, None
            
        except Exception as e:
            logger.error(f"选择和发布评论时出错: {e}")
            return False, None

    async def check_duplicate_content(self, content):
        """检查内容是否已经发布过"""
        try:
            # 检查数据库中是否有相同的内容
            conn = sqlite3.connect('reddit_data.db')
            cursor = conn.cursor()
            
            # 查询最近7天内是否有相同内容
            seven_days_ago = datetime.now() - timedelta(days=7)
            cursor.execute("""
                SELECT COUNT(*) FROM reddit_comments 
                WHERE body = ? AND sent_at > ? AND tweet_id IS NOT NULL
            """, (content, seven_days_ago.strftime('%Y-%m-%d %H:%M:%S')))
            
            count = cursor.fetchone()[0]
            conn.close()
            
            return count > 0
            
        except Exception as e:
            logger.error(f"检查重复内容时出错: {e}")
            return False

    async def make_content_unique(self, content):
        """为重复内容添加变化使其唯一"""
        try:
            # 添加时间戳使内容唯一
            timestamp = datetime.now().strftime("%H:%M")
            
            # 如果内容太长，先截短再添加时间戳
            max_length = 280 - len(f" [{timestamp}]")
            if len(content) > max_length:
                content = content[:max_length-3] + "..."
            
            unique_content = f"{content} [{timestamp}]"
            return unique_content
            
        except Exception as e:
            logger.error(f"创建唯一内容时出错: {e}")
            return content

    async def auto_post_to_twitter(self, comment, api_call_count, scrape_duration=0, force_unique=False):
        """自动发布评论到Twitter"""
        try:
            # 检查评论长度
            content = comment.get('body', '')
            if len(content) > 280:
                content = content[:277] + "..."
            
            # 清理内容 - 移除可能导致问题的字符
            content = content.replace('\r\n', '\n').replace('\r', '\n')
            # 移除连续的换行符
            content = re.sub(r'\n+', '\n', content).strip()
            
            # 如果强制唯一化（用于处理所有评论都重复的情况）
            if force_unique:
                logger.info(f"强制为重复内容添加变化: {content[:50]}...")
                content = await self.make_content_unique(content)
                logger.info(f"修改后的内容: {content[:50]}...")
            
            logger.info(f"准备发送推文内容: {repr(content[:100])}")
            
            # 发送推文（使用V2 API）
            response = self.twitter_client.create_tweet(text=content)
            tweet_id = response.data['id']
            
            # 更新评论数据（保存实际发布的内容）
            comment['tweet_id'] = tweet_id
            comment['sent_at'] = datetime.now()
            comment['api_call_count'] = api_call_count
            comment['body'] = content  # 更新为实际发布的内容
            
            # 保存到数据库
            self.data_processor.save_comments_to_database([comment])
            
            # 发送成功通知
            await self.send_auto_post_notification(comment, api_call_count, scrape_duration)
            
            return True
            
        except Exception as e:
            error_msg = str(e)
            if "403" in error_msg:
                if "duplicate" in error_msg.lower():
                    logger.error(f"Twitter重复内容错误: {error_msg}")
                    await self.send_notification(f"⚠️ Twitter检测到重复内容，请检查重复检测逻辑")
                elif "not permitted" in error_msg.lower():
                    logger.error(f"Twitter权限错误: {error_msg}")
                    await self.send_notification(
                        f"🚫 <b>Twitter API权限不足</b>\n\n"
                        f"错误详情: {error_msg}\n\n"
                        f"可能原因:\n"
                        f"• API密钥权限不足（需要Read and Write权限）\n"
                        f"• Twitter开发者账户被限制\n"
                        f"• API访问级别不够（需要Basic或以上）\n\n"
                        f"请检查Twitter开发者控制台的API设置。"
                    )
                else:
                    logger.error(f"Twitter 403错误: {error_msg}")
                    await self.send_notification(f"🚫 Twitter访问被拒绝: {error_msg}")
            elif "401" in error_msg:
                logger.error(f"Twitter认证错误: {error_msg}")
                await self.send_notification(
                    f"🔐 <b>Twitter API认证失败</b>\n\n"
                    f"请检查API密钥是否正确配置:\n"
                    f"• TWITTER_API_KEY\n"
                    f"• TWITTER_API_SECRET\n"
                    f"• TWITTER_ACCESS_TOKEN\n"
                    f"• TWITTER_ACCESS_TOKEN_SECRET"
                )
            else:
                logger.error(f"自动发布到Twitter失败: {e}")
                await self.send_notification(f"❌ 发布到Twitter失败: {str(e)}")
            return False

    async def send_auto_post_notification(self, comment, api_call_count, scrape_duration=0):
        """发送自动发布的通知"""
        try:
            content = comment.get('body', '')
            if len(content) > 100:
                display_content = content[:100] + "..."
            else:
                display_content = content
            
            # 性能统计
            performance_info = ""
            if scrape_duration > 0:
                performance_info = f"\n⚡ <b>爬取性能:</b> 用时 {scrape_duration:.2f}秒"
            
            notification = f"""
🤖 <b>自动发布成功</b>

📝 <b>发布内容:</b> 
{display_content}

⏰ <b>发布时间:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🤖 <b>AI评估:</b>
• 置信度: {comment.get('confidence', 0):.2f}
• 评价: {comment.get('reason', '无')}

📊 <b>资源使用:</b>
• Gemini API调用: {api_call_count} 次{performance_info}

🔗 <b>来源:</b> r/{comment.get('subreddit', 'unknown')}
⭐ <b>Reddit评分:</b> {comment.get('score', 0)}
            """.strip()
            
            await self.send_notification(notification)
            
        except Exception as e:
            logger.error(f"发送自动发布通知失败: {e}")

    async def send_notification(self, message: str):
        """发送通知消息到Telegram"""
        try:
            await self.send_telegram_message(message)
        except Exception as e:
            logger.error(f"发送通知失败: {e}")

    async def start_auto_scraper(self):
        """启动自动爬取任务"""
        try:
            logger.info("自动爬取任务已启动，等待开关启用...")
            
            while True:
                # 检查自动爬取开关
                scraper_enabled = self.config_manager.get_config('AUTO_SCRAPER_ENABLED', False)
                
                if scraper_enabled and not self.auto_scraper_running:
                    self.auto_scraper_running = True
                    fetch_interval = self.config_manager.get_config('REDDIT_FETCH_INTERVAL', 60)
                    logger.info(f"自动爬取已启用，将在 {fetch_interval} 分钟后开始首次爬取")
                    await self.send_notification(f"🤖 自动爬取系统已启动，将在 {fetch_interval} 分钟后开始首次爬取")
                    # 计算首次爬取时间
                    self.next_scrape_time = datetime.now() + timedelta(minutes=fetch_interval)
                elif not scraper_enabled and self.auto_scraper_running:
                    self.auto_scraper_running = False
                    self.next_scrape_time = None
                    logger.info("自动爬取已禁用")
                    await self.send_notification("⏸️ 自动爬取系统已停止")
                
                if scraper_enabled:
                    fetch_interval = self.config_manager.get_config('REDDIT_FETCH_INTERVAL', 60)
                    await asyncio.sleep(fetch_interval * 60)  # 等待间隔时间
                    # 执行爬取
                    await self.auto_scrape_and_post()
                    # 计算下次爬取时间
                    self.next_scrape_time = datetime.now() + timedelta(minutes=fetch_interval)
                else:
                    # 如果禁用，每30秒检查一次开关状态
                    await asyncio.sleep(30)
                
        except asyncio.CancelledError:
            logger.info("自动爬取任务已停止")
            self.auto_scraper_running = False
        except Exception as e:
            logger.error(f"自动爬取任务出错: {e}")
            self.auto_scraper_running = False
            # 出错后等待5分钟再重试
            await asyncio.sleep(300)
            # 递归重启任务
            await self.start_auto_scraper()

    async def send_telegram_message(self, message: str):
        """发送消息到Telegram"""
        try:
            application = Application.builder().token(self.telegram_token).build()
            await application.bot.send_message(
                chat_id=self.authorized_user_id,
                text=message,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"发送Telegram消息失败: {e}")
    
    async def handle_dm_webhook(self, request):
        """处理Twitter私信webhook"""
        try:
            # 获取签名
            signature = request.headers.get('x-twitter-webhooks-signature')
            if not signature:
                logger.warning("收到没有签名的webhook请求")
                return web.Response(status=401)
            
            # 读取请求体
            body = await request.read()
            
            # 验证签名
            if not self.verify_webhook_signature(body, signature):
                logger.warning("Webhook签名验证失败")
                return web.Response(status=401)
            
            # 解析JSON
            data = json.loads(body.decode('utf-8'))
            
            # 检查是否是私信事件
            if 'direct_message_events' in data:
                for dm_event in data['direct_message_events']:
                    # 确保不是自己发送的消息
                    sender_id = dm_event.get('message_create', {}).get('sender_id')
                    if sender_id != str(self.twitter_access_token).split('-')[0]:  # 简单检查
                        
                        # 获取发送者信息
                        users = data.get('users', {})
                        sender_info = users.get(sender_id, {})
                        sender_name = sender_info.get('name', 'Unknown')
                        sender_username = sender_info.get('screen_name', 'unknown')
                        
                        # 获取消息内容
                        message_data = dm_event.get('message_create', {}).get('message_data', {})
                        text = message_data.get('text', '')
                        
                        # 格式化消息
                        formatted_message = f"""
📩 <b>收到新私信</b>

👤 <b>发送者:</b> {sender_name} (@{sender_username})
💬 <b>内容:</b> {text}

🔗 <b>时间:</b> {dm_event.get('created_timestamp', 'Unknown')}
                        """.strip()
                        
                        # 发送到Telegram
                        await self.send_telegram_message(formatted_message)
                        logger.info(f"已转发私信到Telegram: 来自 @{sender_username}")
            
            return web.Response(text="OK")
            
        except Exception as e:
            logger.error(f"处理私信webhook时出错: {e}")
            return web.Response(status=500)
    
    async def webhook_challenge(self, request):
        """处理Twitter webhook验证挑战"""
        try:
            # 获取挑战码
            crc_token = request.query.get('crc_token')
            if not crc_token or not self.webhook_secret:
                return web.Response(status=400)
            
            # 生成响应
            signature = hmac.new(
                self.webhook_secret.encode('utf-8'),
                crc_token.encode('utf-8'),
                hashlib.sha256
            ).digest()
            
            response_token = base64.b64encode(signature).decode('utf-8')
            
            return web.json_response({
                'response_token': f'sha256={response_token}'
            })
            
        except Exception as e:
            logger.error(f"处理webhook挑战时出错: {e}")
            return web.Response(status=500)
    
    async def keep_alive(self):
        """自动保活任务，每14分钟ping一次健康检查端点"""
        if not self.app_url:
            logger.info("未设置APP_URL，跳过自动保活")
            return
            
        while True:
            try:
                await asyncio.sleep(14 * 60)  # 14分钟
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.app_url}/health") as response:
                        if response.status == 200:
                            logger.info("保活ping成功")
                        else:
                            logger.warning(f"保活ping失败，状态码: {response.status}")
            except Exception as e:
                logger.error(f"保活ping出错: {e}")
            except asyncio.CancelledError:
                break
    
    async def run(self):
        # 设置Telegram bot
        application = Application.builder().token(self.telegram_token).build()
        
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help))
        application.add_handler(CommandHandler("status", self.status))
        application.add_handler(CommandHandler("settings", self.settings))
        application.add_handler(CommandHandler("set", self.set_config))
        application.add_handler(CommandHandler("start_scraper", self.start_scraper_command))
        application.add_handler(CommandHandler("stop_scraper", self.stop_scraper_command))
        application.add_handler(CommandHandler("scrape_now", self.scrape_now_command))
        application.add_handler(CommandHandler("test_twitter", self.test_twitter_command))
        application.add_handler(CommandHandler("cancel", self.cancel_command))
        
        # 回调处理器
        application.add_handler(CallbackQueryHandler(self.handle_tweet_callback, pattern="^(confirm_tweet_|cancel_tweet_)"))
        application.add_handler(CallbackQueryHandler(self.handle_config_selection, pattern="^(config_|close_settings|back_to_settings|cancel_config|bool_config_)"))
        
        # 消息处理器
        application.add_handler(MessageHandler(filters.PHOTO, self.tweet_with_image))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))
        
        # 设置健康检查服务器
        async def health_check(request):
            return web.Response(text="OK", status=200)
        
        app = web.Application()
        app.router.add_get("/health", health_check)
        app.router.add_get("/", health_check)
        app.router.add_get("/webhook/twitter", self.webhook_challenge)  # Twitter webhook验证
        app.router.add_post("/webhook/twitter", self.handle_dm_webhook)  # Twitter私信webhook
        
        # 启动HTTP服务器
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", 8000)
        await site.start()
        
        logger.info("健康检查服务器启动在端口8000...")
        logger.info("Bot开始运行...")
        
        # 启动自动保活任务
        keep_alive_task = None
        if self.app_url:
            keep_alive_task = asyncio.create_task(self.keep_alive())
            logger.info("自动保活任务已启动")
        
        # 启动自动爬取任务
        self.auto_scraper_task = asyncio.create_task(self.start_auto_scraper())
        logger.info("自动爬取任务已启动")
        
        # 启动Telegram bot
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        # 发送启动通知
        await self.send_startup_notification()
        
        # 保持运行
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("收到停止信号...")
        finally:
            if keep_alive_task:
                keep_alive_task.cancel()
                try:
                    await keep_alive_task
                except asyncio.CancelledError:
                    pass
            
            # 取消自动爬取任务
            if self.auto_scraper_task:
                self.auto_scraper_task.cancel()
                try:
                    await self.auto_scraper_task
                except asyncio.CancelledError:
                    pass
            
            # 关闭Reddit连接
            try:
                await self.reddit_scraper.close()
                logger.info("Reddit连接已关闭")
            except Exception as e:
                logger.error(f"关闭Reddit连接时出错: {e}")
            await application.updater.stop()
            await application.stop()
            await application.shutdown()
            await runner.cleanup()

if __name__ == "__main__":
    bot = TwitterBot()
    asyncio.run(bot.run())