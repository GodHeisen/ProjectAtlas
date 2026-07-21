"""Ollama local LLM service wrapper.

Talks to a locally running Ollama server exclusively through its HTTP API
(``http://localhost:11434`` by default). This never shells out to the
``ollama`` CLI, so it behaves identically whether Ollama is running as a
background service, a desktop app, or in a container reachable over the
network.
"""

import json
import time

import requests

from app.core.config import Settings
from app.core.exceptions import ConfigurationError, LLMError
from app.core.logger import get_logger
from app.services.llm_service import LLMHealthCheck, LLMServiceInterface

logger = get_logger(__name__)

_CHAT_ENDPOINT = "/api/chat"
_TAGS_ENDPOINT = "/api/tags"

# Rough heuristic (English prose/JSON averages ~4 characters per token). Only
# used for logging visibility into prompt size, not for exact accounting.
_CHARS_PER_TOKEN_ESTIMATE = 4

# Per-message character budget before Atlas truncates a prompt. CPU-only
# inference of a small local model (e.g. qwen2.5:3b on a laptop CPU) slows
# down substantially as context length grows, which is what was causing
# requests to exceed OLLAMA_TIMEOUT even though Ollama itself was healthy.
# 6000 chars is roughly 1500 tokens per message (~3000 tokens total across
# system + user), which keeps prefill time reasonable on modest hardware.
_DEFAULT_MAX_MESSAGE_CHARS = 6000

# Separate, short connect timeout: if Ollama isn't running at all, TCP
# connect fails almost instantly, so there's no reason to wait long for it.
# The (much longer) read timeout is OLLAMA_TIMEOUT, since a local CPU model
# genuinely needs tens of seconds to minutes to generate a response —
# especially on a cold start, when Ollama has to load model weights into RAM
# before it can even begin inference.
_CONNECT_TIMEOUT_SECONDS = 10.0

# How long Ollama should keep the model loaded in RAM after a request. Atlas
# makes several LLM calls per pipeline run (research, fact-check, one call per
# script section); keeping the model warm between them avoids repeatedly
# paying the (often 60s+) cold-load cost that caused first-attempt timeouts.
_KEEP_ALIVE = "30m"

# Upper bound on generated tokens per call. Small local models can
# occasionally rathole/loop instead of stopping, which silently turns a
# ~30s generation into a multi-minute one. 2048 tokens comfortably covers
# every Atlas call today (script sections top out around 220 words/~300
# tokens; research/fact-check JSON extraction is normally well under this),
# while still capping worst-case runaway generation time.
_DEFAULT_NUM_PREDICT = 2048


