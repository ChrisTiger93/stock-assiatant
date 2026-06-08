package com.tigerbase.aiassistant.network

import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import com.tigerbase.aiassistant.network.models.WsEvent
import com.tigerbase.aiassistant.network.models.WsMessage
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import okhttp3.*
import kotlin.math.min
import kotlin.math.pow

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

    private var conversationId: String = ""
    private var reconnectAttempt = 0
    private var shouldReconnect = false
    @Volatile private var isConnected = false

    fun connect(conversationId: String) {
        this.conversationId = conversationId
        shouldReconnect = true
        reconnectAttempt = 0
        doConnect()
    }

    private fun doConnect() {
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
            override fun onOpen(webSocket: WebSocket, response: Response) {
                isConnected = true
                reconnectAttempt = 0
                _events.trySend(WsEvent(type = "ws_connected"))
            }

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
                isConnected = false
                _events.trySend(WsEvent(type = "error", content = t.message ?: "WebSocket connection failed"))
                scheduleReconnect()
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                isConnected = false
                // 非正常关闭（非客户端主动断开）则重连
                if (code != 1000 && shouldReconnect) {
                    scheduleReconnect()
                } else if (!shouldReconnect) {
                    _events.trySend(WsEvent(type = "closed"))
                }
            }
        })
    }

    private fun scheduleReconnect() {
        if (!shouldReconnect) return
        val delayMs = (min(2.0.pow(reconnectAttempt.toDouble()), 32.0) * 1000).toLong()
        reconnectAttempt++
        Thread {
            try {
                _events.trySend(WsEvent(type = "ws_reconnecting", content = "${delayMs / 1000}s"))
                Thread.sleep(delayMs)
                doConnect()
            } catch (_: InterruptedException) {
            }
        }.start()
    }

    fun sendMessage(content: String, inputType: String = "text") {
        val msg = WsMessage(content = content, inputType = inputType)
        webSocket?.send(wsMessageAdapter.toJson(msg))
    }

    fun disconnect() {
        shouldReconnect = false
        webSocket?.close(1000, "Client closing")
        webSocket = null
    }
}
