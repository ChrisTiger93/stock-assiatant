"""
AI 编排核心 —— 对话流程、工具调用、记忆集成
"""
import json
from typing import AsyncGenerator, List, Optional
from datetime import datetime, timezone

from openai import AsyncOpenAI
from loguru import logger

from config import settings
from memory.manager import MemoryManager
from search.engine import search_engine
from finance.engine import finance_engine
from orchestrator.prompts import (
    SYSTEM_PROMPT_TEMPLATE,
    SYSTEM_PROMPT_NO_MEMORY,
    TOOLS,
)


import re

_RAW_TOOL_MARKERS = [
    "<|tool_calls|>", "</|tool_calls|>", "</|tool_calls|",
    "<tool_call>", "</tool_call>",
    '<invoke name="search">', '<invoke name="search">',
    "</invoke>", "<function_call>", "</function_call>",
    "<|function", '<parameter name=',
]

# 匹配所有 DSML tool call 标签（含 opening/closing）
_TOOL_BLOCK_RE = re.compile(
    r'<\s*/?\s*\|?\s*(?:tool_calls?|invoke|function_call|parameter)\b[^>]*>',
    re.IGNORECASE)


def _is_raw_tool_text(text: str) -> bool:
    """检测文本是否包含 DSML tool call 标记"""
    for m in _RAW_TOOL_MARKERS:
        if m in text:
            return True
    return False


def _looks_like_tool_json(text: str) -> bool:
    """检测文本是否看起来像 tool call 中的 JSON 片段"""
    stripped = text.strip()
    # JSON 结构特征：以 { } [ ] " : 开头的大量内容
    if not stripped:
        return False
    # 纯 JSON 片段（DeepSeek 有时把 arguments 当 text 发出来）
    if stripped[0] in '{}[]"' or stripped.startswith('"') or stripped.startswith('arguments'):
        return True
    # 以逗号或冒号开头的 JSON 续片
    if len(stripped) < 2 and stripped in ',:':
        return True
    return False


def clean_tool_markup(text: str) -> str:
    """清理响应中的所有原始 tool call 标记"""
    return _TOOL_BLOCK_RE.sub('', text).strip()


