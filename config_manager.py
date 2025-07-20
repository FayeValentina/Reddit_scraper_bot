import sqlite3
import json
import os
import logging
from datetime import datetime
import config
from database_manager import db_manager

logger = logging.getLogger(__name__)

class ConfigManager:
    def __init__(self):
        self.db_path = config.DATABASE_PATH
        # 创建数据目录
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else '.', exist_ok=True)
        self._init_config_table()
        self._set_default_configs()
    
    def _init_config_table(self):
        """初始化配置表"""
        try:
            with db_manager.get_transaction() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS bot_config (
                        config_key TEXT PRIMARY KEY,
                        config_value TEXT NOT NULL,
                        config_type TEXT NOT NULL DEFAULT 'str',
                        description TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
        except Exception as e:
            logger.error(f"初始化配置表失败: {e}")
            pass  # Allow initialization to continue
    
    def _set_default_configs(self):
        """设置默认配置值"""
        default_configs = {
            'GEMINI_BATCH_SIZE': {
                'value': '10',
                'type': 'int',
                'description': '每次调用gemini api时批处理评论内容的数量'
            },
            'TOP_COMMENTS_COUNT': {
                'value': '50',
                'type': 'int', 
                'description': '赞数最高的前N条评论'
            },
            'REDDIT_POST_FETCH_COUNT': {
                'value': '50',
                'type': 'int',
                'description': '每个reddit板块爬取指定数量的帖子'
            },
            'REDDIT_SORT_METHOD': {
                'value': 'hot',
                'type': 'str',
                'description': 'Reddit帖子排序方式：hot(热门), new(最新), top(顶尖), controversial(有争议), rising(上升中), gilded(镀金)'
            },
            'REDDIT_TIME_FILTER': {
                'value': 'day',
                'type': 'str',
                'description': '时间筛选范围（仅对top和controversial排序有效）：all(全部时间), year(过去一年), month(过去一月), week(过去一周), day(过去一天), hour(过去一小时)'
            },
            'REDDIT_COMMENTS_PER_POST': {
                'value': '20',
                'type': 'int',
                'description': '每个帖子的评论数量限制'
            },
            'REDDIT_FETCH_INTERVAL': {
                'value': '60',
                'type': 'int',
                'description': '爬取时间间隔（单位分钟）'
            },
            'REDDIT_SUBREDDITS': {
                'value': 'python,programming,MachineLearning,artificial,technology',
                'type': 'list',
                'description': '要爬取的reddit板块集合（逗号分隔）'
            },
            'AUTO_SCRAPER_ENABLED': {
                'value': 'false',
                'type': 'bool',
                'description': '自动爬取系统开关（true/false）'
            }
        }
        
        for key, config_data in default_configs.items():
            if not self.get_config(key):
                self.set_config(key, config_data['value'], config_data['type'], config_data['description'])
    
    def get_config(self, key, default=None):
        """获取配置值"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT config_value, config_type FROM bot_config WHERE config_key = ?', (key,))
                result = cursor.fetchone()
                
                if result:
                    value, config_type = result
                    return self._convert_value(value, config_type)
                return default
        except Exception as e:
            logger.error(f"获取配置 {key} 失败: {e}")
            return default
    
    def set_config(self, key, value, config_type='str', description=''):
        """设置配置值"""
        try:
            with db_manager.get_transaction() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO bot_config 
                    (config_key, config_value, config_type, description, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (key, str(value), config_type, description, datetime.now()))
            return True
        except Exception as e:
            logger.error(f"设置配置 {key} 失败: {e}")
            return False
    
    def get_all_configs(self):
        """获取所有配置"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT config_key, config_value, config_type, description FROM bot_config ORDER BY config_key')
                results = cursor.fetchall()
                
                configs = {}
                for key, value, config_type, description in results:
                    configs[key] = {
                        'value': self._convert_value(value, config_type),
                        'type': config_type,
                        'description': description
                    }
                return configs
        except Exception as e:
            logger.error(f"获取所有配置失败: {e}")
            return {}
    
    def _convert_value(self, value, config_type):
        """根据类型转换配置值"""
        if config_type == 'int':
            return int(value)
        elif config_type == 'float':
            return float(value)
        elif config_type == 'bool':
            return value.lower() in ('true', '1', 'yes', 'on')
        elif config_type == 'list':
            return [item.strip() for item in value.split(',') if item.strip()]
        elif config_type == 'json':
            return json.loads(value)
        else:  # str
            return str(value)
    
    def update_config(self, key, new_value):
        """更新现有配置的值"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT config_type FROM bot_config WHERE config_key = ?', (key,))
                result = cursor.fetchone()
                
                if result:
                    with db_manager.get_transaction() as trans_conn:
                        trans_cursor = trans_conn.cursor()
                        trans_cursor.execute('''
                            UPDATE bot_config 
                            SET config_value = ?, updated_at = ?
                            WHERE config_key = ?
                        ''', (str(new_value), datetime.now(), key))
                    return True
                else:
                    return False
        except Exception as e:
            logger.error(f"更新配置 {key} 失败: {e}")
            return False