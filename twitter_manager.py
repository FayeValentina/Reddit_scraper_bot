import os
import logging
import tweepy
import tempfile
import re
from PIL import Image
from datetime import datetime

logger = logging.getLogger(__name__)

class TwitterManager:
    """Twitter API管理类，负责所有Twitter相关操作"""
    
    def __init__(self):
        self.twitter_api_key = os.getenv('TWITTER_API_KEY')
        self.twitter_api_secret = os.getenv('TWITTER_API_SECRET')
        self.twitter_access_token = os.getenv('TWITTER_ACCESS_TOKEN')
        self.twitter_access_token_secret = os.getenv('TWITTER_ACCESS_TOKEN_SECRET')
        self.twitter_bearer_token = os.getenv('TWITTER_BEARER_TOKEN')
        
        # 初始化Twitter客户端
        self.twitter_client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """初始化Twitter API客户端"""
        if not all([self.twitter_api_key, self.twitter_api_secret, 
                   self.twitter_access_token, self.twitter_access_token_secret, 
                   self.twitter_bearer_token]):
            logger.error("Twitter API配置不完整")
            return
        
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
    
    def is_available(self) -> bool:
        """检查Twitter API是否可用"""
        return self.twitter_client is not None
    
    async def test_connection(self) -> dict:
        """测试Twitter API连接和权限"""
        if not self.twitter_client:
            return {
                'success': False,
                'error': 'Twitter API未初始化，请检查API配置'
            }
        
        try:
            user = self.twitter_client.get_me(user_fields=['public_metrics'])
            username = user.data.username
            user_id = user.data.id
            followers_count = user.data.public_metrics.get('followers_count', 0) if hasattr(user.data, 'public_metrics') else 0
            
            return {
                'success': True,
                'username': username,
                'user_id': user_id,
                'followers_count': followers_count
            }
        except Exception as e:
            error_msg = str(e)
            error_type = 'unknown'
            
            if "403" in error_msg:
                error_type = 'permission'
            elif "401" in error_msg:
                error_type = 'authentication'
            
            return {
                'success': False,
                'error': error_msg,
                'error_type': error_type
            }
    
    async def post_text_tweet(self, text: str) -> dict:
        """发布文本推文"""
        if not self.twitter_client:
            return {'success': False, 'error': 'Twitter API未初始化'}
        
        try:
            # 清理内容
            content = self._clean_content(text)
            if len(content) > 280:
                content = content[:277] + "..."
            
            response = self.twitter_client.create_tweet(text=content)
            tweet_id = response.data['id']
            
            return {
                'success': True,
                'tweet_id': tweet_id,
                'content': content
            }
        except Exception as e:
            return self._handle_twitter_error(e)
    
    async def post_image_tweet(self, text: str, image_file_id: str, context) -> dict:
        """发布带图片的推文"""
        if not self.twitter_client:
            return {'success': False, 'error': 'Twitter API未初始化'}
        
        try:
            # 获取图片文件
            file = await context.bot.get_file(image_file_id)
            
            # 创建临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
                await file.download_to_drive(temp_file.name)
                
                try:
                    # 优化图片
                    optimized_path = self._optimize_image(temp_file.name)
                    
                    # 上传媒体（使用V1.1 API）
                    auth = tweepy.OAuth1UserHandler(
                        self.twitter_api_key,
                        self.twitter_api_secret,
                        self.twitter_access_token,
                        self.twitter_access_token_secret
                    )
                    twitter_api_v1 = tweepy.API(auth)
                    media = twitter_api_v1.media_upload(optimized_path)
                    
                    # 创建推文（使用V2 API）
                    content = self._clean_content(text)
                    if len(content) > 280:
                        content = content[:277] + "..."
                    
                    response = self.twitter_client.create_tweet(
                        text=content,
                        media_ids=[media.media_id]
                    )
                    
                    tweet_id = response.data['id']
                    
                    return {
                        'success': True,
                        'tweet_id': tweet_id,
                        'content': content
                    }
                    
                finally:
                    # 清理临时文件
                    try:
                        os.unlink(temp_file.name)
                        if 'optimized_path' in locals():
                            os.unlink(optimized_path)
                    except:
                        pass
                        
        except Exception as e:
            return self._handle_twitter_error(e)
    
    def _optimize_image(self, image_path: str) -> str:
        """优化图片"""
        with Image.open(image_path) as img:
            # 转换为RGB
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # 调整图片大小
            max_size = (2048, 2048)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # 保存优化后的图片
            optimized_path = image_path.replace('.jpg', '_optimized.jpg')
            img.save(optimized_path, 'JPEG', quality=85, optimize=True)
            
            return optimized_path
    
    def _clean_content(self, content: str) -> str:
        """清理推文内容"""
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        content = re.sub(r'\n+', '\n', content).strip()
        return content
    
    def _handle_twitter_error(self, error: Exception) -> dict:
        """处理Twitter API错误"""
        error_msg = str(error)
        error_type = 'unknown'
        
        if "403" in error_msg:
            if "duplicate" in error_msg.lower():
                error_type = 'duplicate'
            elif "not permitted" in error_msg.lower():
                error_type = 'permission'
            else:
                error_type = 'forbidden'
        elif "401" in error_msg:
            error_type = 'authentication'
        elif "413" in error_msg or "too large" in error_msg.lower():
            error_type = 'file_too_large'
        
        return {
            'success': False,
            'error': error_msg,
            'error_type': error_type
        }