"""
通用工具类模块
包含配置管理、错误处理、时间工具和数据库操作等通用功能
"""

import os
import logging
import asyncio
import functools
from datetime import datetime, timedelta
from typing import Any, Optional, Dict, Union, Callable
from database_manager import db_manager

logger = logging.getLogger(__name__)


class UnifiedConfigManager:
    """统一的配置管理器，替代分散的环境变量读取"""
    
    _instance = None
    _config_cache = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(UnifiedConfigManager, cls).__new__(cls)
        return cls._instance
    
    def get_config(self, key: str, default: Any = None, required: bool = False) -> Any:
        """统一的配置获取方法"""
        if key not in self._config_cache:
            value = os.getenv(key, default)
            if required and not value:
                raise ValueError(f"必需的配置项 {key} 未设置")
            self._config_cache[key] = value
        return self._config_cache[key]
    
    def get_twitter_config(self) -> Dict[str, str]:
        """获取Twitter配置组"""
        return {
            'api_key': self.get_config('TWITTER_API_KEY', required=True),
            'api_secret': self.get_config('TWITTER_API_SECRET', required=True),
            'access_token': self.get_config('TWITTER_ACCESS_TOKEN', required=True),
            'access_token_secret': self.get_config('TWITTER_ACCESS_TOKEN_SECRET', required=True),
            'bearer_token': self.get_config('TWITTER_BEARER_TOKEN', required=True),
        }
    
    def get_reddit_config(self) -> Dict[str, str]:
        """获取Reddit配置组"""
        return {
            'client_id': self.get_config('REDDIT_CLIENT_ID', required=True),
            'client_secret': self.get_config('REDDIT_CLIENT_SECRET', required=True),
            'user_agent': self.get_config('REDDIT_USER_AGENT', 'RedditBot/1.0'),
            'username': self.get_config('REDDIT_USERNAME'),
            'password': self.get_config('REDDIT_PASSWORD'),
        }
    
    def get_telegram_config(self) -> Dict[str, str]:
        """获取Telegram配置组"""
        return {
            'bot_token': self.get_config('TELEGRAM_BOT_TOKEN', required=True),
            'authorized_user_id': self.get_config('AUTHORIZED_USER_ID', required=True),
        }
    
    def get_gemini_config(self) -> Dict[str, str]:
        """获取Gemini配置组"""
        return {
            'api_key': self.get_config('GEMINI_API_KEY'),
        }
    
    def get_health_monitor_config(self) -> Dict[str, str]:
        """获取健康监控配置组"""
        return {
            'app_url': self.get_config('APP_URL'),
            'webhook_secret': self.get_config('TWITTER_WEBHOOK_SECRET'),
        }
    
    def get_database_config(self) -> Dict[str, str]:
        """获取数据库配置"""
        return {
            'database_path': self.get_config('DATABASE_PATH', 'reddit_data.db'),
        }


def handle_errors(default_return: Any = None, log_prefix: str = "操作", 
                 reraise: bool = False, notify_callback: Callable = None):
    """统一的错误处理装饰器
    
    Args:
        default_return: 发生错误时的默认返回值
        log_prefix: 日志前缀
        reraise: 是否重新抛出异常
        notify_callback: 错误通知回调函数
    """
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                error_msg = f"{log_prefix}失败: {e}"
                logger.error(error_msg)
                
                # 如果有通知回调，发送错误通知
                if notify_callback:
                    try:
                        await notify_callback(f"❌ {error_msg}")
                    except:
                        pass  # 避免通知失败影响主流程
                
                if reraise:
                    raise
                return default_return
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_msg = f"{log_prefix}失败: {e}"
                logger.error(error_msg)
                
                # 同步函数的通知回调处理
                if notify_callback:
                    try:
                        if asyncio.iscoroutinefunction(notify_callback):
                            # 如果是异步回调，在事件循环中运行
                            try:
                                loop = asyncio.get_event_loop()
                                loop.create_task(notify_callback(f"❌ {error_msg}"))
                            except:
                                pass
                        else:
                            notify_callback(f"❌ {error_msg}")
                    except:
                        pass
                
                if reraise:
                    raise
                return default_return
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


