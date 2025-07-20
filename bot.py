import os
import logging
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# 导入新的模块
from data_processor import DataProcessor
from reddit_scraper import AsyncRedditScraper
from config_manager import ConfigManager
from twitter_manager import TwitterManager
from ai_evaluator import AIEvaluator
from health_monitor import HealthMonitor
from auto_scraper_manager import AutoScraperManager
from database_manager import db_manager

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TwitterBot:
    """重构后的TwitterBot主类，专注于Telegram Bot逻辑"""
    
    def __init__(self):
        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.authorized_user_id = os.getenv('AUTHORIZED_USER_ID')
        
        if not all([self.telegram_token, self.authorized_user_id]):
            raise ValueError("Missing required environment variables: TELEGRAM_BOT_TOKEN, AUTHORIZED_USER_ID")
        
        # 初始化各个组件
        self.data_processor = DataProcessor()
        self.config_manager = ConfigManager()
        self.reddit_scraper = AsyncRedditScraper()
        self.twitter_manager = TwitterManager()
        self.ai_evaluator = AIEvaluator()
        self.health_monitor = HealthMonitor(notification_callback=self.send_telegram_message)
        self.auto_scraper_manager = AutoScraperManager(
            reddit_scraper=self.reddit_scraper,
            ai_evaluator=self.ai_evaluator,
            twitter_manager=self.twitter_manager,
            data_processor=self.data_processor,
            config_manager=self.config_manager,
            notification_callback=self.send_telegram_message
        )
        
        # 用户状态管理
        self.user_states = {}
        self.pending_tweets = {}
        
        # Telegram Application实例（单例）
        self._application = None
    
    def is_authorized_user(self, user_id: int) -> bool:
        """检查用户是否有权限"""
        return str(user_id) == self.authorized_user_id
    
    def _get_application(self):
        """获取Telegram Application实例（单例模式）"""
        if self._application is None:
            self._application = Application.builder().token(self.telegram_token).build()
        return self._application
    
    # ===== Telegram Bot 命令处理器 =====
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """启动命令处理"""
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
            
        await update.message.reply_text(
            "你好！发送任何消息给我，我会自动转发到你的Twitter账户。\n\n"
            "使用 /help 查看帮助信息。"
        )
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """帮助命令处理"""
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
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """状态查看命令"""
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
        
        try:
            # 检查Twitter API连接
            twitter_status = "✅ 正常" if self.twitter_manager.is_available() else "❌ 失败"
            
            # 获取自动爬取状态
            scraper_info = self.auto_scraper_manager.get_status_info()
            
            if scraper_info['enabled'] and scraper_info['running']:
                scraper_status = "🟢 运行中"
                scraper_detail = f"🔄 间隔时间: {scraper_info['interval']} 分钟\n"
                
                if scraper_info['last_scrape_time']:
                    scraper_detail += f"📅 上次爬取: {scraper_info['last_scrape_time'].strftime('%Y-%m-%d %H:%M:%S')}\n"
                else:
                    scraper_detail += f"📅 上次爬取: 尚未开始\n"
                
                if scraper_info['next_scrape_time']:
                    now = datetime.now()
                    if scraper_info['next_scrape_time'] > now:
                        time_diff = scraper_info['next_scrape_time'] - now
                        minutes_left = int(time_diff.total_seconds() / 60)
                        hours_left = minutes_left // 60
                        mins_left = minutes_left % 60
                        
                        if hours_left > 0:
                            time_left_str = f"{hours_left}小时{mins_left}分钟"
                        else:
                            time_left_str = f"{mins_left}分钟"
                        
                        scraper_detail += f"⏰ 下次爬取: {scraper_info['next_scrape_time'].strftime('%H:%M:%S')} (还有{time_left_str})"
                    else:
                        scraper_detail += f"⏰ 下次爬取: 即将开始"
                else:
                    scraper_detail += f"⏰ 下次爬取: 计算中..."
                
            elif scraper_info['enabled'] and not scraper_info['running']:
                scraper_status = "🟡 启用但未运行"
                scraper_detail = f"🔄 间隔时间: {scraper_info['interval']} 分钟\n📅 等待系统启动"
            else:
                scraper_status = "🔴 已停止"
                scraper_detail = "使用 /start_scraper 启动"
            
            status_message = f"""
📊 <b>Bot 运行状态</b>

🤖 <b>Telegram Bot:</b> ✅ 在线
🐦 <b>Twitter API:</b> {twitter_status}
🔄 <b>自动爬取:</b> {scraper_status}
📝 <b>爬取详情:</b> {scraper_detail}
⏱️ <b>运行状态:</b> 运行中
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
    
    async def test_twitter_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """测试Twitter API连接"""
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
        
        try:
            await update.message.reply_text("🔍 正在测试Twitter API连接和权限...")
            
            result = await self.twitter_manager.test_connection()
            
            if result['success']:
                await update.message.reply_text(
                    f"✅ <b>Twitter API连接测试成功</b>\n\n"
                    f"👤 <b>账户:</b> @{result['username']}\n"
                    f"🆔 <b>用户ID:</b> {result['user_id']}\n"
                    f"👥 <b>粉丝数:</b> {result['followers_count']:,}\n"
                    f"🔑 <b>API方式:</b> OAuth 1.0a\n"
                    f"📡 <b>连接状态:</b> 已连接\n\n"
                    f"💡 <b>说明:</b>\n"
                    f"• 使用OAuth 1.0a认证\n"
                    f"• 完全兼容X.com免费版\n"
                    f"• 可以发布推文和上传媒体",
                    parse_mode='HTML'
                )
            else:
                error_type = result.get('error_type', 'unknown')
                error_msg = result['error']
                
                if error_type == 'permission':
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
                elif error_type == 'authentication':
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
    
    # ===== 推文发布相关 =====
    
    async def tweet_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理文本推文"""
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
        
        if not self.twitter_manager.is_available():
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
        """处理图片推文"""
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
        
        if not self.twitter_manager.is_available():
            await update.message.reply_text("❌ Twitter API未正确配置，请检查环境变量。")
            return
            
        # 获取图片和文字描述
        photo = update.message.photo[-1]
        caption = update.message.caption or ""
        
        if len(caption) > 280:
            await update.message.reply_text("文字描述太长了！Twitter限制280字符以内。")
            return
        
        # 存储待发送的推文
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
                        result = await self.twitter_manager.post_text_tweet(tweet_data['content'])
                    elif tweet_data['type'] == 'image':
                        result = await self.twitter_manager.post_image_tweet(
                            tweet_data['content'], tweet_data['photo_file_id'], context
                        )
                    
                    if result['success']:
                        await query.edit_message_text(
                            f"✅ 推文发送成功！\n\n"
                            f"推文ID: {result['tweet_id']}\n"
                            f"内容: {result['content']}"
                        )
                    else:
                        # 传递内容信息给错误处理器
                        content = tweet_data['content']
                        await self._handle_tweet_error(query, result, content)
                        
                    # 清理待发送数据
                    del self.pending_tweets[user_id]
                    
                except Exception as e:
                    logger.error(f"发送推文时出错: {e}")
                    # 显示异常和内容信息
                    content = tweet_data.get('content', '') if user_id in self.pending_tweets else ''
                    display_content = content[:150] + "..." if len(content) > 150 else content
                    content_info = f"\n\n📝 发送的内容:\n{display_content}" if content else ""
                    await query.edit_message_text(f"❌ 发送推文时发生异常: {str(e)}{content_info}")
            else:
                await query.edit_message_text("❌ 推文数据已过期，请重新发送。")
                
        elif data.startswith("cancel_tweet_"):
            # 取消发送推文
            if user_id in self.pending_tweets:
                del self.pending_tweets[user_id]
            await query.edit_message_text("❌ 推文发送已取消。")
    
    async def _handle_tweet_error(self, query, result, content=None):
        """处理推文发送错误，包含内容信息"""
        error_type = result.get('error_type', 'unknown')
        error_msg = result.get('error', 'Unknown error')
        
        # 格式化内容信息
        content_info = ""
        if content:
            display_content = content[:150] + "..." if len(content) > 150 else content
            content_info = f"\n\n📝 发送的内容:\n{display_content}"
        
        if error_type == 'authentication':
            await query.edit_message_text(
                f"❌ Twitter API认证失败，请检查API密钥和权限设置。{content_info}"
            )
        elif error_type == 'file_too_large':
            await query.edit_message_text(
                f"❌ 图片太大，请发送较小的图片。{content_info}"
            )
        elif error_type == 'duplicate':
            await query.edit_message_text(
                f"⚠️ Twitter检测到重复内容。{content_info}"
            )
        elif error_type == 'forbidden':
            await query.edit_message_text(
                f"🚫 Twitter拒绝发布此内容，可能违反社区准则。\n错误: {error_msg}{content_info}"
            )
        else:
            await query.edit_message_text(
                f"❌ 发送推文失败: {error_msg}{content_info}"
            )
    
    # ===== 自动爬取控制 =====
    
    async def start_scraper_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """启动自动爬取系统"""
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
        
        try:
            current_status = self.config_manager.get_config('AUTO_SCRAPER_ENABLED', False)
            
            if current_status:
                await update.message.reply_text("ℹ️ 自动爬取系统已经在运行中")
                return
            
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
            current_status = self.config_manager.get_config('AUTO_SCRAPER_ENABLED', False)
            
            if not current_status:
                await update.message.reply_text("ℹ️ 自动爬取系统当前处于停止状态")
                return
            
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
            await self.auto_scraper_manager.auto_scrape_and_post()
            
            # 更新下次爬取时间
            self.auto_scraper_manager.update_next_scrape_time()
            
            await update.message.reply_text(
                "✅ <b>立即爬取完成</b>\n\n"
                "已完成一次完整的爬取和发布流程。\n"
                "如果自动爬取正在运行，下次爬取时间已重新计算。",
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"立即爬取时出错: {e}")
            await update.message.reply_text(f"❌ 立即爬取失败: {str(e)}")
    
    # ===== 配置管理 =====
    
    async def settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示配置设置"""
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
            
            application = self._get_application()
            if edit and message_id:
                await application.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=settings_message,
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
            else:
                await application.bot.send_message(
                    chat_id=chat_id,
                    text=settings_message,
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
            
        except Exception as e:
            logger.error(f"显示设置菜单时出错: {e}")
            application = self._get_application()
            await application.bot.send_message(chat_id=chat_id, text="❌ 显示设置菜单失败")
    
    # ===== 消息处理 =====
    
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
            
            if user_id not in self.user_states:
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
                
                # 编辑原消息显示成功
                application = self._get_application()
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
    
    # ===== 配置回调处理 =====
    
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
                await query.edit_message_text("✅ 设置菜单已关闭")
                if user_id in self.user_states:
                    del self.user_states[user_id]
                return
            
            elif data.startswith("config_"):
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
                if user_id in self.user_states:
                    del self.user_states[user_id]
                await self.show_settings_menu(query.message.chat_id, query.message.message_id, edit=True)
            
            elif data == "cancel_config":
                if user_id in self.user_states:
                    del self.user_states[user_id]
                await query.edit_message_text("❌ 配置修改已取消")
                
            elif data.startswith("bool_config_"):
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
            
            # 解析回调数据
            remaining = data[12:]  # 移除 "bool_config_"
            last_underscore_index = remaining.rfind("_")
            if last_underscore_index == -1:
                await query.edit_message_text("❌ 无效的配置数据")
                return
            
            config_key = remaining[:last_underscore_index]
            new_value = remaining[last_underscore_index + 1:]
            
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
            'REDDIT_SORT_METHOD': '📝 输入排序方式:\n• hot (热门)\n• new (最新)\n• top (顶尖)\n• controversial (有争议)\n• rising (上升中)\n• gilded (镀金)',
            'REDDIT_TIME_FILTER': '📝 输入时间筛选范围:\n• all (全部时间)\n• year (过去一年)\n• month (过去一月)\n• week (过去一周)\n• day (过去一天)\n• hour (过去一小时)',
            'REDDIT_COMMENTS_PER_POST': '📝 输入数字 (建议: 10-50)',
            'REDDIT_FETCH_INTERVAL': '📝 输入分钟数 (建议: 30-180)',
            'REDDIT_SUBREDDITS': '📝 输入板块名称，用逗号分隔\n例如: python,programming,MachineLearning',
            'AUTO_SCRAPER_ENABLED': '📝 输入开关状态: true 或 false'
        }
        
        return hints.get(config_key, f'📝 输入新的{config_type}类型值')
    
    # ===== 其他命令 =====
    
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
    
    # ===== 通知功能 =====
    
    async def send_startup_notification(self):
        """发送启动通知给授权用户"""
        try:
            application = self._get_application()
            startup_message = f"""
