import sqlite3
import threading
import logging
import os
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

class DatabaseManager:
    """数据库连接管理器，提供连接池和上下文管理器功能"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DatabaseManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, db_path: str = None):
        if self._initialized:
            return
        
        # 使用环境变量或默认路径，避免导入config模块
        self.db_path = db_path or os.getenv('DATABASE_PATH', 'reddit_data.db')
        self._local = threading.local()
        self._initialized = True
        logger.info(f"数据库管理器初始化，数据库路径: {self.db_path}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取线程本地的数据库连接"""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            try:
                self._local.connection = sqlite3.connect(
                    self.db_path,
                    check_same_thread=False,
                    timeout=30.0
                )
                # 启用外键约束
                self._local.connection.execute("PRAGMA foreign_keys = ON")
                # 设置WAL模式以提高并发性能
                self._local.connection.execute("PRAGMA journal_mode = WAL")
                logger.debug("创建新的数据库连接")
            except Exception as e:
                logger.error(f"创建数据库连接失败: {e}")
                raise
        return self._local.connection
    
    @contextmanager
    def get_connection(self):
        """上下文管理器，自动管理数据库连接"""
        conn = None
        try:
            conn = self._get_connection()
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"数据库操作失败: {e}")
            raise
        finally:
            # 注意：不关闭连接，因为我们使用线程本地连接池
            pass
    
    @contextmanager
    def get_transaction(self):
        """事务上下文管理器，自动提交或回滚"""
        conn = None
        try:
            conn = self._get_connection()
            yield conn
            conn.commit()
            logger.debug("事务提交成功")
        except Exception as e:
            if conn:
                conn.rollback()
                logger.warning(f"事务回滚: {e}")
            raise
        finally:
            # 不关闭连接，重用线程本地连接
            pass
    
    def execute_query(self, query: str, params: tuple = None) -> Optional[list]:
        """执行查询并返回结果"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                
                # 如果是SELECT查询，返回结果
                if query.strip().upper().startswith('SELECT'):
                    return cursor.fetchall()
                else:
                    conn.commit()
                    return None
        except Exception as e:
            logger.error(f"执行查询失败: {query[:100]}..., 错误: {e}")
            raise
    
    def close_all_connections(self):
        """关闭所有连接（在应用程序关闭时调用）"""
        try:
            if hasattr(self._local, 'connection') and self._local.connection:
                self._local.connection.close()
                self._local.connection = None
                logger.info("数据库连接已关闭")
        except Exception as e:
            logger.error(f"关闭数据库连接时出错: {e}")

# 全局数据库管理器实例
db_manager = DatabaseManager()