class TimeUtils:
    """统一的时间处理工具类"""
    
    STANDARD_FORMAT = '%Y-%m-%d %H:%M:%S'
    
    @staticmethod
    def now_string() -> str:
        """获取当前时间字符串"""
        return datetime.now().strftime(TimeUtils.STANDARD_FORMAT)
    
    @staticmethod
    def format_timestamp(timestamp: Union[datetime, int, float, str]) -> str:
        """格式化时间戳为标准字符串格式"""
        if timestamp is None:
            return ""
        
        if hasattr(timestamp, 'strftime'):
            return timestamp.strftime(TimeUtils.STANDARD_FORMAT)
        elif isinstance(timestamp, (int, float)):
            return datetime.fromtimestamp(timestamp).strftime(TimeUtils.STANDARD_FORMAT)
        elif isinstance(timestamp, str):
            return timestamp  # 假设已经是正确格式
        else:
            return str(timestamp)
    
    @staticmethod
    def days_ago(days: int) -> datetime:
        """获取几天前的时间"""
        return datetime.now() - timedelta(days=days)
    
    @staticmethod
    def minutes_ago(minutes: int) -> datetime:
        """获取几分钟前的时间"""
        return datetime.now() - timedelta(minutes=minutes)
    
    @staticmethod
    def parse_time_string(time_str: str) -> datetime:
        """解析时间字符串为datetime对象"""
        try:
            return datetime.strptime(time_str, TimeUtils.STANDARD_FORMAT)
        except ValueError:
            # 尝试其他常见格式
            formats = [
                '%Y-%m-%d %H:%M:%S.%f',
                '%Y-%m-%d',
                '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%dT%H:%M:%S.%f'
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(time_str, fmt)
                except ValueError:
                    continue
            raise ValueError(f"无法解析时间字符串: {time_str}")
    
    @staticmethod
    def time_diff_string(start_time: datetime, end_time: datetime = None) -> str:
        """计算时间差并返回友好的字符串"""
        if end_time is None:
            end_time = datetime.now()
        
        diff = end_time - start_time
        total_seconds = int(diff.total_seconds())
        
        if total_seconds < 60:
            return f"{total_seconds}秒"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            return f"{minutes}分钟"
        elif total_seconds < 86400:
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours}小时{minutes}分钟"
        else:
            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            return f"{days}天{hours}小时"


class DatabaseOperationMixin:
    """数据库操作混入类，提供通用的数据库操作方法"""
    
    @handle_errors(default_return=None, log_prefix="数据库查询")
    def execute_query(self, query: str, params: tuple = None, 
                     fetch_one: bool = False, fetch_all: bool = False):
        """统一的数据库查询方法"""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            
            if fetch_one:
                return cursor.fetchone()
            elif fetch_all:
                return cursor.fetchall()
            else:
                conn.commit()
                return cursor.rowcount
    
    @handle_errors(default_return=False, log_prefix="数据库插入")
    def insert_record(self, table: str, data: dict, replace: bool = False) -> bool:
        """通用插入方法"""
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['?' for _ in data])
        
        if replace:
            query = f"INSERT OR REPLACE INTO {table} ({columns}) VALUES ({placeholders})"
        else:
            query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        
        result = self.execute_query(query, tuple(data.values()))
        return result is not None and result > 0
    
    @handle_errors(default_return=None, log_prefix="数据库查找")
    def find_records(self, table: str, conditions: dict = None, 
                    limit: int = None, order_by: str = None) -> list:
        """通用查找方法"""
        query = f"SELECT * FROM {table}"
        params = ()
        
        if conditions:
            where_clauses = [f"{key} = ?" for key in conditions.keys()]
            query += " WHERE " + " AND ".join(where_clauses)
            params = tuple(conditions.values())
        
        if order_by:
            query += f" ORDER BY {order_by}"
            
        if limit:
            query += f" LIMIT {limit}"
        
        return self.execute_query(query, params, fetch_all=True) or []
    
    @handle_errors(default_return=False, log_prefix="数据库更新")
    def update_record(self, table: str, data: dict, conditions: dict) -> bool:
        """通用更新方法"""
        set_clauses = [f"{key} = ?" for key in data.keys()]
        where_clauses = [f"{key} = ?" for key in conditions.keys()]
        
        query = f"UPDATE {table} SET {', '.join(set_clauses)} WHERE {' AND '.join(where_clauses)}"
        params = tuple(data.values()) + tuple(conditions.values())
        
        result = self.execute_query(query, params)
        return result is not None and result > 0
    
    @handle_errors(default_return=False, log_prefix="数据库删除")
    def delete_records(self, table: str, conditions: dict) -> bool:
        """通用删除方法"""
        where_clauses = [f"{key} = ?" for key in conditions.keys()]
        query = f"DELETE FROM {table} WHERE {' AND '.join(where_clauses)}"
        params = tuple(conditions.values())
        
        result = self.execute_query(query, params)
        return result is not None and result >= 0
    
    @handle_errors(default_return=0, log_prefix="数据库计数")
    def count_records(self, table: str, conditions: dict = None) -> int:
        """通用计数方法"""
        query = f"SELECT COUNT(*) FROM {table}"
        params = ()
        
        if conditions:
            where_clauses = [f"{key} = ?" for key in conditions.keys()]
            query += " WHERE " + " AND ".join(where_clauses)
            params = tuple(conditions.values())
        
        result = self.execute_query(query, params, fetch_one=True)
        return result[0] if result else 0


