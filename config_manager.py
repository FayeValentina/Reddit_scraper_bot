import json
import logging
from database_manager import db_manager
from utils import config_manager as unified_config, DatabaseOperationMixin, handle_errors, TimeUtils

logger = logging.getLogger(__name__)

class ConfigManager(DatabaseOperationMixin):
    def __init__(self):
        # 使用统一配置管理器获取数据库路径
        self.db_path = unified_config.get_database_config()['database_path']
        self._init_config_table()
        self._set_default_configs()
    
    @handle_errors(log_prefix="初始化配置表")
    def _init_config_table(self):
        """初始化配置表"""
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
    
    @handle_errors(log_prefix="获取配置", reraise=False)
    def get_config(self, key, default=None):
        """获取配置值 - 使用继承的数据库操作方法"""
        result = self.find_records('bot_config', {'config_key': key}, limit=1)
        if result:
            value, config_type = result[0][1], result[0][2]  # config_value, config_type
            return self._convert_value(value, config_type)
        return default
    
    @handle_errors(default_return=False, log_prefix="设置配置")
    def set_config(self, key, value, config_type='str', description=''):
        """设置配置值 - 使用继承的数据库操作方法"""
        data = {
            'config_key': key,
            'config_value': str(value),
            'config_type': config_type,
            'description': description,
            'updated_at': TimeUtils.now_string()
        }
        return self.insert_record('bot_config', data, replace=True)
    
    @handle_errors(default_return={}, log_prefix="获取所有配置")
    def get_all_configs(self):
        """获取所有配置 - 使用继承的数据库操作方法"""
        results = self.execute_query(
            'SELECT config_key, config_value, config_type, description FROM bot_config ORDER BY config_key',
            fetch_all=True
        )
        
        if not results:
            return {}
        
        configs = {}
        for key, value, config_type, description in results:
            configs[key] = {
                'value': self._convert_value(value, config_type),
                'type': config_type,
                'description': description
            }
        return configs
    
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
    
    @handle_errors(default_return=False, log_prefix="更新配置")
    def update_config(self, key, new_value):
        """更新现有配置的值 - 使用继承的数据库操作方法"""
        # 检查配置是否存在
        existing_config = self.find_records('bot_config', {'config_key': key}, limit=1)
        
        if existing_config:
            data = {
                'config_value': str(new_value),
                'updated_at': TimeUtils.now_string()
            }
            return self.update_record('bot_config', data, {'config_key': key})
        else:
            return False