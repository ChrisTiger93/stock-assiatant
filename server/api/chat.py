"""
WebSocket 对话端点 —— 流式对话 + DB 持久化 + 记忆
"""
import json
from uuid import uuid4, UUID
from sqlalchemy import text

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

import asyncio
import re

from config import settings
from orchestrator.agent import clean_tool_markup
from memory.extractor import generate_conversation_title
from tts.engine import tts_engine

router = APIRouter()


def _uid(s):
    """字符串转 UUID，容错"""
    try:
        return UUID(s)
    except Exception:
        return s


async def _try_get_db():
    """尝试获取 DB 会话，失败返回 None"""
    try:
        from api.deps import async_session_factory
        return async_session_factory()
    except Exception as e:
        logger.warning(f"DB unavailable: {e}")
        return None


async def _db_exec(db, sql, params=None) -> bool:
    """执行原始 SQL，返回是否成功"""
    try:
        await db.execute(text(sql), params or {})
        return True
    except Exception as e:
        logger.error(f"SQL error: {e} | {sql[:100]}")
        return False


@router.websocket("/ws/chat/{conversation_id}")
async def websocket_chat(websocket: WebSocket, conversation_id: str):
    await websocket.accept()

    api_key = websocket.query_params.get("api_key", "")
    if settings.api_key and api_key != settings.api_key:
        await websocket.send_json({"type": "error", "content": "Invalid API key"})
        await websocket.close()
        return

    db = await _try_get_db()
    db_ok = db is not None

    from orchestrator.agent import AIOrchestrator
    from memory.manager import MemoryManager

    try:
        if db_ok:
            memory_mgr = MemoryManager(db)
            orchestrator = AIOrchestrator(memory_mgr)
            await _run_chat(websocket, conversation_id, orchestrator, memory_mgr, db, True)
        else:
            memory_mgr = _LightMemory()
            orchestrator = AIOrchestrator(memory_mgr)
            await _run_chat(websocket, conversation_id, orchestrator, memory_mgr, None, False)
    finally:
        if db_ok:
            try: await db.close()
            except: pass


async def _run_chat(websocket, conv_id, orchestrator, memory_mgr, db, db_ok):
    uid = _uid(conv_id)
    history = []
    conv = None
    extract_count = 0

    # 验证并加载会话（只读，commit 关闭事务）
    if db_ok:
        r = await db.execute(text("SELECT id, title, message_count FROM conversations WHERE id = :id"), {"id": str(uid)})
        row = r.fetchone()
        if not row:
            await websocket.send_json({"type": "error", "content": f"Conversation {conv_id} not found"})
            await websocket.close()
            return
        conv = {"id": str(row[0]), "title": row[1], "message_count": row[2] or 0}

        r = await db.execute(
            text("SELECT role, content FROM messages WHERE conversation_id = :cid ORDER BY created_at"),
            {"cid": str(uid)})
        for row in r.fetchall():
            history.append({"role": row[0], "content": row[1]})
        await db.commit()  # 关闭只读事务

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)

            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if data.get("type") != "message":
                continue

            content = data.get("content", "").strip()
            if not content:
                continue

            input_type = data.get("input_type", "text")

            # 保存用户消息
            if db_ok:
                mid = str(uuid4())
                ok = await _db_exec(db,
                    "INSERT INTO messages (id, conversation_id, role, content, metadata) "
                    "VALUES (:id, :cid, 'user', :content, :meta)",
                    {"id": mid, "cid": str(uid), "content": content,
                     "meta": json.dumps({"input_type": input_type})})
                if ok and conv["title"] is None and len(history) == 0:
                    title = await generate_conversation_title(content)
                    await _db_exec(db, "UPDATE conversations SET title = :t WHERE id = :id",
                                   {"t": title, "id": str(uid)})
                    conv["title"] = title
                if ok:
                    await db.commit()

            history.append({"role": "user", "content": content})

            # 流式生成
            full = ""
            async for event in orchestrator.chat_stream(
                conversation_id=str(uid), user_message=content, history=history):
                if event["type"] == "done" and event.get("content"):
                    # 剥离 <voice> 标签再发给客户端，避免 UI 显示原始标签
                    clean_content, _ = _extract_voice(event["content"])
                    event = {**event, "content": clean_content}
                    if len(event["content"]) > len(full):
                        full = event["content"]
                await websocket.send_json(event)
                if event["type"] == "chunk":
                    full += event["content"]

            # 清理原始 tool_call 标记
            full = clean_tool_markup(full)

            # TTS：提取 <voice> 标签，只朗读精简摘要
            display_text, voice_text = _extract_voice(full)
            logger.info(f"TTS: full_length={len(full)}, "
                        f"voice_found={voice_text is not None}, "
                        f"voice_len={len(voice_text) if voice_text else 0}, "
                        f"full_tail_300={repr(full[-300:])}")

            if voice_text and tts_engine.enabled:
                voice_clean = _clean_for_voice(voice_text)
                logger.info(f"TTS: voice_clean len={len(voice_clean) if voice_clean else 0}")
                if voice_clean:
                    asyncio.create_task(_send_audio_task(websocket, voice_clean))
                    logger.info("TTS: audio task created")
                else:
                    logger.warning("TTS: voice_clean empty, skipping")
            elif not voice_text:
                logger.warning("TTS: no <voice> tag found in response")

            # 保存 AI 回复（用去除了 voice 标签的文本）
            if display_text and db_ok:
                ok = await _db_exec(db,
                    "INSERT INTO messages (id, conversation_id, role, content, metadata) "
                    "VALUES (:id, :cid, 'assistant', :content, '{}')",
                    {"id": str(uuid4()), "cid": str(uid), "content": display_text})
                if ok:
                    conv["message_count"] = conv["message_count"] + 1
                    await _db_exec(db, "UPDATE conversations SET message_count = :mc, updated_at = NOW() WHERE id = :id",
                                   {"mc": conv["message_count"], "id": str(uid)})
                    await db.commit()
                    extract_count += 2

            if display_text:
                history.append({"role": "assistant", "content": display_text})

            # 每10轮自动提取记忆
            if db_ok and extract_count >= 10:
                try:
                    await memory_mgr.finalize_conversation(str(uid), history)
                    extract_count = 0
                except Exception as e:
                    logger.warning(f"Extract failed: {e}")

    except WebSocketDisconnect:
        logger.info(f"Disconnected from {conv_id}")
        if db_ok and extract_count > 0:
            try: await memory_mgr.finalize_conversation(str(uid), history)
            except: pass
    except Exception as e:
        logger.error(f"WS error: {e}")
        try: await websocket.send_json({"type": "error", "content": str(e)})
        except: pass


