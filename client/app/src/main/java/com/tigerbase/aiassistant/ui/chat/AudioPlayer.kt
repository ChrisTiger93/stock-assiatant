package com.tigerbase.aiassistant.ui.chat

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.util.Base64
import android.util.Log
import java.util.concurrent.Executors
import java.util.concurrent.RejectedExecutionException

/**
 * 流式 PCM 音频播放器
 * 使用 AudioTrack MODE_STREAM，边收数据边播放
 */
class AudioPlayer {

    private var track: AudioTrack? = null
    private var currentSampleRate: Int = 24000
    @Volatile private var isMuted: Boolean = false
    private var executor = Executors.newSingleThreadExecutor()

    companion object {
        private const val TAG = "AudioPlayer"
        private const val CHANNEL = AudioFormat.CHANNEL_OUT_MONO
        private const val ENCODING = AudioFormat.ENCODING_PCM_16BIT
    }

    fun setMuted(muted: Boolean) {
        if (isMuted == muted) return
        isMuted = muted
        if (muted) {
            executor.shutdownNow()
            releaseTrack()
            executor = Executors.newSingleThreadExecutor()
        }
    }

    /**
     * 播放一段 base64 编码的 PCM 音频数据
     */
    fun playChunk(base64Data: String, sampleRate: Int = 24000) {
        if (isMuted) return

        try {
            executor.execute {
                if (isMuted) return@execute
                try {
                    val pcm = Base64.decode(base64Data, Base64.DEFAULT)
                    playPcm(pcm, sampleRate)
                } catch (e: Exception) {
                    Log.w(TAG, "decode/play failed: ${e.message}", e)
                }
            }
        } catch (_: RejectedExecutionException) {
            // executor 正在重建中，丢弃
        }
    }

    private fun playPcm(pcm: ByteArray, sampleRate: Int) {
        if (isMuted) return

        try {
            if (track == null || track?.state != AudioTrack.STATE_INITIALIZED || sampleRate != currentSampleRate) {
                releaseTrack()
                currentSampleRate = sampleRate

                val minBufferSize = AudioTrack.getMinBufferSize(sampleRate, CHANNEL, ENCODING)
                val bufSize = (minBufferSize * 4).coerceAtMost(65536)

                track = AudioTrack.Builder()
                    .setAudioAttributes(
                        AudioAttributes.Builder()
                            .setUsage(AudioAttributes.USAGE_MEDIA)
                            .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                            .build()
                    )
                    .setAudioFormat(
                        AudioFormat.Builder()
                            .setEncoding(ENCODING)
                            .setSampleRate(sampleRate)
                            .setChannelMask(CHANNEL)
                            .build()
                    )
                    .setBufferSizeInBytes(bufSize)
                    .setTransferMode(AudioTrack.MODE_STREAM)
                    .build()

                if (track?.state != AudioTrack.STATE_INITIALIZED) {
                    Log.w(TAG, "AudioTrack init failed")
                    releaseTrack()
                    return
                }
                track?.play()
            }

            val t = track ?: return
            if (t.playState != AudioTrack.PLAYSTATE_PLAYING) {
                t.play()
            }
            t.write(pcm, 0, pcm.size)
        } catch (e: Exception) {
            Log.e(TAG, "playPcm error: ${e.message}", e)
            releaseTrack()
        }
    }

    fun release() {
        executor.shutdownNow()
        releaseTrack()
    }

    private fun releaseTrack() {
        try {
            track?.stop()
            track?.release()
        } catch (_: Exception) {}
        track = null
    }
}
