import logging
from utils import config_manager, DatabaseOperationMixin, handle_errors, TimeUtils

logger = logging.getLogger(__name__)

class DataProcessor(DatabaseOperationMixin):
    def __init__(self):
        # 使用统一配置管理器获取数据库路径
        self.db_path = config_manager.get_database_config()['database_path']
    
    @handle_errors(log_prefix="保存评论到数据库")
    def save_comments_to_database(self, comments_data):
        """
        保存评论数据到SQLite数据库 - 使用继承的数据库操作方法
        
        Args:
            comments_data (list): 评论数据列表
        """
        # 确保表存在
        self._ensure_table_exists()
        
        saved_count = 0
        for comment in comments_data:
            # 标准化时间字段
            comment_data = comment.copy()
            comment_data['created_utc'] = TimeUtils.format_timestamp(comment_data['created_utc'])
            
            if comment_data.get('sent_at'):
                comment_data['sent_at'] = TimeUtils.format_timestamp(comment_data['sent_at'])
            
            # 使用继承的插入方法
            success = self.insert_record('reddit_comments', comment_data, replace=True)
            if success:
                saved_count += 1
            else:
                logger.warning(f"保存评论失败: {comment.get('comment_id', 'unknown')}")
        
        logger.info(f"成功保存 {saved_count}/{len(comments_data)} 条评论到数据库")
    
    @handle_errors(log_prefix="确保表存在")
    def _ensure_table_exists(self):
        """确保reddit_comments表存在并包含所有必要字段"""
        # 创建基础表结构
        create_table_sql = '''
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
        '''
        self.execute_query(create_table_sql)