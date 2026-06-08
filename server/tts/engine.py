"""
TTS 引擎 —— DashScope CosyVoice 语音合成
使用 dashscope SDK（底层 WebSocket），asyncio 线程池执行避免阻塞事件循环
"""
import asyncio
import base64
import os
from concurrent.futures import ThreadPoolExecutor

from loguru import logger
from config import settings


class TTSEngine:
    """CosyVoice TTS，线程池执行同步 SDK 调用"""

    # sample_rate → AudioFormat 映射
    _SAMPLE_RATE_MAP = {
        8000: "PCM_8000HZ_MONO_16BIT",
        16000: "PCM_16000HZ_MONO_16BIT",
        22050: "PCM_22050HZ_MONO_16BIT",
        24000: "PCM_24000HZ_MONO_16BIT",
        44100: "PCM_44100HZ_MONO_16BIT",
        48000: "PCM_48000HZ_MONO_16BIT",
    }

    def __init__(self):
        self.api_key = settings.dashscope_api_key
        self.model = settings.tts_model
        self.voice = settings.tts_voice
        self.sample_rate = settings.tts_sample_rate
        self._enabled = bool(self.api_key)
        self._executor = ThreadPoolExecutor(max_workers=2)

        if self._enabled:
            os.environ.setdefault("DASHSCOPE_API_KEY", self.api_key)
            from dashscope.audio.tts_v2 import AudioFormat
            fmt_name = self._SAMPLE_RATE_MAP.get(self.sample_rate, "PCM_24000HZ_MONO_16BIT")
            self._audio_format = getattr(AudioFormat, fmt_name, AudioFormat.PCM_24000HZ_MONO_16BIT)
            logger.info(f"TTS engine ready: model={self.model}, voice={self.voice}, format={fmt_name}")

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def synthesize(self, text: str) -> bytes | None:
        """
        合成一段文本为 PCM 音频

        Returns:
            PCM 16-bit mono bytes, or None on failure
        """
        if not self._enabled or not text.strip():
            return None

        loop = asyncio.get_running_loop()
        try:
            audio = await loop.run_in_executor(
                self._executor,
                self._synthesize_sync,
                text,
            )
            return audio
        except Exception as e:
            logger.warning(f"TTS error: {e}")
            return None

    def _synthesize_sync(self, text: str) -> bytes | None:
        """同步合成（在线程池中执行）"""
        from dashscope.audio.tts_v2 import SpeechSynthesizer

        synthesizer = SpeechSynthesizer(
            model=self.model,
            voice=self.voice,
            format=self._audio_format,
        )

        audio = synthesizer.call(text)
        if audio:
            return audio
        return None

    async def synthesize_to_base64(self, text: str) -> str | None:
        """合成并返回 base64 编码的 PCM 数据"""
        pcm = await self.synthesize(text)
        if pcm:
            return base64.b64encode(pcm).decode("ascii")
        return None


# 单例
tts_engine = TTSEngine()
