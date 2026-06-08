package com.tigerbase.aiassistant.ui.settings

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.tigerbase.aiassistant.AiAssistantApp
import com.tigerbase.aiassistant.data.PreferencesManager
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class SettingsUiState(
    val serverUrl: String = PreferencesManager.DEFAULT_SERVER_URL,
    val apiKey: String = PreferencesManager.DEFAULT_API_KEY,
    val ttsEnabled: Boolean = PreferencesManager.DEFAULT_TTS_ENABLED,
    val isConnecting: Boolean = false,
    val connectionStatus: String = "",  // "" = untested, "ok" = connected, "fail" = failed
)

class SettingsViewModel(application: Application) : AndroidViewModel(application) {

    private val app = application as AiAssistantApp

    private val _uiState = MutableStateFlow(SettingsUiState())
    val uiState: StateFlow<SettingsUiState> = _uiState.asStateFlow()

    init {
        viewModelScope.launch {
            app.prefs.serverUrl.collect { url ->
                _uiState.value = _uiState.value.copy(serverUrl = url)
            }
        }
        viewModelScope.launch {
            app.prefs.apiKey.collect { key ->
                _uiState.value = _uiState.value.copy(apiKey = key)
            }
        }
        viewModelScope.launch {
            app.prefs.ttsEnabled.collect { enabled ->
                _uiState.value = _uiState.value.copy(ttsEnabled = enabled)
            }
        }
    }

    fun onServerUrlChange(url: String) {
        _uiState.value = _uiState.value.copy(serverUrl = url, connectionStatus = "")
    }

    fun onApiKeyChange(key: String) {
        _uiState.value = _uiState.value.copy(apiKey = key, connectionStatus = "")
    }

    fun onTtsToggle(enabled: Boolean) {
        _uiState.value = _uiState.value.copy(ttsEnabled = enabled)
        viewModelScope.launch {
            app.prefs.setTtsEnabled(enabled)
        }
    }

    fun saveAndTest() {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isConnecting = true, connectionStatus = "")

            val url = _uiState.value.serverUrl.trimEnd('/')
            val key = _uiState.value.apiKey.trim()

            app.prefs.setServerUrl(url)
            app.prefs.setApiKey(key)

            try {
                val api = app.buildApi(url)
                val health = api.health()
                _uiState.value = _uiState.value.copy(
                    isConnecting = false,
                    connectionStatus = if (health.status == "ok") "ok" else "fail",
                )
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(
                    isConnecting = false,
                    connectionStatus = "fail",
                )
            }
        }
    }
}
