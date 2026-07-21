"""Tests for OllamaLLMService: HTTP behavior, retries, health checks, JSON mode."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from app.core.config import Settings
from app.core.exceptions import ConfigurationError, LLMError
from app.services.ollama_llm_service import OllamaLLMService


def build_settings(**overrides) -> Settings:
    return Settings(
        OPENAI_API_KEY="",
        LLM_PROVIDER="ollama",
        OLLAMA_HOST=overrides.get("ollama_host", "http://localhost:11434"),
        OLLAMA_MODEL=overrides.get("ollama_model", "qwen2.5:3b"),
        OLLAMA_TEMPERATURE=overrides.get("ollama_temperature", 0.2),
        OLLAMA_TIMEOUT=overrides.get("ollama_timeout", 30.0),
    )


def make_service(**overrides) -> OllamaLLMService:
    settings = build_settings(**overrides)
    return OllamaLLMService(
        settings,
        max_retries=overrides.get("max_retries", 2),
        retry_backoff_seconds=overrides.get("retry_backoff_seconds", 0.0),
    )


def fake_chat_response(content: str, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.content = content.encode("utf-8")
    response.text = content
    response.json.return_value = {"message": {"role": "assistant", "content": content}}
    return response


# ---- configuration ------------------------------------------------------


def test_is_configured_true_when_model_set() -> None:
    service = make_service(ollama_model="qwen2.5:3b")
    assert service.is_configured() is True


def test_is_configured_false_when_model_empty() -> None:
    service = make_service(ollama_model="")
    assert service.is_configured() is False


def test_complete_raises_configuration_error_when_model_not_set() -> None:
    service = make_service(ollama_model="")
    with pytest.raises(ConfigurationError):
        service.complete("system", "user")


# ---- complete() -----------------------------------------------------------


def test_complete_success_returns_content() -> None:
    service = make_service()
    response = fake_chat_response("Generated narration text.")

    with patch(
        "app.services.ollama_llm_service.requests.post", return_value=response
    ) as post:
        result = service.complete("system prompt", "user prompt")

    assert result == "Generated narration text."
    assert post.call_count == 1
    called_url = post.call_args.args[0]
    assert called_url == "http://localhost:11434/api/chat"
    payload = post.call_args.kwargs["json"]
    assert payload["model"] == "qwen2.5:3b"
    assert payload["options"]["temperature"] == 0.2
    assert payload["messages"][0] == {"role": "system", "content": "system prompt"}
    assert payload["messages"][1] == {"role": "user", "content": "user prompt"}


def test_complete_raises_llm_error_on_empty_content() -> None:
    service = make_service()
    response = fake_chat_response("   ")

    with patch("app.services.ollama_llm_service.requests.post", return_value=response):
        with pytest.raises(LLMError):
            service.complete("system", "user")


def test_complete_uses_separate_connect_and_read_timeout() -> None:
    service = make_service(ollama_timeout=45.0)
    response = fake_chat_response("OK.")

    with patch(
        "app.services.ollama_llm_service.requests.post", return_value=response
    ) as post:
        service.complete("system", "user")

    assert post.call_args.kwargs["timeout"] == (10.0, 45.0)


def test_complete_sets_keep_alive_to_avoid_repeated_cold_starts() -> None:
    service = make_service()
    response = fake_chat_response("OK.")

    with patch(
        "app.services.ollama_llm_service.requests.post", return_value=response
    ) as post:
        service.complete("system", "user")

    payload = post.call_args.kwargs["json"]
    assert payload["keep_alive"] == "30m"


# ---- retries ---------------------------------------------------------------


def test_complete_retries_connection_error_then_succeeds() -> None:
    service = make_service(max_retries=2)
    success_response = fake_chat_response("Recovered after retry.")

    with patch(
        "app.services.ollama_llm_service.requests.post",
        side_effect=[
            requests.ConnectionError("refused"),
            success_response,
        ],
    ) as post:
        result = service.complete("system", "user")

    assert result == "Recovered after retry."
    assert post.call_count == 2


def test_complete_retries_timeout_then_succeeds() -> None:
    service = make_service(max_retries=2)
    success_response = fake_chat_response("Recovered after timeout retry.")

    with patch(
        "app.services.ollama_llm_service.requests.post",
        side_effect=[requests.Timeout("slow"), success_response],
    ) as post:
        result = service.complete("system", "user")

    assert result == "Recovered after timeout retry."
    assert post.call_count == 2


def test_complete_raises_after_exhausting_retries() -> None:
    service = make_service(max_retries=2)

    with patch(
        "app.services.ollama_llm_service.requests.post",
        side_effect=requests.ConnectionError("refused"),
    ) as post:
        with pytest.raises(LLMError) as exc_info:
            service.complete("system", "user")

    # 1 initial attempt + 2 retries = 3 total calls
    assert post.call_count == 3
    message = str(exc_info.value).lower()
    assert "ollama" in message
    assert "running" in message or "install" in message


def test_complete_does_not_retry_on_model_not_found() -> None:
    service = make_service(max_retries=2)
    not_found_response = fake_chat_response("model not found", status_code=404)

    with patch(
        "app.services.ollama_llm_service.requests.post",
        return_value=not_found_response,
    ) as post:
        with pytest.raises(LLMError) as exc_info:
            service.complete("system", "user")

    assert post.call_count == 1
    assert "pull" in str(exc_info.value).lower()


def test_complete_retries_on_server_error_status() -> None:
    service = make_service(max_retries=1)
    error_response = fake_chat_response("internal error", status_code=500)
    success_response = fake_chat_response("Recovered after 500.")

    with patch(
        "app.services.ollama_llm_service.requests.post",
        side_effect=[error_response, success_response],
    ) as post:
        result = service.complete("system", "user")

    assert result == "Recovered after 500."
    assert post.call_count == 2


# ---- structured JSON output -------------------------------------------------


def test_complete_json_parses_valid_json() -> None:
    service = make_service()
    response = fake_chat_response('{"claim": "Example claim", "confidence": 0.8}')

    with patch(
        "app.services.ollama_llm_service.requests.post", return_value=response
    ) as post:
        result = service.complete_json("system", "user")

    assert result == {"claim": "Example claim", "confidence": 0.8}
    payload = post.call_args.kwargs["json"]
    assert payload["format"] == "json"


def test_complete_json_raises_on_invalid_json() -> None:
    service = make_service()
    response = fake_chat_response("not valid json {")

    with patch("app.services.ollama_llm_service.requests.post", return_value=response):
        with pytest.raises(LLMError):
            service.complete_json("system", "user")


# ---- health checks ----------------------------------------------------------


def test_health_check_healthy_when_model_available() -> None:
    service = make_service(ollama_model="qwen2.5:3b")
    tags_response = MagicMock()
    tags_response.status_code = 200
    tags_response.json.return_value = {"models": [{"name": "qwen2.5:3b"}]}

    with patch(
        "app.services.ollama_llm_service.requests.get", return_value=tags_response
    ):
        result = service.health_check()

    assert result.healthy is True
    assert "qwen2.5:3b" in result.message


def test_health_check_unreachable_server() -> None:
    service = make_service()

    with patch(
        "app.services.ollama_llm_service.requests.get",
        side_effect=requests.ConnectionError("refused"),
    ):
        result = service.health_check()

    assert result.healthy is False
    assert "not reachable" in result.message.lower()


def test_health_check_model_not_pulled() -> None:
    service = make_service(ollama_model="qwen2.5:3b")
    tags_response = MagicMock()
    tags_response.status_code = 200
    tags_response.json.return_value = {"models": [{"name": "llama3.2:3b"}]}

    with patch(
        "app.services.ollama_llm_service.requests.get", return_value=tags_response
    ):
        result = service.health_check()

    assert result.healthy is False
    assert "not pulled" in result.message.lower()
    assert "ollama pull qwen2.5:3b" in result.message


def test_health_check_no_model_configured() -> None:
    service = make_service(ollama_model="")
    result = service.health_check()
    assert result.healthy is False
    assert "not configured" in result.message.lower()


# ---- oversized prompt truncation (fixes the 120s ReadTimeout on large research contexts) --


def test_short_prompts_are_not_truncated() -> None:
    service = make_service()
    response = fake_chat_response("OK.")

    with patch(
        "app.services.ollama_llm_service.requests.post", return_value=response
    ) as post:
        service.complete("short system", "short user")

    payload = post.call_args.kwargs["json"]
    assert payload["messages"][0]["content"] == "short system"
    assert payload["messages"][1]["content"] == "short user"


def test_oversized_user_prompt_is_truncated_before_sending() -> None:
    settings = build_settings()
    service = OllamaLLMService(
        settings, max_retries=0, retry_backoff_seconds=0.0, max_message_chars=200
    )
    huge_user_prompt = "HEAD" + ("x" * 5000) + "TAIL"
    response = fake_chat_response("Handled a huge prompt.")

    with patch(
        "app.services.ollama_llm_service.requests.post", return_value=response
    ) as post:
        result = service.complete("system", huge_user_prompt)

    assert result == "Handled a huge prompt."
    sent_user_content = post.call_args.kwargs["json"]["messages"][1]["content"]
    assert len(sent_user_content) <= 200 + 100  # truncation marker adds some overhead
    assert sent_user_content.startswith("HEAD")
    assert sent_user_content.endswith("TAIL")
    assert "truncated" in sent_user_content


def test_oversized_system_prompt_is_truncated_before_sending() -> None:
    settings = build_settings()
    service = OllamaLLMService(
        settings, max_retries=0, retry_backoff_seconds=0.0, max_message_chars=200
    )
    huge_system_prompt = "RULES-START" + ("y" * 5000) + "RULES-END"
    response = fake_chat_response("Handled a huge system prompt.")

    with patch(
        "app.services.ollama_llm_service.requests.post", return_value=response
    ) as post:
        service.complete(huge_system_prompt, "user")

    sent_system_content = post.call_args.kwargs["json"]["messages"][0]["content"]
    assert len(sent_system_content) <= 200 + 100
    assert sent_system_content.startswith("RULES-START")
    assert sent_system_content.endswith("RULES-END")


def test_truncation_does_not_trigger_below_budget() -> None:
    settings = build_settings()
    service = OllamaLLMService(settings, max_message_chars=200)
    text_at_budget = "a" * 200
    truncated, was_truncated = service._truncate_to_budget(text_at_budget, "user")
    assert was_truncated is False
    assert truncated == text_at_budget


def test_health_check_handles_timeout() -> None:
    service = make_service()

    with patch(
        "app.services.ollama_llm_service.requests.get",
        side_effect=requests.Timeout("slow"),
    ):
        result = service.health_check()

    assert result.healthy is False
    assert "did not respond" in result.message.lower()
