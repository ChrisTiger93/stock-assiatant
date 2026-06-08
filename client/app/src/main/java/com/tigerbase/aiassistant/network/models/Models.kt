package com.tigerbase.aiassistant.network.models

import com.squareup.moshi.Json

// ==================== 会话 ====================

data class ConversationResponse(
    val id: String,
    val title: String?,
    val summary: String?,
    val tags: List<String>,
    @Json(name = "message_count") val messageCount: Int,
    @Json(name = "created_at") val createdAt: String?,
    @Json(name = "updated_at") val updatedAt: String?,
)

data class ConversationCreate(
    val title: String? = null,
)

// ==================== 消息 ====================

data class MessageResponse(
    val id: String,
    val role: String,
    val content: String,
    val metadata: Map<String, Any>?,
    @Json(name = "created_at") val createdAt: String?,
)

// ==================== 记忆 ====================

data class MemoryResponse(
    val id: String,
    val title: String?,
    val tags: List<String>,
    val importance: Double,
    @Json(name = "access_count") val accessCount: Int,
    @Json(name = "source_type") val sourceType: String,
    @Json(name = "created_at") val createdAt: String?,
)

data class ManualMemory(
    val content: String,
    val tags: List<String> = emptyList(),
    val importance: Double = 0.7,
)

data class MemoryCreated(
    val id: String,
    val status: String,
)

// ==================== 健康检查 ====================

data class HealthResponse(
    val status: String,
    val version: String,
    @Json(name = "db_available") val dbAvailable: Boolean,
    @Json(name = "vector_available") val vectorAvailable: Boolean,
)

// ==================== 通用 ====================

data class StatusResponse(
    val status: String,
)

// ==================== WebSocket ====================

data class WsEvent(
    val type: String,        // chunk | done | error | tool_result | pong | audio_chunk
    val content: String? = null,
    val tool: String? = null,
    val query: String? = null,
    val data: List<SearchResult>? = null,
    val error: String? = null,
    @Json(name = "sample_rate") val sampleRate: Int = 24000,
)

data class SearchResult(
    val title: String,
    val url: String,
    val snippet: String,
)

data class WsMessage(
    val type: String = "message",
    val content: String,
    @Json(name = "input_type") val inputType: String = "text",
)