# ----------------------------------------------------------------
# TTS 语音播报辅助
# ----------------------------------------------------------------

_VOICE_TAG_RE = re.compile(r'<voice>(.*?)</voice>', re.DOTALL)

_VOICE_CLEAN_RE = re.compile(
    r'\*\*|__|' r'`' r'|~~|#{1,6}\s*|'
    r'\[([^\]]*)\]\([^)]*\)|'
    r'!\[.*?\]\([^)]*\)|'
    r'<[^>]+>|'
    r'https?://\S+|'
    r'[⭐🌟✅❌🔥💡📊📈📉🔍🎯⚠️🚀💰📌👉]|'
    r'^\s*[-*+>]\s*'
)


def _extract_voice(text: str) -> tuple:
    """提取 <voice> 内容，返回 (去除标签后文本, voice内容或None)"""
    m = _VOICE_TAG_RE.search(text)
    if m:
        voice = m.group(1).strip()
        text = _VOICE_TAG_RE.sub("", text).strip()
        return text, voice
    return text, None


def _clean_for_voice(text: str, max_len: int = 300) -> str:
    """清理文本使其适合语音播报"""
    cleaned = _VOICE_CLEAN_RE.sub("", text)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = re.sub(r'[（(][^)）]*[)）]', '', cleaned)
    if len(cleaned) > max_len:
        cutoff = cleaned.rfind('。', 0, max_len)
        if cutoff > max_len // 2:
            cleaned = cleaned[:cutoff + 1]
        else:
            cleaned = cleaned[:max_len]
    return cleaned.strip()


async def _send_audio_task(websocket, text: str):
    """后台任务：合成一段文本并推送音频"""
    logger.info(f"TTS task: start synthesize, text_len={len(text)}")
    audio_b64 = await tts_engine.synthesize_to_base64(text)
    if audio_b64:
        b64_len = len(audio_b64)
        # 估算 PCM 时长 (16-bit mono: bytes / 2 / sample_rate)
        pcm_bytes = len(audio_b64) * 3 // 4  # base64 解码后约为 3/4
        duration_ms = pcm_bytes * 1000 // 2 // settings.tts_sample_rate
        logger.info(f"TTS task: synthesized ok, b64_len={b64_len}, sr={settings.tts_sample_rate}, est_duration={duration_ms}ms")
        try:
            ws_state = websocket.client_state.name if hasattr(websocket, 'client_state') else 'unknown'
            logger.info(f"TTS task: sending audio_chunk, ws_state={ws_state}")
            await websocket.send_json({
                "type": "audio_chunk",
                "content": audio_b64,
                "sample_rate": settings.tts_sample_rate,
            })
            logger.info(f"TTS task: audio_chunk sent successfully")
        except Exception as e:
            logger.warning(f"TTS task: send failed ({type(e).__name__}: {e})")
    else:
        logger.warning(f"TTS task: synthesize returned None")


# ----------------------------------------------------------------
# 无 DB 轻量记忆
# ----------------------------------------------------------------

class _LightMemory:
    """无 DB 轻量记忆"""
    async def retrieve(self, q):
        from memory.store import vector_store
        results = await vector_store.query_multi(q, n_results_per_collection=3)
        mems = []
        for cn, cr in results.items():
            if cr.get("documents") and cr["documents"][0]:
                for doc, dist in zip(cr["documents"][0], cr["distances"][0]):
                    sim = 1.0 - (dist / 2.0) if dist else 1.0
                    mems.append({"content": doc, "collection": cn, "similarity": round(sim,4), "score": round(sim,4), "tags": []})
        mems.sort(key=lambda m: m["score"], reverse=True)
        return mems

    async def build_context_for_prompt(self, q, max_tokens=1500):
        mems = await self.retrieve(q)
        if not mems: return ""
        lb = {"memories": "长期记忆", "conversation_chunks": "近期对话", "knowledge_snippets": "知识库"}
        lines = ["## 相关记忆"]
        for m in mems[:8]:
            lines.append(f"- [{lb.get(m['collection'],m['collection'])}] {m['content']} (相关度:{m['similarity']})")
        return "\n".join(lines)

    async def add_conversation_chunk(self, cid, text, idx):
        from memory.store import vector_store
        try: await vector_store.add(collection="conversation_chunks", documents=[text], metadatas=[{"conversation_id":cid,"chunk_index":idx}], ids=[f"chunk_{cid}_{idx}"])
        except: pass

    async def add_knowledge_snippet(self, content, url="", query=""):
        from memory.store import vector_store
        import uuid
        try: await vector_store.add(collection="knowledge_snippets", documents=[content], metadatas=[{"url":url,"source":"search","search_query":query}], ids=[f"snippet_{uuid.uuid4().hex[:12]}"])
        except: pass

    async def finalize_conversation(self, *a, **kw): pass