class AIOrchestrator:
    """AI 对话编排器"""

    def __init__(self, memory_manager: MemoryManager):
        self.memory = memory_manager
        self.client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )

    async def chat_stream(
        self,
        conversation_id: str,
        user_message: str,
        history: List[dict],
    ) -> AsyncGenerator[dict, None]:
        """
        流式对话，返回事件 dict:
          {"type": "chunk", "content": "..."}
          {"type": "tool_call", "tool": "search", "query": "..."}
          {"type": "tool_result", "tool": "search", "data": [...]}
          {"type": "done", "message_id": "...", "conversation_id": "..."}

        Args:
            conversation_id: 会话 ID
            user_message: 用户最新消息
            history: 当前会话的历史消息
        """
        # 1. 检索相关记忆
        memory_context = await self.memory.build_context_for_prompt(user_message)

        # 2. 构建消息
        now = datetime.now(timezone.utc).strftime("%Y年%m月%d日 %H:%M UTC")
        date_note = f"\n\n## 当前时间\n现在是 {now}。如果用户问及时间敏感的问题，请注意日期准确性。搜索时请使用具体日期而非相对时间（如用\"2026年6月\"而非\"本月\"）。"

        base = SYSTEM_PROMPT_TEMPLATE.format(memory_context=memory_context) if memory_context else SYSTEM_PROMPT_NO_MEMORY
        system_prompt = base + date_note

        messages = [{"role": "system", "content": system_prompt}]
        # 注入短期记忆（历史消息，限制轮数）
        short_term = history[-(settings.short_term_turns * 2):]
        messages.extend(short_term)
        messages.append({"role": "user", "content": user_message})

        # 3. 流式调用
        full_content = ""
        tool_calls_buffer = []

        try:
            stream = await self.client.chat.completions.create(
                model=settings.chat_model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                stream=True,
                temperature=0.7,
                max_tokens=4096,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is None:
                    continue

                has_tool_calls = bool(delta.tool_calls)

                # 处理文本内容
                if delta.content:
                    text = delta.content
                    # 跳过 DSML 标记、tool call JSON 片段、以及 tool calls 流中的文本
                    if _is_raw_tool_text(text):
                        continue
                    if has_tool_calls:
                        # tool_calls 正在进行中，text content 是 DSML 噪声
                        continue
                    if _looks_like_tool_json(text):
                        continue
                    full_content += text
                    yield {"type": "chunk", "content": text}

                # 处理工具调用
                if has_tool_calls:
                    for tc in delta.tool_calls:
                        # 累积 tool call 信息
                        idx = tc.index
                        while len(tool_calls_buffer) <= idx:
                            tool_calls_buffer.append({
                                "id": "",
                                "function": {"name": "", "arguments": ""},
                            })
                        if tc.id:
                            tool_calls_buffer[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_buffer[idx]["function"]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_buffer[idx]["function"]["arguments"] += tc.function.arguments

            # 4. 执行工具调用
            if tool_calls_buffer:
                # 添加 assistant 消息（必须包含 tool_calls）
                assistant_tool_msg = {"role": "assistant", "content": full_content or None}
                if full_content:
                    assistant_tool_msg["content"] = full_content
                assistant_tool_msg["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"],
                        },
                    }
                    for tc in tool_calls_buffer
                ]
                messages.append(assistant_tool_msg)

                # 执行工具并添加结果
                for tc in tool_calls_buffer:
                    if tc["function"]["name"] == "search":
                        result = await self._execute_search(tc)
                        yield result
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps(result.get("data", []), ensure_ascii=False),
                        })
                    elif tc["function"]["name"] == "get_stock_price":
                        result = await self._execute_stock_price(tc)
                        yield result
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps(result.get("data", {}), ensure_ascii=False),
                        })
                    elif tc["function"]["name"] == "get_stock_financials":
                        result = await self._execute_stock_financials(tc)
                        yield result
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps(result.get("data", {}), ensure_ascii=False),
                        })
                    elif tc["function"]["name"] == "get_stock_news":
                        result = await self._execute_stock_news(tc)
                        yield result
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps(result.get("data", {}), ensure_ascii=False),
                        })

                # 继续流式生成最终回复
                stream2 = await self.client.chat.completions.create(
                    model=settings.chat_model,
                    messages=messages,
                    stream=True,
                    temperature=0.7,
                    max_tokens=4096,
                )

                final_content = ""
                async for chunk in stream2:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        text = delta.content
                        if _is_raw_tool_text(text):
                            continue
                        final_content += text
                        yield {"type": "chunk", "content": text}

                full_content = final_content

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield {"type": "error", "content": str(e)}
            return

        # 6. 写入短期记忆（对话片段）
        try:
            combined = user_message + "\n" + full_content
            # 估算当前已存的 chunk 数
            chunk_index = len(history) // 2  # 粗略估算
            await self.memory.add_conversation_chunk(
                conversation_id, combined[:settings.chunk_size], chunk_index
            )
        except Exception as e:
            logger.error(f"Failed to save chunk: {e}")

        # 7. 完成
        full_content = clean_tool_markup(full_content)
        yield {"type": "done", "content": full_content}

    async def _execute_search(self, tool_call: dict) -> dict:
        """执行搜索工具调用"""
        try:
            args = json.loads(tool_call["function"]["arguments"])
            query = args.get("query", "")
            logger.info(f"Searching: {query}")

            results = await search_engine.search(query, num_results=5)

            # 存储搜索结果到知识片段
            for r in results:
                snippet = f"{r['title']}: {r['snippet']}"
                try:
                    await self.memory.add_knowledge_snippet(
                        content=snippet, url=r["url"], query=query
                    )
                except Exception:
                    pass

            return {
                "type": "tool_result",
                "tool": "search",
                "query": query,
                "data": results,
            }
        except Exception as e:
            logger.error(f"Search execution failed: {e}")
            return {
                "type": "tool_result",
                "tool": "search",
                "error": str(e),
            }

    async def _execute_stock_price(self, tool_call: dict) -> dict:
        """执行股票行情查询"""
        try:
            args = json.loads(tool_call["function"]["arguments"])
            symbol = args.get("symbol", "").upper()
            logger.info(f"Stock price: {symbol}")

            data = await finance_engine.get_stock_price(symbol)
            return {
                "type": "tool_result",
                "tool": "get_stock_price",
                "symbol": symbol,
                "data": data,
            }
        except Exception as e:
            logger.error(f"Stock price failed: {e}")
            return {
                "type": "tool_result",
                "tool": "get_stock_price",
                "error": str(e),
            }

    async def _execute_stock_financials(self, tool_call: dict) -> dict:
        """执行财务数据查询"""
        try:
            args = json.loads(tool_call["function"]["arguments"])
            symbol = args.get("symbol", "").upper()
            logger.info(f"Stock financials: {symbol}")

            data = await finance_engine.get_stock_financials(symbol)
            return {
                "type": "tool_result",
                "tool": "get_stock_financials",
                "symbol": symbol,
                "data": data,
            }
        except Exception as e:
            logger.error(f"Stock financials failed: {e}")
            return {
                "type": "tool_result",
                "tool": "get_stock_financials",
                "error": str(e),
            }

    async def _execute_stock_news(self, tool_call: dict) -> dict:
        """执行股票新闻查询"""
        try:
            args = json.loads(tool_call["function"]["arguments"])
            symbol = args.get("symbol", "").upper()
            logger.info(f"Stock news: {symbol}")

            data = await finance_engine.get_stock_news(symbol)
            return {
                "type": "tool_result",
                "tool": "get_stock_news",
                "symbol": symbol,
                "data": data,
            }
        except Exception as e:
            logger.error(f"Stock news failed: {e}")
            return {
                "type": "tool_result",
                "tool": "get_stock_news",
                "error": str(e),
            }

    async def finalize_conversation(
        self, conversation_id: str, messages: List[dict]
    ):
        """对话结束后处理：提取记忆、生成摘要"""
        try:
            await self.memory.finalize_conversation(conversation_id, messages)
        except Exception as e:
            logger.error(f"Failed to finalize conversation: {e}")
