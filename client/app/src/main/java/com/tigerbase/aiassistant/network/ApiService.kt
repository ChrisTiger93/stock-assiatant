package com.tigerbase.aiassistant.network

import com.tigerbase.aiassistant.network.models.*
import retrofit2.http.*

interface ApiService {

    // ==================== 健康检查 ====================

    @GET("/api/health")
    suspend fun health(): HealthResponse

    // ==================== 会话 ====================

    @POST("/api/conversations")
    suspend fun createConversation(
        @Body body: ConversationCreate = ConversationCreate(),
    ): ConversationResponse

    @GET("/api/conversations")
    suspend fun listConversations(
        @Query("limit") limit: Int = 20,
        @Query("offset") offset: Int = 0,
    ): List<ConversationResponse>

    @GET("/api/conversations/{id}")
    suspend fun getConversation(
        @Path("id") conversationId: String,
    ): ConversationResponse

    @DELETE("/api/conversations/{id}")
    suspend fun deleteConversation(
        @Path("id") conversationId: String,
    ): StatusResponse

    @GET("/api/conversations/{id}/messages")
    suspend fun listMessages(
        @Path("id") conversationId: String,
        @Query("limit") limit: Int = 100,
    ): List<MessageResponse>

    // ==================== 记忆 ====================

    @GET("/api/memories")
    suspend fun listMemories(
        @Query("collection") collection: String = "memories",
        @Query("limit") limit: Int = 50,
    ): List<MemoryResponse>

    @POST("/api/memories")
    suspend fun addMemory(
        @Body body: ManualMemory,
    ): MemoryCreated

    @DELETE("/api/memories/{id}")
    suspend fun deleteMemory(
        @Path("id") memoryId: String,
        @Query("collection") collection: String = "memories",
    ): StatusResponse
}
