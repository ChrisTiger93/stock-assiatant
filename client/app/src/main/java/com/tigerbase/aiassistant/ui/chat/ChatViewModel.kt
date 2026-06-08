package com.tigerbase.aiassistant.ui.chat

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.tigerbase.aiassistant.AiAssistantApp
import com.tigerbase.aiassistant.network.WebSocketClient
import com.tigerbase.aiassistant.network.models.MessageResponse
import com.tigerbase.aiassistant.network.models.WsEvent
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

data class ChatMessage(
    val id: String = "",
    val role: String,       // "user" | "assistant" | "system"
    val content: String,
    val isStreaming: Boolean = false,
)

data class ChatUiState(
    val title: String = "加载中...",
    val messages: List<ChatMessage> = emptyList(),
    val isConnected: Boolean = false,
    val isGenerating: Boolean = false,
    val ttsEnabled: Boolean = true,
    val error: String? = null,
)

class ChatViewModel(application: Application) : AndroidViewModel(application) {

    private val app = application as AiAssistantApp

    private val _uiState = MutableStateFlow(ChatUiState())
    val uiState: StateFlow<ChatUiState> = _uiState.asStateFlow()

    private var wsClient: WebSocketClient? = null
    private var wsJob: Job? = null
    private var streamingMessageId = ""
    val audioPlayer = AudioPlayer()

    init {
        // 监听 TTS 设置，自动应用静音状态并更新 UI
        viewModelScope.launch {
            app.prefs.ttsEnabled.collect { enabled ->
                audioPlayer.setMuted(!enabled)
                _uiState.value = _uiState.value.copy(ttsEnabled = enabled)
            }
        }
    }

    fun loadConversation(conversationId: String) {
        viewModelScope.launch {
            try {
                val conv = app.api.getConversation(conversationId)
                _uiState.value = _uiState.value.copy(title = conv.title ?: "新对话")

                val msgs = app.api.listMessages(conversationId)
                _uiState.value = _uiState.value.copy(
                    messages = msgs.map { it.toChatMessage() },
                )
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(error = e.message)
            }
        }
    }

    fun connectWebSocket(conversationId: String) {
        viewModelScope.launch {
            val url = app.prefs.serverUrl.first()
            val key = app.prefs.apiKey.first()

            wsClient = WebSocketClient(url, key)
            wsClient?.connect(conversationId)

            wsJob = launch {
                wsClient?.events?.collect { event ->
                    handleEvent(event)
                }
            }

            _uiState.value = _uiState.value.copy(isConnected = true)
        }
    }

    fun sendMessage(content: String) {
        if (content.isBlank()) return

        val userMsg = ChatMessage(
            id = "user_${System.currentTimeMillis()}",
            role = "user",
            content = content,
        )

        streamingMessageId = "assistant_${System.currentTimeMillis()}"
        val placeholderMsg = ChatMessage(
            id = streamingMessageId,
            role = "assistant",
            content = "",
            isStreaming = true,
        )

        _uiState.value = _uiState.value.copy(
            messages = _uiState.value.messages + userMsg + placeholderMsg,
            isGenerating = true,
        )

        wsClient?.sendMessage(content)
    }

    private fun handleEvent(event: WsEvent) {
        when (event.type) {
            "chunk" -> {
                val content = event.content ?: ""
                _uiState.value = _uiState.value.copy(
                    messages = _uiState.value.messages.map { msg ->
                        if (msg.id == streamingMessageId) {
                            msg.copy(content = msg.content + content)
                        } else msg
                    },
                )
            }

            "done" -> {
                val finalContent = event.content ?: ""
                _uiState.value = _uiState.value.copy(
                    messages = _uiState.value.messages.map { msg ->
                        if (msg.id == streamingMessageId) {
                            msg.copy(content = finalContent, isStreaming = false)
                        } else msg
                    },
                    isGenerating = false,
                )
            }

            "error" -> {
                _uiState.value = _uiState.value.copy(
                    error = event.content ?: "未知错误",
                    isGenerating = false,
                )
            }

            "tool_result" -> {
                // 搜索工具结果，静默处理 —— 在 stream 中可以后续展示
                val toolNote = ChatMessage(
                    id = "tool_${System.currentTimeMillis()}",
                    role = "system",
                    content = "🔍 搜索中... (${event.data?.size ?: 0} 个结果)",
                )
                _uiState.value = _uiState.value.copy(
                    messages = _uiState.value.messages + toolNote,
                )
            }

            "audio_chunk" -> {
                val b64 = event.content ?: ""
                val sr = event.sampleRate
                if (b64.isNotBlank()) {
                    audioPlayer.playChunk(b64, sr)
                }
            }

            "closed" -> {
                _uiState.value = _uiState.value.copy(isConnected = false)
            }
        }
    }

    fun toggleTts() {
        viewModelScope.launch {
            val current = app.prefs.ttsEnabled.first()
            app.prefs.setTtsEnabled(!current)
        }
    }

    override fun onCleared() {
        super.onCleared()
        wsJob?.cancel()
        wsClient?.disconnect()
        audioPlayer.release()
    }
}

private fun MessageResponse.toChatMessage() = ChatMessage(
    id = id,
    role = role,
    content = content,
)
