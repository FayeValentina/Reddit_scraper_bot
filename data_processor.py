import sqlite3
import config
from datetime import datetime
import os
import logging
from database_manager import db_manager

logger = logging.getLogger(__name__)

class DataProcessor:
    def __init__(self):
        self.db_path = config.DATABASE_PATH
        # 创建数据目录
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else '.', exist_ok=True)
    
    def save_comments_to_database(self, comments_data):
        """
        保存评论数据到SQLite数据库
        
        Args:
            comments_data (list): 评论数据列表
        """
        try:
            with db_manager.get_transaction() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS reddit_comments (
                        comment_id TEXT PRIMARY KEY,
                        post_id TEXT,
                        author TEXT,
                        body TEXT,
                        score INTEGER,
                        created_utc TIMESTAMP,
                        parent_id TEXT,
                        is_submitter BOOLEAN,
                        subreddit TEXT,
                        tweet_id TEXT,
                        sent_at TIMESTAMP,
                        scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        confidence REAL,
                        reason TEXT,
                        api_call_count INTEGER
                    )
                ''')
                
                # 添加新字段（如果表已存在）
                try:
                    cursor.execute('ALTER TABLE reddit_comments ADD COLUMN confidence REAL')
                except sqlite3.OperationalError:
                    pass  # 字段已存在
                
                try:
                    cursor.execute('ALTER TABLE reddit_comments ADD COLUMN reason TEXT')
                except sqlite3.OperationalError:
                    pass  # 字段已存在
                    
                try:
                    cursor.execute('ALTER TABLE reddit_comments ADD COLUMN api_call_count INTEGER')
                except sqlite3.OperationalError:
                    pass  # 字段已存在
                
                for comment in comments_data:
                    # Convert pandas Timestamp to string if needed
                    created_utc = comment['created_utc']
                    if hasattr(created_utc, 'strftime'):
                        created_utc = created_utc.strftime('%Y-%m-%d %H:%M:%S')
                    
                    # Convert sent_at timestamp if needed
                    sent_at = comment.get('sent_at')
                    if sent_at and hasattr(sent_at, 'strftime'):
                        sent_at = sent_at.strftime('%Y-%m-%d %H:%M:%S')
                    
                    cursor.execute('''
                        INSERT OR REPLACE INTO reddit_comments 
                        (comment_id, post_id, author, body, score, created_utc, 
                         parent_id, is_submitter, subreddit, tweet_id, sent_at,
                         confidence, reason, api_call_count)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        comment['comment_id'], comment['post_id'], comment['author'],
                        comment['body'], comment['score'], created_utc,
                        comment['parent_id'], comment['is_submitter'],
                        comment.get('subreddit'), comment.get('tweet_id'), sent_at,
                        comment.get('confidence'), comment.get('reason'), comment.get('api_call_count')
                    ))
                
            logger.info(f"成功保存 {len(comments_data)} 条评论到数据库")
            
        except Exception as e:
            logger.error(f"保存评论数据到数据库失败: {e}")
            pass  # Allow operation to continue