🤖 <b>Twitter Bot 已启动</b>

✅ <b>状态:</b> 在线运行
🔗 <b>Twitter API:</b> {'已连接' if self.twitter_manager.is_available() else '未连接'}
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
    
    async def send_telegram_message(self, message: str):
        """发送消息到Telegram"""
        try:
            application = self._get_application()
            await application.bot.send_message(
                chat_id=self.authorized_user_id,
                text=message,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"发送Telegram消息失败: {e}")
    
    def _close_database_connections(self):
        """关闭数据库连接"""
        try:
            db_manager.close_all_connections()
            logger.info("数据库连接已关闭")
        except Exception as e:
            logger.error(f"关闭数据库连接时出错: {e}")
    
    # ===== 主运行函数 =====
    
    async def run(self):
        """启动机器人"""
        # 设置Telegram bot
        application = self._get_application()
        
        # 添加命令处理器
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help))
        application.add_handler(CommandHandler("status", self.status))
        application.add_handler(CommandHandler("settings", self.settings))
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
        
        # 启动健康监控服务器
        await self.health_monitor.start_server()
        
        logger.info("Bot开始运行...")
        
        # 启动自动保活任务
        keep_alive_task = asyncio.create_task(self.health_monitor.keep_alive())
        logger.info("自动保活任务已启动")
        
        # 启动自动爬取任务
        auto_scraper_task = asyncio.create_task(self.auto_scraper_manager.start_auto_scraper())
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
            # 清理任务
            keep_alive_task.cancel()
            auto_scraper_task.cancel()
            
            try:
                await keep_alive_task
            except asyncio.CancelledError:
                pass
            
            try:
                await auto_scraper_task
            except asyncio.CancelledError:
                pass
            
            # 关闭各组件
            await self.reddit_scraper.close()
            await self.health_monitor.stop_server()
            
            # 关闭数据库连接
            self._close_database_connections()
            
            # 关闭Telegram bot
            await application.updater.stop()
            await application.stop()
            await application.shutdown()

if __name__ == "__main__":
    bot = TwitterBot()
    asyncio.run(bot.run())