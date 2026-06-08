package com.tigerbase.aiassistant.network

import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import com.tigerbase.aiassistant.network.models.WsEvent
import com.tigerbase.aiassistant.network.models.WsMessage
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import okhttp3.*

class WebSocketClient(
    private val baseUrl: String,
    private val apiKey: String,
) {
    private val client = OkHttpClient.Builder()
        .pingInterval(30, java.util.concurrent.TimeUnit.SECONDS)
        .build()

    private val moshi = Moshi.Builder()
        .addLast(KotlinJsonAdapterFactory())
        .build()
    private val wsMessageAdapter = moshi.adapter(WsMessage::class.java)
    private val wsEventAdapter = moshi.adapter(WsEvent::class.java)

    private var webSocket: WebSocket? = null
    private val _events = Channel<WsEvent>(Channel.BUFFERED)
    val events: Flow<WsEvent> = _events.receiveAsFlow()

    fun connect(conversationId: String) {
        val wsUrl = buildString {
            append(baseUrl.replace("http://", "ws://").replace("https://", "wss://"))
            append("/ws/chat/")
            append(conversationId)
            append("?api_key=")
            append(apiKey)
        }

        val request = Request.Builder()
            .url(wsUrl)
            .build()

        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val event = wsEventAdapter.fromJson(text)
                    if (event != null) {
                        _events.trySend(event)
                    }
                } catch (_: Exception) {
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                _events.trySend(WsEvent(type = "error", content = t.message ?: "WebSocket connection failed"))
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                _events.trySend(WsEvent(type = "closed"))
            }
        })
    }

    fun sendMessage(content: String, inputType: String = "text") {
        val msg = WsMessage(content = content, inputType = inputType)
        webSocket?.send(wsMessageAdapter.toJson(msg))
    }

    fun sendPing() {
        webSocket?.send("""{"type":"ping"}""")
    }

    fun disconnect() {
        webSocket?.close(1000, "Client closing")
        webSocket = null
    }
}
