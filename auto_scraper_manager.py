import logging
import asyncio
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)

class AutoScraperManager:
    """自动爬取管理类，负责Reddit内容爬取和发布逻辑"""
    
    def __init__(self, reddit_scraper, ai_evaluator, twitter_manager, data_processor, config_manager, notification_callback=None):
        self.reddit_scraper = reddit_scraper
        self.ai_evaluator = ai_evaluator
        self.twitter_manager = twitter_manager
        self.data_processor = data_processor
        self.config_manager = config_manager
        self.notification_callback = notification_callback
        
        # 自动爬取任务管理
        self.auto_scraper_task = None
        self.auto_scraper_running = False
        self.last_scrape_time = None
        self.next_scrape_time = None
    
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
            
            logger.info(f"爬取配置: subreddits={subreddits}, posts={post_fetch_count}, sort={sort_method}")
            
            # 爬取Reddit评论
            all_comments, scrape_duration = await self._scrape_reddit_comments(
                subreddits, post_fetch_count, sort_method, time_filter, comments_per_post
            )
            
            if not all_comments:
                logger.warning("未获取到任何评论")
                await self._send_notification("⚠️ 自动爬取失败：未获取到任何评论")
                return
            
            # AI质量筛选
            filtered_comments, api_calls = await self._filter_comments_with_ai(
                all_comments, top_comments_count, gemini_batch_size
            )
            
            if not filtered_comments:
                logger.warning("AI筛选后无高质量评论")
                await self._send_notification("⚠️ AI筛选后无高质量评论可发布")
                return
            
            # 选择合适的评论发布
            result, selected_comment = await self._select_and_post_comment(filtered_comments, api_calls, scrape_duration)
            
            if result == "all_duplicate":
                logger.warning("本次爬取的所有内容都已经在Twitter发布过")
                await self._send_notification("📄 本次爬取的所有内容都已经在Twitter发布过！")
            elif result:
                logger.info("自动发布成功")
            else:
                logger.error("自动发布失败")
                
        except Exception as e:
            logger.error(f"自动爬取和发布时出错: {e}")
            await self._send_notification(f"❌ 自动爬取系统出错: {str(e)}")
    
    async def _scrape_reddit_comments(self, subreddits, post_fetch_count, sort_method, time_filter, comments_per_post):
        """爬取Reddit评论"""
        all_comments = []
        
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
            
            return all_comments, scrape_duration
                    
        except Exception as e:
            logger.error(f"并发爬取时出错: {e}")
            await self._send_notification(f"❌ 并发爬取失败: {str(e)}")
            return [], 0
    
    async def _filter_comments_with_ai(self, all_comments, top_comments_count, gemini_batch_size):
        """使用AI筛选评论质量"""
        logger.info(f"总共获取了 {len(all_comments)} 条评论")
        
        # 按分数排序，取前N条
        sorted_comments = sorted(all_comments, key=lambda x: x.get('score', 0), reverse=True)
        top_comments = sorted_comments[:top_comments_count]
        
        logger.info(f"选择前 {len(top_comments)} 条高分评论进行AI筛选")
        
        # AI质量筛选
        if self.ai_evaluator.is_available():
            filtered_comments, api_calls = await self.ai_evaluator.filter_comments_with_ai(top_comments, gemini_batch_size)
            logger.info(f"AI筛选完成，使用了 {api_calls} 次API调用，获得 {len(filtered_comments)} 条高质量评论")
            return filtered_comments, api_calls
        else:
            # 如果没有AI评估，直接使用评分排序的结果
            filtered_comments = top_comments[:10]
            for comment in filtered_comments:
                comment['confidence'] = 0.9
                comment['reason'] = '基于评分排序（未使用AI筛选）'
            logger.info("未配置AI评估，使用评分排序")
            return filtered_comments, 0
    
    async def _select_and_post_comment(self, filtered_comments, api_call_count, scrape_duration=0):
        """智能选择评论并发布，避免重复内容"""
        try:
            # 按置信度排序评论
            sorted_comments = sorted(filtered_comments, key=lambda x: x.get('confidence', 0), reverse=True)
            
            for i, comment in enumerate(sorted_comments):
                content = comment.get('body', '')
                if len(content) > 280:
                    content = content[:277] + "..."
                
                # 检查是否重复
                is_duplicate = await self._check_duplicate_content(content)
                
                if not is_duplicate:
                    # 找到非重复内容，直接发布
                    logger.info(f"选择第{i+1}优先评论发布，置信度: {comment.get('confidence', 0):.2f}")
                    success = await self._auto_post_to_twitter(comment, api_call_count, scrape_duration)
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
    
    async def _check_duplicate_content(self, content):
        """检查内容是否已经发布过"""
        try:
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
    
    async def _auto_post_to_twitter(self, comment, api_call_count, scrape_duration=0):
        """自动发布评论到Twitter"""
        try:
            content = comment.get('body', '')
            if len(content) > 280:
                content = content[:277] + "..."
            
            result = await self.twitter_manager.post_text_tweet(content)
            
            if result['success']:
                # 更新评论数据
                comment['tweet_id'] = result['tweet_id']
                comment['sent_at'] = datetime.now()
                comment['api_call_count'] = api_call_count
                comment['body'] = result['content']
                
                # 保存到数据库
                self.data_processor.save_comments_to_database([comment])
                
                # 发送成功通知
                await self._send_auto_post_notification(comment, api_call_count, scrape_duration)
                
                return True
            else:
                # 发布失败时，传递内容和评论信息
                await self._handle_twitter_error(result, content, comment)
                return False
                
        except Exception as e:
            logger.error(f"自动发布到Twitter失败: {e}")
            
            # 格式化内容信息用于异常通知
            display_content = content[:200] + "..." if len(content) > 200 else content
            content_info = f"\n\n📝 <b>准备发布的内容:</b>\n<code>{display_content}</code>"
            
            # 格式化评论来源信息
            source_info = ""
            if comment:
                source_info = f"\n\n🔗 <b>内容来源:</b>\n"
                source_info += f"• 板块: r/{comment.get('subreddit', 'unknown')}\n"
                source_info += f"• Reddit评分: {comment.get('score', 0)}\n"
                if comment.get('confidence'):
                    source_info += f"• AI置信度: {comment.get('confidence', 0):.2f}\n"
                if comment.get('reason'):
                    source_info += f"• AI评价: {comment.get('reason', '无')}"
            
            await self._send_notification(
                f"❌ <b>发布到Twitter时发生异常</b>\n\n"
                f"异常详情: {str(e)}\n\n"
                f"💡 这可能是系统级错误，请检查网络连接和API状态。"
                f"{content_info}{source_info}"
            )
            return False
    
    async def _handle_twitter_error(self, result, content=None, comment_info=None):
        """处理Twitter API错误，包含准备发布的内容信息"""
        error_type = result.get('error_type', 'unknown')
        error_msg = result.get('error', 'Unknown error')
        
        # 格式化内容信息
        content_info = ""
        if content:
            display_content = content[:200] + "..." if len(content) > 200 else content
            content_info = f"\n\n📝 <b>准备发布的内容:</b>\n<code>{display_content}</code>"
        
        # 格式化评论来源信息
        source_info = ""
        if comment_info:
            source_info = f"\n\n🔗 <b>内容来源:</b>\n"
            source_info += f"• 板块: r/{comment_info.get('subreddit', 'unknown')}\n"
            source_info += f"• Reddit评分: {comment_info.get('score', 0)}\n"
            if comment_info.get('confidence'):
                source_info += f"• AI置信度: {comment_info.get('confidence', 0):.2f}\n"
            if comment_info.get('reason'):
                source_info += f"• AI评价: {comment_info.get('reason', '无')}"
        
        # 根据错误类型发送不同的通知
        if error_type == 'permission':
            await self._send_notification(
                f"🚫 <b>Twitter API权限不足</b>\n\n"
                f"错误详情: {error_msg}\n\n"
                f"可能原因:\n"
                f"• API密钥权限不足（需要Read and Write权限）\n"
                f"• Twitter开发者账户被限制\n"
                f"• API访问级别不够（需要Basic或以上）"
                f"{content_info}{source_info}"
            )
        elif error_type == 'authentication':
            await self._send_notification(
                f"🔐 <b>Twitter API认证失败</b>\n\n"
                f"错误详情: {error_msg}\n\n"
                f"请检查API密钥是否正确配置"
                f"{content_info}{source_info}"
            )
        elif error_type == 'duplicate':
            await self._send_notification(
                f"⚠️ <b>Twitter检测到重复内容</b>\n\n"
                f"系统的重复检测可能存在漏洞，Twitter仍然检测到重复。"
                f"{content_info}{source_info}"
            )
        elif error_type == 'forbidden':
            await self._send_notification(
                f"🚫 <b>Twitter内容被拒绝</b>\n\n"
                f"错误详情: {error_msg}\n\n"
                f"可能原因:\n"
                f"• 内容违反Twitter社区准则\n"
                f"• 包含敏感词汇或链接\n"
                f"• 内容格式不当\n"
                f"• 账户被临时限制"
                f"{content_info}{source_info}"
            )
        elif error_type == 'file_too_large':
            await self._send_notification(
                f"📁 <b>文件过大</b>\n\n"
                f"错误详情: {error_msg}\n\n"
                f"媒体文件超过Twitter限制"
                f"{content_info}{source_info}"
            )
        else:
            await self._send_notification(
                f"❌ <b>Twitter发布失败</b>\n\n"
                f"错误类型: {error_type}\n"
                f"错误详情: {error_msg}\n\n"
                f"💡 这可能是一个新的错误类型，请检查内容是否有特殊字符或格式问题。"
                f"{content_info}{source_info}"
            )
    
    async def _send_auto_post_notification(self, comment, api_call_count, scrape_duration=0):
        """发送自动发布的通知"""
        try:
            content = comment.get('body', '')
            display_content = content[:100] + "..." if len(content) > 100 else content
            
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
            
            await self._send_notification(notification)
            
        except Exception as e:
            logger.error(f"发送自动发布通知失败: {e}")
    
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
                    await self._send_notification(f"🤖 自动爬取系统已启动，将在 {fetch_interval} 分钟后开始首次爬取")
                    self.next_scrape_time = datetime.now() + timedelta(minutes=fetch_interval)
                elif not scraper_enabled and self.auto_scraper_running:
                    self.auto_scraper_running = False
                    self.next_scrape_time = None
                    logger.info("自动爬取已禁用")
                    await self._send_notification("⏸️ 自动爬取系统已停止")
                
                if scraper_enabled:
                    fetch_interval = self.config_manager.get_config('REDDIT_FETCH_INTERVAL', 60)
                    await asyncio.sleep(fetch_interval * 60)
                    await self.auto_scrape_and_post()
                    self.next_scrape_time = datetime.now() + timedelta(minutes=fetch_interval)
                else:
                    await asyncio.sleep(30)
                
        except asyncio.CancelledError:
            logger.info("自动爬取任务已停止")
            self.auto_scraper_running = False
        except Exception as e:
            logger.error(f"自动爬取任务出错: {e}")
            self.auto_scraper_running = False
            await asyncio.sleep(300)
            await self.start_auto_scraper()
    
    def get_status_info(self) -> dict:
        """获取爬取状态信息"""
        scraper_enabled = self.config_manager.get_config('AUTO_SCRAPER_ENABLED', False)
        fetch_interval = self.config_manager.get_config('REDDIT_FETCH_INTERVAL', 60)
        
        status_info = {
            'enabled': scraper_enabled,
            'running': self.auto_scraper_running,
            'interval': fetch_interval,
            'last_scrape_time': self.last_scrape_time,
            'next_scrape_time': self.next_scrape_time
        }
        
        return status_info
    
    async def _send_notification(self, message: str):
        """发送通知消息"""
        if self.notification_callback:
            await self.notification_callback(message)
    
    def update_next_scrape_time(self):
        """手动更新下次爬取时间"""
        if self.auto_scraper_running:
            fetch_interval = self.config_manager.get_config('REDDIT_FETCH_INTERVAL', 60)
            self.next_scrape_time = datetime.now() + timedelta(minutes=fetch_interval)
    
    async def stop_auto_scraper(self):
        """停止自动爬取任务"""
        if self.auto_scraper_task:
            self.auto_scraper_task.cancel()
            try:
                await self.auto_scraper_task
            except asyncio.CancelledError:
                pass
            self.auto_scraper_task = None
        
        self.auto_scraper_running = False
        self.next_scrape_time = None