class OllamaLLMService(LLMServiceInterface):
    """LLM service backed by a local Ollama server's HTTP API.

    Implements the same ``LLMServiceInterface`` as the OpenAI-backed
    ``LLMService``, so it is a drop-in replacement wherever an
    ``LLMServiceInterface`` is expected.
    """

    def __init__(
        self,
        settings: Settings,
        max_retries: int = 2,
        retry_backoff_seconds: float = 1.0,
        max_message_chars: int = _DEFAULT_MAX_MESSAGE_CHARS,
    ) -> None:
        self._settings = settings
        self._max_retries = max(0, max_retries)
        self._retry_backoff_seconds = retry_backoff_seconds
        self._max_message_chars = max_message_chars

    # ---- configuration -----------------------------------------------

    @property
    def _host(self) -> str:
        return (self._settings.ollama_host or "http://localhost:11434").rstrip("/")

    @property
    def _model(self) -> str:
        return self._settings.ollama_model

    @property
    def _temperature(self) -> float:
        return self._settings.ollama_temperature

    @property
    def _timeout(self) -> float:
        return self._settings.ollama_timeout

    def is_configured(self) -> bool:
        """Ollama needs no API key; it's configured once a model name is set."""
        return bool(self._model)

    # ---- public API -----------------------------------------------------

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Send a chat completion request to Ollama, retrying transient failures."""
        payload = self._build_payload(system_prompt, user_prompt, json_mode=False)
        data = self._request_with_retries(payload)
        content = (data.get("message") or {}).get("content", "")
        if not content or not content.strip():
            raise LLMError("Ollama returned an empty response.")
        return content.strip()

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        """Send a chat completion request asking Ollama for structured JSON output.

        Uses Ollama's ``format: "json"`` mode so the server constrains
        generation to valid JSON, then parses and returns it as a dict.
        Raises ``LLMError`` if the response is not valid JSON.
        """
        payload = self._build_payload(system_prompt, user_prompt, json_mode=True)
        data = self._request_with_retries(payload)
        content = (data.get("message") or {}).get("content", "")
        if not content or not content.strip():
            raise LLMError("Ollama returned an empty response.")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(
                f"Ollama's response was not valid JSON despite format='json': {exc}"
            ) from exc

    def health_check(self) -> LLMHealthCheck:
        """Check whether Ollama is reachable and the configured model is pulled."""
        if not self._model:
            return LLMHealthCheck(
                healthy=False,
                message="OLLAMA_MODEL is not configured.",
            )

        try:
            response = requests.get(
                f"{self._host}{_TAGS_ENDPOINT}",
                timeout=min(self._timeout, 5.0),
            )
        except requests.ConnectionError:
            return LLMHealthCheck(
                healthy=False,
                message=(
                    f"Ollama is not reachable at {self._host}. Is it installed and "
                    "running? Start it with `ollama serve` (or open the Ollama app), "
                    "then try again."
                ),
            )
        except requests.Timeout:
            return LLMHealthCheck(
                healthy=False,
                message=f"Ollama at {self._host} did not respond within 5s.",
            )
        except requests.RequestException as exc:
            return LLMHealthCheck(healthy=False, message=f"Ollama health check failed: {exc}")

        if response.status_code != 200:
            return LLMHealthCheck(
                healthy=False,
                message=f"Ollama health check returned HTTP {response.status_code}.",
            )

        try:
            models = [m.get("name", "") for m in response.json().get("models", [])]
        except ValueError:
            return LLMHealthCheck(
                healthy=False,
                message="Ollama responded, but /api/tags was not valid JSON.",
            )

        if self._model not in models and f"{self._model}:latest" not in models:
            return LLMHealthCheck(
                healthy=False,
                message=(
                    f"Ollama is running, but model '{self._model}' is not pulled. "
                    f"Run `ollama pull {self._model}`. Installed models: "
                    f"{', '.join(models) or 'none'}."
                ),
            )

        return LLMHealthCheck(
            healthy=True,
            message=f"Ollama is running at {self._host} with model '{self._model}' available.",
        )

    # ---- internals --------------------------------------------------------

    def _build_payload(self, system_prompt: str, user_prompt: str, json_mode: bool) -> dict:
        system_prompt, system_truncated = self._truncate_to_budget(system_prompt, "system")
        user_prompt, user_truncated = self._truncate_to_budget(user_prompt, "user")
        self._log_prompt_size(system_prompt, user_prompt, system_truncated, user_truncated)

        payload: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": self._temperature,
                "num_predict": _DEFAULT_NUM_PREDICT,
            },
            "keep_alive": _KEEP_ALIVE,
        }
        if json_mode:
            payload["format"] = "json"
        return payload

    def _truncate_to_budget(self, text: str, label: str) -> tuple[str, bool]:
        """Truncate an oversized prompt section to keep local CPU inference fast.

        Keeps the head (topic/instructions, usually front-loaded) and tail
        (often the most recently added content) of the text, dropping the
        middle — typically where bulk source/claim material accumulates —
        rather than sending the entire prompt and risking a read timeout.
        """
        max_chars = self._max_message_chars
        if len(text) <= max_chars:
            return text, False

        # Reserve a slice of the budget for the marker itself, scaling with
        # max_chars so small budgets (e.g. in tests) don't get swamped by a
        # fixed-size marker, while staying capped for normal-sized budgets.
        marker_budget = min(120, max(max_chars // 4, 40))
        content_budget = max(max_chars - marker_budget, 20)
        keep_head = int(content_budget * 0.7)
        keep_tail = content_budget - keep_head
        removed = len(text) - keep_head - keep_tail
        marker = f"\n\n[... truncated {removed} characters to fit the local model's context budget ...]\n\n"
        truncated = text[:keep_head] + marker + text[-keep_tail:]

        logger.warning(
            "Ollama %s prompt was %d chars, exceeding the %d-char budget; truncated to "
            "%d chars (dropped %d chars from the middle) to keep local CPU inference fast. "
            "If this loses important content, raise OllamaLLMService's max_message_chars "
            "or reduce the volume of research passed into the prompt.",
            label,
            len(text),
            max_chars,
            len(truncated),
            removed,
        )
        return truncated, True

    def _log_prompt_size(
        self,
        system_prompt: str,
        user_prompt: str,
        system_truncated: bool,
        user_truncated: bool,
    ) -> None:
        """Log prompt size (chars + estimated tokens) without logging prompt content."""
        system_chars = len(system_prompt)
        user_chars = len(user_prompt)
        total_chars = system_chars + user_chars
        estimated_tokens = total_chars // _CHARS_PER_TOKEN_ESTIMATE
        logger.info(
            "Ollama prompt size: system=%d chars, user=%d chars, total=%d chars "
            "(~%d tokens estimated, %d chars/token heuristic). system_truncated=%s "
            "user_truncated=%s",
            system_chars,
            user_chars,
            total_chars,
            estimated_tokens,
            _CHARS_PER_TOKEN_ESTIMATE,
            system_truncated,
            user_truncated,
        )

    def _request_with_retries(self, payload: dict) -> dict:
        """POST to Ollama's /api/chat, retrying transient network failures.

        Non-transient failures (missing model, bad request) fail fast with a
        clear error rather than being retried.
        """
        if not self.is_configured():
            raise ConfigurationError(
                "OLLAMA_MODEL is not set. Configure OLLAMA_MODEL in .env, e.g. "
                "'qwen2.5:3b' or 'llama3.2:3b'."
            )

        url = f"{self._host}{_CHAT_ENDPOINT}"
        last_exc: Exception | None = None
        attempts = self._max_retries + 1

        message_lengths = [
            {"role": m["role"], "chars": len(m["content"])} for m in payload.get("messages", [])
        ]
        logger.info(
            "Ollama request payload: model=%s stream=%s format=%s temperature=%s "
            "messages=%s",
            payload.get("model"),
            payload.get("stream"),
            payload.get("format", "text"),
            payload.get("options", {}).get("temperature"),
            message_lengths,
        )

        for attempt in range(1, attempts + 1):
            logger.info(
                "Ollama request attempt %d/%d: POST %s model=%s",
                attempt,
                attempts,
                url,
                payload.get("model"),
            )
            try:
                response = requests.post(
                    url,
                    json=payload,
                    timeout=(_CONNECT_TIMEOUT_SECONDS, self._timeout),
                )
            except requests.ConnectionError as exc:
                last_exc = exc
                logger.warning(
                    "Ollama connection attempt %d/%d failed: could not reach %s (%s)",
                    attempt,
                    attempts,
                    self._host,
                    exc,
                )
            except requests.Timeout as exc:
                last_exc = exc
                logger.warning(
                    "Ollama request attempt %d/%d timed out after %.1fs (read timeout). "
                    "This usually means generation is still running on a slow CPU — often "
                    "a one-time cold start while Ollama loads the model into RAM. If this "
                    "happens consistently, raise OLLAMA_TIMEOUT further.",
                    attempt,
                    attempts,
                    self._timeout,
                )
            else:
                if response.status_code == 200:
                    logger.info(
                        "Ollama response: status=200 size=%d bytes",
                        len(response.content),
                    )
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise LLMError(
                            f"Ollama returned an unparseable response: {exc}"
                        ) from exc

                if response.status_code == 404:
                    # Model not found is not transient — fail immediately with
                    # a clear, actionable message instead of retrying.
                    raise LLMError(
                        f"Ollama model '{self._model}' was not found on {self._host}. "
                        f"Pull it first with: ollama pull {self._model}"
                    )

                last_exc = LLMError(
                    f"Ollama returned HTTP {response.status_code}: {response.text[:300]}"
                )
                logger.warning(
                    "Ollama attempt %d/%d returned HTTP %d",
                    attempt,
                    attempts,
                    response.status_code,
                )

            if attempt < attempts:
                backoff = self._retry_backoff_seconds * attempt
                logger.info("Retrying Ollama request in %.1fs...", backoff)
                time.sleep(backoff)

        raise self._unavailable_error(last_exc)

    def _unavailable_error(self, exc: Exception | None) -> LLMError:
        detail = f" Last error: {exc}" if exc else ""
        return LLMError(
            f"Could not reach Ollama at {self._host} after {self._max_retries + 1} "
            "attempt(s). Make sure Ollama is installed and running (`ollama serve`), "
            f"and that the model has been pulled (`ollama pull {self._model}`)."
            f"{detail}"
        )
