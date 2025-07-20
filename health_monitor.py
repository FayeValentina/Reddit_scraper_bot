import os
import json
import hmac
import hashlib
import base64
import logging
import asyncio
import aiohttp
from aiohttp import web
from datetime import datetime

logger = logging.getLogger(__name__)

class HealthMonitor:
    """健康监控和Webhook处理类"""
    
    def __init__(self, notification_callback=None):
        self.app_url = os.getenv('APP_URL')
        self.webhook_secret = os.getenv('TWITTER_WEBHOOK_SECRET')
        self.notification_callback = notification_callback
        self.runner = None
        self.site = None
    
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
    
    async def health_check(self, request):
        """健康检查端点"""
        return web.Response(text="OK", status=200)
    
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
                await self._process_dm_events(data)
            
            return web.Response(text="OK")
            
        except Exception as e:
            logger.error(f"处理私信webhook时出错: {e}")
            return web.Response(status=500)
    
    async def _process_dm_events(self, data):
        """处理私信事件"""
        for dm_event in data['direct_message_events']:
            # 确保不是自己发送的消息（简单检查）
            sender_id = dm_event.get('message_create', {}).get('sender_id')
            
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
            
            # 发送通知
            if self.notification_callback:
                await self.notification_callback(formatted_message)
            
            logger.info(f"已转发私信到Telegram: 来自 @{sender_username}")
    
    async def start_server(self, port=8000):
        """启动HTTP服务器"""
        try:
            app = web.Application()
            app.router.add_get("/health", self.health_check)
            app.router.add_get("/", self.health_check)
            app.router.add_get("/webhook/twitter", self.webhook_challenge)
            app.router.add_post("/webhook/twitter", self.handle_dm_webhook)
            
            self.runner = web.AppRunner(app)
            await self.runner.setup()
            self.site = web.TCPSite(self.runner, "0.0.0.0", port)
            await self.site.start()
            
            logger.info(f"健康检查服务器启动在端口{port}...")
            return True
        except Exception as e:
            logger.error(f"启动健康检查服务器失败: {e}")
            return False
    
    async def stop_server(self):
        """停止HTTP服务器"""
        try:
            if self.runner:
                await self.runner.cleanup()
                self.runner = None
                self.site = None
                logger.info("健康检查服务器已停止")
        except Exception as e:
            logger.error(f"停止健康检查服务器时出错: {e}")
    
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