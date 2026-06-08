"""
记忆提取器 —— 利用 LLM 从对话中提取摘要和关键事实
"""
import json
from typing import List
from openai import AsyncOpenAI
from loguru import logger

from config import settings

_client = AsyncOpenAI(
    api_key=settings.deepseek_api_key,
    base_url=settings.deepseek_base_url,
)

EXTRACT_FACTS_PROMPT = """你是一个知识提取器。从以下对话中提取关键事实、用户偏好和值得长期记住的信息。

规则：
1. 只提取有长期价值的信息（用户偏好、决策、重要事实、联系方式等）
2. 每条信息一句话概括，独立成条
3. 不要提取闲聊、临时性的讨论
4. 如果没有任何值得长期记住的信息，返回空数组
5. 对每条信息生成 1-3 个标签（中文）

输出格式（纯 JSON）：
{
  "summary": "一句话总结这次对话的核心内容",
  "facts": [
    {"content": "用户偏好使用 Rust 做系统编程", "tags": ["编程偏好", "Rust"], "importance": 0.8},
    {"content": "用户计划下个月去成都出差", "tags": ["计划", "出差", "成都"], "importance": 0.6}
  ]
}

importance 评分：0.9-1.0 = 极其重要（身份、核心偏好），0.7-0.8 = 重要（偏好、计划），0.5-0.6 = 一般（临时信息但值得记），0.0-0.4 = 低价值

对话内容：
{conversation}

请输出 JSON："""


async def extract_from_conversation(messages: List[dict]) -> dict:
    """
    从对话中提取摘要和关键事实

    Args:
        messages: [{"role": "user/assistant", "content": "..."}, ...]

    Returns:
        {"summary": str, "facts": [{"content": str, "tags": [...], "importance": float}]}
    """
    # 构建对话文本
    conversation_text = ""
    for msg in messages:
        role = "用户" if msg["role"] == "user" else "AI"
        conversation_text += f"{role}: {msg['content']}\n"

    prompt = EXTRACT_FACTS_PROMPT.format(conversation=conversation_text)

    try:
        response = await _client.chat.completions.create(
            model=settings.chat_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1000,
        )
        text = response.choices[0].message.content
        # 清理 markdown code block
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
        result = json.loads(text.strip())
        logger.info(f"Extracted {len(result.get('facts', []))} facts, summary: {result.get('summary', '')[:50]}...")
        return result
    except Exception as e:
        logger.error(f"Failed to extract facts: {e}")
        return {"summary": "", "facts": []}


async def generate_conversation_title(first_message: str) -> str:
    """根据对话的第一条消息生成标题"""
    try:
        response = await _client.chat.completions.create(
            model=settings.chat_model,
            messages=[
                {
                    "role": "user",
                    "content": f"为以下对话生成一个简短的标题（10字以内，只返回标题本身）：\n{first_message}",
                }
            ],
            temperature=0.5,
            max_tokens=50,
        )
        title = response.choices[0].message.content.strip().strip('"').strip("《》")
        return title[:50]
    except Exception as e:
        logger.error(f"Failed to generate title: {e}")
        return first_message[:50]
