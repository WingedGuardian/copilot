"""Background SLM extraction — runs async after each exchange, never blocks."""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, TYPE_CHECKING

from loguru import logger

from nanobot.providers.base import LLMProvider
from nanobot.copilot.cost.logger import CostLogger
from nanobot.copilot.extraction.schemas import ExtractionResult

if TYPE_CHECKING:
    from nanobot.copilot.slm_queue.manager import SlmWorkQueue

_EXTRACTION_PROMPT = """\
Extract structured information from this user↔assistant exchange.
Return ONLY valid JSON matching this schema — no markdown, no explanation:

{
  "facts": ["specific factual statements"],
  "decisions": ["decisions made or agreed to"],
  "constraints": ["limitations, deadlines, requirements mentioned"],
  "entities": ["names, values, URLs, specific references"],
  "sentiment": "positive|negative|neutral|frustrated",
  "topic_shift": true or false,
  "suggested_topic": "new topic name if shifted, else null"
}

USER: {user_message}

ASSISTANT: {assistant_response}
"""


class BackgroundExtractor:
    """Extracts structured facts/decisions/constraints after each exchange.

    Uses a local SLM when available (free), cloud as fallback (~$0.001).
    If both fail, falls back to regex-based heuristic extraction.
    """

    def __init__(
        self,
        local_provider: LLMProvider | None = None,
        fallback_provider: LLMProvider | None = None,
        cost_logger: CostLogger | None = None,
        local_model: str = "llama-3.2-3b-instruct",
        fallback_model: str = "anthropic/claude-3-haiku-20240307",
    ):
        self._local = local_provider
        self._fallback = fallback_provider
        self._cost_logger = cost_logger
        self._local_model = local_model
        self._fallback_model = fallback_model
        self._current_task: asyncio.Task | None = None
        self._slm_queue: SlmWorkQueue | None = None
        self._last_source: str = "none"  # "local", "cloud", "heuristic", "none"

        # Callback set by the agent loop to persist results
        self.on_result: Any = None  # async def on_result(session_key, result)

    def schedule_extraction(
        self,
        user_message: str,
        assistant_response: str,
        session_key: str,
    ) -> asyncio.Task:
        """Fire-and-forget extraction. Cancels any in-flight extraction."""
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()

        self._current_task = asyncio.create_task(
            self._run(user_message, assistant_response, session_key)
        )
        return self._current_task

    async def _run(
        self,
        user_message: str,
        assistant_response: str,
        session_key: str,
    ) -> None:
        """Execute extraction and persist results."""
        try:
            conversation_ts = time.time()
            result = await self.extract(
                user_message, assistant_response,
                session_key=session_key, conversation_ts=conversation_ts,
            )
            if self.on_result:
                await self.on_result(session_key, result)
            logger.debug(
                f"Extraction done for {session_key}: "
                f"{len(result.facts)}F {len(result.decisions)}D "
                f"{len(result.entities)}E sentiment={result.sentiment}"
            )
        except asyncio.CancelledError:
            logger.debug(f"Extraction cancelled for {session_key}")
        except Exception as e:
            logger.warning(f"Extraction failed for {session_key}: {type(e).__name__}: {e}")

    async def extract(
        self,
        user_message: str,
        assistant_response: str,
        session_key: str = "",
        conversation_ts: float | None = None,
    ) -> ExtractionResult:
        """Extract structured information from an exchange.

        Tries local SLM → cloud fallback (Haiku) → queue for deferred → heuristic.
        """
        prompt = _EXTRACTION_PROMPT.format(
            user_message=user_message[:2000],
            assistant_response=assistant_response[:2000],
        )
        messages = [{"role": "user", "content": prompt}]

        # Try local SLM
        if self._local:
            try:
                response = await asyncio.wait_for(
                    self._local.chat(
                        messages=messages,
                        model=self._local_model,
                        max_tokens=512,
                        temperature=0.1,
                    ),
                    timeout=10.0,
                )
                result = self._parse_json(response.content)
                if result:
                    result.token_count_estimate = (
                        len(user_message) + len(assistant_response)
                    ) // 4
                    self._last_source = "local"
                    return result
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"Local extraction failed: {e}")

        # Cloud fallback (cheap model like Haiku — ~$0.001/call)
        if self._fallback:
            try:
                response = await asyncio.wait_for(
                    self._fallback.chat(
                        messages=messages,
                        model=self._fallback_model,
                        max_tokens=512,
                        temperature=0.1,
                    ),
                    timeout=15.0,
                )
                result = self._parse_json(response.content)
                if result:
                    result.token_count_estimate = (
                        len(user_message) + len(assistant_response)
                    ) // 4
                    # Log cost
                    if self._cost_logger:
                        tokens_in = response.usage.get("prompt_tokens", 0)
                        tokens_out = response.usage.get("completion_tokens", 0)
                        cost = self._cost_logger.calculate_cost(
                            self._fallback_model, tokens_in, tokens_out,
                        )
                        await self._cost_logger.log_call(
                            self._fallback_model, tokens_in, tokens_out, cost,
                        )
                    self._last_source = "cloud"
                    logger.debug(f"Cloud extraction succeeded for {session_key}")
                    return result
                else:
                    logger.debug(f"Cloud extraction returned unparseable JSON")
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"Cloud extraction failed: {e}")

        # Queue for deferred SLM processing when local comes back
        if self._slm_queue and session_key:
            try:
                await self._slm_queue.enqueue_extraction(
                    user_message, assistant_response,
                    session_key, conversation_ts,
                )
                logger.debug(f"Extraction queued for {session_key}")
            except Exception as qe:
                logger.debug(f"Queue enqueue failed: {qe}")

        # Heuristic fallback (immediate low-quality results)
        self._last_source = "heuristic"
        return self._heuristic_extract(user_message, assistant_response)

    async def extract_local_only(
        self,
        user_message: str,
        assistant_response: str,
    ) -> ExtractionResult:
        """Extract using local SLM only. Raises on failure (used by queue drainer)."""
        if not self._local:
            raise RuntimeError("No local provider configured")
        prompt = _EXTRACTION_PROMPT.format(
            user_message=user_message[:2000],
            assistant_response=assistant_response[:2000],
        )
        response = await asyncio.wait_for(
            self._local.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self._local_model,
                max_tokens=512,
                temperature=0.1,
            ),
            timeout=15.0,
        )
        result = self._parse_json(response.content)
        if not result:
            raise ValueError("Local SLM returned unparseable extraction")
        result.token_count_estimate = (
            len(user_message) + len(assistant_response)
        ) // 4
        return result

    @staticmethod
    def _parse_json(text: str | None) -> ExtractionResult | None:
        """Try to parse extraction JSON from LLM output."""
        if not text:
            return None
        # Strip markdown code fences if present
        text = re.sub(r"^```(?:json)?\s*", "", text.strip())
        text = re.sub(r"\s*```$", "", text.strip())
        try:
            data = json.loads(text)
            return ExtractionResult(**data)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

    @staticmethod
    def _heuristic_extract(
        user_message: str, assistant_response: str
    ) -> ExtractionResult:
        """Regex-based extraction when all LLMs fail."""
        facts = []
        entities = []

        # First sentence of user message as a fact
        first_sentence = user_message.split(".")[0].strip()
        if first_sentence and len(first_sentence) > 10:
            facts.append(first_sentence)

        # Extract things that look like names, URLs, emails, numbers
        for pattern, label in [
            (r"https?://\S+", "url"),
            (r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)+\b", "name"),
            (r"\b\d{4}[-/]\d{2}[-/]\d{2}\b", "date"),
            (r"\$[\d,]+(?:\.\d{2})?", "money"),
        ]:
            for match in re.findall(pattern, user_message + " " + assistant_response):
                entities.append(match)

        return ExtractionResult(
            facts=facts[:3],
            entities=entities[:5],
            token_count_estimate=(len(user_message) + len(assistant_response)) // 4,
        )