class TwitterTextUtils:
    """Twitter文本处理工具类 - 使用官方twitter-text-parser库进行准确的字符计算"""
    
    @staticmethod
    def get_tweet_length(text: str) -> int:
        """获取推文的实际字符数（按Twitter官方规则计算）
        
        Args:
            text: 推文文本
            
        Returns:
            int: Twitter计算的字符数
        """
        try:
            from twitter_text import parse_tweet
            result = parse_tweet(text)
            return result.weightedLength  # 注意：是weightedLength，不是weighted_length
        except ImportError:
            logger.warning("twitter-text-parser库未安装，使用简单字符计算")
            return len(text)
        except Exception as e:
            logger.warning(f"Twitter字符计算出错: {e}，使用简单字符计算")
            return len(text)
    
    @staticmethod
    def is_valid_tweet(text: str) -> bool:
        """检查推文是否在字符限制内
        
        Args:
            text: 推文文本
            
        Returns:
            bool: 是否符合Twitter字符限制
        """
        try:
            from twitter_text import parse_tweet
            result = parse_tweet(text)
            return result.valid
        except ImportError:
            logger.warning("twitter-text-parser库未安装，使用简单字符检查")
            return len(text) <= 280
        except Exception as e:
            logger.warning(f"Twitter字符验证出错: {e}，使用简单字符检查")
            return len(text) <= 280
    
    @staticmethod
    def truncate_for_twitter(text: str, max_length: int = 280) -> str:
        """按Twitter规则智能截断文本
        
        Args:
            text: 原始文本
            max_length: 最大字符数（默认280）
            
        Returns:
            str: 截断后的文本
        """
        if TwitterTextUtils.is_valid_tweet(text):
            return text
        
        # 如果文本过长，逐步截断直到符合要求
        try:
            # 预留3个字符给省略号
            target_length = max_length - 3
            
            # 二分查找最优截断位置
            left, right = 0, len(text)
            result = ""
            
            while left <= right:
                mid = (left + right) // 2
                candidate = text[:mid] + "..."
                
                if TwitterTextUtils.is_valid_tweet(candidate):
                    result = candidate
                    left = mid + 1
                else:
                    right = mid - 1
            
            return result if result else "..."
            
        except Exception as e:
            logger.error(f"Twitter文本截断出错: {e}")
            # 回退到简单截断
            if len(text) <= 280:
                return text
            return text[:277] + "..."
    
    @staticmethod
    def estimate_twitter_length_fallback(text: str) -> int:
        """备用的Twitter字符长度估算（当官方库不可用时）
        
        Args:
            text: 文本内容
            
        Returns:
            int: 估算的字符数
        """
        length = 0
        for char in text:
            # CJK字符（中日韩）计为2个字符
            if ('\u4e00' <= char <= '\u9fff' or    # 中文
                '\u3400' <= char <= '\u4dbf' or    # 中文扩展A
                '\u3040' <= char <= '\u309f' or    # 日文平假名
                '\u30a0' <= char <= '\u30ff' or    # 日文片假名
                '\uac00' <= char <= '\ud7af'):     # 韩文
                length += 2
            else:
                length += 1
        return length


# 全局配置管理器实例
config_manager = UnifiedConfigManager()