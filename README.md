# TigerBase AI Assistant

<p align="center">
  <strong>🤖 多模态 AI 助理 — 记忆 · 搜索 · 金融 · 语音</strong>
</p>

一个完整的 AI 助理系统，包含多轮对话、三层语义记忆、网络搜索、美股分析、TTS 语音播报。服务端基于 FastAPI + WebSocket，客户端为 Android (Jetpack Compose)。

## 特性

- 💬 **多轮对话** — 基于 DeepSeek 大模型，支持工具调用（搜索、股票行情/财务/新闻）
- 🧠 **三层记忆** — 工作记忆 (Redis) + 短期 (ChromaDB) + 长期 (自动提取偏好/事实)
- 🔍 **网络搜索** — 集成 SearXNG，实时获取最新信息
- 📈 **美股分析** — 实时行情、财务指标、新闻与分析评级 (Finnhub)
- 🔊 **TTS 语音** — 阿里云 CosyVoice 语音合成，回复末尾口语化摘要自动播报
- 📱 **Android 客户端** — Jetpack Compose 原生界面，WebSocket 流式对话

## 架构

```
┌─────────────────────┐      ┌──────────────────────────────────┐
│   Android Client    │      │         FastAPI Server            │
│   (Jetpack Compose) │◄────►│                                  │
│                     │ WS   │  ┌──────────┐  ┌──────────────┐  │
│  • ChatScreen       │      │  │Orchestrator│  │   Memory     │  │
│  • AudioPlayer      │      │  │ (DeepSeek)│  │ (ChromaDB)   │  │
│  • TTS 语音播报      │      │  └──────────┘  └──────────────┘  │
└─────────────────────┘      │  ┌──────────┐  ┌──────────────┐  │
                             │  │  Search   │  │   Finance    │  │
                             │  │ (SearXNG) │  │  (Finnhub)   │  │
                             │  └──────────┘  └──────────────┘  │
                             │  ┌──────────┐  ┌──────────────┐  │
                             │  │    TTS    │  │  PostgreSQL  │  │
                             │  │(CosyVoice)│  │   + Redis    │  │
                             │  └──────────┘  └──────────────┘  │
                             └──────────────────────────────────┘
```

## 快速开始

### 1. 配置

```bash
cd docker
cp .env.example .env
# 编辑 .env，填入 API Key：
#   DEEPSEEK_API_KEY    — DeepSeek 对话模型
#   DASHSCOPE_API_KEY   — 阿里云 DashScope（嵌入 + TTS）
#   FINNHUB_API_KEY     — 美股数据（可选）
#   API_KEY             — 服务端鉴权（Android 客户端用）
```

### 2. 启动服务

```bash
# Docker Compose（推荐）
cd docker
docker compose up -d

# 本地开发
cd server
pip install -r requirements.txt
python main.py
```

### 3. 验证

```bash
# 健康检查
curl http://localhost:8000/api/health

# 创建会话
curl -X POST http://localhost:8000/api/conversations \
  -H "X-API-Key: your-service-api-key"

# WebSocket 对话
websocat ws://localhost:8000/ws/chat/{conversation_id}?api_key=your-service-api-key
```

### 4. Android 客户端

用 Android Studio 打开 `client/` 目录，修改 `PreferencesManager.kt` 中的 `DEFAULT_SERVER_URL` 指向你的服务器地址，构建安装即可。

## API 概览

| 端点 | 说明 |
|------|------|
| `GET /api/health` | 健康检查 |
| `POST /api/conversations` | 创建新会话 |
| `GET /api/conversations` | 会话列表 |
| `GET /api/conversations/{id}` | 会话详情 |
| `GET /api/conversations/{id}/messages` | 消息列表 |
| `DELETE /api/conversations/{id}` | 删除会话 |
| `WS /ws/chat/{id}?api_key=xxx` | WebSocket 流式对话 |
| `GET /api/memories` | 记忆列表 |
| `POST /api/memories` | 手动添加记忆 |
| `DELETE /api/memories/{id}` | 删除记忆 |

### WebSocket 事件

| 事件 | 说明 |
|------|------|
| `chunk` | 流式文本片段 |
| `tool_result` | 工具调用结果（搜索/股票） |
| `audio_chunk` | TTS 语音 (base64 PCM 16-bit) |
| `done` | 本轮对话完成 |
| `error` | 错误信息 |

## 记忆系统

三层记忆模型：

| 层级 | 存储 | 说明 |
|------|------|------|
| 工作记忆 | Redis + 内存 | 当前会话上下文 |
| 短期记忆 | ChromaDB `conversation_chunks` | 近期对话片段，语义检索 |
| 长期记忆 | ChromaDB `memories` | LLM 自动提取的知识/偏好/事实 |

流程：消息实时向量化 → 对话结束自动提取事实 → 新对话注入相关记忆

## 目录结构

```
├── server/                  # 服务端 (Python/FastAPI)
│   ├── main.py              # 应用入口
│   ├── config.py            # 配置管理 (.env)
│   ├── api/                 # HTTP + WebSocket 端点
│   ├── orchestrator/        # AI 编排 (对话/工具调用)
│   ├── memory/              # 记忆管理 (ChromaDB)
│   ├── search/              # 搜索引擎 (SearXNG)
│   ├── finance/             # 金融数据 (Finnhub)
│   ├── tts/                 # 语音合成 (CosyVoice)
│   └── models/              # 数据模型
├── client/                  # Android 客户端 (Kotlin)
│   └── app/src/main/java/com/tigerbase/aiassistant/
│       ├── network/         # WebSocket + HTTP
│       ├── ui/chat/         # 对话界面 + AudioPlayer
│       ├── ui/settings/     # 设置
│       ├── ui/conversations/# 会话列表
│       └── data/            # 数据持久化
├── docker/                  # Docker Compose 部署
│   ├── docker-compose.yml
│   ├── nginx.conf
│   └── .env.example
└── data/                    # 持久化数据 (gitignored)
```

## License

MIT
