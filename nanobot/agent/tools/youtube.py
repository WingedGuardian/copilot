"""YouTube transcript extraction tool.

Primary: TranscriptAPI (transcriptapi.com) — fast, reliable, handles auto-captions.
Fallback: yt-dlp --write-auto-sub — free, local, already installed.
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.tools.base import Tool


def _extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$",  # bare ID
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


class YouTubeTranscriptTool(Tool):
    """Extract transcript/captions from a YouTube video."""

    @property
    def name(self) -> str:
        return "youtube_transcript"

    @property
    def description(self) -> str:
        return (
            "Extract the transcript from a YouTube video. "
            "Tries captions/subtitles first, then downloads audio and transcribes via Whisper. "
            "Supports full URLs, shortened URLs (youtu.be, search.app), and bare video IDs."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "YouTube URL or video ID",
                },
                "format": {
                    "type": "string",
                    "enum": ["text", "json"],
                    "description": "Output format: 'text' for plain transcript, 'json' for timestamped segments",
                },
            },
            "required": ["url"],
        }

    async def execute(self, url: str, format: str = "text", **kwargs: Any) -> str:
        # Resolve shortened URLs (search.app, youtu.be redirects)
        resolved_url = await self._resolve_url(url)

        video_id = _extract_video_id(resolved_url)
        if not video_id:
            return f"Error: Could not extract YouTube video ID from '{url}'"

        # Try TranscriptAPI first (if key configured)
        api_key = self._load_api_key()
        if api_key:
            try:
                result = await self._fetch_transcript_api(video_id, api_key, format)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"TranscriptAPI failed, falling back to yt-dlp: {e}")

        # Fallback: yt-dlp subtitle extraction
        subtitle_err = ""
        try:
            return await self._fetch_ytdlp(video_id, format)
        except Exception as e:
            subtitle_err = str(e)
            logger.warning(f"Subtitle extraction failed: {e}")

        # Last resort: download audio and transcribe via Groq/OpenAI
        try:
            return await self._fetch_audio_transcription(video_id)
        except Exception as e:
            return (
                f"Error: All transcript methods failed for video {video_id}.\n"
                f"Subtitles: {subtitle_err}\n"
                f"Audio transcription: {e}"
            )

    async def _resolve_url(self, url: str) -> str:
        """Follow redirects to resolve shortened URLs."""
        if not url.startswith("http"):
            return url  # Bare video ID, no resolution needed
        try:
            import httpx
            async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
                resp = await client.head(url)
                return str(resp.url)
        except Exception:
            return url  # Use original if resolution fails

    @staticmethod
    def _load_api_key() -> str:
        """Load TranscriptAPI key from secrets.json."""
        secrets_path = Path.home() / ".nanobot" / "secrets.json"
        if not secrets_path.exists():
            return ""
        try:
            data = json.loads(secrets_path.read_text())
            return data.get("providers", {}).get("transcriptapi", {}).get("apiKey", "")
        except Exception:
            return ""

    async def _fetch_transcript_api(
        self, video_id: str, api_key: str, fmt: str,
    ) -> str | None:
        """Fetch transcript from TranscriptAPI."""
        import httpx

        url = "https://transcriptapi.com/api/v2/youtube/transcript"
        params = {"video_id": video_id, "text": "true" if fmt == "text" else "false"}
        headers = {"x-api-key": api_key}

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"TranscriptAPI returned {resp.status_code}: {resp.text[:200]}")
                return None

            data = resp.json()
            if fmt == "text":
                # API returns {"transcript": "full text..."} in text mode
                text = data.get("transcript", "")
                if text:
                    return text
                # Fallback: join segments
                segments = data.get("segments", data.get("captions", []))
                return " ".join(s.get("text", "") for s in segments).strip() or None
            else:
                return json.dumps(data, indent=2)

    async def _fetch_ytdlp(self, video_id: str, fmt: str) -> str:
        """Fetch transcript via yt-dlp subtitle extraction."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            yt_url = f"https://www.youtube.com/watch?v={video_id}"
            cmd = [
                "yt-dlp",
                "--skip-download",
                "--write-auto-sub",
                "--sub-lang", "en",
                "--sub-format", "vtt",
                "--output", f"{tmpdir}/%(id)s.%(ext)s",
                yt_url,
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=60,
            )

            if proc.returncode != 0:
                err = stderr.decode(errors="replace").strip()
                raise RuntimeError(f"yt-dlp exit {proc.returncode}: {err[:300]}")

            # Find the subtitle file
            vtt_files = list(Path(tmpdir).glob("*.vtt"))
            if not vtt_files:
                raise RuntimeError("yt-dlp produced no subtitle file")

            vtt_content = vtt_files[0].read_text(encoding="utf-8", errors="replace")
            transcript = self._parse_vtt(vtt_content)

            if fmt == "json":
                return json.dumps({"video_id": video_id, "source": "yt-dlp", "text": transcript})
            return transcript

    async def _fetch_audio_transcription(self, video_id: str) -> str:
        """Download audio via yt-dlp, transcribe via Groq (primary) or OpenAI."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = Path(tmpdir) / f"{video_id}.m4a"
            yt_url = f"https://www.youtube.com/watch?v={video_id}"
            cmd = [
                "yt-dlp",
                "-x", "--audio-format", "m4a",
                "--audio-quality", "5",  # lower quality = smaller file
                "-o", str(audio_path),
                "--max-filesize", "25m",
                yt_url,
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=120,
            )
            if proc.returncode != 0:
                err = stderr.decode(errors="replace").strip()
                raise RuntimeError(f"yt-dlp audio download failed: {err[:500]}")

            # Find the audio file (yt-dlp may add codec suffix)
            audio_files = list(Path(tmpdir).glob(f"{video_id}.*"))
            if not audio_files:
                raise RuntimeError("yt-dlp produced no audio file")
            audio_file = audio_files[0]

            # Try Groq first (cheapest), then OpenAI
            transcript = await self._transcribe_groq(audio_file)
            if transcript:
                return f"[Audio transcription via Groq]\n\n{transcript}"

            transcript = await self._transcribe_openai(audio_file)
            if transcript:
                return f"[Audio transcription via OpenAI]\n\n{transcript}"

            raise RuntimeError("Both Groq and OpenAI transcription returned empty")

    async def _transcribe_groq(self, audio_path: Path) -> str | None:
        """Transcribe via Groq Whisper API."""
        secrets_path = Path.home() / ".nanobot" / "secrets.json"
        try:
            data = json.loads(secrets_path.read_text())
            api_key = data.get("providers", {}).get("groq", {}).get("apiKey", "")
        except Exception:
            return None
        if not api_key:
            return None

        try:
            import httpx
            async with httpx.AsyncClient(timeout=120) as client:
                with open(audio_path, "rb") as f:
                    resp = await client.post(
                        "https://api.groq.com/openai/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        files={"file": (audio_path.name, f, "audio/m4a")},
                        data={"model": "whisper-large-v3", "language": "en"},
                    )
                if resp.status_code == 200:
                    return resp.json().get("text", "")
                logger.warning(f"Groq transcription HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"Groq transcription failed: {e}")
        return None

    async def _transcribe_openai(self, audio_path: Path) -> str | None:
        """Transcribe via OpenAI Whisper API."""
        secrets_path = Path.home() / ".nanobot" / "secrets.json"
        try:
            data = json.loads(secrets_path.read_text())
            api_key = data.get("providers", {}).get("openai", {}).get("apiKey", "")
        except Exception:
            return None
        if not api_key:
            return None

        try:
            import httpx
            async with httpx.AsyncClient(timeout=120) as client:
                with open(audio_path, "rb") as f:
                    resp = await client.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        files={"file": (audio_path.name, f, "audio/m4a")},
                        data={"model": "whisper-1", "language": "en"},
                    )
                if resp.status_code == 200:
                    return resp.json().get("text", "")
                logger.warning(f"OpenAI transcription HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"OpenAI transcription failed: {e}")
        return None

    @staticmethod
    def _parse_vtt(vtt: str) -> str:
        """Strip VTT formatting, deduplicate lines, return clean text."""
        lines = []
        seen = set()
        for line in vtt.splitlines():
            # Skip headers, timestamps, and blank lines
            if not line.strip() or line.startswith("WEBVTT") or "-->" in line:
                continue
            # Strip VTT tags like <c>, </c>, <00:00:01.234>
            clean = re.sub(r"<[^>]+>", "", line).strip()
            if clean and clean not in seen:
                seen.add(clean)
                lines.append(clean)
        return " ".join(lines)
