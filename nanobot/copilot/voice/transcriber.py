"""Voice transcription with local faster-whisper and Groq API fallback."""

from pathlib import Path

from loguru import logger


class VoiceTranscriber:
    """Transcribes audio files using faster-whisper (local) or Groq API.

    Falls back gracefully: local → Groq → error message.
    """

    def __init__(self, groq_api_key: str | None = None):
        self._groq_key = groq_api_key
        self._local_model = None

        # Try to load faster-whisper at init time
        try:
            from faster_whisper import WhisperModel  # noqa: F401
            self._local_available = True
        except ImportError:
            self._local_available = False

    async def transcribe(self, audio_path: Path) -> str:
        """Transcribe an audio file.

        Returns transcribed text, or an error message on failure.
        """
        if not audio_path.exists():
            logger.warning(f"Audio file not found: {audio_path}")
            return "[Voice message: file not found]"

        # Try local faster-whisper
        if self._local_available:
            try:
                text = self._transcribe_local(audio_path)
                if text:
                    logger.info(f"Transcribed locally: {text[:60]}...")
                    return text
            except Exception as e:
                logger.debug(f"Local transcription failed: {e}")

        # Try Groq API (reuses nanobot's existing provider)
        if self._groq_key:
            try:
                from nanobot.providers.transcription import GroqTranscriptionProvider
                provider = GroqTranscriptionProvider(api_key=self._groq_key)
                text = await provider.transcribe(audio_path)
                if text:
                    logger.info(f"Transcribed via Groq: {text[:60]}...")
                    return text
            except Exception as e:
                logger.debug(f"Groq transcription failed: {e}")

        return "[Voice message could not be transcribed]"

    def _transcribe_local(self, audio_path: Path) -> str:
        """Transcribe using faster-whisper on CPU."""
        from faster_whisper import WhisperModel

        if self._local_model is None:
            self._local_model = WhisperModel(
                "base", device="cpu", compute_type="int8"
            )

        segments, _info = self._local_model.transcribe(str(audio_path))
        return " ".join(s.text.strip() for s in segments)
