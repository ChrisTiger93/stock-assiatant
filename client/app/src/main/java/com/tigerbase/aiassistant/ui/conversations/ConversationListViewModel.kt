package com.tigerbase.aiassistant.ui.conversations

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.tigerbase.aiassistant.AiAssistantApp
import com.tigerbase.aiassistant.network.models.ConversationResponse
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class ConversationListUiState(
    val conversations: List<ConversationResponse> = emptyList(),
    val isLoading: Boolean = false,
    val error: String? = null,
)

class ConversationListViewModel(application: Application) : AndroidViewModel(application) {

    private val app = application as AiAssistantApp

    private val _uiState = MutableStateFlow(ConversationListUiState())
    val uiState: StateFlow<ConversationListUiState> = _uiState.asStateFlow()

    init {
        loadConversations()
    }

    fun loadConversations() {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, error = null)
            try {
                val list = app.api.listConversations()
                _uiState.value = _uiState.value.copy(conversations = list, isLoading = false)
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    error = e.message ?: "加载失败",
                )
            }
        }
    }

    fun createConversation(onCreated: (String) -> Unit) {
        viewModelScope.launch {
            try {
                val conv = app.api.createConversation()
                _uiState.value = _uiState.value.copy(
                    conversations = listOf(conv) + _uiState.value.conversations,
                )
                onCreated(conv.id)
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(error = e.message ?: "创建失败")
            }
        }
    }

    fun deleteConversation(id: String) {
        viewModelScope.launch {
            try {
                app.api.deleteConversation(id)
                _uiState.value = _uiState.value.copy(
                    conversations = _uiState.value.conversations.filter { it.id != id },
                )
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(error = e.message ?: "删除失败")
            }
        }
    }
}
