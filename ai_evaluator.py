import os
import json
import logging
import asyncio
from google import genai

logger = logging.getLogger(__name__)

class AIEvaluator:
    """AI质量评估类，负责使用Gemini API评估评论质量"""
    
    def __init__(self):
        self.gemini_client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """初始化Gemini API客户端"""
        gemini_api_key = os.getenv('GEMINI_API_KEY')
        if gemini_api_key:
            os.environ['GEMINI_API_KEY'] = gemini_api_key
            self.gemini_client = genai.Client()
            logger.info("Gemini API客户端初始化成功")
        else:
            logger.warning("GEMINI_API_KEY未设置，将跳过评论质量筛选")
    
    def is_available(self) -> bool:
        """检查AI评估是否可用"""
        return self.gemini_client is not None
    
    def get_comment_quality_prompt(self, comment: str) -> str:
        """获取单条评论质量评估的提示词"""
        return f"""请评估以下评论是否适合作为独立主题使用。

评判标准：
✅ 表达完整，不依赖上下文就能理解
✅ 包含足够的信息量或明确观点
✅ 不是简单的语气词、问候语或无意义回复
❌ 过滤掉："太麻烦了"、"谢谢"、"哈哈"、"不知道"等

评论内容："{comment}"

请严格按照以下JSON格式返回评估结果，不要包含任何其他内容：
{{
    "result": "yes",
    "reason": "判断理由简短说明",
    "confidence": 0.9
}}

其中confidence请根据你的判断给出0.1到1.0之间的数值，越符合标准，confidence越接近于1。"""

    def get_batch_comment_quality_prompt(self, comments: list) -> str:
        """获取批量评论质量评估的提示词"""
        comment_list = ""
        for i, comment in enumerate(comments):
            comment_list += f"评论{i+1}: \"{comment['body']}\"\n"
        
        return f"""请批量评估以下{len(comments)}条评论是否适合作为独立主题使用。

评判标准：
✅ 表达完整，不依赖上下文就能理解
✅ 包含足够的信息量或明确观点
✅ 不是简单的语气词、问候语或无意义回复
❌ 过滤掉："太麻烦了"、"谢谢"、"哈哈"、"不知道"等

评论内容：
{comment_list}

请严格按照以下JSON格式返回评估结果，不要包含任何其他内容：
{{
    "results": [
        {{
            "index": 1,
            "result": "yes",
            "reason": "判断理由简短说明",
            "confidence": 0.9
        }},
        {{
            "index": 2,
            "result": "no", 
            "reason": "判断理由简短说明",
            "confidence": 0.3
        }}
    ]
}}

对于每条评论，confidence请根据你的判断给出0.1到1.0之间的数值，越符合标准，confidence越接近于1。
请确保返回的results数组包含{len(comments)}个评估结果，按顺序对应上述评论。"""

    async def assess_comment_quality(self, comment: str) -> dict:
        """使用Gemini API评估单条评论质量"""
        if not self.gemini_client:
            return {"result": "yes", "reason": "未启用质量筛选", "confidence": 0.5}
        
        try:
            response = self.gemini_client.models.generate_content(
                model="gemini-2.5-flash-lite-preview-06-17",
                contents=self.get_comment_quality_prompt(comment)
            )
            
            content = response.text.strip()
            
            # 尝试解析JSON
            try:
                clean_content = self._clean_json_content(content)
                result_data = json.loads(clean_content)
                return {
                    "result": result_data.get("result", "no"),
                    "reason": result_data.get("reason", ""),
                    "confidence": float(result_data.get("confidence", 0.0))
                }
            except json.JSONDecodeError as e:
                logger.warning(f"JSON解析失败: {e}, 原始内容: {content[:200]}")
                # 如果JSON解析失败，从文本中提取信息
                result = "yes" if "yes" in content.lower() else "no"
                return {
                    "result": result,
                    "reason": content[:100],
                    "confidence": 0.5
                }
        except Exception as e:
            logger.error(f"评估评论质量时出错: {e}")
            return {"result": "yes", "reason": "评估失败", "confidence": 0.5}

    async def assess_batch_comment_quality(self, comments: list) -> list:
        """使用Gemini API批量评估评论质量"""
        if not self.gemini_client:
            return [{"result": "yes", "reason": "未启用质量筛选", "confidence": 0.5} for _ in comments]
        
        try:
            response = self.gemini_client.models.generate_content(
                model="gemini-2.5-flash-lite-preview-06-17",
                contents=self.get_batch_comment_quality_prompt(comments)
            )
            
            content = response.text.strip()
            
            # 尝试解析JSON
            try:
                clean_content = self._clean_json_content(content)
                result_data = json.loads(clean_content)
                results = result_data.get("results", [])
                
                # 确保结果数量与输入评论数量一致
                if len(results) != len(comments):
                    logger.warning(f"批量评估结果数量不匹配: 期望{len(comments)}，得到{len(results)}")
                    return await self._fallback_to_individual_assessment(comments)
                
                # 转换结果格式
                formatted_results = []
                for result in results:
                    formatted_results.append({
                        "result": result.get("result", "no"),
                        "reason": result.get("reason", ""),
                        "confidence": float(result.get("confidence", 0.0))
                    })
                
                return formatted_results
                
            except json.JSONDecodeError as e:
                logger.warning(f"批量评估JSON解析失败: {e}")
                return await self._fallback_to_individual_assessment(comments)
                
        except Exception as e:
            logger.error(f"批量评估评论质量时出错: {e}")
            return await self._fallback_to_individual_assessment(comments)

    async def filter_comments_with_ai(self, comments: list, batch_size: int = 10):
        """使用AI筛选评论质量"""
        filtered_comments = []
        total_api_calls = 0
        
        try:
            # 分批处理评论
            for i in range(0, len(comments), batch_size):
                batch = comments[i:i + batch_size]
                
                # 过滤太短的评论
                valid_batch = [c for c in batch if len(c.get('body', '')) >= 10]
                if not valid_batch:
                    continue
                
                # 使用批量评估方法
                batch_results = await self.assess_batch_comment_quality(valid_batch)
                total_api_calls += 1
                
                # 处理批量结果
                for comment, quality_result in zip(valid_batch, batch_results):
                    # 只保留result为"yes"且confidence大于0.8的评论
                    if quality_result['result'] == 'yes' and quality_result['confidence'] > 0.8:
                        comment['confidence'] = quality_result['confidence']
                        comment['reason'] = quality_result['reason']
                        filtered_comments.append(comment)
                
                # 批次间延迟
                if i + batch_size < len(comments):
                    await asyncio.sleep(0.5)
            
            return filtered_comments, total_api_calls
            
        except Exception as e:
            logger.error(f"AI筛选过程出错: {e}")
            return [], total_api_calls

    async def _fallback_to_individual_assessment(self, comments: list) -> list:
        """回退到逐条评估模式"""
        logger.info("回退到逐条评估模式")
        batch_results = []
        for comment in comments:
            try:
                single_result = await self.assess_comment_quality(comment['body'])
                batch_results.append(single_result)
            except:
                batch_results.append({"result": "yes", "reason": "评估失败", "confidence": 0.5})
        return batch_results

    def _clean_json_content(self, content: str) -> str:
        """清理JSON内容，移除markdown格式"""
        clean_content = content.strip()
        if clean_content.startswith("```json"):
            clean_content = clean_content[7:]
        if clean_content.endswith("```"):
            clean_content = clean_content[:-3]
        return clean_content.strip()